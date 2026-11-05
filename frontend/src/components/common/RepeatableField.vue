<!--
  Editor for a repeatable schema field: a stacked list of rows, each = a value
  input + (if the field has a qualifier) a combobox for the qualifier key
  (`lang`, `type`, …). Models `QualifiedValue[]`.
-->
<template>
  <div class="mb-3">
    <div class="text-caption text-medium-emphasis mb-1">{{ field.label }}</div>

    <div v-for="(row, i) in rows" :key="i" class="d-flex ga-2 mb-1 align-start">
      <v-text-field
        density="compact"
        hide-details
        :model-value="row.value"
        :placeholder="field.label"
        @update:model-value="patch(i, { value: $event })"
      />

      <v-combobox
        v-if="field.qualifier"
        density="compact"
        hide-details
        :items="field.qualifier_options ?? []"
        :label="field.qualifier"
        :model-value="row[field.qualifier]"
        style="max-width: 150px"
        @update:model-value="patch(i, { [field.qualifier]: $event || undefined })"
      />

      <v-btn class="mt-1" icon="mdi-close" size="small" variant="text" @click="removeRow(i)" />
    </div>

    <v-btn prepend-icon="mdi-plus" size="small" variant="text" @click="addRow">Add</v-btn>
  </div>
</template>

<script lang="ts" setup>
import type { FieldSchema, QualifiedValue } from '@/api/entry'
import { computed } from 'vue'

defineProps<{ field: FieldSchema }>()
const model = defineModel<QualifiedValue[]>({ default: () => [] })

const rows = computed(() => model.value ?? [])

function patch(i: number, delta: Partial<QualifiedValue>) {
  model.value = rows.value.map((row, idx) => (idx === i ? { ...row, ...delta } : row))
}
function addRow() {
  model.value = [...rows.value, { value: '' }]
}
function removeRow(i: number) {
  model.value = rows.value.filter((_, idx) => idx !== i)
}
</script>
