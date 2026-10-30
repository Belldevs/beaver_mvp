<template>
  <section class="page">
    <h1 class="h1">{{ title }}</h1>
    <div class="card empty"><p class="muted">{{ text }}</p></div>
  </section>
</template>

<script setup>
defineProps({ title: String, text: String })
</script>

<style scoped>
.page { padding-top: 12px; }
.empty { margin-top: 20px; padding: 40px 20px; text-align: center; }
</style>
