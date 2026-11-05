import type { Http } from './client'

// GET /{project}/relations  →  RelationWithLabels
export interface Relation {
  id: number
  subject_id: number
  predicate: string
  object_id: number
  subject_label: string
  object_label: string
}

// POST /{project}/relations  →  RelationPublic (no labels — the caller creating
// one already has both client-side)
export interface RelationCreate {
  subject_id: number
  predicate: string
  object_id: number
}

export interface ListRelationsParams {
  subject_id?: number
  object_id?: number
  predicate?: string
  offset?: number
  limit?: number
}

const enc = encodeURIComponent

export function listRelations(http: Http, project: string, params: ListRelationsParams = {}) {
  return http.get<Relation[]>(`${enc(project)}/relations`, { params }).then((r) => r.data)
}

export function createRelation(http: Http, project: string, payload: RelationCreate) {
  return http
    .post<RelationCreate & { id: number }>(`${enc(project)}/relations`, payload)
    .then((r) => r.data)
}

export function deleteRelation(http: Http, project: string, id: number) {
  return http.delete<{ ok: boolean }>(`${enc(project)}/relations/${id}`).then((r) => r.data)
}
