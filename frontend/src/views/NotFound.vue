<!-- An unknown path under /index/. Deliberately a page, not a redirect: the
     platform's router and this app's share window.history, and when the
     platform navigates elsewhere this router sees that path too, just before
     the app is unmounted — a redirect would then rewrite the platform's URL. -->
<template>
  <v-container>
    <p class="not-found">Diese Seite gibt es nicht.</p>
    <v-btn :to="{ name: 'projects' }" variant="tonal">Zu den Projekten</v-btn>
  </v-container>
</template>

<style scoped>
.not-found {
  margin-bottom: 1rem;
}
</style>
