import { type MaybeRefOrGetter, ref, toValue, watch } from 'vue'
import {
  type Comment,
  type CommentCreate,
  createComment,
  deleteComment,
  listComments,
} from '@/api/comment'
import { useHttp } from '@/context'

/** Every comment on one entry, sorted the way `GET /{project}/comments`
 *  already returns them (by created_at). */
export function useComments(
  project: MaybeRefOrGetter<string | undefined>,
  entryId: MaybeRefOrGetter<number | undefined>,
) {
  const http = useHttp()
  const comments = ref<Comment[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    const proj = toValue(project)
    const id = toValue(entryId)
    if (!proj || !id) {
      comments.value = []
      return
    }
    loading.value = true
    error.value = null
    try {
      comments.value = await listComments(http, proj, { entry_id: id })
    } catch {
      error.value = 'Failed to load comments.'
    } finally {
      loading.value = false
    }
  }

  watch([() => toValue(project), () => toValue(entryId)], load, { immediate: true })

  async function create(payload: CommentCreate) {
    await createComment(http, toValue(project)!, payload)
    await load()
  }

  async function remove(id: number) {
    await deleteComment(http, toValue(project)!, id)
    await load()
  }

  return { comments, loading, error, load, create, remove }
}
