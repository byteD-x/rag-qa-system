<template>
  <div class="login-view">
    <h2 class="login-title">登录</h2>
    <p class="login-subtitle">使用企业账号登录工作台</p>

    <el-form
      ref="formRef"
      :model="form"
      :rules="rules"
      class="login-form"
      label-position="top"
      @keyup.enter="handleLogin"
    >
      <el-form-item label="邮箱" prop="email">
        <el-input
          v-model="form.email"
          type="email"
          placeholder="请输入邮箱"
          :prefix-icon="Message"
          autocomplete="username"
          size="large"
        />
      </el-form-item>

      <el-form-item label="密码" prop="password">
        <el-input
          v-model="form.password"
          type="password"
          placeholder="请输入密码"
          :prefix-icon="Lock"
          show-password
          autocomplete="current-password"
          size="large"
        />
      </el-form-item>

      <el-form-item class="submit-item">
        <el-button type="primary" :loading="loading" class="submit-button" @click="handleLogin">
          进入工作台
        </el-button>
      </el-form-item>
    </el-form>

    <div class="auth-links">
      <RouterLink to="/register">注册新账号</RouterLink>
      <RouterLink to="/password-reset">忘记密码？</RouterLink>
    </div>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage } from 'element-plus';
import { Lock, Message } from '@element-plus/icons-vue';
import { login } from '@/api/auth';
import { useAuthStore } from '@/store/auth';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const formRef = ref();

const form = reactive({
  email: '',
  password: ''
});

const loading = ref(false);

const rules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }],
  password: [{ required: true, message: '请输入密码', trigger: 'blur' }]
};

const handleLogin = async () => {
  if (!formRef.value) {
    return;
  }

  await formRef.value.validate(async (valid: boolean) => {
    if (!valid) {
      return;
    }

    loading.value = true;
    try {
      const res: any = await login({ email: form.email, password: form.password });
      if (res.access_token) {
        authStore.setAuth(res.access_token, res.user);
        ElMessage.success('登录成功');
        const redirect = (route.query.redirect as string) || '/workspace/entry';
        router.push(redirect);
      }
    } finally {
      loading.value = false;
    }
  });
};
</script>

<style scoped>
.login-view {
  display: flex;
  flex-direction: column;
  gap: 28px;
}

.login-title {
  margin: 0;
  font-size: var(--text-h1, 1.375rem);
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.03em;
}

.login-subtitle {
  margin: 6px 0 0;
  font-size: var(--text-body, 0.9375rem);
  color: var(--text-muted);
  line-height: 1.55;
}

.login-form :deep(.el-form-item__label) {
  font-weight: 600;
  font-size: var(--text-caption, 0.75rem);
}

.login-form :deep(.el-input__wrapper) {
  min-height: 44px !important;
  border-radius: var(--radius-sm) !important;
}

.login-form {
  margin-bottom: 0;
}

.submit-item {
  margin-bottom: 0;
}

.submit-item :deep(.el-form-item__content) {
  margin-top: 16px;
}

.submit-button {
  width: 100%;
  min-height: 46px;
  font-size: var(--text-body);
  font-weight: 600;
  border-radius: var(--radius-sm);
  transition: opacity var(--transition-base);
}

.auth-links {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  font-size: var(--text-caption, 0.75rem);
}

.auth-links a { color: var(--blue-600); }
</style>
