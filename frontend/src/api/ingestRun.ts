import type { Http } from './client'

// GET /ingest-runs  →  IngestRunPublic[] (platform admins only). Written only
// by the ingest itself — the UI never creates or edits these, only reads them.
export interface IngestRunProblem {
  fname: string
  ext_id: string | null
  detail: string
  kind: 'conflict' | 'skipped' | 'failed'
}

export interface IngestRun {
  id: number
  project: string // the ingest profile slug, e.g. "schleiermacher_persons"
  started_at: string
  finished_at: string
  status: 'ok' | 'conflicts' | 'failed'
  created: number
  updated: number
  unchanged: number
  problems: IngestRunProblem[]
}

export interface ListIngestRunsParams {
  project?: string
  offset?: number
  limit?: number
}

export function listIngestRuns(http: Http, params: ListIngestRunsParams = {}) {
  return http.get<IngestRun[]>('ingest-runs', { params }).then((r) => r.data)
}
