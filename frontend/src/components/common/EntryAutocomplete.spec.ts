import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listEntryOptions } from '@/api/entry'
import EntryAutocomplete from './EntryAutocomplete.vue'

vi.mock('@/api/entry', () => ({
  listEntryOptions: vi.fn(),
}))

beforeEach(() => {
  vi.clearAllMocks()
  vi.useFakeTimers()
})

describe('EntryAutocomplete', () => {
  it('loads options for (project, entryType) on mount, with no query', async () => {
    vi.mocked(listEntryOptions).mockResolvedValue([{ id: 1, label: 'Bülow' }])
    mount(EntryAutocomplete, { props: { project: 'schleiermacher', entryType: 'group' } })
    await flushPromises()
    expect(listEntryOptions).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', { entry_type: 'group', q: undefined })
  })

  it('debounces search input before querying again', async () => {
    vi.mocked(listEntryOptions).mockResolvedValue([])
    const wrapper = mount(EntryAutocomplete, { props: { project: 'schleiermacher', entryType: 'group' } })
    await flushPromises()
    vi.mocked(listEntryOptions).mockClear()

    const input = wrapper.find('input')
    await input.setValue('Bü')
    await input.setValue('Bül')
    expect(listEntryOptions).not.toHaveBeenCalled() // debounce not elapsed yet

    await vi.advanceTimersByTimeAsync(250)
    await flushPromises()
    expect(listEntryOptions).toHaveBeenCalledTimes(1)
    expect(listEntryOptions).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', { entry_type: 'group', q: 'Bül' })
  })

  it('re-queries when project or entryType changes', async () => {
    vi.mocked(listEntryOptions).mockResolvedValue([])
    const wrapper = mount(EntryAutocomplete, { props: { project: 'schleiermacher', entryType: 'group' } })
    await flushPromises()
    vi.mocked(listEntryOptions).mockClear()

    await wrapper.setProps({ entryType: 'person' })
    await flushPromises()
    expect(listEntryOptions).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', { entry_type: 'person', q: undefined })
  })

  it('emits update:modelValue on selection', async () => {
    vi.mocked(listEntryOptions).mockResolvedValue([{ id: 42, label: 'Bülow' }])
    const wrapper = mount(EntryAutocomplete, {
      props: { project: 'schleiermacher', entryType: 'group', modelValue: null },
    })
    await flushPromises()

    await wrapper.getComponent({ name: 'VAutocomplete' }).vm.$emit('update:modelValue', 42)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([42])
  })
})
