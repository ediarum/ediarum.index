import type { Http } from './client'

// GET /projects  →  ProjectPublic[]: the projects the caller may use (from the
// platform's project registry; edited there, not here)
export interface Project {
  name: string
  label: string
  description: string | null
  is_active: boolean
  // the platform registry's flag: where this app takes the registers from;
  // null while the registry is unreachable
  index_source_of_truth: 'xml' | 'app' | null
  // the registers are ingested from TEI files: edits here don't reach them
  registers_from_xml: boolean | null
  // an entry created without a Project ID gets one from ediarum.id
  assigns_ids: boolean
}

export function listProjects(http: Http) {
  return http.get<Project[]>('projects').then((r) => r.data)
}
