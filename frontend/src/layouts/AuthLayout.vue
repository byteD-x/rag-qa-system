<template>
  <div class="auth-layout">
    <div class="auth-wrapper animate-slide-up">
      <div class="auth-container glass-panel">
        <div class="auth-header">
          <div class="logo-circle">
            <el-icon :size="32" color="var(--el-color-primary)"><Platform /></el-icon>
          </div>
          <h1>RAG-P QA System</h1>
          <p>Enterprise Knowledge Base & AI Assistant</p>
        </div>
        <router-view />
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { Platform } from '@element-plus/icons-vue'
</script>

<style scoped>
.auth-layout {
  height: 100vh;
  width: 100vw;
  display: flex;
  justify-content: center;
  align-items: center;
  background: linear-gradient(135deg, #f0f4f8 0%, #d9e2ec 100%);
  position: relative;
  overflow: hidden;
}

.auth-layout::before {
  content: '';
  position: absolute;
  top: -20%;
  left: -10%;
  width: 50%;
  height: 60%;
  background: radial-gradient(circle, rgba(59,130,246,0.15) 0%, rgba(255,255,255,0) 70%);
  border-radius: 50%;
  z-index: 0;
}

.auth-layout::after {
  content: '';
  position: absolute;
  bottom: -20%;
  right: -10%;
  width: 60%;
  height: 70%;
  background: radial-gradient(circle, rgba(99,102,241,0.1) 0%, rgba(255,255,255,0) 70%);
  border-radius: 50%;
  z-index: 0;
}

.auth-wrapper {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 440px;
  padding: 0 20px;
}

.auth-container {
  padding: 48px 40px;
  border-radius: 24px;
  background: rgba(255, 255, 255, 0.85);
  box-shadow: var(--shadow-xl);
}

.auth-header {
  text-align: center;
  margin-bottom: 40px;
}

.logo-circle {
  width: 64px;
  height: 64px;
  margin: 0 auto 20px;
  background: rgba(59, 130, 246, 0.1);
  border-radius: 16px;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: var(--shadow-sm);
}

.auth-header h1 {
  margin: 0 0 12px;
  color: var(--text-primary);
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.auth-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 15px;
}
</style>
