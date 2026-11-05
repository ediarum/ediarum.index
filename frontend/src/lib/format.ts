import type { FieldValue } from '@/api/entry'

// keys on a repeatable-field item that carry its qualifier (lang, type, kind)
const QUALIFIER_KEYS = new Set(['kind', 'type', 'lang'])

/** One repeatable-field item -> a compact "value (qualifier)" string. Handles
 *  the plain `{value}` shape and mop's `{surname, forename}` alt-name shape. */
export function formatItem(it: unknown): string {
  if (!it || typeof it !== 'object') return String(it)
  const o = it as Record<string, string | undefined>
  const name = o.value ?? ([o.surname, o.forename].filter(Boolean).join(', ') || o.name)
  const q = Object.entries(o).find(([k]) => QUALIFIER_KEYS.has(k))?.[1]
  return q ? `${name}  (${q})` : String(name ?? '')
}

/** Any `entry.data[field]` value -> one display string. A repeatable value's
 *  items are joined with `join` — `'\n'` (default) for a multi-line detail
 *  view, `'; '` for a single table-cell line. */
export function formatFieldValue(v: FieldValue | null | undefined, join = '\n'): string {
  if (v == null || v === '') return '—'
  if (typeof v === 'boolean') return v ? 'yes' : 'no'
  if (Array.isArray(v)) {
    if (v.length === 0) return '—'
    return v.map((it) => formatItem(it)).join(join)
  }
  return String(v)
}

/** One piece of a display string: plain text, or a URL to render as a link. */
export interface TextPart {
  text: string
  href?: string
}

// an http(s) URL runs to the next whitespace; trailing sentence punctuation
// ("see https://d-nb.info/gnd/118557831.") and a closing bracket are not part of it
const URL_RE = /https?:\/\/[^\s<>"]+/g
const URL_TRAIL_RE = /[.,;:!?)\]]+$/

/** Split a display string into text and URL parts, so the entry view can
 *  render each URL as an external link. */
export function splitUrls(s: string): TextPart[] {
  const parts: TextPart[] = []
  let last = 0
  for (const m of s.matchAll(URL_RE)) {
    const href = m[0].replace(URL_TRAIL_RE, '')
    if (m.index > last) parts.push({ text: s.slice(last, m.index) })
    parts.push({ text: href, href })
    last = m.index + href.length
  }
  if (last < s.length) parts.push({ text: s.slice(last) })
  return parts
}
