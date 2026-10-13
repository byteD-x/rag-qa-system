<template>
  <div class="auth-form-view">
    <h2>找回密码</h2>
    <p class="subtitle">输入注册邮箱获取一次性重置链接。</p>
    <el-form v-if="!token" ref="requestRef" :model="requestForm" :rules="requestRules" label-position="top" @submit.prevent="requestReset">
      <el-form-item label="邮箱" prop="email"><el-input v-model="requestForm.email" type="email" autocomplete="email" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" class="submit-button">发送重置链接</el-button>
    </el-form>
    <el-form v-else ref="confirmRef" :model="confirmForm" :rules="confirmRules" label-position="top" @submit.prevent="confirmReset">
      <el-form-item label="重置令牌" prop="token"><el-input v-model="confirmForm.token" autocomplete="one-time-code" /></el-form-item>
      <el-form-item label="新密码" prop="password"><el-input v-model="confirmForm.password" type="password" show-password autocomplete="new-password" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" class="submit-button">更新密码</el-button>
    </el-form>
    <RouterLink class="back-link" to="/login">返回登录</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { confirmPasswordReset, requestPasswordReset } from '@/api/auth';

const requestRef = ref();
const confirmRef = ref();
const loading = ref(false);
const token = ref('');
const requestForm = reactive({ email: '' });
const confirmForm = reactive({ token: '', password: '' });
const requestRules = { email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }] };
const confirmRules = {
  token: [{ required: true, message: '请输入重置令牌', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 位，并包含字母和数字', trigger: 'blur' }]
};

async function requestReset() {
  if (!(await requestRef.value?.validate())) return;
  loading.value = true;
  try {
    const response: any = await requestPasswordReset(requestForm);
    if (response.reset_token) {
      token.value = response.reset_token;
      confirmForm.token = response.reset_token;
      ElMessage.success('本地开发环境已生成重置令牌，请继续设置新密码。');
    } else {
      ElMessage.success(response.message || '如果邮箱存在，重置链接已发送。');
    }
  } finally { loading.value = false; }
}

async function confirmReset() {
  if (!(await confirmRef.value?.validate())) return;
  loading.value = true;
  try {
    await confirmPasswordReset({ token: confirmForm.token, password: confirmForm.password });
    ElMessage.success('密码已更新，请重新登录。');
    token.value = '';
    confirmForm.password = '';
  } finally { loading.value = false; }
}
</script>

<style scoped>
.auth-form-view { display: flex; flex-direction: column; gap: 18px; }
h2 { margin: 0; color: var(--text-primary); }
.subtitle { margin: 0; color: var(--text-muted); line-height: 1.6; }
.submit-button { width: 100%; min-height: 44px; }
.back-link { color: var(--blue-600); text-align: center; }
</style>
