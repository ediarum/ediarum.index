import { afterEach, describe, expect, it, vi } from 'vitest'
import { platformTheme, readPlatformTokens, watchColorScheme } from './theme'

afterEach(() => {
  document.documentElement.removeAttribute('style')
  vi.restoreAllMocks()
})

describe('readPlatformTokens', () => {
  it("reads the platform's --ep-color-* tokens", () => {
    document.documentElement.style.setProperty('--ep-color-accent', '#123456')
    document.documentElement.style.setProperty('--ep-color-bg', '#fafafa')
    const tokens = readPlatformTokens(false)
    expect(tokens.accent).toBe('#123456')
    expect(tokens.bg).toBe('#fafafa')
  })

  it("falls back to the platform's own values per token", () => {
    expect(readPlatformTokens(false).accent).toBe('#c8221f')
    expect(readPlatformTokens(true).accent).toBe('#f0524f')
  })

  it('ignores a token Vuetify could not parse', () => {
    document.documentElement.style.setProperty('--ep-color-accent', 'oklch(60% 0.2 25)')
    expect(readPlatformTokens(false).accent).toBe('#c8221f')
  })
})

describe('platformTheme', () => {
  it('maps the tokens onto the Vuetify theme', () => {
    document.documentElement.style.setProperty('--ep-color-accent', '#123456')
    document.documentElement.style.setProperty('--ep-color-surface', '#eeeeee')
    const theme = platformTheme(false)
    expect(theme.dark).toBe(false)
    expect(theme.colors?.primary).toBe('#123456')
    expect(theme.colors?.['surface-light']).toBe('#eeeeee')
    expect(platformTheme(true).dark).toBe(true)
  })
})

describe('watchColorScheme', () => {
  it('follows the scheme until stopped', () => {
    const listeners = new Set<(e: MediaQueryListEvent) => void>()
    vi.spyOn(window, 'matchMedia').mockReturnValue({
      matches: false,
      addEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => listeners.add(l),
      removeEventListener: (_: string, l: (e: MediaQueryListEvent) => void) => listeners.delete(l),
    } as unknown as MediaQueryList)
    const seen: boolean[] = []
    const stop = watchColorScheme((dark) => seen.push(dark))
    for (const l of listeners) l({ matches: true } as MediaQueryListEvent)
    stop()
    expect(seen).toEqual([true])
    expect(listeners.size).toBe(0)
  })
})
