<template>
  <el-config-provider>
    <router-view v-slot="{ Component }">
      <transition name="fade-transform" mode="out-in">
        <component :is="Component" />
      </transition>
    </router-view>
  </el-config-provider>
</template>

<script setup lang="ts">
</script>
<style>
/* Global styles are now handled in style.css */
</style>
