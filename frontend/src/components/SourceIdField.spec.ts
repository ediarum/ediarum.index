import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SourceIdField from './SourceIdField.vue'

function input(wrapper: ReturnType<typeof mount>) {
  return wrapper.find('input')
}
async function toggleLock(wrapper: ReturnType<typeof mount>) {
  await wrapper.find('.v-field__append-inner .v-icon').trigger('click')
}

describe('SourceIdField', () => {
  it('is left to ediarum.id when creating and the backend assigns ids', () => {
    const wrapper = mount(SourceIdField, { props: { creating: true, assignsIds: true, modelValue: '' } })
    expect(input(wrapper).attributes('readonly')).toBeDefined()
    expect(wrapper.text()).toContain('Assigned by ediarum.id when you save.')
  })

  it('can be unlocked for an existing id, and locking again empties it', async () => {
    const wrapper = mount(SourceIdField, { props: { creating: true, assignsIds: true, modelValue: '' } })
    await toggleLock(wrapper)
    expect(input(wrapper).attributes('readonly')).toBeUndefined()
    expect(wrapper.text()).toContain('not checked against ediarum.id')

    await wrapper.setProps({ modelValue: 'H0000001' })
    await toggleLock(wrapper)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([''])
  })

  it('is a plain field when creating without ediarum.id', () => {
    const wrapper = mount(SourceIdField, { props: { creating: true, assignsIds: false, modelValue: '' } })
    expect(input(wrapper).attributes('readonly')).toBeUndefined()
    expect(wrapper.find('.v-field__append-inner .v-icon').exists()).toBe(false)
  })

  it('protects the id of a saved entry: texts reference it', async () => {
    const wrapper = mount(SourceIdField, {
      props: { creating: false, assignsIds: true, original: 'H0012069', modelValue: 'H0012069' },
    })
    expect(input(wrapper).attributes('readonly')).toBeDefined()
    expect(wrapper.text()).toContain('Referenced by the texts')

    await toggleLock(wrapper)
    expect(input(wrapper).attributes('readonly')).toBeUndefined()
    expect(wrapper.text()).toContain('will no longer point to this entry')

    await wrapper.setProps({ modelValue: 'H9' })
    await toggleLock(wrapper) // locking again restores the saved id
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['H0012069'])
  })

  it('is a plain field when editing an entry without an id', () => {
    const wrapper = mount(SourceIdField, {
      props: { creating: false, assignsIds: true, original: null, modelValue: '' },
    })
    expect(input(wrapper).attributes('readonly')).toBeUndefined()
  })
})
