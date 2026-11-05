<!--
  Renders one dynamic form control from a backend FieldSchema. The parent keeps a
  `Record<string, string | boolean | null | QualifiedValue[]>` and binds each
  entry here with `v-model`; this component maps it to the right Vuetify input
  (checkbox -> bool, repeatable -> a RepeatableField list, multiline -> a
  textarea, everything else -> string) and applies the "required" rule.
-->
<template>
  <RepeatableField v-if="field.repeatable" v-model="asList" :field="field" />

  <v-checkbox v-else-if="field.type === 'checkbox'" v-model="asBool" :label="field.label" />

  <v-select
    v-else-if="field.type === 'select'"
    v-model="asText"
    clearable
    :items="field.options ?? []"
    :label="field.label"
    :rules="rules"
  />

  <v-text-field
    v-else-if="field.type === 'number'"
    v-model="asText"
    :label="field.label"
    :rules="rules"
    type="number"
  />

  <v-text-field
    v-else-if="field.type === 'date'"
    v-model="asText"
    :label="field.label"
    :rules="rules"
    type="date"
  />

  <v-textarea
    v-else-if="field.multiline"
    v-model="asText"
    auto-grow
    :label="field.label"
    rows="4"
    :rules="rules"
  />

  <v-text-field
    v-else
    v-model="asText"
    :hint="field.type === 'reference' ? `reference to a ${field.ref_type} entry` : undefined"
    :label="field.label"
    :persistent-hint="field.type === 'reference'"
    :rules="rules"
  />
</template>

<script lang="ts" setup>
import type { FieldSchema, QualifiedValue } from '@/api/entry'
import { computed } from 'vue'
import RepeatableField from './RepeatableField.vue'

const props = defineProps<{ field: FieldSchema }>()
const model = defineModel<string | boolean | null | QualifiedValue[]>()

const required = (v: unknown) => (v !== null && v !== undefined && v !== '') || 'Required'
const rules = computed(() => (props.field.required ? [required] : []))

const asText = computed<string>({
  get: () => (typeof model.value === 'string' ? model.value : ''),
  set: (v) => {
    model.value = v
  },
})
const asBool = computed<boolean>({
  get: () => model.value === true,
  set: (v) => {
    model.value = v
  },
})
const asList = computed<QualifiedValue[]>({
  get: () => (Array.isArray(model.value) ? model.value : []),
  set: (v) => {
    model.value = v
  },
})
</script>
