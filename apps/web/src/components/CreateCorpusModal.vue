<template>
  <el-dialog v-model="visible" title="新建知识库" width="500px" @closed="handleClosed">
    <el-form :model="form" ref="formRef" :rules="rules" label-width="100px">
      <el-form-item label="名称" prop="name">
        <el-input v-model="form.name" placeholder="输入知识库名称" />
      </el-form-item>
      <el-form-item label="描述" prop="description">
        <el-input v-model="form.description" type="textarea" placeholder="输入知识库描述" />
      </el-form-item>
    </el-form>
    <template #footer>
      <span class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button type="primary" :loading="loading" @click="handleSubmit">
          确认
        </el-button>
      </span>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, reactive } from 'vue';
import { createCorpus } from '@/api/corpora';
import { ElMessage } from 'element-plus';

const emit = defineEmits(['success']);

const visible = ref(false);
const loading = ref(false);
const formRef = ref();

const form = reactive({
  name: '',
  description: ''
});

const rules = {
  name: [{ required: true, message: '请输入名称', trigger: 'blur' }]
};

const open = () => {
  visible.value = true;
};

const handleClosed = () => {
  if (formRef.value) formRef.value.resetFields();
};

const handleSubmit = async () => {
  if (!formRef.value) return;
  await formRef.value.validate(async (valid: boolean) => {
    if (valid) {
      loading.value = true;
      try {
        await createCorpus({ name: form.name, description: form.description });
        ElMessage.success('创建成功');
        visible.value = false;
        emit('success');
      } finally {
        loading.value = false;
      }
    }
  });
};

defineExpose({ open });
</script>
