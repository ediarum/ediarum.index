import type { Comment } from '@/api/comment'
import type { Entry, FieldSchema } from '@/api/entry'
import { flushPromises, mount } from '@vue/test-utils'
import { beforeEach, describe, expect, it, vi } from 'vitest'
import { createComment, deleteComment, listComments } from '@/api/comment'
import EntryComments from './EntryComments.vue'

vi.mock('@/api/comment', () => ({
  listComments: vi.fn(),
  createComment: vi.fn(),
  deleteComment: vi.fn(),
}))

const entry: Entry = {
  id: 1,
  project_name: 'schleiermacher',
  entry_type: 'person',
  label: 'A',
  source_id: 'S1',
  data: {},
}

const schema: FieldSchema[] = [
  {
    name: 'surname',
    label: 'Surname',
    type: 'text',
    required: false,
    options: null,
    ref_type: null,
    repeatable: false,
    qualifier: null,
    qualifier_options: null,
    multiline: false,
  },
]

function comment(over: Partial<Comment>): Comment {
  return {
    id: 1,
    entry_id: 1,
    text: 'a remark',
    author: 'fkoch',
    created_at: '2024-01-24T16:29:10',
    source: 'ingested',
    start_field: null,
    end_field: null,
    ...over,
  }
}

beforeEach(() => {
  vi.clearAllMocks()
  vi.mocked(listComments).mockResolvedValue([])
})

describe('EntryComments', () => {
  it('shows the empty state when there are no comments', async () => {
    const wrapper = mount(EntryComments, { props: { entry, canEdit: true, schema } })
    await flushPromises()
    expect(wrapper.text()).toContain('No comments.')
  })

  it('renders a comment with its author and field anchor', async () => {
    vi.mocked(listComments).mockResolvedValue([
      comment({ text: 'Schreibweise unsicher', author: 'fkoch', start_field: 'surname', end_field: 'surname' }),
    ])
    const wrapper = mount(EntryComments, { props: { entry, canEdit: true, schema } })
    await flushPromises()
    expect(wrapper.text()).toContain('Schreibweise unsicher')
    expect(wrapper.text()).toContain('fkoch')
    expect(wrapper.text()).toContain('Surname')
  })

  it('deleting a comment calls deleteComment and refetches', async () => {
    vi.mocked(listComments).mockResolvedValue([comment({ id: 10 })])
    vi.mocked(deleteComment).mockResolvedValue({ ok: true })
    const wrapper = mount(EntryComments, { props: { entry, canEdit: true, schema } })
    await flushPromises()
    vi.mocked(listComments).mockClear()

    await wrapper.find('.mdi-delete-outline').trigger('click')
    await flushPromises()

    expect(deleteComment).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', 10)
    expect(listComments).toHaveBeenCalled() // refetched
  })

  it('hides the delete button when canEdit is false', async () => {
    vi.mocked(listComments).mockResolvedValue([comment({ id: 10 })])
    const wrapper = mount(EntryComments, { props: { entry, canEdit: false, schema } })
    await flushPromises()
    expect(wrapper.find('.mdi-delete-outline').exists()).toBe(false)
  })

  it('adds a general comment with no field anchor by default', async () => {
    vi.mocked(createComment).mockResolvedValue(
      comment({ id: 5, text: 'looks wrong', author: 'editor', source: 'app' }),
    )
    const wrapper = mount(EntryComments, { props: { entry, canEdit: true, schema } })
    await flushPromises()

    await wrapper.find('button').trigger('click') // "Add comment"
    await flushPromises()
    await wrapper.find('textarea').setValue('looks wrong')
    await wrapper.findAll('button').find((b) => b.text() === 'Add')?.trigger('click')
    await flushPromises()

    expect(createComment).toHaveBeenCalledWith(expect.anything(), 'schleiermacher', {
      entry_id: 1,
      text: 'looks wrong',
      start_field: null,
      end_field: null,
    })
  })
})
