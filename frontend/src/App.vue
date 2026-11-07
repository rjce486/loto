<script setup lang="ts">
import { useRoute } from 'vue-router'
import logo from './assets/logo.png'
const route = useRoute()
</script>
<template>
  <div :class="{ admin: route.path.startsWith('/admin') }">
    <header class="site-header">
      <router-link to="/" class="brand">
        <img :src="logo" alt="Société de tir de Tartegnin" width="760" height="787" />
      </router-link>
    </header>
    <main><router-view /></main>
  </div>
</template>
