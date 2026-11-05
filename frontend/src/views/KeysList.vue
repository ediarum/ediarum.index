<!-- Platform admins only: API keys for programs without a platform session —
     ediarum/oXygen reading a project's entries, ediarum.webdav reporting saved
     files (POST /files), scripts. A key is shown once, right after it is
     created; afterwards only its name and scope are known. -->
<template>
  <DataListView
    create-label="New key"
    :error="error"
    :headers="headers"
    item-value="name"
    :items="keys"
    :loading="loading"
    title="API keys"
    @create="openCreate"
  >
    <template #[`item.projects`]="{ item }">
      {{ item.projects.includes('*') ? 'all projects' : item.projects.join(', ') }}
    </template>

    <template #[`item.is_active`]="{ item }">
      <v-chip :color="item.is_active ? 'success' : undefined" size="small" variant="tonal">
        {{ item.is_active ? 'active' : 'revoked' }}
      </v-chip>
    </template>

    <template #[`item.actions`]="{ item }">
      <v-btn
        v-if="item.is_active"
        color="error"
        size="small"
        variant="text"
        @click.stop="askRevoke(item)"
      >
        Revoke
      </v-btn>
    </template>
  </DataListView>

  <FormDialog
    v-model="dialog"
    :error="submitError"
    :saving="saving"
    title="New API key"
    @submit="onCreate"
  >
    <v-text-field
      v-model="draft.name"
      hint="letters, digits, . _ - — e.g. oxygen-schleiermacher"
      label="Name"
      persistent-hint
      :rules="[required, validName]"
    />

    <v-checkbox v-model="draft.all" hide-details label="All projects" />

    <v-select
      v-if="!draft.all"
      v-model="draft.projects"
      chips
      item-title="label"
      item-value="name"
      :items="projects"
      label="Projects"
      multiple
      :rules="[atLeastOne]"
    />
  </FormDialog>

  <v-dialog v-model="shownKeyOpen" max-width="560" persistent>
    <v-card :title="`Key for ${shownKey?.name}`">
      <v-card-text>
        <p class="key-hint">
          Copy it now — it is shown only this once. Programs send it as
          <code>Authorization: Bearer …</code>, or append <code>?key=…</code> to a URL.
        </p>

        <v-text-field
          class="key-value"
          hide-details
          :model-value="shownKey?.key"
          readonly
          @focus="($event.target as HTMLInputElement).select()"
        />
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn @click="closeShownKey">Done</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>

  <ConfirmDialog
    v-model="confirm"
    :loading="revoking"
    :message="`Programs using ${toRevoke?.name ?? ''} stop working at once. This can't be undone.`"
    title="Revoke key?"
    @confirm="confirmRevoke"
  />
</template>

<script lang="ts" setup>
import type { ApiKey, NewApiKey } from '@/api/key'
import { onMounted, reactive, ref } from 'vue'
import { apiError } from '@/api/error'
import ConfirmDialog from '@/components/common/ConfirmDialog.vue'
import DataListView from '@/components/common/DataListView.vue'
import FormDialog from '@/components/common/FormDialog.vue'
import { useKeys } from '@/composables/useKeys'
import { useProjects } from '@/composables/useProjects'

const { keys, loading, error, load, create, revoke } = useKeys()
const { projects, load: loadProjects } = useProjects()

const headers = [
  { title: 'Name', key: 'name' },
  { title: 'Projects', key: 'projects', sortable: false },
  { title: 'Status', key: 'is_active' },
  { title: 'Created by', key: 'created_by' },
  { title: '', key: 'actions', sortable: false, align: 'end' as const },
]

const required = (v: string) => (v ?? '').trim() !== '' || 'Required'
const validName = (v: string) => /^[\w.-]+$/.test(v ?? '') || 'Letters, digits, . _ - only'
const atLeastOne = (v: string[]) => (v ?? []).length > 0 || 'Choose at least one project'

const dialog = ref(false)
const saving = ref(false)
const submitError = ref<string | null>(null)
const draft = reactive({ name: '', all: false, projects: [] as string[] })

function openCreate() {
  Object.assign(draft, { name: '', all: false, projects: [] })
  submitError.value = null
  dialog.value = true
}

const shownKey = ref<NewApiKey | null>(null)
const shownKeyOpen = ref(false)
function closeShownKey() {
  shownKeyOpen.value = false
  shownKey.value = null // the key leaves memory with the dialog
}

async function onCreate() {
  saving.value = true
  submitError.value = null
  try {
    shownKey.value = await create({
      name: draft.name.trim(),
      projects: draft.all ? ['*'] : draft.projects,
    })
    dialog.value = false
    shownKeyOpen.value = true
  } catch (error_) {
    submitError.value = apiError(error_)
  } finally {
    saving.value = false
  }
}

const confirm = ref(false)
const toRevoke = ref<ApiKey | null>(null)
const revoking = ref(false)
function askRevoke(item: ApiKey) {
  toRevoke.value = item
  confirm.value = true
}
async function confirmRevoke() {
  if (!toRevoke.value) return
  revoking.value = true
  try {
    await revoke(toRevoke.value.name)
    confirm.value = false
  } finally {
    revoking.value = false
  }
}

onMounted(() => {
  load()
  loadProjects()
})
</script>

<style scoped>
.key-hint {
  margin-bottom: 0.75rem;
}
.key-value :deep(input) {
  font-family: var(--font-mono);
}
</style>
