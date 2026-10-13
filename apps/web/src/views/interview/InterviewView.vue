<template>
  <div class="page-shell interview-page">
    <PageHeaderCompact title="AI 模拟面试">
      <template #subtitle>题目只来自已发布且可追溯的知识库题池</template>
    </PageHeaderCompact>

    <main class="interview-content">
      <section v-if="!session" class="panel setup-panel">
        <div class="panel-header"><h2>开始一场面试</h2></div>
        <el-form label-position="top" @submit.prevent>
          <el-form-item label="岗位">
            <el-select v-model="form.job_position_id" clearable filterable placeholder="选择岗位" style="width: 100%">
              <el-option v-for="item in positions" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <el-form-item label="知识库">
            <el-select v-model="form.base_id" filterable placeholder="选择知识库" style="width: 100%">
              <el-option v-for="item in availableBases" :key="item.id" :label="item.name" :value="item.id" />
            </el-select>
          </el-form-item>
          <div class="form-row">
            <el-form-item label="题数"><el-input-number v-model="form.question_count" :min="1" :max="50" /></el-form-item>
            <el-form-item label="难度"><el-input v-model="form.difficulty" placeholder="留空表示不限" /></el-form-item>
            <el-form-item label="题型"><el-input v-model="form.question_type" placeholder="留空表示不限" /></el-form-item>
          </div>
          <el-button type="primary" :loading="loading" :disabled="!form.base_id || !form.job_position_id" @click="start">开始面试</el-button>
        </el-form>
      </section>

      <section v-else-if="!completed" class="panel question-panel">
        <div class="panel-header">
          <h2>第 {{ currentQuestion?.sequence_no || 1 }} 题</h2>
          <el-tag effect="plain">{{ currentQuestion?.difficulty || '未标注难度' }}</el-tag>
        </div>
        <p class="question-stem">{{ currentQuestion?.stem }}</p>
        <el-input v-model="answer" type="textarea" :rows="8" maxlength="30000" show-word-limit placeholder="输入你的回答" />
        <div class="question-actions">
          <span class="muted">来源已绑定到知识库文档与切片</span>
          <el-button type="primary" :loading="loading" :disabled="!answer.trim()" @click="submitAnswer">提交回答</el-button>
        </div>
        <div v-if="lastEvaluation" class="evaluation-note">
          <strong>本题评分：{{ lastEvaluation.total_score }}/10</strong>
          <span>{{ lastEvaluation.feedback }}</span>
        </div>
      </section>

      <section v-else class="panel report-panel">
        <div class="panel-header"><h2>面试报告</h2><el-button @click="reset">再来一场</el-button></div>
        <div class="score-grid">
          <div class="score-item"><span>总分</span><strong>{{ report?.total_score ?? 0 }}</strong></div>
          <div v-for="(score, key) in report?.dimension_scores || {}" :key="key" class="score-item"><span>{{ key }}</span><strong>{{ score }}</strong></div>
        </div>
        <el-table :data="report?.items || []" size="small">
          <el-table-column prop="sequence_no" label="#" width="56" />
          <el-table-column prop="stem" label="题目" min-width="260" show-overflow-tooltip />
          <el-table-column prop="total_score" label="得分" width="80" />
          <el-table-column label="来源" min-width="220">
            <template #default="{ row }">{{ row.source?.[0]?.document_id || '-' }} / {{ row.source?.[0]?.chunk_id || '-' }}</template>
          </el-table-column>
        </el-table>
      </section>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, reactive, ref, watch } from 'vue';
import { ElMessage } from 'element-plus';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import { listKBJobPositions, listKnowledgeBases } from '@/api/kb';
import { answerInterview, getInterviewReport, startInterview, type InterviewAnswerResponse, type InterviewQuestion, type InterviewSessionResponse } from '@/api/interview';

const bases = ref<any[]>([]);
const positions = ref<any[]>([]);
const session = ref<InterviewSessionResponse | null>(null);
const currentQuestion = ref<InterviewQuestion | null>(null);
const report = ref<any>(null);
const lastEvaluation = ref<InterviewAnswerResponse['evaluation'] | null>(null);
const answer = ref('');
const loading = ref(false);
const completed = ref(false);
const form = reactive({ base_id: '', job_position_id: '', question_count: 5, difficulty: '', question_type: '' });
const availableBases = computed(() => {
  if (!form.job_position_id) return [];
  return bases.value.filter((base) =>
    (base.job_positions || []).some((position: { id?: string }) => position.id === form.job_position_id),
  );
});

async function loadOptions() {
  const [baseResult, positionResult] = await Promise.all([listKnowledgeBases(), listKBJobPositions()]);
  bases.value = (baseResult as any)?.items || [];
  positions.value = (positionResult as any)?.items || [];
}

async function start() {
  loading.value = true;
  try {
    const result = await startInterview(form);
    session.value = result as any;
    currentQuestion.value = (result as any).question;
    completed.value = false;
    answer.value = '';
  } catch {
    // request layer displays the server error.
  } finally {
    loading.value = false;
  }
}

async function submitAnswer() {
  if (!session.value || !currentQuestion.value) return;
  loading.value = true;
  try {
    const result = await answerInterview(session.value.session_id, currentQuestion.value.id, answer.value);
    lastEvaluation.value = result.evaluation;
    if (result.completed) {
      completed.value = true;
      report.value = await getInterviewReport(session.value.session_id);
    } else {
      currentQuestion.value = result.next_question;
      answer.value = '';
    }
  } catch {
    ElMessage.error('回答提交失败，请稍后重试');
  } finally {
    loading.value = false;
  }
}

function reset() {
  session.value = null;
  currentQuestion.value = null;
  report.value = null;
  lastEvaluation.value = null;
  completed.value = false;
  answer.value = '';
}

onMounted(() => loadOptions().catch(() => undefined));
watch(() => form.job_position_id, () => {
  if (!availableBases.value.some((base) => base.id === form.base_id)) form.base_id = '';
});
</script>

<style scoped>
.interview-page { display: flex; flex-direction: column; height: 100%; overflow: hidden; }
.interview-content { flex: 1; overflow: auto; padding: 20px; background: var(--bg-panel-muted); }
.panel { max-width: 960px; margin: 0 auto; background: var(--bg-panel); border: 1px solid var(--border-color); border-radius: var(--radius-sm); padding: 20px; }
.panel-header, .question-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.panel-header h2 { margin: 0; font-size: 18px; }
.form-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.question-stem { font-size: 20px; line-height: 1.6; margin: 24px 0; white-space: pre-wrap; }
.question-actions { margin-top: 16px; }
.evaluation-note { margin-top: 18px; padding: 12px; background: var(--bg-panel-muted); display: flex; flex-direction: column; gap: 4px; }
.score-grid { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0; }
.score-item { min-width: 110px; padding: 12px; border: 1px solid var(--border-color); display: flex; flex-direction: column; gap: 5px; }
.score-item strong { font-size: 22px; }
.muted { color: var(--text-secondary); font-size: 13px; }
@media (max-width: 680px) { .interview-content { padding: 12px; } .form-row { grid-template-columns: 1fr; } .question-stem { font-size: 18px; } .question-actions { align-items: flex-start; flex-direction: column; } }
</style>
