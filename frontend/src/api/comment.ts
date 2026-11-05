import type { Http } from './client'

// GET/POST /{project}/comments  →  CommentPublic
export interface Comment {
  id: number
  entry_id: number
  text: string
  author: string
  created_at: string
  source: 'ingested' | 'app'
  start_field: string | null
  end_field: string | null
}

// POST /{project}/comments  →  CommentIn: always a hand-written comment — the
// backend sets source="app", the caller as author and the write time
export interface CommentCreate {
  entry_id: number
  text: string
  start_field?: string | null
  end_field?: string | null
}

export interface ListCommentsParams {
  entry_id?: number
  offset?: number
  limit?: number
}

const enc = encodeURIComponent

export function listComments(http: Http, project: string, params: ListCommentsParams = {}) {
  return http.get<Comment[]>(`${enc(project)}/comments`, { params }).then((r) => r.data)
}

export function createComment(http: Http, project: string, payload: CommentCreate) {
  return http.post<Comment>(`${enc(project)}/comments`, payload).then((r) => r.data)
}

export function deleteComment(http: Http, project: string, id: number) {
  return http.delete<{ ok: boolean }>(`${enc(project)}/comments/${id}`).then((r) => r.data)
}
