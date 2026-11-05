<!--
  Reusable list scaffold: page container, error alert, and a data table with a
  toolbar (title + primary action). Any `item.<key>` slot is forwarded to the
  table; a `toolbar-extension` slot (e.g. tabs) renders as the toolbar extension.

  Pass `server-items-length` to switch to a server-driven table: it then emits
  `update:options` on every page / sort / page-size change instead of paginating
  and sorting client-side. Emits `create` and `row-click`.

  `must-sort`: every column click-cycles asc ↔ desc only, never to "unsorted".
  Without it, Vuetify's 3rd click proposes `sortBy: []`; a server table has no
  natural "no sort" (it always orders by something), so callers would have to
  invent a fallback column for that state — which then hijacks *every* other
  column's 3rd click too (their "unsorted" jumps to that fallback instead of
  back to their own ascending state), a 2-click cycle for the fallback column
  and a surprising 3-click one for everything else.
-->
<template>
  <v-container>
    <v-alert v-if="error" class="mb-4" type="error" variant="tonal">{{ error }}</v-alert>

    <component
      :is="server ? VDataTableServer : VDataTable"
      :headers="headers"
      hover
      :item-value="itemValue"
      :items="items"
      :items-length="serverItemsLength"
      :items-per-page="itemsPerPage"
      :items-per-page-options="[10, 25, 50, 100]"
      :loading="loading"
      must-sort
      :page="page"
      :sort-by="sortBy"
      @click:row="onRowClick"
      @update:options="emit('update:options', $event)"
    >
      <template #top>
        <v-toolbar flat>
          <v-toolbar-title>{{ title }}</v-toolbar-title>
          <v-spacer />

          <slot name="actions">
            <v-btn
              v-if="createLabel"
              color="primary"
              prepend-icon="mdi-plus"
              @click="emit('create')"
            >
              {{ createLabel }}
            </v-btn>
          </slot>

          <template v-if="hasExtension" #extension>
            <slot name="toolbar-extension" />
          </template>
        </v-toolbar>
      </template>

      <template v-for="name in itemSlots" :key="name" #[name]="slotProps">
        <slot :name="name" v-bind="slotProps" />
      </template>
    </component>
  </v-container>
</template>

<script lang="ts" setup generic="T extends Record<string, unknown>">
import type { SortItem, TableOptions } from '@/lib/table'
import { computed, useSlots } from 'vue'
import { VDataTable, VDataTableServer } from 'vuetify/components'

const props = withDefaults(
  defineProps<{
    title: string
    headers: readonly Record<string, unknown>[]
    items: readonly T[]
    loading?: boolean
    error?: string | null
    createLabel?: string
    itemsPerPage?: number
    itemValue?: string
    serverItemsLength?: number
    page?: number
    sortBy?: readonly SortItem[]
  }>(),
  { loading: false, error: null, itemsPerPage: 25, itemValue: 'id' },
)

const emit = defineEmits<{
  create: []
  'row-click': [item: T]
  'update:options': [options: TableOptions]
}>()

const server = computed(() => props.serverItemsLength !== undefined)

const slots = useSlots()
// useSlots() returns a plain object Vue mutates in place, not a reactive
// one — reading Object.keys(slots) inside a computed with no other
// dependency makes it cache forever from whatever slots existed at its
// first evaluation. A caller whose dynamically-named `item.data.<field>`
// slots depend on an async-loaded schema (e.g. EntriesList.vue, whose
// headers/slots for a project's fields only exist once GET /schema/...
// resolves) would then never get those columns forwarded — Vuetify falls
// back to its own default rendering, which dumps a repeatable field's raw
// array/object value as JSON instead of going through formatFieldValue.
// `headers` is a genuinely reactive prop that changes at exactly the same
// time the caller's slot set does, so reading it (even unused) gives this
// computed a real dependency to re-run on, and `slots` is then read at the
// right moment instead of only once.
const itemSlots = computed(() => {
  void props.headers
  return Object.keys(slots).filter((n) => n.startsWith('item.'))
})
const hasExtension = computed(() => !!slots['toolbar-extension'])

function onRowClick(_event: Event, ctx: { item: T }) {
  emit('row-click', ctx.item)
}
</script>

<style scoped>
/* Every caller ends `headers` with an unlabelled `actions` column (edit /
   delete). On a wide table (many schema columns) that column scrolls off to
   the right, and — because the table's own horizontal scrollbar sits at the
   *bottom* of the table, not the viewport — reaching it means scrolling all
   the way down a long list first. Pinning the last column avoids that: the
   actions stay on-screen regardless of horizontal (or vertical) scroll. */
:deep(.v-table__wrapper) {
  overflow-x: auto;
}
:deep(th:last-child),
:deep(td:last-child) {
  position: sticky;
  right: 0;
  background: rgb(var(--v-theme-surface));
  box-shadow: -4px 0 4px -4px rgba(0, 0, 0, 0.2);
}
:deep(th:last-child),
:deep(tr:hover td:last-child) {
  background: rgb(var(--v-theme-surface-light));
}
</style>
