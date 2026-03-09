<template>
  <div class="auth-shell">
    <section class="auth-showcase" aria-hidden="true">
      <div class="showcase-content">
        <div class="showcase-brand">
          <div class="brand-mark">
            <el-icon :size="28"><Platform /></el-icon>
          </div>
          <div class="brand-copy">
            <h1>RAG-QA 2.0</h1>
            <p>企业知识库问答与治理工作台</p>
          </div>
        </div>
        <div class="showcase-features">
          <div class="feature-item">
            <span class="feature-dot" />
            <span>知识库生命周期管理</span>
          </div>
          <div class="feature-item">
            <span class="feature-dot" />
            <span>检索增强问答（RAG）</span>
          </div>
          <div class="feature-item">
            <span class="feature-dot" />
            <span>审计与可观测性</span>
          </div>
        </div>
      </div>
    </section>

    <section class="auth-panel">
      <div class="auth-panel-card">
        <router-view />
      </div>
    </section>
  </div>
</template>

<script setup lang="ts">
import { Platform } from '@element-plus/icons-vue';
</script>

<style scoped>
.auth-shell {
  display: grid;
  grid-template-columns: minmax(0, 1fr) minmax(420px, 480px);
  min-height: 100vh;
}

.auth-showcase {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 56px 48px;
  background: linear-gradient(160deg, #0f172a 0%, #1e3a5f 35%, #1e293b 60%, #0c1222 100%);
  color: #fff;
}

.showcase-content {
  max-width: 440px;
}

.showcase-brand {
  display: flex;
  align-items: flex-start;
  gap: 20px;
}

.brand-mark {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 56px;
  height: 56px;
  flex-shrink: 0;
  border-radius: var(--radius-md);
  background: rgba(59, 130, 246, 0.15);
  border: 1px solid rgba(59, 130, 246, 0.3);
  color: #93c5fd;
}

.brand-copy h1 {
  margin: 0;
  font-size: 1.5rem;
  font-weight: 700;
  letter-spacing: -0.03em;
}

.brand-copy p {
  margin-top: 10px;
  font-size: var(--text-body, 0.9375rem);
  color: rgba(255, 255, 255, 0.7);
  line-height: 1.55;
}

.showcase-features {
  margin-top: 48px;
  display: flex;
  flex-direction: column;
  gap: 16px;
}

.feature-item {
  display: flex;
  align-items: center;
  gap: 14px;
  font-size: var(--text-body, 0.9375rem);
  color: rgba(255, 255, 255, 0.88);
  font-weight: 500;
}

.feature-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: rgba(59, 130, 246, 0.9);
  flex-shrink: 0;
}

.auth-panel {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 36px;
  background: var(--bg-page);
}

.auth-panel-card {
  width: 100%;
  max-width: 420px;
  padding: 36px 32px;
  border-radius: var(--radius-lg);
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-md);
  transition: box-shadow var(--transition-base), border-color var(--transition-base);
}

.auth-panel-card:hover {
  box-shadow: var(--shadow-lg);
  border-color: var(--border-strong);
}

@media (max-width: 900px) {
  .auth-shell {
    grid-template-columns: 1fr;
  }

  .auth-showcase {
    display: none;
  }

  .auth-panel {
    padding: 24px 20px;
    background: var(--bg-page);
  }
}

@media (max-width: 480px) {
  .auth-panel-card {
    padding: 24px 20px;
  }
}
</style>
