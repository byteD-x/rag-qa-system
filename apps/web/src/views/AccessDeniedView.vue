<template>
  <div class="page-shell access-denied-page">
    <section class="access-denied-panel" role="alert" aria-labelledby="access-denied-title">
      <div class="access-denied-code">403</div>
      <h1 id="access-denied-title">没有访问权限</h1>
      <p>当前账号无法访问此页面。</p>
      <p v-if="permission">所需权限：<code>{{ permission }}</code></p>
      <p v-if="fromPath" class="access-denied-path">请求页面：{{ fromPath }}</p>
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
const fromPath = computed(() => String(route.query.from || ''));

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

.access-denied-code {
  color: var(--blue-600);
  font-size: 48px;
  font-weight: 700;
}

.access-denied-panel h1 {
  margin: 12px 0 8px;
  font-size: 24px;
}

.access-denied-panel p {
  margin: 8px 0;
  color: var(--text-secondary);
}

.access-denied-path {
  overflow-wrap: anywhere;
  font-size: 13px;
}

.access-denied-panel code {
  color: var(--text-primary);
  font-family: var(--font-mono);
}

.access-denied-panel .el-button {
  margin-top: 20px;
}
</style>
