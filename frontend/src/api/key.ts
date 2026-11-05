import type { Http } from './client'

// GET /keys  →  KeyOut[] (platform admins only): API clients for programs
// without a platform session (ediarum/oXygen, ediarum.webdav, scripts)
export interface ApiKey {
  name: string
  projects: string[] // slugs, or ['*'] for every project
  is_admin: boolean
  is_active: boolean
  created_by: string | null
}

// POST /keys  →  NewKey: the key itself is in this response only
export interface ApiKeyCreate {
  name: string
  projects: string[]
}

export interface NewApiKey {
  name: string
  key: string
}

export function listKeys(http: Http) {
  return http.get<ApiKey[]>('keys').then((r) => r.data)
}

export function createKey(http: Http, payload: ApiKeyCreate) {
  return http.post<NewApiKey>('keys', payload).then((r) => r.data)
}

export function revokeKey(http: Http, name: string) {
  return http.post<void>(`keys/${encodeURIComponent(name)}/revoke`).then(() => undefined)
}
