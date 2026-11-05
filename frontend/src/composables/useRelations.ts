import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'
import {
  createRelation,
  deleteRelation,
  listRelations,
  type Relation,
  type RelationCreate,
} from '@/api/relation'
import { useHttp } from '@/context'

/** Every relation for one entry, both directions — `outgoing` (entry is the
 *  subject) and `incoming` (entry is the object), loaded and kept in sync
 *  together since either can change as a result of create()/remove(). */
export function useRelations(
  project: MaybeRefOrGetter<string | undefined>,
  entryId: MaybeRefOrGetter<number | undefined>,
) {
  const http = useHttp()
  const outgoing = ref<Relation[]>([])
  const incoming = ref<Relation[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    const proj = toValue(project)
    const id = toValue(entryId)
    if (!proj || !id) {
      outgoing.value = []
      incoming.value = []
      return
    }
    loading.value = true
    error.value = null
    try {
      const [out, inc] = await Promise.all([
        listRelations(http, proj, { subject_id: id }),
        listRelations(http, proj, { object_id: id }),
      ])
      outgoing.value = out
      incoming.value = inc
    } catch {
      error.value = 'Failed to load relations.'
    } finally {
      loading.value = false
    }
  }

  watch([() => toValue(project), () => toValue(entryId)], load, { immediate: true })

  async function create(payload: RelationCreate) {
    await createRelation(http, toValue(project)!, payload)
    await load()
  }

  async function remove(id: number) {
    await deleteRelation(http, toValue(project)!, id)
    await load()
  }

  return { outgoing, incoming, loading, error, load, create, remove }
}
