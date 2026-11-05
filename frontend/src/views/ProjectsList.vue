<!-- The projects the caller may use (GET /projects; the platform's project
     registry decides which exist and who may use them). A row opens the
     project's entries. -->
<template>
  <DataListView
    :error="error"
    :headers="headers"
    item-value="name"
    :items="projects"
    :loading="loading"
    title="Projekte"
    @row-click="openEntries"
  />
</template>

<script lang="ts" setup>
import type { Project } from '@/api/project'
import { onMounted } from 'vue'
import { useRouter } from 'vue-router'
import DataListView from '@/components/common/DataListView.vue'
import { useProjects } from '@/composables/useProjects'

const router = useRouter()
const { projects, loading, error, load } = useProjects()

const headers = [
  { title: 'Projekt', key: 'label' },
  { title: 'Kürzel', key: 'name' },
  { title: 'Beschreibung', key: 'description' },
]

function openEntries(item: Project) {
  router.push({ name: 'entries', params: { project: item.name } })
}

onMounted(load)
</script>
