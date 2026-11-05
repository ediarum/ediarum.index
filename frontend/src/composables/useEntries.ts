import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'
import {
  createEntry,
  deleteEntry,
  type Entry,
  type EntryCreate,
  type EntryUpdate,
  listEntries,
  updateEntry,
} from '@/api/entry'
import { useHttp } from '@/context'

/** Server-paginated, server-sorted, server-filtered list of entries for a
 *  (project, entry_type). `search` / `searchField` map to the `q` / `q_field`
 *  query params. */
export function useEntries(
  project: MaybeRefOrGetter<string>,
  entryType?: MaybeRefOrGetter<string | undefined>,
  search?: MaybeRefOrGetter<string | undefined>,
  searchField?: MaybeRefOrGetter<string | undefined>,
) {
  const http = useHttp()
  const entries = ref<Entry[]>([])
  const total = ref(0)
  const loading = ref(false)
  const error = ref<string | null>(null)

  const page = ref(1)
  const itemsPerPage = ref(25)
  const sortBy = ref('label')
  const descending = ref(false)

  async function load() {
    loading.value = true
    error.value = null
    try {
      const res = await listEntries(http, toValue(project), {
        entry_type: toValue(entryType),
        q: toValue(search) || undefined,
        q_field: toValue(searchField) || undefined,
        offset: (page.value - 1) * itemsPerPage.value,
        limit: itemsPerPage.value,
        sort_by: sortBy.value,
        descending: descending.value,
      })
      entries.value = res.items
      total.value = res.total
    } catch {
      error.value = 'Failed to load entries.'
    } finally {
      loading.value = false
    }
  }

  // a changed filter goes back to page 1; any of these triggers a refetch
  watch(
    [
      () => toValue(project),
      () => toValue(entryType),
      () => toValue(search),
      () => toValue(searchField),
    ],
    () => {
      page.value = 1
    },
  )
  watch(
    [
      () => toValue(project),
      () => toValue(entryType),
      () => toValue(search),
      () => toValue(searchField),
      page,
      itemsPerPage,
      sortBy,
      descending,
    ],
    load,
  )

  async function create(payload: EntryCreate) {
    const created = await createEntry(http, toValue(project), payload)
    await load()
    return created
  }

  async function update(id: number, payload: EntryUpdate) {
    const updated = await updateEntry(http, toValue(project), id, payload)
    await load()
    return updated
  }

  async function remove(id: number) {
    await deleteEntry(http, toValue(project), id)
    await load()
  }

  return {
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
  }
}
