import type { MountContext } from '@/platform/contract'
import { flushPromises } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { contractVersion, mount } from './embed'

vi.mock('@/api/project', () => ({ listProjects: vi.fn().mockResolvedValue([]) }))

const ctx: MountContext = {
  routerBase: '/index/',
  apiBase: '/api/index',
  user: { name: 'Ada', roles: [], projects: ['schleiermacher'] },
  onUnauthorized: () => {},
}

describe('embed', () => {
  it('implements the platform contract', () => {
    expect(contractVersion).toBe(1)
    expect(typeof mount).toBe('function')
  })

  it('mounts into el and leaves nothing behind on unmount', async () => {
    const el = document.createElement('div')
    document.body.append(el)
    const unmount = mount(el, ctx)
    await flushPromises()

    const root = el.querySelector('.index-root')
    expect(root).not.toBeNull()
    expect(root!.querySelector('.index-toolbar')).not.toBeNull()
    expect(root!.querySelector('.index-overlays')).not.toBeNull()
    expect(document.querySelector('#index-vuetify-theme')).not.toBeNull()

    unmount()
    expect(el.childElementCount).toBe(0)
    expect(document.querySelector('#index-vuetify-theme')).toBeNull()
    expect(document.documentElement.className).toBe('')
    el.remove()
  })
})
