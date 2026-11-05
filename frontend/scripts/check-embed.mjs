// After `vite build`: the platform imports dist/embed.js and needs its
// `contractVersion` and `mount` exports (the bundler may drop them otherwise).
import { readFileSync } from 'node:fs'

const code = readFileSync(new URL('../dist/embed.js', import.meta.url), 'utf8')
const exported = /export\s*\{([^}]*)\}\s*(?:;\s*)?$/.exec(code.trim())?.[1] ?? ''
const names = exported.split(',').map((s) => s.trim().split(/\s+as\s+/).pop())
for (const name of ['contractVersion', 'mount']) {
  if (!names.includes(name)) {
    throw new Error(`dist/embed.js does not export ${name} (exports: ${names.join(', ') || 'none'})`)
  }
}
console.log('dist/embed.js exports contractVersion and mount')
