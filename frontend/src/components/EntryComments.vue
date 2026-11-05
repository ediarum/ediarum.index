<!-- Editorial remarks on one entry — either preserved from the source XML's
     own oxy_comment_start/end PIs and plain XML comments (see backend
     ingest.py), or written by a curator here. Mirrors EntryRelations.vue's
     shape (titled section, flat list, delete-if-canEdit, inline add-form). -->
<template>
  <div class="mt-5">
    <div class="text-caption text-medium-emphasis mb-1">Comments</div>

    <v-alert v-if="error" density="compact" type="error" variant="tonal">{{ error }}</v-alert>

    <div v-else-if="!loading && comments.length === 0" class="text-body-2 text-medium-emphasis">
      No comments.
    </div>

    <v-list v-else density="compact">
      <v-list-item v-for="c in comments" :key="c.id">
        <v-list-item-title style="white-space: pre-wrap">{{ c.text }}</v-list-item-title>

        <v-list-item-subtitle>
          {{ c.author || 'unknown' }} · {{ formatDate(c.created_at) }}
          <template v-if="c.start_field">· {{ fieldLabel(c.start_field, c.end_field) }}</template>
        </v-list-item-subtitle>

        <template v-if="canEdit" #append>
          <v-btn
            :disabled="removing === c.id"
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            @click="onRemove(c.id)"
          />
        </template>
      </v-list-item>
    </v-list>

    <div v-if="canEdit" class="mt-2">
      <v-btn v-if="!adding" size="small" variant="text" @click="adding = true">Add comment</v-btn>

      <div v-else class="d-flex flex-column ga-2">
        <v-select
          v-model="field"
          density="compact"
          hide-details
          item-title="title"
          item-value="value"
          :items="fieldOptions"
          label="Field"
        />

        <v-textarea
          v-model="text"
          auto-grow
          density="compact"
          hide-details
          label="Comment"
          rows="2"
        />

        <v-alert v-if="addError" density="compact" type="error" variant="tonal">{{ addError }}</v-alert>

        <div class="d-flex ga-2">
          <v-btn
            color="primary"
            :disabled="!text.trim()"
            :loading="submitting"
            size="small"
            @click="onAdd"
          >
            Add
          </v-btn>

          <v-btn size="small" variant="text" @click="adding = false">Cancel</v-btn>
        </div>
      </div>
    </div>
  </div>
</template>

<script lang="ts" setup>
import type { Entry, FieldSchema } from '@/api/entry'
import { computed, ref, watch } from 'vue'
import { apiError } from '@/api/error'
import { useComments } from '@/composables/useComments'

const props = defineProps<{ entry: Entry; canEdit: boolean; schema?: FieldSchema[] }>()

const { comments, loading, error, create, remove } = useComments(
  () => props.entry.project_name,
  () => props.entry.id,
)

const fieldOptions = computed(() => [
  { title: 'General', value: null as string | null },
  ...(props.schema ?? []).map((f) => ({ title: f.label, value: f.name })),
])

function fieldName(name: string): string {
  return (props.schema ?? []).find((f) => f.name === name)?.label ?? name
}

function fieldLabel(startField: string, endField: string | null): string {
  return startField === endField || !endField
    ? fieldName(startField)
    : `${fieldName(startField)} → ${fieldName(endField)}`
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleDateString()
}

const removing = ref<number | null>(null)
async function onRemove(id: number) {
  removing.value = id
  try {
    await remove(id)
  } finally {
    removing.value = null
  }
}

// --- add comment ------------------------------------------------------------

const adding = ref(false)
const field = ref<string | null>(null)
const text = ref('')
const submitting = ref(false)
const addError = ref<string | null>(null)

// re-open the form fresh for a different entry rather than keeping stale input
watch(
  () => props.entry.id,
  () => {
    adding.value = false
    field.value = null
    text.value = ''
  },
)

async function onAdd() {
  if (!text.value.trim()) return
  submitting.value = true
  addError.value = null
  try {
    await create({
      entry_id: props.entry.id,
      text: text.value.trim(),
      start_field: field.value,
      end_field: field.value,
    })
    adding.value = false
    field.value = null
    text.value = ''
  } catch (error_) {
    addError.value = apiError(error_)
  } finally {
    submitting.value = false
  }
}
</script>
