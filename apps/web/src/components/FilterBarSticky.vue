<template>
  <div class="filter-bar-sticky">
    <div class="filter-bar-sticky__inner">
      <slot />
    </div>
  </div>
</template>

<script setup lang="ts">
</script>

<style scoped>
.filter-bar-sticky {
  position: sticky;
  top: 0;
  z-index: 5;
  flex-shrink: 0;
}

.filter-bar-sticky__inner {
  padding: 14px 0 16px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-panel);
}
</style>
