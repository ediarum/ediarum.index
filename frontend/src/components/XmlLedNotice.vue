<!-- For projects whose registers this app ingests from TEI files
     (`registers_from_xml`): an edit here changes the index only. The ingest
     never overwrites it — the next change to the entry's XML is reported as a
     conflict instead (see the ingest run history). -->
<template>
  <v-alert
    class="mb-4"
    density="compact"
    icon="mdi-file-xml-box"
    type="warning"
    variant="tonal"
  >
    This project's registers are maintained in XML. Changes made here stay in the index: they
    don't reach the XML files, and a later change to this entry's XML is reported as a conflict
    instead of being applied.
  </v-alert>
</template>
