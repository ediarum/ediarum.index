import { describe, expect, it } from 'vitest'
import { personLabel, primaryValue } from './label'

describe('primaryValue', () => {
  it('returns a scalar string as-is', () => {
    expect(primaryValue('Leibniz')).toBe('Leibniz')
  })
  it('prefers the German entry of a repeatable value', () => {
    expect(
      primaryValue([
        { value: 'John', lang: 'eng' },
        { value: 'Johannes', lang: 'deu' },
      ]),
    ).toBe('Johannes')
  })
  it('falls back to the first repeatable entry', () => {
    expect(primaryValue([{ value: 'Ἰωάννης', lang: 'grc' }])).toBe('Ἰωάννης')
  })
  it('is empty for null / undefined', () => {
    expect(primaryValue(null)).toBe('')
    expect(primaryValue(undefined)).toBe('')
  })
})

describe('personLabel', () => {
  it('"Surname, Forename" when both are present', () => {
    expect(personLabel('Leibniz', 'Gottfried Wilhelm')).toBe('Leibniz, Gottfried Wilhelm')
  })
  it('surname only', () => {
    expect(personLabel('Brinck', '')).toBe('Brinck')
    expect(personLabel('Brinck', undefined)).toBe('Brinck')
  })
  it('forename only', () => {
    expect(personLabel('', 'Aristoteles')).toBe('Aristoteles')
  })
  it('empty when neither is set', () => {
    expect(personLabel('', '')).toBe('')
  })
  it('works with repeatable multilingual names', () => {
    expect(
      personLabel(
        [{ value: 'of Cyzicus', lang: 'eng' }, { value: 'von Kyzikos', lang: 'deu' }],
        [{ value: 'Eunomius', lang: 'deu' }],
      ),
    ).toBe('von Kyzikos, Eunomius')
  })
})
