import type { FieldValue } from '@/api/entry'

/** Primary display string for a field value; a repeatable value prefers the
 *  German (`lang: 'deu'`) entry, else the first. */
export function primaryValue(v: FieldValue | undefined): string {
  if (Array.isArray(v)) {
    const de = v.find((x) => x.lang === 'deu')
    return (de ?? v[0])?.value ?? ''
  }
  if (typeof v === 'string') return v
  return v == null ? '' : String(v)
}

/** Person label: "Surname, Forename" when both are present, otherwise whichever
 *  one is there. */
export function personLabel(surname: FieldValue | undefined, forename: FieldValue | undefined): string {
  const s = primaryValue(surname).trim()
  const f = primaryValue(forename).trim()
  return s && f ? `${s}, ${f}` : s || f
}
