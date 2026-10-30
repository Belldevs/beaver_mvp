<template>
  <span><template v-for="(p, i) in parts" :key="i"><strong v-if="p.bold">{{ p.text }}</strong><template v-else>{{ p.text }}</template></template></span>
</template>

<script setup>
// Renders **bold** and nothing else. No v-html, so text from the AI can never inject markup.
import { computed } from 'vue'

const props = defineProps({ text: { type: String, default: '' } })

const parts = computed(() =>
  String(props.text || '')
    .split(/(\*\*[^*]+\*\*)/)
    .filter(Boolean)
    .map((s) =>
      s.length > 4 && s.startsWith('**') && s.endsWith('**') ? { bold: true, text: s.slice(2, -2) } : { bold: false, text: s }
    )
)
</script>

<style scoped>
strong { font-weight: 600; color: var(--text); }
</style>