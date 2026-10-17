<template>
  <div class="auth-form-view">
    <h2>注册账号</h2>
    <p class="subtitle">创建账号后即可保存自己的知识库和问答记录。</p>
    <el-form ref="formRef" :model="form" :rules="rules" label-position="top" @submit.prevent="submit">
      <el-form-item label="邮箱" prop="email"><el-input v-model="form.email" type="email" autocomplete="email" /></el-form-item>
      <el-form-item label="密码（至少 8 位，含字母和数字）" prop="password"><el-input v-model="form.password" type="password" show-password autocomplete="new-password" /></el-form-item>
      <el-form-item label="部门（留空则检索不到本部门文档）" prop="department"><el-input v-model="form.department" maxlength="120" /></el-form-item>
      <el-button type="primary" native-type="submit" :loading="loading" class="submit-button">注册并进入工作台</el-button>
    </el-form>
    <RouterLink class="back-link" to="/login">已有账号？返回登录</RouterLink>
  </div>
</template>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { ElMessage } from 'element-plus';
import { useRouter } from 'vue-router';
import { register } from '@/api/auth';
import { useAuthStore } from '@/store/auth';

const router = useRouter();
const authStore = useAuthStore();
const formRef = ref();
const loading = ref(false);
const form = reactive({ email: '', password: '', department: '' });
const rules = {
  email: [{ required: true, message: '请输入邮箱', trigger: 'blur' }],
  password: [{ required: true, min: 8, message: '密码至少 8 位，并包含字母和数字', trigger: 'blur' }]
};

async function submit() {
  if (!(await formRef.value?.validate())) return;
  loading.value = true;
  try {
    const response: any = await register(form);
    authStore.setAuth(response.access_token, response.user);
    ElMessage.success('注册成功');
    await router.push('/workspace/entry');
  } finally {
    loading.value = false;
  }
}
</script>

<style scoped>
.auth-form-view { display: flex; flex-direction: column; gap: 18px; }
h2 { margin: 0; font-size: var(--text-h1); color: var(--text-primary); }
.subtitle { margin: 0; color: var(--text-muted); line-height: 1.6; }
.submit-button { width: 100%; min-height: 44px; }
.back-link { color: var(--blue-600); text-align: center; }
</style>
