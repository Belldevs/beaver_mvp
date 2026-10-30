<template>
  <button class="icon-btn" :title="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'"
          :aria-label="theme === 'dark' ? 'Switch to light theme' : 'Switch to dark theme'" @click="toggleTheme">
    <Icon :name="theme === 'dark' ? 'sun' : 'moon'" />
  </button>
</template>

<script setup>
import Icon from './Icon.vue'
import { theme, toggleTheme } from '../lib/theme'
</script>
