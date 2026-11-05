import { describe, expect, it } from 'vitest'
import { formatFieldValue, formatItem, splitUrls } from './format'

describe('formatItem', () => {
  it('formats a value with a qualifier', () => {
    expect(formatItem({ value: 'Euseb', lang: 'deu' })).toBe('Euseb  (deu)')
  })
  it('formats a bare value with no qualifier', () => {
    expect(formatItem({ value: 'urn:x' })).toBe('urn:x')
  })
  it('formats a surname/forename alt-name pair', () => {
    expect(formatItem({ surname: 'Adlerberg', forename: 'Eduard' })).toBe('Adlerberg, Eduard')
  })
  it('stringifies a non-object item as-is', () => {
    expect(formatItem('plain')).toBe('plain')
  })
})

describe('formatFieldValue', () => {
  it('is an em dash for null / undefined / empty string', () => {
    expect(formatFieldValue(null)).toBe('—')
    expect(formatFieldValue(undefined)).toBe('—')
    expect(formatFieldValue('')).toBe('—')
  })
  it('formats a boolean', () => {
    expect(formatFieldValue(true)).toBe('yes')
    expect(formatFieldValue(false)).toBe('no')
  })
  it('stringifies a scalar', () => {
    expect(formatFieldValue('nach 1824')).toBe('nach 1824')
    expect(formatFieldValue(1809)).toBe('1809')
  })
  it('is an em dash for an empty repeatable value', () => {
    expect(formatFieldValue([])).toBe('—')
  })
  it('joins a repeatable value with the given separator (newline by default)', () => {
    const surnames = [
      { value: 'of Nicomedeia', lang: 'eng' },
      { value: 'von Nikomedien', lang: 'deu' },
    ]
    expect(formatFieldValue(surnames)).toBe('of Nicomedeia  (eng)\nvon Nikomedien  (deu)')
    expect(formatFieldValue(surnames, '; ')).toBe('of Nicomedeia  (eng); von Nikomedien  (deu)')
  })
})

describe('splitUrls', () => {
  it('returns plain text as one part', () => {
    expect(splitUrls('nach 1824')).toEqual([{ text: 'nach 1824' }])
  })
  it('splits URLs out of surrounding text', () => {
    expect(splitUrls('GND: https://d-nb.info/gnd/118557831 (geprüft)')).toEqual([
      { text: 'GND: ' },
      { text: 'https://d-nb.info/gnd/118557831', href: 'https://d-nb.info/gnd/118557831' },
      { text: ' (geprüft)' },
    ])
  })
  it('keeps trailing punctuation out of the link', () => {
    expect(splitUrls('siehe https://viaf.org/viaf/1.')).toEqual([
      { text: 'siehe ' },
      { text: 'https://viaf.org/viaf/1', href: 'https://viaf.org/viaf/1' },
      { text: '.' },
    ])
  })
  it('links each of several URLs, one per line', () => {
    const parts = splitUrls('https://a.org/1\nhttps://b.org/2  (uri)')
    expect(parts.filter((p) => p.href).map((p) => p.href)).toEqual(['https://a.org/1', 'https://b.org/2'])
    expect(parts.map((p) => p.text).join('')).toBe('https://a.org/1\nhttps://b.org/2  (uri)')
  })
  it('does not link a bare identifier', () => {
    expect(splitUrls('118557831  (GND)')).toEqual([{ text: '118557831  (GND)' }])
  })
})
