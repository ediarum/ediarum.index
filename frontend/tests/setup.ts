import { config } from '@vue/test-utils'
import { createVuetify } from 'vuetify'
import * as components from 'vuetify/components'
import * as directives from 'vuetify/directives'
import { APP_CONTEXT, createAppContext } from '@/context'

// happy-dom lacks a couple of APIs Vuetify touches while mounting
globalThis.ResizeObserver ??= class {
  observe() {}
  unobserve() {}
  disconnect() {}
} as unknown as typeof ResizeObserver

// VOverlay's location strategy (v-dialog, v-menu, v-select's popup, …) reads
// this to position itself; happy-dom doesn't implement it at all
globalThis.visualViewport ??= {
  width: 1024,
  height: 768,
  offsetLeft: 0,
  offsetTop: 0,
  pageLeft: 0,
  pageTop: 0,
  scale: 1,
  addEventListener() {},
  removeEventListener() {},
  dispatchEvent: () => false,
} as unknown as VisualViewport

if (!window.matchMedia) {
  window.matchMedia = ((query: string) => ({
    matches: false,
    media: query,
    onchange: null,
    addEventListener() {},
    removeEventListener() {},
    addListener() {},
    removeListener() {},
    dispatchEvent: () => false,
  })) as unknown as typeof window.matchMedia
}

// every mounted component gets a Vuetify instance
config.global.plugins = [createVuetify({ components, directives })]

// …and the per-mount app context embed.ts provides (API client, user, search);
// tests mock the api/* functions, so the client itself is never used
config.global.provide = {
  [APP_CONTEXT as symbol]: createAppContext({
    routerBase: '/index/',
    apiBase: '/api/index',
    user: { name: 'Test Editor', roles: [], projects: ['schleiermacher'] },
    onUnauthorized: () => {},
  }),
}
