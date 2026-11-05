<!-- The app inside the platform's content area: its own toolbar (project,
     search, admin pages) and the routed view below, scrolling
     inside the app's area. The toolbar is the only header: it hosts the
     platform's controls (<ediarum-home> far left, <ediarum-user-menu> far
     right), so the platform hides its top bar (ediarum-platform
     docs/integrating-an-app.md, 3.10). No login or user menu of our own. -->
<template>
  <v-app class="index-shell">
    <!-- 52px = the platform's --ep-topbar-height (3.25rem), as in the other apps -->
    <v-toolbar class="index-toolbar" color="surface" height="52">
      <ediarum-home class="platform-home" />

      <v-toolbar-title
        class="app-title"
        role="button"
        tabindex="0"
        @click="goHome"
        @keyup.enter="goHome"
      >
        Index
      </v-toolbar-title>

      <v-select
        v-if="projects.length > 0"
        class="project-picker"
        density="compact"
        flat
        hide-details
        item-title="label"
        item-value="name"
        :items="projects"
        :model-value="currentProject"
        placeholder="Projekt wählen"
        single-line
        variant="solo-filled"
        @update:model-value="openProject"
      />

      <div v-if="currentProject" class="search-group">
        <v-text-field
          v-model="draft"
          class="search-term"
          clearable
          density="compact"
          flat
          hide-details
          :placeholder="`${currentFieldLabel} durchsuchen …`"
          prepend-inner-icon="mdi-magnify"
          single-line
          variant="solo-filled"
        />

        <v-menu>
          <template #activator="{ props: menu }">
            <v-btn
              v-bind="menu"
              append-icon="mdi-menu-down"
              class="search-scope"
              size="small"
              variant="text"
            >
              {{ currentFieldLabel }}
            </v-btn>
          </template>

          <v-list density="compact" min-width="180" :selected="[searchField]">
            <v-list-item
              v-for="o in searchFields"
              :key="o.value"
              :value="o.value"
              @click="searchField = o.value"
            >
              <v-list-item-title>{{ o.title }}</v-list-item-title>
            </v-list-item>
          </v-list>
        </v-menu>
      </div>

      <v-spacer />

      <v-menu v-if="isAdmin">
        <template #activator="{ props: menu }">
          <v-btn v-bind="menu" aria-label="Verwaltung" class="ms-2" icon variant="text">
            <v-icon icon="mdi-cog-outline" />
          </v-btn>
        </template>

        <v-list density="compact">
          <v-list-item :to="{ name: 'ingest-runs' }">
            <v-list-item-title>Ingest runs</v-list-item-title>
          </v-list-item>

          <v-list-item :to="{ name: 'keys' }">
            <v-list-item-title>API keys</v-list-item-title>
          </v-list-item>
        </v-list>
      </v-menu>

      <ediarum-user-menu class="platform-user-menu" />
    </v-toolbar>

    <div class="index-content">
      <router-view />
    </div>
  </v-app>
</template>

<script lang="ts" setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { useProjects } from '@/composables/useProjects'
import { useAppContext } from '@/context'

const route = useRoute()
const router = useRouter()
const { isAdmin, search } = useAppContext()

const { projects, load: loadProjects } = useProjects()
onMounted(loadProjects)

const currentProject = computed(() =>
  typeof route.params.project === 'string' ? route.params.project : undefined,
)
function openProject(slug: string | null) {
  if (slug) router.push({ name: 'entries', params: { project: slug } })
}

// the toolbar search filters live: `draft` is the local input, debounced into
// the shared term so the table narrows as you type (no Enter)
const { term: searchTerm, field: searchField, fields: searchFields } = search
const draft = ref(searchTerm.value)

const currentFieldLabel = computed(
  () => searchFields.value.find((o) => o.value === searchField.value)?.title ?? 'Label',
)

let debounce: ReturnType<typeof setTimeout> | undefined
watch(draft, (value) => {
  clearTimeout(debounce)
  debounce = setTimeout(() => {
    searchTerm.value = (value ?? '').trim()
  }, 250)
})
// keep the input in step if the term is changed elsewhere (e.g. a reset), but
// don't clobber a value the user is still typing
watch(searchTerm, (value) => {
  if ((draft.value ?? '').trim() !== value) draft.value = value
})
// a different project starts a fresh search
watch(currentProject, () => {
  searchTerm.value = ''
  searchField.value = 'label'
})
onBeforeUnmount(() => clearTimeout(debounce))

function goHome() {
  router.push({ name: 'projects' })
}
</script>

<style scoped>
/* Vuetify's layout utility classes are disabled project-wide
   (settings.scss $utilities: false), so the toolbar layout is done here. */

/* Same header rules as the platform's top bar and the other apps (WebDAV, ID):
   0.75rem side padding, 1rem from the home control to the app name, the name
   in the platform's font size at weight 600 (weight/letter-spacing: main.scss) */
.index-toolbar :deep(.v-toolbar__content) {
  padding-inline: var(--ep-space-3, 0.75rem);
}

/* platform controls: natural size, never squeezed or hidden (guide 3.10) */
.platform-home,
.platform-user-menu {
  flex: 0 0 auto;
}
.platform-home {
  margin-inline: 0 var(--ep-space-4, 1rem);
}
.platform-user-menu {
  margin-inline: 0.5rem 0;
}

/* brand: fixed size, never collapses under the toolbar's nowrap layout */
.app-title {
  flex: 0 0 auto;
  margin-inline: 0 1rem;
  font-size: var(--ep-font-size, 0.9375rem);
  line-height: 1.5;
  cursor: pointer;
}

.project-picker {
  flex: 0 1 260px;
  min-width: 160px;
}

/* search: a flex row that fills the free space; the term field
   absorbs any squeeze, the scope button keeps its natural size */
.search-group {
  display: flex;
  align-items: center;
  gap: 4px;
  flex: 1 1 auto;
  min-width: 0;
  max-width: 440px;
  margin-inline-start: 1rem;
}
.search-term {
  flex: 1 1 auto;
  min-width: 0;
}
.search-scope {
  flex: 0 0 auto;
}

/* no search on narrow screens */
@media (max-width: 839px) {
  .search-group {
    display: none;
  }
}

/* narrow screens: leave room for both platform controls */
@media (max-width: 599px) {
  .app-title {
    margin-inline-end: 0.5rem;
  }
  .project-picker {
    min-width: 110px;
  }
}
</style>
