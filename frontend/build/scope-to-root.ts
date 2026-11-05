// PostCSS plugin: confine every CSS rule of the bundle to the app's root
// element, so neither our CSS nor Vuetify's / Tailwind's resets reach the
// platform (ediarum-platform docs/integrating-an-app.md, 3.6).
//
//   .x            → .index-root .x
//   html, body, :root          → .index-root
//   html .x       → .index-root .x
//   html.dark     → dropped (describes the document, not the app)
//   :deep(.x)     → untouched (a <style scoped> rule; see scopeSelector)
//   @keyframes …  → untouched; @font-face stays global (harmless)

import type { AtRule, Node, Plugin, Rule } from 'postcss'

export const ROOT = '.index-root'

/** Split a selector list at top-level commas only. */
export function splitSelectors(list: string): string[] {
  const parts: string[] = []
  let depth = 0
  let start = 0
  for (let i = 0; i < list.length; i++) {
    const ch = list[i]
    if (ch === '(' || ch === '[') depth++
    else if (ch === ')' || ch === ']') depth--
    else if (ch === ',' && depth === 0) {
      parts.push(list.slice(start, i))
      start = i + 1
    }
  }
  parts.push(list.slice(start))
  return parts.map((s) => s.trim()).filter(Boolean)
}

/** One selector, scoped to ROOT — or null to drop it. */
export function scopeSelector(selector: string): string | null {
  if (selector.startsWith(ROOT)) return selector
  // This runs before Vue's scoped-CSS transform, which puts `[data-v-…]` on
  // the compound in front of a leading `:deep()`: prefixed, `:deep(td)`
  // would become `.index-root[data-v-…] td` and match nothing. Unprefixed it
  // becomes `[data-v-…] td` — already confined to the component's own
  // elements, which are inside the root.
  if (selector.startsWith(':deep(')) return selector
  const root = /^(?:html|body|:root)(?![\w-])/.exec(selector)
  if (root) {
    const rest = selector.slice(root[0].length)
    if (rest === '') return ROOT
    return /^\s/.test(rest) ? ROOT + rest : null // `html .x` → inside; `html.x` → drop
  }
  return `${ROOT} ${selector}`
}

const scoped = new WeakSet<Rule>()

export function scopeToRoot(): Plugin {
  return {
    postcssPlugin: 'scope-to-root',
    Rule(rule) {
      if (scoped.has(rule)) return
      scoped.add(rule)
      for (let p: Node | undefined = rule.parent ?? undefined; p; p = p.parent ?? undefined) {
        if (p.type === 'atrule' && /keyframes$/i.test((p as AtRule).name)) return
      }
      const selectors = splitSelectors(rule.selector)
        .map((s) => scopeSelector(s))
        .filter((s): s is string => s !== null)
      if (selectors.length > 0) rule.selector = [...new Set(selectors)].join(',\n')
      else rule.remove()
    },
  }
}
