import postcss from 'postcss'
import { describe, expect, it } from 'vitest'
import { scopeSelector, scopeToRoot, splitSelectors } from './scope-to-root'

describe('scopeSelector', () => {
  it.each([
    ['.v-btn', '.index-root .v-btn'],
    ['button', '.index-root button'],
    ['*, ::before', '.index-root *, ::before'], // one selector; lists are split first
    [':root', '.index-root'],
    ['html', '.index-root'],
    ['body .x', '.index-root .x'],
    ['.index-root .x', '.index-root .x'],
    ['html.readable-text', null], // describes the platform's document
    [':deep(td:last-child)', ':deep(td:last-child)'], // Vue scopes it with [data-v-…]
    ['.a :deep(input)', '.index-root .a :deep(input)'],
  ])('%s → %s', (input, expected) => {
    expect(scopeSelector(input)).toBe(expected)
  })
})

describe('splitSelectors', () => {
  it('splits at top-level commas only', () => {
    expect(splitSelectors('.a, :is(.b, .c), [d="e,f"]')).toEqual(['.a', ':is(.b, .c)', '[d="e,f"]'])
  })
})

describe('scopeToRoot', () => {
  it('scopes rules, keeps keyframes and font faces, drops document rules', async () => {
    const input = `
      :root { --x: 1 }
      html, body { margin: 0 }
      html.dark .y { color: red }
      @layer base { .a, .b { color: blue } }
      @keyframes spin { from { opacity: 0 } to { opacity: 1 } }
      @font-face { font-family: X; src: url(x.woff2) }
    `
    const { css } = await postcss([scopeToRoot()]).process(input, { from: undefined })
    expect(css).toContain('.index-root { --x: 1 }')
    expect(css).toContain('.index-root { margin: 0 }')
    expect(css).not.toContain('dark')
    expect(css).toMatch(/\.index-root \.a,\s*\.index-root \.b/)
    expect(css).toContain('from { opacity: 0 }')
    expect(css).toContain('@font-face { font-family: X')
  })
})
