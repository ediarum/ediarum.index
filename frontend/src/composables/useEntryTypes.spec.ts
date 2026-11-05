import { flushPromises } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { ref } from 'vue'
import { listEntryTypes, listProjectEntryTypes } from '@/api/entry'
import { useEntryTypes } from './useEntryTypes'

vi.mock('@/context', () => ({ useHttp: () => ({}) }))
vi.mock('@/api/entry', () => ({
  listEntryTypes: vi.fn(),
  listProjectEntryTypes: vi.fn(),
}))

const t = (name: string) => ({ name, label: name, description: null })

beforeEach(() => {
  vi.mocked(listEntryTypes).mockReset()
  vi.mocked(listProjectEntryTypes).mockReset()
})

describe('useEntryTypes', () => {
  it("loads the project's types and reloads when the project changes", async () => {
    vi.mocked(listProjectEntryTypes).mockImplementation(async (_http, project) =>
      project === 'avhr' ? [t('person'), t('place')] : [t('person'), t('glossary')],
    )
    const project = ref('avhr')
    const { entryTypes } = useEntryTypes(project)
    await flushPromises()
    expect(entryTypes.value.map((x) => x.name)).toEqual(['person', 'place'])

    project.value = 'schleiermacher'
    await flushPromises()
    expect(entryTypes.value.map((x) => x.name)).toEqual(['person', 'glossary'])
    expect(listEntryTypes).not.toHaveBeenCalled()
  })

  it('loads every type without a project', async () => {
    vi.mocked(listEntryTypes).mockResolvedValue([t('person')])
    const { entryTypes } = useEntryTypes()
    await flushPromises()
    expect(entryTypes.value.map((x) => x.name)).toEqual(['person'])
  })

  it("ignores a slow answer for a project that's no longer current", async () => {
    let answerOld: (v: ReturnType<typeof t>[]) => void = () => {}
    vi.mocked(listProjectEntryTypes)
      .mockImplementationOnce(() => new Promise((resolve) => (answerOld = resolve)))
      .mockResolvedValueOnce([t('person')])
    const project = ref('old')
    const { entryTypes } = useEntryTypes(project)
    project.value = 'new'
    await flushPromises()
    answerOld([t('glossary')])
    await flushPromises()
    expect(entryTypes.value.map((x) => x.name)).toEqual(['person'])
  })
})
