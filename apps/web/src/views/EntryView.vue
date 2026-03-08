<template>
  <div class="page">
    <section class="hero">
      <div class="hero-copy">
        <el-tag effect="dark" round>企业文档 RAG / 证据优先 / 问答闭环</el-tag>
        <h1>围绕企业知识库组织上传、检索与有依据问答</h1>
        <p>
          当前工作台聚焦制度、流程、规范、FAQ 与项目文档。
          系统只保留一条企业 RAG-QA 主业务线：文档上传、异步 ingest、混合检索、证据化回答。
        </p>
      </div>
    </section>

    <section class="entry-grid">
      <el-card shadow="hover" class="entry-card kb-card">
        <div class="entry-badge">Enterprise RAG</div>
        <h2>企业知识库 QA 业务线</h2>
        <p>支持 txt / pdf / docx 批量导入，进入知识库批处理、状态追踪与证据化问答工作台。</p>
        <ul>
          <li>第 1 步：上传文档到知识库，由 worker 异步 ingest</li>
          <li>第 2 步：基于 section / chunk / vector 做混合检索</li>
          <li>第 3 步：以证据和引文为约束生成统一 QA 回答</li>
        </ul>
        <div class="entry-actions">
          <el-button type="primary" @click="router.push('/workspace/kb/upload')">进入上传</el-button>
          <el-button plain @click="router.push('/workspace/kb/chat')">进入问答</el-button>
        </div>
      </el-card>
    </section>
  </div>
</template>

<script setup lang="ts">
import { useRouter } from 'vue-router';

const router = useRouter();
</script>

<style scoped>
.page {
  display: flex;
  flex-direction: column;
  gap: 24px;
}

.hero {
  padding: 36px;
  border-radius: 28px;
  background:
    radial-gradient(circle at top left, rgba(37, 99, 235, 0.18), transparent 32%),
    radial-gradient(circle at bottom right, rgba(15, 118, 110, 0.18), transparent 30%),
    linear-gradient(135deg, #ffffff, #f8fafc);
  border: 1px solid rgba(148, 163, 184, 0.2);
}

.hero-copy {
  max-width: 760px;
}

.hero-copy h1 {
  margin: 16px 0 12px;
  font-size: 44px;
  line-height: 1.1;
}

.hero-copy p {
  margin: 0;
  font-size: 17px;
  line-height: 1.8;
  color: var(--text-regular);
}

.entry-grid {
  display: grid;
  grid-template-columns: minmax(0, 1fr);
  gap: 20px;
}

.entry-card {
  border-radius: 28px;
  border: none;
}

.entry-card :deep(.el-card__body) {
  padding: 28px;
}

.entry-badge {
  display: inline-flex;
  padding: 6px 12px;
  border-radius: 999px;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.kb-card {
  background: linear-gradient(180deg, rgba(15, 118, 110, 0.08), #ffffff);
}

.kb-card .entry-badge {
  background: rgba(15, 118, 110, 0.14);
  color: #0f766e;
}

.entry-card h2 {
  margin: 18px 0 10px;
  font-size: 30px;
}

.entry-card p {
  margin: 0;
  line-height: 1.7;
  color: var(--text-regular);
}

.entry-card ul {
  margin: 18px 0 0;
  padding-left: 20px;
  color: var(--text-regular);
  line-height: 1.8;
}

.entry-actions {
  display: flex;
  gap: 12px;
  margin-top: 24px;
  flex-wrap: wrap;
}

@media (max-width: 960px) {
  .hero-copy h1 {
    font-size: 34px;
  }
}
</style>
