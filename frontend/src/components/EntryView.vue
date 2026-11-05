<!-- Read-only single-entry view, opened as a modal from the list. Shows every
     field (the note included) in a readable label/value table; editing happens
     in <EntryDialog>, reached via the Edit button (`edit` event). Fetches its own
     schema from the entry's (type, project) so it works from any list. -->
<template>
  <v-dialog v-model="model" max-width="960" scrollable>
    <v-card v-if="entry">
      <v-progress-linear v-if="loadingSchema" indeterminate />

      <v-card-title class="d-flex align-center ga-2">
        <span class="text-truncate">{{ entry.label }}</span>
        <v-spacer />
        <v-chip size="small" variant="tonal">{{ entry.entry_type }}</v-chip>
      </v-card-title>

      <v-card-subtitle>{{ projectLabel ?? entry.project_name }}</v-card-subtitle>

      <v-divider />

      <v-card-text>
        <XmlLedNotice v-if="registersFromXml && canEdit" />

        <v-table density="comfortable">
          <tbody>
            <tr v-for="row in rows" :key="row.key">
              <td class="text-medium-emphasis" style="width: 30%; vertical-align: top">
                {{ row.label }}
              </td>

              <!-- URLs (Normdaten-URIs, uri-typed ids, links in a note) open
                   in a new tab -->
              <td style="white-space: pre-wrap">
                <template v-for="(part, i) in row.parts" :key="i">
                  <a
                    v-if="part.href"
                    :href="part.href"
                    rel="noopener noreferrer"
                    target="_blank"
                  >{{ part.text }}</a>

                  <template v-else>{{ part.text }}</template>
                </template>
              </td>
            </tr>
          </tbody>
        </v-table>

        <EntryRelations :can-edit="canEdit" :entry="entry" />
        <EntryComments :can-edit="canEdit" :entry="entry" :schema="schema" />
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="model = false">Close</v-btn>

        <v-btn v-if="canEdit" color="primary" prepend-icon="mdi-pencil" @click="emit('edit')">
          Edit
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts" setup>
import type { Entry, FieldSchema } from '@/api/entry'
import { computed, ref, watch } from 'vue'
import { getSchema } from '@/api/entry'
import { useHttp } from '@/context'
import { formatFieldValue, splitUrls } from '@/lib/format'
import EntryComments from './EntryComments.vue'
import EntryRelations from './EntryRelations.vue'
import XmlLedNotice from './XmlLedNotice.vue'

const model = defineModel<boolean>({ default: false })
const http = useHttp()
const props = withDefaults(
  defineProps<{
    entry?: Entry | null
    projectLabel?: string
    // false for a logged-out viewer: no Edit button (the backend would 401 anyway)
    canEdit?: boolean
    // the project's registers come from TEI files: edits here don't reach them
    registersFromXml?: boolean
  }>(),
  { canEdit: true },
)
const emit = defineEmits<{ edit: [] }>()

const schema = ref<FieldSchema[]>([])
const loadingSchema = ref(false)

const rows = computed(() => {
  const e = props.entry
  if (!e) return []
  const out: { key: string; label: string; value: string }[] = [
    { key: 'source_id', label: 'Project ID', value: formatFieldValue(e.source_id) },
  ]
  const seen = new Set<string>()
  for (const f of schema.value) {
    seen.add(f.name)
    out.push({ key: f.name, label: f.label, value: formatFieldValue(e.data[f.name]) })
  }
  for (const [k, v] of Object.entries(e.data)) {
    if (seen.has(k)) continue
    out.push({ key: k, label: k, value: formatFieldValue(v) })
  }
  return out.map((r) => ({ ...r, parts: splitUrls(r.value) }))
})

watch(
  [model, () => props.entry],
  async ([open]) => {
    if (!open || !props.entry) return
    loadingSchema.value = true
    try {
      schema.value = await getSchema(http, props.entry.project_name, props.entry.entry_type)
    } catch {
      schema.value = []
    } finally {
      loadingSchema.value = false
    }
  },
  { immediate: true },
)
</script>
