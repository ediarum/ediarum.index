import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'
import { type EntryTypeInfo, listEntryTypes, listProjectEntryTypes } from '@/api/entry'
import { useHttp } from '@/context'

/** The entry types in canonical order: those `project` uses (GET
 *  /{project}/entry-types, reloaded when it changes), or every registered
 *  type (GET /entry-types) without a project. */
export function useEntryTypes(project?: MaybeRefOrGetter<string | undefined>) {
  const http = useHttp()
  const entryTypes = ref<EntryTypeInfo[]>([])
  const loading = ref(false)

  async function load() {
    loading.value = true
    const slug = toValue(project)
    let types: EntryTypeInfo[]
    try {
      types = slug ? await listProjectEntryTypes(http, slug) : await listEntryTypes(http)
    } catch {
      types = []
    }
    if (toValue(project) !== slug) return // the project changed meanwhile: its load wins
    entryTypes.value = types
    loading.value = false
  }

  watch(() => toValue(project), load, { immediate: true })
  return { entryTypes, loading, load }
}
