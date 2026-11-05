import { mount } from '@vue/test-utils'
import { describe, expect, it } from 'vitest'
import { defineComponent, h, nextTick, ref } from 'vue'
import DataListView from './DataListView.vue'

// A dynamically-named `item.<key>` slot that only starts existing on a
// LATER render (not at mount) must still get forwarded to the underlying
// VDataTable — this is exactly EntriesList.vue's real shape: its headers
// (and so its per-field `item.data.<field>` slots) come from a project's
// schema, fetched asynchronously via getSchema() after the initial mount.
// A regression here previously fell back to Vuetify's own default cell
// rendering for the unforwarded column, which dumps a repeatable field's
// raw array/object value as JSON instead of going through formatFieldValue.
const schema = ref<string[]>([])

const Harness = defineComponent({
  components: { DataListView },
  setup() {
    const items = [{ label: 'Item', data: { tags: [{ value: 'a repeatable value' }] } }]
    return () =>
      h(
        DataListView,
        {
          title: 'Items',
          headers: [
            { title: 'Label', key: 'label' },
            ...schema.value.map((name) => ({ title: name, key: `data.${name}` })),
          ],
          items,
        },
        Object.fromEntries(
          schema.value.map((name) => [
            `item.data.${name}`,
            ({ item }: { item: { data: Record<string, { value: string }[]> } }) =>
              h('span', { class: 'formatted' }, item.data[name].map((v) => v.value).join('; ')),
          ]),
        ),
      )
  },
})

describe('DataListView', () => {
  it('forwards a dynamic item.<key> slot that only appears after mount', async () => {
    schema.value = []
    const wrapper = mount(Harness)
    await nextTick()

    schema.value = ['tags'] // arrives later, like a resolved getSchema() call
    await nextTick()
    await nextTick()

    expect(wrapper.find('.formatted').exists()).toBe(true)
    expect(wrapper.text()).toContain('a repeatable value')
    expect(wrapper.text()).not.toContain('"value"') // the JSON-dump symptom this guards against
    wrapper.unmount()
  })
})
