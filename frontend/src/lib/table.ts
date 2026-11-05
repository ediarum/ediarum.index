/** Shape of Vuetify's `v-data-table` `update:options` payload (the parts we use). */
export interface SortItem {
  key: string
  order: 'asc' | 'desc'
}

export interface TableOptions {
  page: number
  itemsPerPage: number
  sortBy: SortItem[]
}
