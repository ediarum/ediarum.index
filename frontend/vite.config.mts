/// <reference types="vitest/config" />
import { readFileSync } from 'node:fs'
import { fileURLToPath, URL } from 'node:url'
import tailwindcss from '@tailwindcss/vite'
import Vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vite'
import cssInjectedByJs from 'vite-plugin-css-injected-by-js'
import Vuetify, { transformAssetUrls } from 'vite-plugin-vuetify'
import { scopeToRoot } from './build/scope-to-root'

// Built as an ediarum.platform app (ediarum-platform docs/integrating-an-app.md):
// the platform loads /apps/index/embed.js and calls its `mount` — no
// index.html. `base` is the same in dev and build, so lazy chunks and assets
// always load from this app's own container.
const LAYER_ORDER = readFileSync(new URL('src/styles/layers.css', import.meta.url), 'utf8')

export default defineConfig({
  base: '/apps/index/',
  plugins: [
    tailwindcss(),
    Vue({
      template: {
        transformAssetUrls,
        // the platform's header controls (<ediarum-home>, <ediarum-user-menu>)
        // are custom elements the platform defines before mounting
        compilerOptions: { isCustomElement: (tag) => tag.startsWith('ediarum-') },
      },
    }),
    // https://github.com/vuetifyjs/vuetify-loader/tree/master/packages/vite-plugin#readme
    Vuetify({
      autoImport: true,
      styles: {
        configFile: 'src/styles/settings.scss',
      },
    }),
    // a JS entry doesn't load its extracted CSS: inject it when embed.js runs —
    // led by the cascade-layer order (a file of bare `@layer x;` statements
    // doesn't survive bundling on its own), so Tailwind's reset stays below
    // Vuetify whatever order the chunks' CSS ends up in
    cssInjectedByJs({
      styleId: 'index-styles',
      preRenderCSSCode: (css) => LAYER_ORDER + css,
    }),
  ],
  css: { postcss: { plugins: [scopeToRoot()] } },
  build: {
    rolldownOptions: {
      input: 'src/embed.ts',
      // keep the entry's `mount` / `contractVersion` exports
      preserveEntrySignatures: 'exports-only',
      output: {
        entryFileNames: 'embed.js',
        chunkFileNames: 'assets/[name]-[hash].js',
        assetFileNames: 'assets/[name]-[hash][extname]',
      },
    },
  },
  define: { 'process.env': {} },
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('src', import.meta.url)),
    },
    extensions: ['.js', '.json', '.jsx', '.mjs', '.ts', '.tsx', '.vue'],
  },
  // `npm run dev`: the platform's dev server proxies /apps/index/ here
  // (EDIARUM_DEV_BUNDLES=index=http://localhost:5174)
  server: {
    port: 5174,
    strictPort: true,
  },
  // Vitest — unit / component tests. `npm run test`
  test: {
    environment: 'happy-dom',
    globals: true,
    setupFiles: ['./tests/setup.ts'],
    include: ['src/**/*.{test,spec}.ts', 'build/**/*.spec.ts'],
    exclude: ['**/node_modules/**', '**/dist/**'],
    server: { deps: { inline: ['vuetify'] } },
  },
})
