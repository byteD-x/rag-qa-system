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
  padding: 12px 0 14px;
  border-bottom: 1px solid var(--border-color);
  background: var(--bg-panel);
  @supports (backdrop-filter: blur(8px)) {
    background: color-mix(in srgb, var(--bg-panel) 85%, transparent);
    backdrop-filter: blur(8px);
    -webkit-backdrop-filter: blur(8px);
  }
}
</style>
