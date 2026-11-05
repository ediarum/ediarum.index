import type { Entry } from '@/api/entry'
import type * as EntryApi from '@/api/entry'
import type { Relation } from '@/api/relation'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { listEntryOptions, listEntryTypes } from '@/api/entry'
import { createRelation, deleteRelation, listRelations } from '@/api/relation'
import EntryRelations from './EntryRelations.vue'

vi.mock('@/api/relation', () => ({
  listRelations: vi.fn(),
  createRelation: vi.fn(),
  deleteRelation: vi.fn(),
}))
vi.mock('@/api/entry', async (importOriginal) => ({
  ...(await importOriginal<typeof EntryApi>()),
  listEntryTypes: vi.fn(),
  listEntryOptions: vi.fn(),
}))

const entry: Entry = {
  id: 1,
  project_name: 'schleiermacher',
  entry_type: 'person',
  label: 'A',
  source_id: 'S1',
  data: {},
}

function relation(over: Partial<Relation>): Relation {
  return {
    id: 1,
    subject_id: 1,
    predicate: 'member_of',
    object_id: 2,
    subject_label: 'A',
    object_label: 'B',
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listEntryTypes).mockResolvedValue([
    { name: 'person', label: 'Person', description: null },
    { name: 'group', label: 'Group', description: null },
  ])
  vi.mocked(listEntryOptions).mockResolvedValue([{ id: 99, label: 'Bülow' }])
  vi.mocked(listRelations).mockResolvedValue([])
})

describe('EntryRelations', () => {
  it('shows the empty state when there are no relations', async () => {
    vi.mocked(listRelations).mockResolvedValue([])
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('No relations.')
  })

  it('renders outgoing relations with the object label, and incoming with the subject label', async () => {
    vi.mocked(listRelations).mockImplementation((_http, _project, params = {}) => {
      if (params.subject_id === entry.id) return Promise.resolve([relation({ id: 10, object_label: 'Bülow' })])
      if (params.object_id === entry.id) return Promise.resolve([relation({ id: 11, subject_label: 'C' })])
      return Promise.resolve([])
    })
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('member_of: Bülow')
    expect(wrapper.text()).toContain('member_of: C')
  })

  it('words an incoming mention from this entry\'s side', async () => {
    vi.mocked(listRelations).mockImplementation((_http, _project, params = {}) => {
      if (params.subject_id === entry.id)
        return Promise.resolve([relation({ id: 10, predicate: 'mentions', object_label: 'Bülow' })])
      if (params.object_id === entry.id)
        return Promise.resolve([relation({ id: 11, predicate: 'mentions', subject_label: 'C' })])
      return Promise.resolve([])
    })
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()
    expect(wrapper.text()).toContain('mentions: Bülow')
    expect(wrapper.text()).toContain('mentioned by: C')
    expect(wrapper.text()).not.toContain('mentions: C')
  })

  it('deleting a relation calls deleteRelation and refetches', async () => {
    vi.mocked(listRelations).mockImplementation((_http, _project, params = {}) =>
      Promise.resolve(
        params.subject_id === entry.id ? [relation({ id: 10 })] : [],
      ),
    )
    vi.mocked(deleteRelation).mockResolvedValue({ ok: true })
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()
    vi.mocked(listRelations).mockClear()

    await wrapper.find('.mdi-delete-outline').trigger('click')
    await flushPromises()

    expect(deleteRelation).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', 10)
    expect(listRelations).toHaveBeenCalled() // refetched
  })

  it('hides the delete button when canEdit is false', async () => {
    vi.mocked(listRelations).mockImplementation((_http, _project, params = {}) =>
      Promise.resolve(params.subject_id === entry.id ? [relation({ id: 10 })] : []),
    )
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: false } })
    await flushPromises()
    expect(wrapper.find('.mdi-delete-outline').exists()).toBe(false)
  })

  it('adds an outgoing relation: this entry is the subject', async () => {
    vi.mocked(createRelation).mockResolvedValue({ id: 5, subject_id: 1, predicate: 'member_of', object_id: 99 })
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()

    await wrapper.find('button').trigger('click') // "Add relation" (only button before the form opens)
    await flushPromises()
    await wrapper.getComponent({ name: 'EntryAutocomplete' }).vm.$emit('update:modelValue', 99)
    await wrapper.findAll('button').find((b) => b.text() === 'Add')?.trigger('click')
    await flushPromises()

    expect(createRelation).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', { subject_id: 1, predicate: 'member_of', object_id: 99 })
  })

  it('adds an incoming relation when direction is flipped: this entry is the object', async () => {
    vi.mocked(createRelation).mockResolvedValue({ id: 5, subject_id: 99, predicate: 'member_of', object_id: 1 })
    const wrapper = mount(EntryRelations, { props: { entry, canEdit: true } })
    await flushPromises()

    await wrapper.find('button').trigger('click') // open the form
    await flushPromises()
    const targetToggle = wrapper.findAll('button').find((b) => b.text().includes('Target'))
    await targetToggle?.trigger('click')
    await wrapper.getComponent({ name: 'EntryAutocomplete' }).vm.$emit('update:modelValue', 99)
    await wrapper.findAll('button').find((b) => b.text() === 'Add')?.trigger('click')
    await flushPromises()

    expect(createRelation).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', { subject_id: 99, predicate: 'member_of', object_id: 1 })
  })
})
