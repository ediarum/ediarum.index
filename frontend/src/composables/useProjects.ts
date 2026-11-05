import { ref } from 'vue'
import { listProjects, type Project } from '@/api/project'
import { useHttp } from '@/context'

/** The projects the caller may use (GET /projects) — the platform's project
 *  registry decides which exist and who may use them. */
export function useProjects() {
  const http = useHttp()
  const projects = ref<Project[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load() {
    loading.value = true
    error.value = null
    try {
      projects.value = await listProjects(http)
    } catch {
      error.value = 'Failed to load projects.'
    } finally {
      loading.value = false
    }
  }

  function find(slug: string): Project | undefined {
    return projects.value.find((p) => p.name === slug)
  }

  function label(slug: string) {
    return find(slug)?.label ?? slug
  }

  return { projects, loading, error, load, find, label }
}
