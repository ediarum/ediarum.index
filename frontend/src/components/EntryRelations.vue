<!-- Generic relations section for the entry-detail view: every relation this
     entry is a subject or object of, either direction, with a resolved label
     for whichever entry is on the *other* end (never a bare id — see
     api/relation.ts). Not specific to any one predicate or project; e.g.
     schleiermacher's `person --member_of--> group` is just one relation this
     shows like any other. -->
<template>
  <div class="mt-5">
    <div class="text-caption text-medium-emphasis mb-1">Relations</div>

    <v-alert v-if="error" density="compact" type="error" variant="tonal">{{ error }}</v-alert>

    <div v-else-if="!loading && rows.length === 0" class="text-body-2 text-medium-emphasis">
      No relations.
    </div>

    <v-list v-else density="compact">
      <v-list-item v-for="row in rows" :key="row.id">
        <template #prepend>
          <v-icon :icon="row.direction === 'outgoing' ? 'mdi-arrow-right' : 'mdi-arrow-left'" size="small" />
        </template>

        <v-list-item-title>{{ row.predicate }}: {{ row.otherLabel }}</v-list-item-title>

        <template v-if="canEdit" #append>
          <v-btn
            :disabled="removing === row.id"
            icon="mdi-delete-outline"
            size="small"
            variant="text"
            @click="onRemove(row.id)"
          />
        </template>
      </v-list-item>
    </v-list>

    <div v-if="canEdit" class="mt-2">
      <v-btn v-if="!adding" size="small" variant="text" @click="adding = true">Add relation</v-btn>

      <div v-else class="d-flex flex-column ga-2">
        <v-btn-toggle v-model="direction" color="primary" density="compact" mandatory variant="outlined">
          <v-btn value="outgoing">This entry → target</v-btn>
          <v-btn value="incoming">Target → this entry</v-btn>
        </v-btn-toggle>

        <v-combobox
          v-model="predicate"
          density="compact"
          hide-details
          :items="predicateSuggestions"
          label="Predicate"
        />

        <v-select
          v-model="targetType"
          density="compact"
          hide-details
          :item-title="'label'"
          :item-value="'name'"
          :items="entryTypes"
          label="Target type"
        />

        <EntryAutocomplete
          v-model="targetId"
          density="compact"
          :entry-type="targetType"
          label="Target entry"
          :project="entry.project_name"
        />

        <v-alert v-if="addError" density="compact" type="error" variant="tonal">{{ addError }}</v-alert>

        <div class="d-flex ga-2">
          <v-btn
            color="primary"
            :disabled="!predicate || !targetId"
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
import type { Entry } from '@/api/entry'
import { computed, ref, watch } from 'vue'
import { apiError } from '@/api/error'
import { useEntryTypes } from '@/composables/useEntryTypes'
import { useRelations } from '@/composables/useRelations'
import EntryAutocomplete from './common/EntryAutocomplete.vue'

const props = defineProps<{ entry: Entry; canEdit: boolean }>()

const { outgoing, incoming, loading, error, create, remove } = useRelations(
  () => props.entry.project_name,
  () => props.entry.id,
)

// an incoming relation, read from this entry's side: "← mentions: X" read as
// "this entry mentions X", the other way round
const INCOMING_WORDING: Record<string, string> = { mentions: 'mentioned by' }

const rows = computed(() => [
  ...outgoing.value.map((r) => ({
    id: r.id,
    predicate: r.predicate,
    otherLabel: r.object_label,
    direction: 'outgoing' as const,
  })),
  ...incoming.value.map((r) => ({
    id: r.id,
    predicate: INCOMING_WORDING[r.predicate] ?? r.predicate,
    otherLabel: r.subject_label,
    direction: 'incoming' as const,
  })),
])

const removing = ref<number | null>(null)
async function onRemove(id: number) {
  removing.value = id
  try {
    await remove(id)
  } finally {
    removing.value = null
  }
}

// --- add relation ---------------------------------------------------------

// relation targets: the types of the entry's project
const { entryTypes } = useEntryTypes(() => props.entry.project_name)
// member_of: person -> family (group); part_of: sub-place -> place
const predicateSuggestions = ['member_of', 'part_of']

const adding = ref(false)
const direction = ref<'outgoing' | 'incoming'>('outgoing')
const predicate = ref('member_of')
const targetType = ref(props.entry.entry_type)
const targetId = ref<number | null>(null)
const submitting = ref(false)
const addError = ref<string | null>(null)

// reset the target once its own type changes — a stale id from the old type
// must not be submitted against the new one
watch(targetType, () => {
  targetId.value = null
})
// re-open the form fresh for a different entry rather than keeping a stale target
watch(
  () => props.entry.id,
  () => {
    adding.value = false
    targetId.value = null
  },
)

async function onAdd() {
  if (!targetId.value || !predicate.value) return
  submitting.value = true
  addError.value = null
  try {
    const payload =
      direction.value === 'outgoing'
        ? { subject_id: props.entry.id, predicate: predicate.value, object_id: targetId.value }
        : { subject_id: targetId.value, predicate: predicate.value, object_id: props.entry.id }
    await create(payload)
    adding.value = false
    targetId.value = null
  } catch (error_) {
    addError.value = apiError(error_)
  } finally {
    submitting.value = false
  }
}
</script>
