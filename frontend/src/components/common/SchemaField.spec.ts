import type { FieldSchema } from '@/api/entry'
import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import SchemaField from './SchemaField.vue'

function field(over: Partial<FieldSchema>): FieldSchema {
  return {
    name: 'x',
    label: 'X',
    type: 'text',
    required: false,
    options: null,
    ref_type: null,
    repeatable: false,
    qualifier: null,
    qualifier_options: null,
    multiline: false,
    ...over,
  }
}

describe('SchemaField', () => {
  it('renders a checkbox and models a boolean', async () => {
    const wrapper = mount(SchemaField, {
      props: { field: field({ type: 'checkbox' }), modelValue: null },
    })
    const box = wrapper.find('input[type="checkbox"]')
    expect(box.exists()).toBe(true)

    await box.setValue(true)
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual([true])
  })

  it('renders a number input for number fields', () => {
    const wrapper = mount(SchemaField, {
      props: { field: field({ type: 'number', label: 'Birthyear' }), modelValue: '1646' },
    })
    expect(wrapper.find('input[type="number"]').exists()).toBe(true)
  })

  it('renders a plain text input by default and models a string', async () => {
    const wrapper = mount(SchemaField, {
      props: { field: field({ label: 'Surname' }), modelValue: '' },
    })
    await wrapper.find('input').setValue('Leibniz')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['Leibniz'])
  })

  it('renders a textarea for multiline fields and models a string', async () => {
    const wrapper = mount(SchemaField, {
      props: { field: field({ name: 'note', label: 'Note', multiline: true }), modelValue: '' },
    })
    expect(wrapper.find('input').exists()).toBe(false)
    await wrapper.find('textarea').setValue('line one\nline two')
    expect(wrapper.emitted('update:modelValue')?.at(-1)).toEqual(['line one\nline two'])
  })

  it('shows the reference hint for reference fields', () => {
    const wrapper = mount(SchemaField, {
      props: {
        field: field({ type: 'reference', ref_type: 'place', label: 'Birthplace' }),
        modelValue: '',
      },
    })
    expect(wrapper.text()).toContain('reference to a place entry')
  })

  it('renders a RepeatableField for repeatable fields', () => {
    const wrapper = mount(SchemaField, {
      props: {
        field: field({ name: 'idno', label: 'Identifiers', repeatable: true, qualifier: 'type' }),
        modelValue: [{ value: '118557831', type: 'GND' }],
      },
    })
    expect(wrapper.text()).toContain('Add')
    expect((wrapper.find('input').element as HTMLInputElement).value).toBe('118557831')
  })
})
