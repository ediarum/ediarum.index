<!-- Platform admins only: the read-only history of ingest runs
     (GET /ingest-runs) — what the watcher and `ediarum-index ingest` did, a
     place to check after an unattended run. Nothing here is created or edited
     from the UI. -->
<template>
  <DataListView
    :error="error"
    :headers="headers"
    item-value="id"
    :items="runs"
    :loading="loading"
    title="Ingest runs"
    @row-click="openDetail"
  >
    <template #[`item.status`]="{ item }">
      <v-chip :color="statusColor(item.status)" size="small" variant="tonal">
        {{ item.status }}
      </v-chip>
    </template>

    <template #[`item.finished_at`]="{ item }">
      {{ formatDate(item.finished_at) }}
    </template>

    <template #[`item.problems`]="{ item }">
      <span v-if="item.problems.length === 0" class="text-medium-emphasis">—</span>
      <span v-else>{{ item.problems.length }}</span>
    </template>
  </DataListView>

  <v-dialog v-model="detail" max-width="640">
    <v-card v-if="selected" :title="`${selected.project} — ${formatDate(selected.finished_at)}`">
      <v-card-text>
        <p class="mb-4">
          {{ selected.created }} created, {{ selected.updated }} updated,
          {{ selected.unchanged }} unchanged
        </p>

        <p v-if="selected.problems.length === 0" class="text-medium-emphasis">No problems.</p>

        <v-list v-else density="compact">
          <v-list-item v-for="(p, i) in selected.problems" :key="i">
            <v-list-item-title>{{ p.fname }} [{{ p.ext_id ?? '—' }}] — {{ p.kind }}</v-list-item-title>
            <v-list-item-subtitle>{{ p.detail }}</v-list-item-subtitle>
          </v-list-item>
        </v-list>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="detail = false">Close</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts" setup>
import type { IngestRun } from '@/api/ingestRun'
import { onMounted, ref } from 'vue'
import DataListView from '@/components/common/DataListView.vue'
import { useIngestRuns } from '@/composables/useIngestRuns'

const { runs, loading, error, load } = useIngestRuns()

const headers = [
  { title: 'Project', key: 'project' },
  { title: 'Status', key: 'status' },
  { title: 'Created', key: 'created' },
  { title: 'Updated', key: 'updated' },
  { title: 'Unchanged', key: 'unchanged' },
  { title: 'Problems', key: 'problems', sortable: false },
  { title: 'Finished', key: 'finished_at' },
]

function statusColor(status: IngestRun['status']): string | undefined {
  return { ok: 'success', conflicts: 'warning', failed: 'error' }[status]
}

function formatDate(iso: string): string {
  const d = new Date(iso)
  return Number.isNaN(d.getTime()) ? iso : d.toLocaleString()
}

const detail = ref(false)
const selected = ref<IngestRun | null>(null)
function openDetail(item: IngestRun) {
  selected.value = item
  detail.value = true
}

onMounted(() => load())
</script>
