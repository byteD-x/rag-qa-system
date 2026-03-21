<template>
  <div class="citation-container">
    <el-collapse class="citation-collapse" v-model="activeNames">
      <el-collapse-item name="1">
        <template #title>
          <div class="citation-summary">
            <div class="citation-icon-wrap">
              <el-icon><Reading /></el-icon>
            </div>
            <span class="summary-text">{{ citations.length }} 个引用来源</span>
            <div class="citation-avatars">
              <div v-for="(_, i) in citations.slice(0, 3)" :key="i" class="citation-mini-badge">
                {{ i + 1 }}
              </div>
              <span v-if="citations.length > 3" class="citation-more">...</span>
            </div>
          </div>
        </template>
        
        <div class="citation-grid">
          <article v-for="(citation, index) in citations" :key="citation.unit_id || index" class="source-card">
            <div class="source-card-header">
              <span class="source-index">{{ index + 1 }}</span>
              <div class="source-title-group">
                <h4 class="source-title">{{ citation.section_title || citation.document_title || '未命名片段' }}</h4>
                <div class="source-meta">
                  <span v-if="citation.document_title && citation.section_title" class="meta-doc" :title="citation.document_title">
                    {{ citation.document_title }}
                  </span>
                  <span class="meta-divider" v-if="citation.document_title">·</span>
                  <span class="meta-tag">{{ citation.corpus_type || mode }}</span>
                  <span class="meta-tag" v-if="citation.version_label">{{ citation.version_label }}</span>
                  <span class="meta-tag" v-if="citation.is_current_version">当前生效</span>
                  <span class="meta-tag" v-if="citation.version_status">{{ citation.version_status }}</span>
                  <span class="meta-tag" v-if="evidenceKindLabel(citation)">{{ evidenceKindLabel(citation) }}</span>
                  <span class="meta-tag" v-if="citation.page_number">第 {{ citation.page_number }} 页</span>
                  <span class="meta-tag" v-if="regionLabel(citation)">{{ regionLabel(citation) }}</span>
                  <span class="meta-tag" v-if="typeof citation.confidence === 'number'">置信度 {{ (citation.confidence * 100).toFixed(1) }}%</span>
                </div>
              </div>
              <a :href="documentPath(citation)" target="_blank" class="source-link" title="查看原文">
                <el-icon><Document /></el-icon>
              </a>
            </div>

            <a v-if="citation.thumbnail_url && isVisualCitation(citation)" :href="documentPath(citation)" target="_blank" class="source-preview">
              <img :src="citation.thumbnail_url" alt="citation preview" class="source-thumbnail" />
            </a>
            
            <div class="source-content" v-if="citation.quote">
              <div v-if="citation.effective_from || citation.effective_to" class="source-timeline">
                <span v-if="citation.effective_from">生效自 {{ citation.effective_from }}</span>
                <span v-if="citation.effective_to">失效于 {{ citation.effective_to }}</span>
              </div>
              <div class="quote-text">{{ citation.quote }}</div>
              
              <div class="source-footer" v-if="citation.evidence_path?.final_score !== undefined">
                <div class="relevance-indicator">
                  <div class="relevance-track">
                    <div 
                      class="relevance-fill" 
                      :style="{ width: `${Math.min(100, Math.max(0, citation.evidence_path.final_score * 100))}%` }"
                      :class="getScoreClass(citation.evidence_path.final_score)"
                    ></div>
                  </div>
                  <span class="relevance-text">{{ (citation.evidence_path.final_score * 100).toFixed(1) }}% 相关</span>
                </div>
              </div>
            </div>
          </article>
        </div>
      </el-collapse-item>
    </el-collapse>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue';
import { Document, Reading } from '@element-plus/icons-vue';

interface CitationItem {
  unit_id: string;
  document_id: string;
  document_title?: string;
  section_title: string;
  char_range: string;
  quote: string;
  corpus_type?: 'kb';
  version_label?: string;
  version_status?: string;
  is_current_version?: boolean;
  effective_from?: string;
  effective_to?: string;
  evidence_kind?: 'document_chunk' | 'image_asset' | 'visual_region' | string;
  source_kind?: string;
  page_number?: number | null;
  region_label?: string;
  asset_id?: string;
  thumbnail_url?: string;
  bbox?: number[];
  confidence?: number | null;
  evidence_path?: {
    final_score?: number;
  };
}

const props = defineProps<{
  citations: CitationItem[];
  title?: string;
  mode: 'kb';
}>();

const activeNames = ref<string[]>([]);

const documentPath = (citation: CitationItem) => {
  const basePath = `/workspace/kb/documents/${citation.document_id}`;
  const search = new URLSearchParams();
  search.set('versionId', String(citation.document_id));
  if (isVisualCitation(citation) && citation.asset_id) {
    search.set('assetId', String(citation.asset_id));
    if (citation.source_kind === 'visual_region' && citation.unit_id) {
      search.set('regionId', String(citation.unit_id));
    }
  }
  const query = search.toString();
  return query ? `${basePath}?${query}` : basePath;
};

const isVisualCitation = (citation: CitationItem) => ['image_asset', 'visual_region'].includes(String(citation.evidence_kind || ''));

const regionLabel = (citation: CitationItem) => {
  if (citation.source_kind !== 'visual_region') {
    return '';
  }
  const explicitLabel = String(citation.region_label || '').trim();
  if (explicitLabel) {
    return explicitLabel;
  }
  const title = String(citation.section_title || '').trim();
  const match = title.match(/^Page\s+\d+\s+(.+)$/i);
  return (match?.[1] || title).trim();
};

const evidenceKindLabel = (citation: CitationItem) => {
  const value = String(citation.evidence_kind || '').trim();
  if (value === 'visual_region') return '截图区域';
  if (value === 'image_asset') return '截图证据';
  if (value === 'document_chunk') return '文档片段';
  return '';
};

const getScoreClass = (score: number) => {
  if (score >= 0.8) return 'fill-high';
  if (score >= 0.5) return 'fill-medium';
  return 'fill-low';
};
</script>

<style scoped>
.citation-container {
  margin-top: 12px;
  max-width: 100%;
}

.citation-collapse {
  border: 1px solid var(--border-color);
  border-radius: var(--radius-md);
  background: var(--bg-panel);
  overflow: hidden;
  transition: all var(--transition-base);
}

.citation-collapse:hover {
  border-color: rgba(37, 99, 235, 0.2);
}

.citation-collapse :deep(.el-collapse-item__header) {
  height: auto;
  line-height: 1.5;
  padding: 12px 16px;
  background: transparent;
  border-bottom: none;
  font-size: 13px;
  color: var(--text-secondary);
}

.citation-collapse :deep(.el-collapse-item__wrap) {
  border-bottom: none;
  background: transparent;
}

.citation-collapse :deep(.el-collapse-item__content) {
  padding: 0 16px 16px;
}

.citation-summary {
  display: flex;
  align-items: center;
  gap: 10px;
  width: 100%;
}

.citation-icon-wrap {
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--blue-600);
}

.summary-text {
  font-weight: 500;
  color: var(--text-primary);
  font-size: 13px;
}

.citation-avatars {
  display: flex;
  align-items: center;
  margin-left: auto;
  gap: -4px;
}

.citation-mini-badge {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-secondary);
  position: relative;
  margin-right: 4px;
}

.citation-more {
  font-size: 12px;
  color: var(--text-muted);
  margin-left: 4px;
}

.citation-grid {
  display: grid;
  gap: 12px;
  grid-template-columns: repeat(auto-fit, minmax(280px, 1fr));
  margin-top: 8px;
}

.source-card {
  display: flex;
  flex-direction: column;
  border: 1px solid var(--border-color);
  border-radius: var(--radius-sm);
  background: var(--bg-panel-muted);
  overflow: hidden;
}

.source-card-header {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 14px;
  background: rgba(255, 255, 255, 0.4);
  border-bottom: 1px solid var(--border-color);
}

.source-index {
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
  width: 20px;
  height: 20px;
  border-radius: 4px;
  background: var(--blue-50);
  color: var(--blue-600);
  font-size: 11px;
  font-weight: 600;
}

.source-title-group {
  flex: 1;
  min-width: 0;
}

.source-title {
  margin: 0;
  font-size: 13px;
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.source-meta {
  display: flex;
  align-items: center;
  gap: 6px;
  margin-top: 4px;
  font-size: 11px;
  color: var(--text-muted);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-doc {
  max-width: 120px;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-divider {
  color: var(--border-strong);
}

.meta-tag {
  padding: 1px 4px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: 3px;
  font-family: var(--font-mono);
}

.source-link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  border-radius: 4px;
  color: var(--text-secondary);
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  transition: all 0.2s;
}

.source-link:hover {
  color: var(--blue-600);
  border-color: var(--blue-200);
  background: var(--blue-50);
}

.source-preview {
  padding: 12px 14px 0;
}

.source-thumbnail {
  display: block;
  width: 100%;
  max-height: 132px;
  object-fit: cover;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.source-content {
  padding: 12px 14px;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-regular);
}

.source-timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: 11px;
  color: var(--text-muted);
}

.quote-text {
  display: -webkit-box;
  -webkit-line-clamp: 4;
  line-clamp: 4;
  -webkit-box-orient: vertical;
  overflow: hidden;
  position: relative;
  white-space: pre-wrap;
  word-break: break-word;
  padding-left: 16px;
  color: var(--text-secondary);
}

.quote-text::before {
  content: '"';
  color: var(--border-strong);
  font-family: serif;
  font-size: 28px;
  position: absolute;
  left: -2px;
  top: -8px;
  opacity: 0.5;
}

.source-footer {
  margin-top: 12px;
  padding-top: 12px;
  border-top: 1px dashed var(--border-color);
}

.relevance-indicator {
  display: flex;
  align-items: center;
  gap: 8px;
}

.relevance-track {
  flex: 1;
  height: 4px;
  background: var(--border-color);
  border-radius: 999px;
  overflow: hidden;
}

.relevance-fill {
  height: 100%;
  border-radius: 999px;
  transition: width 0.5s ease;
}

.fill-high { background: #10b981; }
.fill-medium { background: #f59e0b; }
.fill-low { background: #94a3b8; }

.relevance-text {
  font-size: 11px;
  font-family: var(--font-mono);
  color: var(--text-muted);
}
</style>
