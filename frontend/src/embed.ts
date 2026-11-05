/**
 * The entry module the ediarum.platform loads (`/apps/index/embed.js`): it
 * mounts the app into the platform's content area — its toolbar hosts the
 * platform's header controls (App.vue) — and unmounts it again
 * (src/platform/contract.ts; ediarum-platform docs/integrating-an-app.md).
 *
 * Everything is created per mount — app, router, Vuetify, API client, search
 * state — and the unmount function removes all of it: requests in flight, the
 * router's popstate listener, the colour-scheme listener, the theme
 * stylesheet, the DOM.
 */

import type {  Mount } from '@/platform/contract'
import { createApp } from 'vue'
import { createRouter, createWebHistory } from 'vue-router'
import App from '@/App.vue'
import { APP_CONTEXT, createAppContext } from '@/context'
import { routes } from '@/routes'
import { platformTheme, THEME_NAME, watchColorScheme } from '@/theme'
import { createIndexVuetify, ROOT_CLASS, THEME_STYLESHEET_ID } from '@/vuetify'

// Tailwind, our overrides — the cascade-layer order (styles/layers.css) leads
// the injected CSS, see vite.config.mts. No fonts: the app uses the platform's.
import '@/styles/tailwind.css'
import '@/styles/main.scss'



export const mount: Mount = (el, ctx) => {
  // one root for the app and everything it renders outside its component tree
  const root = document.createElement('div')
  root.className = ROOT_CLASS
  const appEl = document.createElement('div')
  appEl.className = 'index-app'
  const overlays = document.createElement('div')
  overlays.className = 'index-overlays'
  root.append(appEl, overlays)
  el.append(root)

  const context = createAppContext(ctx)
  const router = createRouter({ history: createWebHistory(ctx.routerBase), routes })
  const vuetify = createIndexVuetify(overlays)
  const app = createApp(App)
  app.provide(APP_CONTEXT, context)
  app.use(vuetify)
  app.use(router)
  app.mount(appEl)
  // the platform's tokens change with the system colour scheme; follow them
  const stopWatching = watchColorScheme((dark) => {
    const theme = vuetify.theme.themes.value[THEME_NAME]!
    const next = platformTheme(dark)
    theme.dark = next.dark
    Object.assign(theme.colors, next.colors)
    Object.assign(theme.variables, next.variables)
  })

  return () => {
    stopWatching()
    context.dispose() // abort requests in flight
    app.unmount()
    vuetify.unmount()
    router.options.history.destroy() // removes the router's popstate listener
    document.querySelector(`#${THEME_STYLESHEET_ID}`)?.remove()
    root.remove()
  }
}

export {CONTRACT_VERSION as contractVersion} from '@/platform/contract'