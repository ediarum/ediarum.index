<!--
  Reusable modal form shell: title bar, optional busy bar, error alert, a
  <v-form> wrapping the default slot, and Cancel / Save actions.

  It validates the form and emits `submit`; it never closes itself — the parent
  owns the `v-model` and closes it after the async work succeeds. Pass `saving`
  for the button spinner, `busy` to disable the form while something loads,
  `error` to show an alert, `scrollable` to scroll a long form inside the
  dialog (header and actions stay in view).
-->
<template>
  <v-dialog v-model="model" :max-width="maxWidth" :scrollable="scrollable">
    <v-card>
      <v-card-title>{{ title }}</v-card-title>

      <v-progress-linear v-if="busy" indeterminate />

      <v-card-text>
        <v-alert v-if="error" class="mb-4" type="error" variant="tonal">{{ error }}</v-alert>

        <v-form ref="formRef" :disabled="busy" @submit.prevent="onSubmit">
          <slot />
        </v-form>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="model = false">{{ cancelText }}</v-btn>

        <v-btn color="primary" :disabled="busy" :loading="saving" @click="onSubmit">
          {{ saveText }}
        </v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts" setup>
import { ref } from 'vue'

const model = defineModel<boolean>({ default: false })

withDefaults(
  defineProps<{
    title: string
    saving?: boolean
    busy?: boolean
    error?: string | null
    maxWidth?: string | number
    saveText?: string
    cancelText?: string
    scrollable?: boolean
  }>(),
  {
    saving: false,
    busy: false,
    error: null,
    maxWidth: 520,
    saveText: 'Save',
    cancelText: 'Cancel',
    scrollable: false,
  },
)

const emit = defineEmits<{ submit: [] }>()

const formRef = ref<{
  validate: () => Promise<{ valid: boolean }>
  resetValidation: () => void
} | null>(null)

async function onSubmit() {
  const result = await formRef.value?.validate()
  if (result && !result.valid) return
  emit('submit')
}

defineExpose({ resetValidation: () => formRef.value?.resetValidation() })
</script>
