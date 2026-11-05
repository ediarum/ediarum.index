import { ref } from 'vue'
import { type ApiKey, type ApiKeyCreate, createKey, listKeys, revokeKey } from '@/api/key'
import { useHttp } from '@/context'

/** API keys (platform admins only). `create` returns the key itself, which the
 *  backend shows only this once. */
export function useKeys() {
  const http = useHttp()
  const keys = ref<ApiKey[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      keys.value = await listKeys(http)
    } catch {
      error.value = 'Failed to load the API keys.'
    } finally {
      loading.value = false
    }
  }

  async function create(payload: ApiKeyCreate) {
    const created = await createKey(http, payload)
    await load()
    return created
  }

  async function revoke(name: string) {
    await revokeKey(http, name)
    await load()
  }

  return { keys, loading, error, load, create, revoke }
}
