<template>
  <div class="citation-container">
    <el-collapse class="citation-collapse" v-model="activeNames">
      <el-collapse-item name="1" :disabled="!expandable">
        <template #title>
          <div class="citation-summary">
            <div class="citation-icon-wrap">
              <el-icon><Reading /></el-icon>
            </div>
            <span class="summary-text">{{ citations.length }} 个引用来源</span>
          </div>
        </template>
        
        <div class="citation-grid">
          <article v-for="(citation, index) in citations" :key="citation.unit_id || index" class="source-card">
            <div class="source-card-header">
              <span class="source-index">{{ index + 1 }}</span>
              <div class="source-title-group">
                <h4 class="source-title">{{ citation.section_title || citation.document_title || '未命名片段' }}</h4>
                <div class="source-meta">
                  <span
                    v-if="citation.version_label || citation.is_current_version || citation.version_status"
                    class="meta-group meta-group--version"
                  >
                    <span v-if="citation.version_label" class="meta-tag">{{ citation.version_label }}</span>
                    <span v-if="citation.is_current_version" class="meta-tag">当前生效</span>
                    <span v-if="citation.version_status" class="meta-tag">{{ citation.version_status }}</span>
                  </span>
                  <span class="meta-group meta-group--location">
                    <span v-if="citation.document_title && citation.section_title" class="meta-doc" :title="citation.document_title">
                      {{ citation.document_title }}
                    </span>
                    <span class="meta-tag">{{ citation.corpus_type || mode }}</span>
                    <span v-if="evidenceKindLabel(citation)" class="meta-tag">{{ evidenceKindLabel(citation) }}</span>
                    <span v-if="citation.page_number" class="meta-tag">第 {{ citation.page_number }} 页</span>
                    <span v-if="regionLabel(citation)" class="meta-tag">{{ regionLabel(citation) }}</span>
                  </span>
                  <span v-if="typeof citation.confidence === 'number'" class="meta-group meta-group--score">
                    <span class="meta-tag" title="视觉区域识别置信度，来自 kb_visual_asset_regions.confidence">
                      区域识别 {{ (citation.confidence * 100).toFixed(1) }}%
                    </span>
                  </span>
                </div>
              </div>
              <a
                :href="documentPath(citation)"
                target="_blank"
                rel="noreferrer"
                class="source-link"
                aria-label="查看原文"
                title="查看原文"
              >
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
              
              <div class="source-footer" v-if="citation.evidence_path?.relevance !== undefined">
                <div class="relevance-indicator">
                  <div class="relevance-track">
                    <div 
                      class="relevance-fill" 
                      :style="{ width: `${Math.min(100, Math.max(0, citation.evidence_path.relevance * 100))}%` }"
                      :class="getScoreClass(citation.evidence_path.relevance)"
                    ></div>
                  </div>
                  <span
                    class="relevance-text"
                    title="检索相关性，来自 dense 单路余弦相似度（evidence_path.relevance）"
                  >{{ (citation.evidence_path.relevance * 100).toFixed(1) }}% 相关性</span>
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
    relevance?: number;
  };
}

const props = withDefaults(defineProps<{
  citations: CitationItem[];
  title?: string;
  mode: 'kb';
  defaultExpanded?: boolean;
  expandable?: boolean;
}>(), {
  expandable: true
});

const AUTO_EXPAND_LIMIT = 3;
const prefersExpanded = props.defaultExpanded ?? props.citations.length <= AUTO_EXPAND_LIMIT;
const expandedByDefault = !props.expandable || prefersExpanded;
const activeNames = ref<string[]>(expandedByDefault ? ['1'] : []);

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
  transition: border-color var(--transition-fast);
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
  font-size: var(--text-caption);
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
  font-size: var(--text-caption);
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
  border-radius: var(--radius-xs);
  background: var(--blue-50);
  color: var(--blue-600);
  font-size: var(--text-caption);
  font-weight: 600;
}

.source-title-group {
  flex: 1;
  min-width: 0;
}

.source-title {
  margin: 0;
  font-size: var(--text-caption);
  font-weight: 600;
  color: var(--text-primary);
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  line-height: 1.4;
}

.source-meta {
  display: flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px 10px;
  margin-top: 4px;
  font-size: var(--text-caption);
  color: var(--text-muted);
}

.meta-group {
  display: inline-flex;
  flex-wrap: wrap;
  align-items: center;
  gap: 4px;
}

.meta-doc {
  max-width: 120px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.meta-tag {
  padding: 1px 4px;
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  border-radius: var(--radius-xs);
  font-family: var(--font-mono);
}

.source-link {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 44px;
  height: 44px;
  border-radius: var(--radius-xs);
  color: var(--text-secondary);
  background: var(--bg-panel);
  border: 1px solid var(--border-color);
  transition: color var(--transition-fast), border-color var(--transition-fast), background-color var(--transition-fast);
}

.source-link:hover {
  color: var(--blue-600);
  border-color: var(--blue-500);
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
  border-radius: var(--radius-sm);
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.source-content {
  padding: 12px 14px;
  font-size: var(--text-caption);
  line-height: 1.6;
  color: var(--text-regular);
}

.source-timeline {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-bottom: 10px;
  font-size: var(--text-caption);
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
  font-size: var(--text-h1);
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
}

.fill-high { background: var(--el-color-success); }
.fill-medium { background: var(--el-color-warning); }
.fill-low { background: var(--slate-500); }

.relevance-text {
  font-size: var(--text-caption);
  font-family: var(--font-mono);
  color: var(--text-muted);
}
</style>
