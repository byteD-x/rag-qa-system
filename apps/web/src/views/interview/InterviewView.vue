<template>
  <div class="page-shell interview-page">
    <PageHeaderCompact title="AI 模拟面试">
          </PageHeaderCompact>

    <main class="interview-content">
      <Transition name="report-fade">
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
            </div>
            <el-button type="primary" :loading="loading" :disabled="!form.base_id || !form.job_position_id" @click="start">开始面试</el-button>
          </el-form>
        </section>

        <section v-else-if="!completed" class="panel question-panel">
          <div class="panel-header">
            <h2>第 {{ currentQuestion?.sequence_no || 1 }} 题</h2>
          </div>
          <div v-if="lastEvaluation" class="evaluation-note" role="status" aria-live="polite">
            <Transition name="eval-enter">
              <div :key="lastEvaluatedSeq ?? 0" class="evaluation-note-body">
                <strong>第 {{ lastEvaluatedSeq }} 题评分：{{ lastEvaluation.total_score }}/10</strong>
                <span>{{ lastEvaluation.feedback }}</span>
              </div>
            </Transition>
          </div>
          <p class="question-stem">{{ currentQuestion?.stem }}</p>
          <el-input ref="answerInput" v-model="answer" type="textarea" :rows="8" :readonly="loading" placeholder="输入你的回答" />
          <div class="question-actions">
            <span class="muted">{{ loading ? '评分中，请稍候…' : '' }}</span>
            <el-button type="primary" :loading="loading" :disabled="!answer.trim()" @click="submitAnswer">提交回答</el-button>
          </div>
        </section>

        <section v-else class="panel report-panel">
          <div class="panel-header"><h2>面试报告</h2><el-button @click="reset">再来一场</el-button></div>
          <template v-if="report">
            <div class="score-grid">
              <div class="score-item"><span>总分</span><strong>{{ report?.total_score }}</strong></div>
              <div v-for="(score, key) in report?.dimension_scores || {}" :key="key" class="score-item"><span>{{ key }}</span><strong>{{ score }}</strong></div>
            </div>
            <el-table :data="report?.items || []" size="small">
              <el-table-column prop="stem" label="题目" min-width="260">
                <template #default="{ row }">
                  <el-tooltip placement="top">
                    <template #content>
                      <div v-if="sourceText(row)">来源：{{ sourceText(row) }}</div>
                      <div class="tooltip-stem">{{ row.stem }}</div>
                    </template>
                    <span class="cell-clamp">{{ row.stem }}</span>
                  </el-tooltip>
                </template>
              </el-table-column>
              <el-table-column prop="total_score" label="得分" width="80" />
              <el-table-column label="反馈" min-width="220" show-overflow-tooltip>
                <template #default="{ row }">{{ row.feedback }}</template>
              </el-table-column>
              <el-table-column label="弱项" min-width="160" show-overflow-tooltip>
                <template #default="{ row }">{{ (row.weak_points || []).join('；') }}</template>
              </el-table-column>
            </el-table>
          </template>
          <LoadingState v-else-if="reportLoading" label="正在生成面试报告…" />
          <EnhancedEmpty
            v-else
            variant="search"
            title="报告未获取到"
            description="这场面试的记录还留在页面上，点击「重试」重新拉取报告。"
          >
            <template #actions>
              <el-button type="primary" @click="loadReport">重试</el-button>
            </template>
          </EnhancedEmpty>
        </section>
      </Transition>
    </main>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import LoadingState from '@/components/LoadingState.vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import { listKBJobPositions, listKnowledgeBases } from '@/api/kb';
import { answerInterview, getInterviewReport, startInterview, type InterviewAnswerResponse, type InterviewQuestion, type InterviewSessionResponse } from '@/api/interview';

const bases = ref<any[]>([]);
const positions = ref<any[]>([]);
const session = ref<InterviewSessionResponse | null>(null);
const currentQuestion = ref<InterviewQuestion | null>(null);
const report = ref<any>(null);
const reportLoading = ref(false);
const lastEvaluation = ref<InterviewAnswerResponse['evaluation'] | null>(null);
const lastEvaluatedSeq = ref<number | null>(null);
const answer = ref('');
const answerInput = ref<any>(null);
const loading = ref(false);
const completed = ref(false);
const form = reactive({ base_id: '', job_position_id: '', question_count: 5 });
const availableBases = computed(() => {
  if (!form.job_position_id) return [];
  return bases.value.filter((base) =>
    (base.job_positions || []).some((position: { id?: string }) => position.id === form.job_position_id),
  );
});

function sourceText(row: { source?: Array<{ document_id?: string; chunk_id?: string }> }) {
  const first = row.source?.[0];
  return [first?.document_id, first?.chunk_id].filter(Boolean).join(' / ');
}

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

async function loadReport() {
  const sessionId = session.value?.session_id;
  if (!sessionId) return;
  reportLoading.value = true;
  try {
    const result = await getInterviewReport(sessionId);
    if (session.value?.session_id === sessionId) report.value = result;
  } catch {
    report.value = null;
  } finally {
    reportLoading.value = false;
  }
}

async function submitAnswer() {
  if (!session.value || !currentQuestion.value) return;
  loading.value = true;
  try {
    const submittedSeq = currentQuestion.value.sequence_no;
    const result = await answerInterview(session.value.session_id, currentQuestion.value.id, answer.value);
    lastEvaluation.value = result.evaluation;
    lastEvaluatedSeq.value = submittedSeq;
    if (result.completed) {
      completed.value = true;
      await loadReport();
    } else {
      currentQuestion.value = result.next_question;
      await nextTick();
      answer.value = '';
      answerInput.value?.focus();
    }
  } catch {
    // request layer displays the server error.
  } finally {
    loading.value = false;
  }
}

function reset() {
  session.value = null;
  currentQuestion.value = null;
  report.value = null;
  lastEvaluation.value = null;
  lastEvaluatedSeq.value = null;
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
.panel { max-width: 960px; margin: 0 auto; }
.panel-header, .question-actions { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.panel-header h2 { margin: 0; font-size: var(--text-h2); }
.form-row { display: grid; grid-template-columns: repeat(3, minmax(0, 1fr)); gap: 12px; }
.question-stem { font-size: var(--text-h2); line-height: 1.6; margin: 24px 0; white-space: pre-wrap; }
.question-actions { margin-top: 16px; }
.evaluation-note { margin-top: 18px; padding: 12px; background: var(--bg-panel-muted); }
.evaluation-note-body { display: flex; flex-direction: column; gap: 4px; }
.eval-enter-enter-from { opacity: 0; transform: translateY(-4px); }
.eval-enter-enter-active { transition: opacity 200ms var(--ease-enter), transform 200ms var(--ease-enter); }
.report-panel.report-fade-enter-from { opacity: 0; }
.report-panel.report-fade-enter-active { transition: opacity var(--transition-smooth); }
.score-grid { display: flex; flex-wrap: wrap; gap: 12px; margin: 18px 0; }
.score-item { min-width: 110px; padding: 12px; display: flex; flex-direction: column; gap: 5px; }
.score-item strong { font-size: var(--text-h1); }
.cell-clamp { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.tooltip-stem { max-width: 320px; white-space: pre-wrap; }
.muted { color: var(--text-secondary); font-size: var(--text-caption); }
@media (max-width: 680px) { .interview-content { padding: 12px; } .form-row { grid-template-columns: 1fr; } .question-actions { align-items: flex-start; flex-direction: column; } }
</style>
