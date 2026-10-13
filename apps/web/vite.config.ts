/// <reference types="vitest/config" />
import path from 'path';
import { defineConfig, loadEnv } from 'vite';
import vue from '@vitejs/plugin-vue';

import { createApiProxy } from './vite.proxy';

export default defineConfig(({ mode }) => {
  const envDir = path.resolve(__dirname, '../..');
  const env = loadEnv(mode, envDir, '');
  const gatewayPort = env.GATEWAY_HOST_PORT || '8080';
  const gatewayOrigin = env.VITE_GATEWAY_ORIGIN || `http://localhost:${gatewayPort}`;
  const demoAdminEmail = env.VITE_DEMO_ADMIN_EMAIL || env.ADMIN_EMAIL || 'admin@local';
  const demoAdminPassword = env.VITE_DEMO_ADMIN_PASSWORD || env.ADMIN_PASSWORD || 'ChangeMe123!';
  const demoMemberEmail = env.VITE_DEMO_MEMBER_EMAIL || env.MEMBER_EMAIL || 'member@local';
  const demoMemberPassword = env.VITE_DEMO_MEMBER_PASSWORD || env.MEMBER_PASSWORD || 'ChangeMe123!';

  return {
    envDir,
    plugins: [vue()],
    define: {
      'import.meta.env.VITE_DEMO_ADMIN_EMAIL': JSON.stringify(demoAdminEmail),
      'import.meta.env.VITE_DEMO_ADMIN_PASSWORD': JSON.stringify(demoAdminPassword),
      'import.meta.env.VITE_DEMO_MEMBER_EMAIL': JSON.stringify(demoMemberEmail),
      'import.meta.env.VITE_DEMO_MEMBER_PASSWORD': JSON.stringify(demoMemberPassword)
    },
    resolve: {
      alias: {
        '@': path.resolve(__dirname, './src')
      }
    },
    build: {
      rollupOptions: {
        output: {
          manualChunks: {
            'vue-vendor': ['vue', 'vue-router', 'pinia'],
            'ui-vendor': ['element-plus'],
            'icons-vendor': ['@element-plus/icons-vue'],
            'http-vendor': ['axios']
          }
        }
      }
    },
    test: {
      environment: 'jsdom',
      setupFiles: ['./src/test/setup.ts']
    },
    server: {
      port: 5173,
      proxy: createApiProxy(gatewayOrigin)
    }
  };
});
