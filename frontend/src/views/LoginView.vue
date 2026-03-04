<template>
  <div class="login-view">
    <el-form :model="form" :rules="rules" ref="formRef" @keyup.enter="handleLogin" class="login-form">
      <el-form-item prop="email">
        <el-input 
          v-model="form.email" 
          placeholder="Email address" 
          prefix-icon="Message" 
          size="large"
          class="custom-input"
        />
      </el-form-item>
      <el-form-item prop="password">
        <el-input 
          v-model="form.password" 
          type="password" 
          placeholder="Password" 
          prefix-icon="Lock" 
          show-password 
          size="large"
          class="custom-input"
        />
      </el-form-item>
      <el-form-item class="submit-item">
        <el-button type="primary" :loading="loading" @click="handleLogin" size="large" class="submit-btn">
          Sign In
        </el-button>
      </el-form-item>
    </el-form>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAuthStore } from '@/store/auth';
import { login } from '@/api/auth';
import { ElMessage } from 'element-plus';

const router = useRouter();
const route = useRoute();
const authStore = useAuthStore();
const formRef = ref();

const form = reactive({
  email: 'admin@local',
  password: 'ChangeMe123!'
});

const rules = {
  email: [{ required: true, message: 'Please input email', trigger: 'blur' }],
  password: [{ required: true, message: 'Please input password', trigger: 'blur' }]
};

const loading = ref(false);

const handleLogin = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid: boolean) => {
    if (valid) {
      loading.value = true;
      try {
        const res: any = await login({ email: form.email, password: form.password });
        if (res.access_token) {
          authStore.setAuth(res.access_token, res.user);
          ElMessage.success('Login Successful');
          const redirect = route.query.redirect as string || '/';
          router.push(redirect);
        }
      } finally {
        loading.value = false;
      }
    }
  });
};
</script>

<style scoped>
.submit-item {
  margin-top: 32px;
  margin-bottom: 0;
}

.submit-btn {
  width: 100%;
  border-radius: 12px;
  font-weight: 600;
  font-size: 16px;
  height: 48px;
  transition: all var(--el-transition-duration);
  box-shadow: var(--shadow-blue);
}

.submit-btn:hover {
  transform: translateY(-1px);
  box-shadow: 0 12px 20px -8px rgba(59, 130, 246, 0.4);
}

:deep(.custom-input .el-input__wrapper) {
  border-radius: 12px;
  padding: 8px 16px;
  box-shadow: 0 0 0 1px var(--border-color-light) inset;
  background-color: var(--bg-base);
  transition: all 0.2s ease;
}

:deep(.custom-input .el-input__wrapper:hover) {
  box-shadow: 0 0 0 1px var(--border-color) inset;
}

:deep(.custom-input .el-input__wrapper.is-focus) {
  box-shadow: 0 0 0 1px var(--el-color-primary) inset, 0 0 0 3px var(--el-color-primary-light-8);
  background-color: var(--bg-surface);
}
</style>
