import type { FieldSchema } from '@/api/entry'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import RepeatableField from './RepeatableField.vue'

const field: FieldSchema = {
  name: 'forename',
  label: 'Forename',
  type: 'text',
  required: false,
  options: null,
  ref_type: null,
  repeatable: true,
  qualifier: 'lang',
  qualifier_options: ['deu', 'grc'],
  multiline: false,
}

describe('RepeatableField', () => {
  it('renders one row per value', () => {
    const wrapper = mount(RepeatableField, {
      props: { field, modelValue: [{ value: 'Johannes', lang: 'deu' }, { value: 'Ἰωάννης', lang: 'grc' }] },
    })
    expect(wrapper.findAll('input[type="text"]').length).toBeGreaterThanOrEqual(2)
  })

  it('adds a blank row', async () => {
    const wrapper = mount(RepeatableField, { props: { field, modelValue: [] } })
    await wrapper.get('button.v-btn').trigger('click') // the "Add" button
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[{ value: '' }]])
  })

  it('removes a row', async () => {
    const wrapper = mount(RepeatableField, {
      props: { field, modelValue: [{ value: 'a', lang: 'deu' }, { value: 'b', lang: 'grc' }] },
    })
    await wrapper.get('.mdi-close').trigger('click')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[{ value: 'b', lang: 'grc' }]])
  })

  it('patches a value in place', async () => {
    const wrapper = mount(RepeatableField, {
      props: { field, modelValue: [{ value: 'a', lang: 'deu' }] },
    })
    await wrapper.get('input[type="text"]').setValue('Johannes')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([[{ value: 'Johannes', lang: 'deu' }]])
  })
})
