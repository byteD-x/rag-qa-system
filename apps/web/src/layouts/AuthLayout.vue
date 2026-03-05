<template>
  <div class="auth-layout">
    <!-- Left Banner Section -->
    <div class="auth-banner">
      <div class="banner-content animate-slide-up">
        <div class="logo-circle">
          <el-icon :size="36" color="#ffffff"><Platform /></el-icon>
        </div>
        <h1>RAG-QA System</h1>
        <p>Next-generation enterprise knowledge retrieval and intelligent assistant platform.</p>
      </div>
      <!-- Decorative Background Shapes -->
      <div class="bg-shape shape-1"></div>
      <div class="bg-shape shape-2"></div>
      <div class="glass-overlay"></div>
    </div>

    <!-- Right Content Section -->
    <div class="auth-content">
      <div class="auth-wrapper animate-fade-in">
        <div class="auth-header">
          <h2>Welcome Back</h2>
          <p>Please enter your details to sign in.</p>
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
  background-color: var(--bg-surface);
  overflow: hidden;
}

/* --- Left Banner --- */
.auth-banner {
  flex: 1;
  position: relative;
  background: linear-gradient(135deg, var(--el-color-primary) 0%, #1e3a8a 100%);
  display: none;
  overflow: hidden;
  color: #ffffff;
}
@media (min-width: 900px) {
  .auth-banner {
    display: flex;
    flex-direction: column;
    justify-content: center;
    padding: 60px;
  }
}

.banner-content {
  position: relative;
  z-index: 10;
  max-width: 480px;
}

.logo-circle {
  width: 72px;
  height: 72px;
  background: rgba(255, 255, 255, 0.2);
  backdrop-filter: blur(10px);
  border-radius: 20px;
  display: flex;
  align-items: center;
  justify-content: center;
  margin-bottom: 32px;
  box-shadow: 0 8px 32px rgba(0, 0, 0, 0.1);
  border: 1px solid rgba(255, 255, 255, 0.3);
}

.banner-content h1 {
  font-size: 42px;
  font-weight: 800;
  line-height: 1.2;
  margin: 0 0 16px;
  letter-spacing: -1px;
}

.banner-content p {
  font-size: 18px;
  line-height: 1.6;
  opacity: 0.9;
  margin: 0;
  font-weight: 300;
}

/* Abstract Background Elements */
.bg-shape {
  position: absolute;
  border-radius: 50%;
  filter: blur(80px);
  z-index: 1;
}
.shape-1 {
  width: 400px;
  height: 400px;
  background: rgba(96, 165, 250, 0.4); /* primary-light-3 */
  top: -100px;
  left: -100px;
}
.shape-2 {
  width: 500px;
  height: 500px;
  background: rgba(147, 197, 253, 0.3); /* primary-light-5 */
  bottom: -150px;
  right: -100px;
}
.glass-overlay {
  position: absolute;
  inset: 0;
  background: linear-gradient(transparent 50%, rgba(0,0,0,0.1));
  z-index: 2;
  pointer-events: none;
}

/* --- Right Content --- */
.auth-content {
  flex: 1;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px;
  position: relative;
  max-width: 600px;
  width: 100%;
  margin: 0 auto;
}

.auth-wrapper {
  width: 100%;
  max-width: 400px;
}

.auth-header {
  margin-bottom: 40px;
}

.auth-header h2 {
  margin: 0 0 8px;
  color: var(--text-primary);
  font-size: 32px;
  font-weight: 700;
  letter-spacing: -0.5px;
}

.auth-header p {
  margin: 0;
  color: var(--text-secondary);
  font-size: 16px;
}
</style>
