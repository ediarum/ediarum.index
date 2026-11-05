/**
 * The app's look comes from the platform: its design tokens (`--ep-*` custom
 * properties on the platform's `:root`, ediarum-platform src/styles.css) are
 * read when the app mounts and turned into the Vuetify theme. So every app
 * that does this looks like the platform and like each other, and follows a
 * change of the tokens without a rebuild — see docs/concepts/ui-design.md.
 *
 * The platform switches its tokens with `prefers-color-scheme`; so does the
 * app: `watchColorScheme` re-reads them when the scheme changes.
 */

/** The platform's light tokens — used where the page doesn't define one
 *  (tests, a token the platform hasn't got). */
const LIGHT_FALLBACK = {
  accent: '#c8221f',
  bg: '#ffffff',
  surface: '#f7f7f8',
  text: '#1f2328',
  muted: '#5f6368',
  border: '#e1e3e6',
  error: '#b3261e',
  success: '#1e6b34',
  focus: '#1a5fb4',
}

const DARK_FALLBACK: typeof LIGHT_FALLBACK = {
  accent: '#f0524f',
  bg: '#18191b',
  surface: '#222326',
  text: '#e6e6e6',
  muted: '#a3a6ab',
  border: '#36383c',
  error: '#ffb4ab',
  success: '#8fd19e',
  focus: '#8ab4f8',
}

// the platform has no warning colour; these sit between its error and accent
const WARNING = { light: '#8a5a00', dark: '#e3b341' }

export const THEME_NAME = 'platform'

export function prefersDark(): boolean {
  return typeof window.matchMedia === 'function' && window.matchMedia('(prefers-color-scheme: dark)').matches
}

/** The platform's current tokens, falling back per token. */
export function readPlatformTokens(dark = prefersDark()): typeof LIGHT_FALLBACK {
  const fallback = dark ? DARK_FALLBACK : LIGHT_FALLBACK
  const style = getComputedStyle(document.documentElement)
  // hex only: Vuetify parses theme colours itself and knows no other notation
  const token = (name: string, otherwise: string) => {
    const value = style.getPropertyValue(`--ep-color-${name}`).trim()
    return /^#(?:[\da-f]{3}){1,2}$/i.test(value) ? value : otherwise
  }
  return {
    accent: token('accent', fallback.accent),
    bg: token('bg', fallback.bg),
    surface: token('surface', fallback.surface),
    text: token('text', fallback.text),
    muted: token('muted', fallback.muted),
    border: token('border', fallback.border),
    error: token('error', fallback.error),
    success: token('success', fallback.success),
    focus: token('focus', fallback.focus),
  }
}

export interface PlatformTheme {
  dark: boolean
  colors: Record<string, string>
  variables: Record<string, string | number>
}

/** A Vuetify theme from the platform's tokens. */
export function platformTheme(dark = prefersDark()): PlatformTheme {
  const t = readPlatformTokens(dark)
  return {
    dark,
    colors: {
      'background': t.bg,
      'surface': t.bg,
      'surface-bright': t.bg,
      'surface-light': t.surface,
      'surface-variant': t.text, // tooltips, snackbars: inverted, as Vuetify intends
      'on-surface-variant': t.bg,
      'on-background': t.text,
      'on-surface': t.text,
      'primary': t.accent,
      'secondary': t.muted,
      'info': t.focus,
      'success': t.success,
      'warning': dark ? WARNING.dark : WARNING.light,
      'error': t.error,
    },
    variables: {
      'border-color': t.border,
      'border-opacity': 1,
      'high-emphasis-opacity': 1,
      'medium-emphasis-opacity': 0.72,
    },
  }
}

/** Follow the platform when the colour scheme changes; returns the function
 *  that stops following (call it on unmount). */
export function watchColorScheme(onChange: (dark: boolean) => void): () => void {
  if (typeof window.matchMedia !== 'function') return () => {}
  const query = window.matchMedia('(prefers-color-scheme: dark)')
  const listener = (event: MediaQueryListEvent) => onChange(event.matches)
  query.addEventListener('change', listener)
  return () => query.removeEventListener('change', listener)
}
