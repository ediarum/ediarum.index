<!-- Reusable entry picker: search-as-you-type over
     GET /{project}/entries/options, scoped to one (project, entryType). -->
<template>
  <v-autocomplete
    v-model="selected"
    v-model:search="search"
    clearable
    :item-title="'label'"
    :item-value="'id'"
    :items="items"
    :label="label"
    :loading="loading"
    no-filter
  />
</template>

<script lang="ts" setup>
import type { EntryRef } from '@/api/entry'
import { onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { listEntryOptions } from '@/api/entry'
import { useHttp } from '@/context'

const props = withDefaults(
  defineProps<{ project: string; entryType: string; label?: string }>(),
  { label: 'Entry' },
)
const selected = defineModel<number | null>({ default: null })
const http = useHttp()

const items = ref<EntryRef[]>([])
const search = ref('')
const loading = ref(false)

let debounceTimer: ReturnType<typeof setTimeout> | undefined

async function load(q?: string) {
  loading.value = true
  try {
    items.value = await listEntryOptions(http, props.project, { entry_type: props.entryType, q })
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

onMounted(() => load())
onBeforeUnmount(() => clearTimeout(debounceTimer))

watch(search, (q) => {
  clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => load(q || undefined), 250)
})

// a changed scope invalidates the previous project/type's results
watch(
  () => [props.project, props.entryType],
  () => load(),
)
</script>
