/**
 * Vuetify, created per mount and confined to the app's root element
 * (ediarum-platform docs/integrating-an-app.md, 3.6):
 *
 * - the theme's CSS variables apply to `.index-root`, not `:root`, from a
 *   stylesheet of our own id that the unmount function removes;
 * - overlays (dialogs, menus, tooltips, snackbars, select lists) render into an
 *   element inside the root, where the scoped CSS reaches them;
 * - dialogs stay inside the app's area and don't block scrolling: that would
 *   add classes and styles to the platform's <html>.
 *
 * The theme itself is the platform's design tokens (src/theme.ts), so the app
 * looks like the platform and every other app built this way.
 */

import { createVuetify } from 'vuetify'
import { platformTheme, THEME_NAME } from '@/theme'
import '@mdi/font/css/materialdesignicons.css'
import 'vuetify/styles'

export const ROOT_CLASS = 'index-root'
export const THEME_STYLESHEET_ID = 'index-vuetify-theme'

export function createIndexVuetify(overlayTarget: HTMLElement) {
  const overlay = { attach: overlayTarget }
  return createVuetify({
    theme: {
      defaultTheme: THEME_NAME,
      // the `bg-*` / `text-*` classes behind the `color` prop (scoped to the
      // root like the rest of the theme)
      utilities: true,
      themes: { [THEME_NAME]: platformTheme() },
      scope: `.${ROOT_CLASS}`,
      stylesheetId: THEME_STYLESHEET_ID,
    },
    defaults: {
      VOverlay: overlay,
      VMenu: overlay,
      VTooltip: overlay,
      VSnackbar: overlay,
      // confined to the app's area (.index-root is positioned): the scrim
      // doesn't cover the platform's top bar
      VDialog: { ...overlay, contained: true, scrollStrategy: 'none' },
      VCard: { border: true, flat: true },
      VToolbar: { flat: true },
      VTextField: { variant: 'outlined', density: 'comfortable' },
      VTextarea: { variant: 'outlined', density: 'comfortable' },
      VSelect: { variant: 'outlined', density: 'comfortable' },
      VBtn: { class: 'text-none' },
    },
    display: {
      mobileBreakpoint: 'md',
      thresholds: {
        xs: 0,
        sm: 600,
        md: 840,
        lg: 1145,
        xl: 1545,
        xxl: 2138,
      },
    },
  })
}
