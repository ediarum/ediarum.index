<!--
  Reusable "are you sure?" dialog. Shows `message` (or the default slot) and
  emits `confirm`; the parent runs the action and closes via `v-model`.
-->
<template>
  <v-dialog v-model="model" max-width="400">
    <v-card>
      <v-card-title>{{ title }}</v-card-title>

      <v-card-text>
        <slot>{{ message }}</slot>
      </v-card-text>

      <v-card-actions>
        <v-spacer />
        <v-btn variant="text" @click="model = false">{{ cancelText }}</v-btn>
        <v-btn :color="color" :loading="loading" @click="emit('confirm')">{{ confirmText }}</v-btn>
      </v-card-actions>
    </v-card>
  </v-dialog>
</template>

<script lang="ts" setup>
const model = defineModel<boolean>({ default: false })

withDefaults(
  defineProps<{
    title: string
    message?: string
    confirmText?: string
    cancelText?: string
    color?: string
    loading?: boolean
  }>(),
  {
    message: '',
    confirmText: 'Delete',
    cancelText: 'Cancel',
    color: 'error',
    loading: false,
  },
)

const emit = defineEmits<{ confirm: [] }>()
</script>
