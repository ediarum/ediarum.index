<template>
  <DataListView
    :create-label="`New ${currentLabel.toLowerCase()}`"
    :error="error"
    :headers="headers"
    :items="entries"
    :items-per-page="itemsPerPage"
    :loading="loading"
    :page="page"
    :server-items-length="total"
    :sort-by="tableSort"
    :title="title"
    @create="openCreate"
    @row-click="openView"
    @update:options="onOptions"
  >
    <template #toolbar-extension>
      <v-tabs v-model="currentType" show-arrows>
        <v-tab v-for="t in entryTypes" :key="t.name" :value="t.name">{{ t.label }}</v-tab>
      </v-tabs>
    </template>

    <template
      v-for="f in dataColumns"
      :key="f.name"
      #[`item.data.${f.name}`]="{ item }"
    >
      <span class="cell-clamp" :title="formatFieldValue(item.data[f.name])">
        {{ formatFieldValue(item.data[f.name], '; ') }}
      </span>
    </template>

    <template #[`item.actions`]="{ item }">
      <v-btn icon="mdi-pencil" size="small" variant="text" @click.stop="openEdit(item)" />

      <v-btn
        color="error"
        icon="mdi-delete"
        size="small"
        variant="text"
        @click.stop="askDelete(item)"
      />
    </template>
  </DataListView>

  <EntryView
    v-model="viewOpen"
    can-edit
    :entry="viewing"
    :project-label="projectLabel(project)"
    :registers-from-xml="currentProject?.registers_from_xml === true"
    @edit="editFromView"
  />

  <EntryDialog
    v-model="dialog"
    :assigns-ids="currentProject?.assigns_ids === true"
    :entry="editing"
    :entry-type="currentType"
    :project="project"
    :registers-from-xml="currentProject?.registers_from_xml === true"
    :saving="saving"
    :submit-error="submitError"
    @submit="onSubmit"
  />

  <ConfirmDialog
    v-model="confirm"
    :loading="deleting"
    :message="`${toDelete?.label ?? ''} will be permanently removed.`"
    title="Delete entry?"
    @confirm="confirmDelete"
  />
</template>

<script lang="ts" setup>
import type { Entry, EntryCreate, FieldSchema } from '@/api/entry'
import type { SortItem, TableOptions } from '@/lib/table'
import { computed, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { getSchema } from '@/api/entry'
import { apiError } from '@/api/error'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import DataListView from '@/components/common/DataListView.vue'
import EntryDialog from '@/components/EntryDialog.vue'
import EntryView from '@/components/EntryView.vue'
import { useEntries } from '@/composables/useEntries'
import { useEntryTypes } from '@/composables/useEntryTypes'
import { useProjects } from '@/composables/useProjects'
import { useAppContext } from '@/context'
import { formatFieldValue } from '@/lib/format'

// every entry belongs to a project: this view is always one project's
// (/:project); the platform checked the caller may use it, the backend too
const props = defineProps<{ project: string }>()

const route = useRoute()
const router = useRouter()
const { http, search } = useAppContext()
// the project's entry types (its tabs)
const { entryTypes } = useEntryTypes(() => props.project)

// the project's human label, for the title
const { label: projectLabel, find: findProject, load: loadProjects } = useProjects()
// how the project is maintained: the notice on XML-led registers, who assigns
// a new entry's Project ID
const currentProject = computed(() => findProject(props.project))

// which entry type is shown; mirrored in the URL as ?type=
const currentType = ref(typeof route.query.type === 'string' ? route.query.type : 'person')
watch(currentType, (t) => {
  if (route.query.type !== t) router.replace({ query: { ...route.query, type: t } })
})
// a type the project doesn't use (?type=glossary on avhr, a project switch):
// fall back to its first one
watch(entryTypes, (types) => {
  const first = types[0]
  if (first && !types.some((t) => t.name === currentType.value)) currentType.value = first.name
})

const currentLabel = computed(
  () => entryTypes.value.find((t) => t.name === currentType.value)?.label ?? currentType.value,
)
const title = computed(() => `${currentLabel.value} – ${projectLabel(props.project)}`)

// the mount's search state (the input lives in the toolbar, App.vue)
const { term: searchTerm, field: searchField, fields: searchFields } = search

const {
  entries,
  total,
  loading,
  error,
  load,
  create,
  update,
  remove,
  page,
  itemsPerPage,
  sortBy,
  descending,
} = useEntries(
  () => props.project,
  () => currentType.value,
  () => searchTerm.value,
  () => searchField.value,
)

// free-text date fields the backend can still sort, via the derived
// birth_sort / death_sort keys (?sort_by=birth_date / death_date)
const SORTABLE_DATE_COLUMNS = new Set(['birth_date', 'death_date'])

// The date columns render from a `data.<x>` key path (like the other JSON-bag
// columns) but the backend sort key is the bare `<x>` (see _ENTRY_SORT_COLS),
// so translate at the table boundary.
function toSortKey(columnKey: string) {
  return columnKey.startsWith('data.') ? columnKey.slice(5) : columnKey
}
function toColumnKey(sortKey: string) {
  return SORTABLE_DATE_COLUMNS.has(sortKey) ? `data.${sortKey}` : sortKey
}

// server-side paging + sort (default: by the generated label)
const tableSort = computed<SortItem[]>(() => [
  { key: toColumnKey(sortBy.value), order: descending.value ? 'desc' : 'asc' },
])
function onOptions(o: TableOptions) {
  page.value = Math.max(1, o.page)
  itemsPerPage.value = o.itemsPerPage > 0 ? o.itemsPerPage : 25 // guard "All" (-1)
  // DataListView sets must-sort, so o.sortBy is never []; the `?? 'label'`
  // is only a defensive default, not the everyday path
  sortBy.value = toSortKey(o.sortBy[0]?.key ?? 'label')
  descending.value = o.sortBy[0]?.order === 'desc'
}

// table columns follow the field schema of the current (type, project)
const schema = ref<FieldSchema[]>([])
watch(
  [currentType, () => props.project],
  async () => {
    try {
      schema.value = await getSchema(http, props.project, currentType.value)
    } catch {
      schema.value = []
    }
    // offer Label + Project ID + every schema field as a search target
    searchFields.value = [
      { title: 'Label', value: 'label' },
      { title: 'Project ID', value: 'source_id' },
      ...schema.value.map((f) => ({ title: f.label, value: f.name })),
    ]
    // if the selected field no longer exists (type switch), fall back to Label
    if (!searchFields.value.some((o) => o.value === searchField.value)) {
      searchField.value = 'label'
    }
  },
  { immediate: true },
)

// verbose (multiline) free text is kept out of the table — it shows in the
// single-entry view. Repeatable fields (multilingual names, typed ids, …) DO
// show here, formatted compactly (formatFieldValue) and width-clamped (.cell-clamp).
const dataColumns = computed(() => schema.value.filter((f) => !f.multiline))

// fixed width so a long multilingual value can't make the table lurch between
// pages/rows — the full value is still available via the cell's title tooltip
const DATA_COLUMN_WIDTH = 200

const headers = computed(() => {
  const cols: Record<string, unknown>[] = [{ title: 'Label', key: 'label' }]
  for (const f of dataColumns.value) {
    // JSON-bag column; only the date fields are sortable (server-side, by the
    // derived birth_sort / death_sort keys)
    cols.push({
      title: f.label,
      key: `data.${f.name}`,
      sortable: SORTABLE_DATE_COLUMNS.has(f.name),
      width: DATA_COLUMN_WIDTH,
    })
  }
  cols.push({ title: 'Project ID', key: 'source_id' }, { title: '', key: 'actions', sortable: false, align: 'end' })
  return cols
})

const dialog = ref(false)
const editing = ref<Entry | null>(null)
const saving = ref(false)
const submitError = ref<string | null>(null)

// read-only single-entry modal; its Edit button hands over to the edit dialog
const viewOpen = ref(false)
const viewing = ref<Entry | null>(null)
// the edit was started from the view: go back to it when the dialog closes
// (saved or cancelled)
const returnToView = ref(false)
watch(dialog, (open) => {
  if (open || !returnToView.value) return
  returnToView.value = false
  viewOpen.value = true
})

function openView(item: Entry) {
  viewing.value = item
  viewOpen.value = true
}
function editFromView() {
  if (!viewing.value) return
  viewOpen.value = false
  openEdit(viewing.value)
  returnToView.value = true
}

function openCreate() {
  returnToView.value = false
  editing.value = null
  submitError.value = null
  dialog.value = true
}
function openEdit(item: Entry) {
  returnToView.value = false
  editing.value = item
  submitError.value = null
  dialog.value = true
}
async function onSubmit(payload: EntryCreate) {
  saving.value = true
  submitError.value = null
  try {
    const saved = await (editing.value ? update(editing.value.id, payload) : create(payload))
    if (returnToView.value) viewing.value = saved
    dialog.value = false
  } catch (error_) {
    submitError.value = apiError(error_)
  } finally {
    saving.value = false
  }
}

const confirm = ref(false)
const toDelete = ref<Entry | null>(null)
const deleting = ref(false)

function askDelete(item: Entry) {
  toDelete.value = item
  confirm.value = true
}
async function confirmDelete() {
  if (!toDelete.value) return
  deleting.value = true
  try {
    await remove(toDelete.value.id)
    confirm.value = false
  } finally {
    deleting.value = false
  }
}

onMounted(() => {
  load()
  loadProjects()
})
</script>

<style scoped>
/* caps a data-bag cell (multilingual names, repeatable ids, …) so one long
   value can't widen the whole column — hover shows the untruncated value */
.cell-clamp {
  display: inline-block;
  max-width: 200px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  vertical-align: middle;
}
</style>
