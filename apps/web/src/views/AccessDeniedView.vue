<template>
  <div class="page-shell access-denied-page">
    <section class="access-denied-panel" role="alert" aria-labelledby="access-denied-title">
      <h1 id="access-denied-title">没有访问权限</h1>
      <p>当前账号无法访问此页面。<template v-if="permission">所需权限：<code>{{ permission }}</code>。</template></p>
      <el-button type="primary" data-testid="back-to-workspace" @click="goToWorkspace">
        返回工作台
      </el-button>
    </section>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useRoute, useRouter } from 'vue-router';

const route = useRoute();
const router = useRouter();

const permission = computed(() => String(route.query.permission || ''));

function goToWorkspace() {
  router.push('/workspace/entry');
}
</script>

<style scoped>
.access-denied-page {
  align-items: center;
  justify-content: center;
  padding: 24px;
}

.access-denied-panel {
  width: min(100%, 520px);
  padding: 40px 32px;
  text-align: center;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
}

.access-denied-panel h1 {
  margin: 12px 0 8px;
  font-size: var(--text-h1);
}

.access-denied-panel p {
  margin: 8px 0;
  color: var(--text-secondary);
}

.access-denied-panel code {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.access-denied-panel .el-button {
  margin-top: 20px;
}
</style>
