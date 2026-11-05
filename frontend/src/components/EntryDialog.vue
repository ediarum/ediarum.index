<!-- Schema-driven create / edit form for one entry. Fetches the field schema for
     the effective (entry_type, project), renders it with <SchemaField>, and emits
     a ready `EntryCreate` payload. The parent persists it and owns `v-model` /
     `saving` / `submitError`. -->
<template>
  <FormDialog
    ref="formDialog"
    v-model="model"
    :busy="loadingSchema"
    :error="schemaError ?? submitError"
    max-width="1100"
    :saving="saving"
    scrollable
    :title="entry ? 'Edit entry' : 'New entry'"
    @submit="onSubmit"
  >
    <!-- two columns: the form is used on desktop, and a single column made
         long schemas (schleiermacher, mega) a scroll marathon -->
    <XmlLedNotice v-if="registersFromXml" />

    <div class="entry-form-grid">
      <v-text-field
        v-model="labelModel"
        :hint="autoLabel !== null ? 'built from surname / forename' : undefined"
        label="Label"
        :persistent-hint="autoLabel !== null"
        :readonly="autoLabel !== null"
        :rules="[required]"
      />

      <SourceIdField
        :key="openings"
        v-model="draft.source_id"
        :assigns-ids="assignsIds"
        :creating="!entry"
        :original="entry?.source_id"
      />

      <v-divider class="full-row mb-3" />

      <!-- long text and repeatable rows (value + qualifier + buttons) need the
           full width -->
      <SchemaField
        v-for="f in schema"
        :key="f.name"
        v-model="draft.values[f.name]"
        :class="{ 'full-row': f.multiline || f.repeatable }"
        :field="f"
      />
    </div>
  </FormDialog>
</template>

<script lang="ts" setup>
import type { Entry, EntryCreate, EntryType, FieldSchema, QualifiedValue } from '@/api/entry'
import { computed, reactive, ref, watch } from 'vue'
import { getSchema } from '@/api/entry'
import FormDialog from '@/components/common/FormDialog.vue'
import SchemaField from '@/components/common/SchemaField.vue'
import SourceIdField from '@/components/SourceIdField.vue'
import XmlLedNotice from '@/components/XmlLedNotice.vue'
import { useHttp } from '@/context'
import { personLabel } from '@/lib/label'

const model = defineModel<boolean>({ default: false })
const props = defineProps<{
  entry?: Entry | null
  // used only when creating; when editing, the entry's own values win
  entryType?: string
  // the project of the view (an entry never changes project)
  project: string
  saving?: boolean
  submitError?: string | null
  // the backend gets a new entry's Project ID from ediarum.id (GET /projects)
  assignsIds?: boolean
  // the project's registers come from TEI files: edits here don't reach them
  registersFromXml?: boolean
}>()
const emit = defineEmits<{ submit: [payload: EntryCreate] }>()

const required = (v: unknown) => (v !== null && v !== undefined && v !== '') || 'Required'

const formDialog = ref<{ resetValidation: () => void } | null>(null)
const http = useHttp()

const effectiveType = computed(() => props.entry?.entry_type ?? props.entryType ?? 'person')

const schema = ref<FieldSchema[]>([])
const loadingSchema = ref(false)
const schemaError = ref<string | null>(null)

// SchemaField controls hold a string (text/number/date/select), a boolean
// (checkbox) or a QualifiedValue[] (repeatable); coerced back in onSubmit.
type DraftValue = string | boolean | null | QualifiedValue[]
interface Draft {
  label: string
  source_id: string
  values: Record<string, DraftValue>
}
const makeDraft = (): Draft => ({ label: '', source_id: '', values: {} })
const draft = reactive<Draft>(makeDraft())

// when the schema has name fields, the label is derived ("Surname, Forename")
// and the Label field is read-only; otherwise it is free text.
const hasNameFields = computed(() =>
  schema.value.some((f) => f.name === 'surname' || f.name === 'forename'),
)
// null → the Label field is free text; a string → it is derived and read-only.
// An empty derivation (no name values yet) stays null so an existing label is
// not blanked out.
const autoLabel = computed<string | null>(() =>
  hasNameFields.value
    ? personLabel(draft.values.surname, draft.values.forename) || null
    : null,
)
const labelModel = computed<string>({
  get: () => autoLabel.value ?? draft.label,
  set: (v) => {
    if (autoLabel.value === null) draft.label = v
  },
})

// (re)build `values` for the current schema, keeping anything already typed
function fillFromSchema() {
  const values: Record<string, DraftValue> = {}
  for (const f of schema.value) {
    const prev = draft.values[f.name]
    const raw = props.entry?.data?.[f.name]
    if (f.repeatable) {
      // clone each row (spread is enough — values are scalars); NOT structuredClone,
      // which throws DataCloneError on the reactive proxy that props.entry.data is
      values[f.name] = Array.isArray(prev)
        ? prev
        : Array.isArray(raw)
          ? raw.map((row) => ({ ...row }))
          : []
    } else if (f.type === 'checkbox') {
      values[f.name] = typeof prev === 'boolean' ? prev : raw === true
    } else {
      values[f.name] = typeof prev === 'string' && prev !== '' ? prev : raw == null ? '' : String(raw)
    }
  }
  draft.values = values
}

async function loadSchema() {
  loadingSchema.value = true
  schemaError.value = null
  try {
    schema.value = await getSchema(http, props.project, effectiveType.value)
  } catch {
    schema.value = []
    schemaError.value = 'Failed to load the form schema.'
  } finally {
    loadingSchema.value = false
  }
}

// full reset when the dialog opens; `openings` remounts the Project ID field
const openings = ref(0)
watch(model, async (open) => {
  if (!open) return
  openings.value++
  Object.assign(draft, makeDraft())
  draft.label = props.entry?.label ?? ''
  draft.source_id = props.entry?.source_id ?? ''
  formDialog.value?.resetValidation()
})

// (re)load the schema whenever the type changes while open
watch(
  [model, effectiveType, () => props.project],
  async ([open]) => {
    if (!open) return
    await loadSchema()
    fillFromSchema()
    formDialog.value?.resetValidation()
  },
  { immediate: true },
)

function onSubmit() {
  // keep any data keys the schema doesn't cover (e.g. provenance like `old_id`)
  const data: NonNullable<EntryCreate['data']> = { ...props.entry?.data }
  for (const f of schema.value) {
    const v = draft.values[f.name]
    if (f.repeatable) {
      const rows = (Array.isArray(v) ? v : [])
        .map((r) => ({ ...r, value: (r.value ?? '').trim() }))
        .filter((r) => r.value !== '')
      if (rows.length > 0) data[f.name] = rows
      else delete data[f.name]
      continue
    }
    if (f.type === 'checkbox') {
      if (v === true) data[f.name] = true
      else delete data[f.name]
      continue
    }
    const s = (typeof v === 'string' ? v : '').trim()
    if (s === '') delete data[f.name]
    else data[f.name] = f.type === 'number' ? Number(s) : s
  }
  emit('submit', {
    entry_type: effectiveType.value as EntryType,
    label: autoLabel.value ?? draft.label,
    source_id: draft.source_id || null,
    data,
  })
}
</script>

<style scoped>
.entry-form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  column-gap: 24px;
  align-items: start;
}
.full-row {
  grid-column: 1 / -1;
}
</style>
