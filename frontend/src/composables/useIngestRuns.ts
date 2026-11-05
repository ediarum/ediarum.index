import { ref } from 'vue'
import { type IngestRun, listIngestRuns, type ListIngestRunsParams } from '@/api/ingestRun'
import { useHttp } from '@/context'

export function useIngestRuns() {
  const http = useHttp()
  const runs = ref<IngestRun[]>([])
  const loading = ref(false)
  const error = ref<string | null>(null)

  async function load(params: ListIngestRunsParams = {}) {
    loading.value = true
    error.value = null
    try {
      runs.value = await listIngestRuns(http, params)
    } catch {
      error.value = 'Failed to load ingest runs.'
    } finally {
      loading.value = false
    }
  }

  return { runs, loading, error, load }
}
