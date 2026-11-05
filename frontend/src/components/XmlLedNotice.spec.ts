import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import XmlLedNotice from './XmlLedNotice.vue'

describe('XmlLedNotice', () => {
  it('says that changes here do not reach the XML', () => {
    const text = mount(XmlLedNotice).text()
    expect(text).toContain('maintained in XML')
    expect(text).toContain("don't reach the XML files")
  })
})
