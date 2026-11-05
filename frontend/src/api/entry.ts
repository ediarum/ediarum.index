import type { Http } from './client'

export type EntryType = 'person' | 'place' | 'group' | 'organisation' | 'work' | 'bible_book' | 'glossary'

// a repeatable field holds a list of these; `value` plus one qualifier key
// (e.g. `lang` or `type`, named by FieldSchema.qualifier)
export interface QualifiedValue {
  [qualifier: string]: string | undefined
  // usually a scalar value; a few ingest fields (e.g. mop `alt_names`) carry
  // `surname` / `forename` sub-parts instead
  value?: string
}

export type FieldValue = string | number | boolean | null | QualifiedValue[]

export type EntryData = Record<string, FieldValue>

// GET /{project}/entries and GET /{project}/entries/{id}  →  EntryPublic
export interface Entry {
  id: number
  project_name: string
  entry_type: EntryType
  label: string
  source_id: string | null
  data: EntryData
}

// POST /{project}/entries  →  EntryIn (the project is the URL's)
export interface EntryCreate {
  entry_type: EntryType
  label: string
  source_id?: string | null
  data?: EntryData
}

// PATCH /{project}/entries/{id}  →  EntryEdit (partial; entry_type is fixed)
export interface EntryUpdate {
  label?: string
  source_id?: string | null
  data?: EntryData
}

// GET /{project}/schema/{entry_type}  →  list[FieldSchema]
export interface FieldSchema {
  name: string
  label: string
  type: 'text' | 'number' | 'select' | 'checkbox' | 'date' | 'reference'
  required: boolean
  options: string[] | null
  ref_type: string | null
  repeatable: boolean
  qualifier: string | null // sub-key on each value, e.g. 'lang' or 'type'
  qualifier_options: string[] | null
  multiline: boolean // long free text: a full-width textarea, no table column
}

// GET /entry-types, GET /{project}/entry-types  →  EntryTypePublic
// (the project's list drives the per-type tabs)
export interface EntryTypeInfo {
  name: string
  label: string
  description: string | null
}

export interface ListEntriesParams {
  entry_type?: string
  q?: string // case-insensitive substring match on q_field
  q_field?: string // 'label' (default), 'source_id', or a data-bag key
  offset?: number
  limit?: number
  sort_by?: string
  descending?: boolean
}

export interface EntryPage {
  items: Entry[]
  total: number
}

const enc = encodeURIComponent

// one page of entries; `total` is the full match count (X-Total-Count header)
export function listEntries(http: Http, project: string, params?: ListEntriesParams): Promise<EntryPage> {
  return http.get<Entry[]>(`${enc(project)}/entries`, { params }).then((r) => ({
    items: r.data,
    total: Number(r.headers['x-total-count'] ?? r.data.length),
  }))
}

export function getEntry(http: Http, project: string, id: number) {
  return http.get<Entry>(`${enc(project)}/entries/${id}`).then((r) => r.data)
}

export function createEntry(http: Http, project: string, payload: EntryCreate) {
  return http.post<Entry>(`${enc(project)}/entries`, payload).then((r) => r.data)
}

export function updateEntry(http: Http, project: string, id: number, payload: EntryUpdate) {
  return http.patch<Entry>(`${enc(project)}/entries/${id}`, payload).then((r) => r.data)
}

export function deleteEntry(http: Http, project: string, id: number) {
  return http.delete<{ ok: boolean }>(`${enc(project)}/entries/${id}`).then((r) => r.data)
}

// The schema is code-defined (fixed per deploy), so each (project, type) is
// fetched once per mount: the list, the entry view and the edit dialog all ask
// for it. A failed fetch is dropped from the cache so the next call retries.
const schemaCache = new WeakMap<Http, Map<string, Promise<FieldSchema[]>>>()

export function getSchema(http: Http, project: string, entryType: string) {
  let byKey = schemaCache.get(http)
  if (!byKey) schemaCache.set(http, (byKey = new Map()))
  const key = `${enc(project)}/schema/${enc(entryType)}`
  let p = byKey.get(key)
  if (!p) {
    p = http.get<FieldSchema[]>(key).then((r) => r.data)
    p.catch(() => byKey.delete(key))
    byKey.set(key, p)
  }
  return p
}

export function listEntryTypes(http: Http) {
  return http.get<EntryTypeInfo[]>('entry-types').then((r) => r.data)
}

// the types `project` uses (its module's ENTRY_TYPES, plus any it has entries of)
export function listProjectEntryTypes(http: Http, project: string) {
  return http.get<EntryTypeInfo[]>(`${project}/entry-types`).then((r) => r.data)
}

// GET /{project}/entries/options  →  EntryRef[] — (id, label) pairs for a
// reference picker / autocomplete, scoped to one entry type
export interface EntryRef {
  id: number
  label: string
}

export interface ListEntryOptionsParams {
  entry_type: string
  q?: string
  limit?: number
}

export function listEntryOptions(http: Http, project: string, params: ListEntryOptionsParams) {
  return http.get<EntryRef[]>(`${enc(project)}/entries/options`, { params }).then((r) => r.data)
}
