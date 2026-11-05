<!-- The entry's Project ID (`source_id`): the xml:id the project's texts
     reference (`persName/@key` …), so it is guarded in two cases:

     - creating, and the backend assigns ids (`assignsIds`, ediarum.id): left
       empty and read-only — the id is reserved on save. The lock opens it for
       an id that already exists elsewhere (a migration); that one is not
       checked against ediarum.id.
     - editing an entry that has an id (`original`): read-only — texts point at
       it. The lock opens it to correct a mistake.

     Otherwise a plain text field. The parent remounts it (key) per dialog
     opening, which resets the lock. -->
<template>
  <v-text-field
    v-model="model"
    :append-inner-icon="mode ? (locked ? 'mdi-lock' : 'mdi-lock-open-variant') : undefined"
    :hint="hint"
    label="Project ID"
    :persistent-hint="!!hint"
    :placeholder="mode === 'assign' && locked ? 'assigned on save' : undefined"
    :readonly="!!mode && locked"
    @click:append-inner="toggle"
  />
</template>

<script lang="ts" setup>
import { computed, ref } from 'vue'

const model = defineModel<string>({ default: '' })
const props = defineProps<{
  creating: boolean
  assignsIds: boolean
  // the saved entry's id (editing)
  original?: string | null
}>()

const mode = computed<'assign' | 'protect' | null>(() => {
  if (props.creating) return props.assignsIds ? 'assign' : null
  return props.original ? 'protect' : null
})
const locked = ref(true)

const HINTS = {
  assign: {
    locked: 'Assigned by ediarum.id when you save.',
    open: 'Only for an id that already exists elsewhere: it is not checked against ediarum.id.',
  },
  protect: {
    locked: 'Referenced by the texts: unlock only to correct it.',
    open: 'Texts that reference the old id will no longer point to this entry.',
  },
}
const hint = computed(() => (mode.value ? HINTS[mode.value][locked.value ? 'locked' : 'open'] : undefined))

function toggle() {
  locked.value = !locked.value
  if (!locked.value) return
  // locking again: back to what it was (empty → assigned on save)
  model.value = mode.value === 'assign' ? '' : (props.original ?? '')
}
</script>
