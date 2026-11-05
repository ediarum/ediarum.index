import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listIngestRuns } from '@/api/ingestRun'
import IngestRunsList from './IngestRunsList.vue'

vi.mock('@/api/ingestRun', () => ({
  listIngestRuns: vi.fn(),
}))

const runs = [
  {
    id: 1,
    project: 'leibniz_v',
    started_at: '2026-01-01T00:00:00',
    finished_at: '2026-01-01T00:01:00',
    status: 'ok' as const,
    created: 2,
    updated: 1,
    unchanged: 5,
    problems: [],
  },
  {
    id: 2,
    project: 'mop',
    started_at: '2026-01-02T00:00:00',
    finished_at: '2026-01-02T00:01:00',
    status: 'failed' as const,
    created: 0,
    updated: 0,
    unchanged: 0,
    problems: [{ fname: 'a.xml', ext_id: 'P1', detail: 'boom', kind: 'failed' as const }],
  },
]

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listIngestRuns).mockResolvedValue(runs)
})

describe('IngestRunsList', () => {
  it('loads and displays every run', async () => {
    const wrapper = mount(IngestRunsList)
    await flushPromises()

    const text = wrapper.text()
    expect(text).toContain('leibniz_v')
    expect(text).toContain('mop')
    expect(text).toContain('ok')
    expect(text).toContain('failed')
  })

  it('opens a detail dialog with problem info on row click', async () => {
    const wrapper = mount(IngestRunsList)
    await flushPromises()

    await wrapper.find('tbody tr:last-child').trigger('click')
    await flushPromises()

    // v-dialog teleports its content to document.body, outside wrapper's own
    // subtree — same reason UsersList.spec.ts checks dialog props instead of
    // rendered text, but this dialog has no dedicated component to target
    const text = document.body.textContent ?? ''
    expect(text).toContain('a.xml')
    expect(text).toContain('boom')
  })
})
