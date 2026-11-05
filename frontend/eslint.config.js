import prettier from 'eslint-config-prettier'
import vuetify from 'eslint-config-vuetify'

// vuetify() resolves to the flat-config array; append eslint-config-prettier
// last so it disables every @stylistic/* and vue/* layout rule that would
// otherwise fight Prettier. Non-layout rules (perfectionist, unused-imports)
// stay active.
export default vuetify({
  ts: true,
}).then((configs) => [...configs, prettier])
