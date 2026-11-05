import { flushPromises, mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { createMemoryHistory, createRouter } from 'vue-router'
import App from './App.vue'

vi.mock('@/api/project', () => ({
  listProjects: vi.fn().mockResolvedValue([]),
}))

const Empty = { render: () => null }

async function mountApp() {
  const router = createRouter({
    history: createMemoryHistory(),
    routes: [{ path: '/', name: 'projects', component: Empty }],
  })
  await router.push('/')
  const wrapper = mount(App, { global: { plugins: [router] } })
  await flushPromises()
  return wrapper
}

describe('App', () => {
  // ediarum-platform docs/integrating-an-app.md, 3.10: the app's header shows
  // the platform controls, so the platform hides its own top bar
  it('shows the platform controls at both ends of its toolbar', async () => {
    const wrapper = await mountApp()
    const toolbar = wrapper.get('.index-toolbar .v-toolbar__content').element
    const controls = Array.from(toolbar.children).map((child) => child.tagName.toLowerCase())

    expect(controls[0]).toBe('ediarum-home')
    expect(controls.at(-1)).toBe('ediarum-user-menu')
    wrapper.unmount()
  })
})
