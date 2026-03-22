<template>
  <div class="page-shell doc-page">
    <PageHeaderCompact :title="document?.file_name || '加载中'">
      <template #actions>
        <el-button plain @click="router.push('/workspace/kb/upload')">返回</el-button>
        <el-button plain :disabled="!document || !canWrite" @click="openEditDrawer">编辑</el-button>
        <el-button plain :disabled="!document" @click="router.push(`/workspace/kb/documents/${document.id}/chunks`)">切片管理</el-button>
        <el-button plain type="danger" :disabled="!document || !canWrite" @click="handleDeleteDocument">删除</el-button>
        <el-button
          v-if="document?.latest_job?.retryable && canManage"
          plain
          type="warning"
          :loading="retryingJob"
          @click="handleRetryIngest"
        >
          重试
        </el-button>
        <el-button type="primary" @click="goChat">按当前版本提问</el-button>
        <el-button plain :disabled="!document" @click="goCompareChat(selectedVersionId || document?.id)">比较提问</el-button>
      </template>
    </PageHeaderCompact>

    <div class="doc-content">
      <div v-if="!document" class="doc-loading">
        <el-icon class="is-loading" :size="24"><Loading /></el-icon>
        <span>加载中</span>
      </div>

      <template v-else>
        <div class="doc-info-row">
          <span class="info-item">{{ formatBytes(document.size_bytes) }}</span>
          <span class="info-item">{{ document.stats_json?.category || '-' }}</span>
          <span class="info-item">{{ document.version_label || '未命名版本' }}</span>
          <el-tag :type="statusMeta(document.status).type" size="small" effect="plain">
            {{ statusMeta(document.status).label }}
          </el-tag>
          <el-tag
            :type="document.is_current_version ? 'success' : 'info'"
            size="small"
            effect="plain"
          >
            {{ document.is_current_version ? '当前版本' : '历史版本' }}
          </el-tag>
          <el-tag
            :type="document.effective_now ? 'success' : 'warning'"
            size="small"
            effect="plain"
          >
            {{ document.effective_now ? '当前生效' : '未生效 / 已失效' }}
          </el-tag>
          <el-tag v-if="document.stats_json?.visual_asset_count" type="success" size="small" effect="plain">
            截图 {{ document.stats_json.visual_asset_count }} 张
          </el-tag>
        </div>

        <section class="smart-ask-panel">
          <div class="smart-ask-panel__header">
            <div>
              <h3>智能提问</h3>
              <p>围绕当前版本、版本比较和截图焦点，直接带上下文进入问答。</p>
            </div>
            <el-tag type="primary" effect="plain">{{ activeQuestionContextV2 }}</el-tag>
          </div>
          <div class="smart-ask-panel__tags">
            <el-tag size="small" effect="plain" type="success">
              当前版本 {{ document.version_label || `v${document.version_number || 1}` }}
            </el-tag>
            <el-tag v-if="compareVersionReady" size="small" effect="plain" type="warning">
              比较 {{ selectedVersionRecord?.version_label || `v${selectedVersionRecord?.version_number || 1}` }}
            </el-tag>
            <el-tag v-if="activeVisualFocusHint?.display_text" size="small" effect="plain" type="info">
              截图焦点 {{ activeVisualFocusHint.display_text }}
            </el-tag>
          </div>
          <el-input
            v-model="questionDraft"
            type="textarea"
            :rows="3"
            resize="none"
            :placeholder="smartQuestionPlaceholderV2"
          />
          <div class="smart-ask-panel__presets">
            <button type="button" class="smart-ask-preset" @click="applyQuestionTemplate('请总结这个版本的关键变化和影响。')">
              总结关键变化
            </button>
            <button type="button" class="smart-ask-preset" @click="applyQuestionTemplate('这个版本中最容易误解的地方是什么？')">
              标出易误解点
            </button>
            <button type="button" class="smart-ask-preset" @click="applyQuestionTemplate('如果我要按这个文档执行，应该特别注意哪些前置条件？')">
              提醒执行前置条件
            </button>
          </div>
          <div class="smart-ask-panel__actions">
            <el-button type="primary" @click="goChat()">按当前版本提问</el-button>
            <el-button plain :disabled="!compareVersionReady" @click="goCompareChat(String(selectedVersionRecord?.id || ''))">
              比较当前与所选版本
            </el-button>
            <el-button plain :disabled="!activeVisualFocusHint" @click="goFocusedVisualChat()">
              聚焦当前截图区域
            </el-button>
          </div>
        </section>

        <el-collapse v-model="activeCollapse">
          <el-collapse-item name="versions" title="版本治理">
            <template #title>
              <span>版本治理</span>
              <el-tag size="small" type="warning" style="margin-left: 8px">{{ versionHistory.length }} 个版本</el-tag>
            </template>
            <EnhancedEmpty
              v-if="!versionHistory.length"
              variant="document"
              title="暂无版本记录"
              description="当前文档还没有整理出版本家族信息。"
              class="chunk-empty"
            />
            <div v-else class="version-list">
              <article
                v-for="item in versionHistory"
                :key="item.id"
                class="version-card"
                :class="{ 'version-card--active': String(item.id) === String(selectedVersionId || document.id) }"
              >
                <div class="version-card__header">
                  <strong>{{ item.version_label || `v${item.version_number || 1}` }}</strong>
                  <div class="version-card__tags">
                    <el-tag size="small" effect="plain" :type="item.is_current_version ? 'success' : 'info'">
                      {{ item.is_current_version ? '当前' : '非当前' }}
                    </el-tag>
                    <el-tag size="small" effect="plain" :type="item.effective_now ? 'success' : 'warning'">
                      {{ item.effective_now ? '生效中' : '非生效' }}
                    </el-tag>
                  </div>
                </div>
                <div class="version-card__meta">
                  <span>{{ item.file_name }}</span>
                  <span>状态：{{ item.version_status || '-' }}</span>
                  <span>版本号：{{ item.version_number || 1 }}</span>
                  <span>生效开始：{{ formatDateTime(item.effective_from) }}</span>
                  <span>生效结束：{{ formatDateTime(item.effective_to) }}</span>
                </div>
                <div class="version-card__actions">
                  <el-button size="small" plain @click="inspectVersion(item)">查看内容</el-button>
                  <el-button size="small" plain type="primary" @click="goChat(String(item.id || ''))">按此版本提问</el-button>
                  <el-button
                    v-if="String(item.id) !== String(document.id)"
                    size="small"
                    type="primary"
                    plain
                    @click="inspectVersion(item, true)"
                  >
                    对比当前
                  </el-button>
                  <el-button
                    v-if="String(item.id) !== String(document.id)"
                    size="small"
                    plain
                    @click="goCompareChat(String(item.id || ''))"
                  >
                    比较提问
                  </el-button>
                </div>
              </article>
            </div>
            <div v-if="selectedVersionContent" class="version-inspector">
              <div class="version-inspector__header">
                <div>
                  <strong>{{ selectedVersionContent.version_label || selectedVersionContent.file_name }}</strong>
                  <span class="version-inspector__sub">
                    {{ selectedVersionContent.section_count }} 节 / {{ selectedVersionContent.chunk_count }} 个切片
                  </span>
                </div>
                <el-tag size="small" effect="plain" :type="selectedVersionContent.is_current_version ? 'success' : 'info'">
                  {{ selectedVersionContent.is_current_version ? '当前版本' : '历史版本' }}
                </el-tag>
              </div>
              <el-tabs v-model="versionInspectorTab">
                <el-tab-pane label="快速摘要" name="summary">
                  <EnhancedEmpty
                    v-if="!selectedVersionSummary.items.length && !selectedVersionSummary.fallback_excerpt"
                    variant="document"
                    title="暂无摘要"
                    description="当前版本还没有可提炼的正文内容，请切换到完整内容查看原文。"
                    class="chunk-empty"
                  />
                  <div v-else class="version-summary">
                    <div class="version-summary__meta">
                      <strong>快速摘要</strong>
                      <span>
                        已提炼 {{ selectedVersionSummary.items.length }} / {{ selectedVersionSummary.total_section_count || selectedVersionSummary.items.length }} 个章节
                      </span>
                    </div>
                    <article
                      v-for="item in selectedVersionSummary.items"
                      :key="item.key"
                      class="version-summary-card"
                    >
                      <div class="version-summary-card__header">
                        <strong>{{ item.title }}</strong>
                        <span>{{ item.char_count }} 字</span>
                      </div>
                      <p>{{ item.excerpt }}</p>
                    </article>
                    <article
                      v-if="selectedVersionSummary.fallback_excerpt"
                      class="version-summary-card version-summary-card--fallback"
                    >
                      <div class="version-summary-card__header">
                        <strong>全文摘要</strong>
                        <span>自动回退</span>
                      </div>
                      <p>{{ selectedVersionSummary.fallback_excerpt }}</p>
                    </article>
                    <p v-if="selectedVersionSummary.hidden_section_count > 0" class="version-summary__hint">
                      还有 {{ selectedVersionSummary.hidden_section_count }} 个章节未展开，可切换到“版本内容”查看完整文本。
                    </p>
                  </div>
                </el-tab-pane>
                <el-tab-pane label="版本内容" name="content">
                  <div class="version-sections">
                    <article v-for="section in selectedVersionContent.sections || []" :key="`${section.section_index}:${section.section_title}`" class="version-section">
                      <strong>{{ section.section_title || `Section ${section.section_index + 1}` }}</strong>
                      <pre>{{ section.text_content || '(空)' }}</pre>
                    </article>
                  </div>
                </el-tab-pane>
                <el-tab-pane label="与当前版本差异" name="diff">
                  <EnhancedEmpty
                    v-if="!selectedVersionDiff?.diff?.diff_text"
                    variant="document"
                    title="暂无文本差异"
                    description="当前查看版本与对比目标没有正文差异。"
                    class="chunk-empty"
                  />
                  <template v-else>
                    <div class="version-diff-summary">
                      <span>新增切片：{{ selectedVersionDiff.diff.summary?.added_chunks || 0 }}</span>
                      <span>删除切片：{{ selectedVersionDiff.diff.summary?.removed_chunks || 0 }}</span>
                      <span>修改切片：{{ selectedVersionDiff.diff.summary?.modified_chunks || 0 }}</span>
                      <span>变更章节：{{ selectedVersionDiff.diff.summary?.changed_sections || 0 }}</span>
                    </div>
                    <pre class="version-diff-text">{{ selectedVersionDiff.diff.diff_text }}</pre>
                  </template>
                </el-tab-pane>
              </el-tabs>
            </div>
          </el-collapse-item>

          <el-collapse-item name="chunks" title="知识切片概览">
            <template #title>
              <span>知识切片概览</span>
              <el-tag size="small" type="info" style="margin-left: 8px">{{ sectionPreview.length }} 项</el-tag>
            </template>
            <EnhancedEmpty
              v-if="!sectionPreview.length"
              variant="document"
              title="暂无切片"
              description="文档切片完成后会在这里展示"
              class="chunk-empty"
            />
            <div v-else class="chunk-grid">
              <div v-for="(item, index) in sectionPreview" :key="index" class="chunk-node">
                <span class="chunk-index">#{{ Number(index) + 1 }}</span>
                <span class="chunk-text">{{ String(item).slice(0, 120) }}{{ String(item).length > 120 ? '…' : '' }}</span>
                <span class="chunk-meta">{{ String(item).length }} 字符</span>
              </div>
            </div>
          </el-collapse-item>

          <el-collapse-item name="visuals" title="截图资产">
            <template #title>
              <span>截图资产</span>
              <el-tag size="small" type="success" style="margin-left: 8px">{{ visualAssets.length }} 张</el-tag>
            </template>
            <EnhancedEmpty
              v-if="!visualAssets.length"
              variant="document"
              title="暂无截图资产"
              description="视觉增强完成后会在这里展示文档里的截图"
              class="chunk-empty"
            />
            <div v-else class="visual-grid">
              <article v-for="asset in visualAssets" :id="visualAssetDomId(asset.asset_id)" :key="asset.asset_id" class="visual-card" :class="{ 'visual-card--focused': isFocusedAsset(asset.asset_id) }">
                <div class="visual-thumb-wrap">
                  <img
                    v-if="asset.thumbnail_url"
                    :src="asset.thumbnail_url"
                    :alt="asset.file_name || 'visual asset'"
                    class="visual-thumb"
                    @click="focusVisualAsset(asset.asset_id)"
                  />
                  <div v-if="asset.thumbnail_url && focusedRegionForAsset(asset) && focusedRegionBoxStyle(asset).width" class="visual-region-box" :style="focusedRegionBoxStyle(asset)"></div>
                  <div v-if="!asset.thumbnail_url" class="visual-thumb visual-thumb--empty">无预览</div>
                </div>
                <div class="visual-meta">
                  <strong>{{ asset.file_name || `截图 ${asset.asset_index || ''}` }}</strong>
                  <span>{{ asset.page_number ? `第 ${asset.page_number} 页` : '内嵌图片' }}</span>
                  <span>{{ asset.status || '-' }}</span>
                  <span v-if="visualRegionsFor(asset).length">区域 {{ visualRegionsFor(asset).length }} 个</span>
                </div>
                <div v-if="visualRegionsFor(asset).length" class="visual-region-list">
                  <article v-for="region in visualRegionsFor(asset)" :id="visualRegionDomId(region.region_id)" :key="region.region_id" class="visual-region-item" :class="{ 'visual-region-item--focused': isFocusedRegion(region.region_id) }" @click="focusVisualRegion(asset.asset_id, region.region_id)">
                    <strong>{{ region.region_label }}</strong>
                    <span v-if="region.layout_hints?.length">{{ region.layout_hints.join(' / ') }}</span>
                    <span v-if="region.confidence !== null && region.confidence !== undefined">
                      置信度 {{ (Number(region.confidence) * 100).toFixed(1) }}%
                    </span>
                    <span v-if="region.bbox?.length === 4">
                      坐标 {{ region.bbox.map((item: number) => Number(item).toFixed(2)).join(', ') }}
                    </span>
                    <span>{{ region.summary || '无摘要' }}</span>
                  </article>
                </div>
              </article>
            </div>
            <div v-if="compareVersionReady" class="visual-compare-panel">
              <div class="visual-compare-panel__header">
                <div>
                  <strong>跨版本截图区域差异高亮</strong>
                  <p>
                    当前 {{ document.version_label || '当前版本' }} vs {{ selectedVersionRecord?.version_label || '所选版本' }}
                  </p>
                </div>
                <el-tag size="small" effect="plain" :type="compareVisualMatch.strategy === 'region' ? 'success' : compareVisualMatch.strategy === 'asset' ? 'warning' : 'info'">
                  {{ compareVisualModeLabel }}
                </el-tag>
              </div>
              <EnhancedEmpty
                v-if="!focusedVisualAsset"
                variant="document"
                title="请选择要对比的截图区域"
                description="先点击当前版本中的截图或红框区域，系统会自动尝试在所选历史版本中匹配对应区域并生成差异高亮。"
                class="chunk-empty"
              />
              <div v-else-if="compareVisualBundleLoading || compareVisualDiffLoading" class="visual-compare-panel__loading">
                <el-icon class="is-loading"><Loading /></el-icon>
                <span>正在生成跨版本截图差异...</span>
              </div>
              <EnhancedEmpty
                v-else-if="compareVisualDiffError"
                variant="document"
                title="差异高亮生成失败"
                :description="compareVisualDiffError"
                class="chunk-empty"
              />
              <EnhancedEmpty
                v-else-if="!compareVisualAsset"
                variant="document"
                title="未找到可对照的历史截图"
                description="当前截图区域在所选版本中没有找到足够接近的页面或区域，建议切换版本后重试。"
                class="chunk-empty"
              />
              <template v-else>
                <div class="visual-compare-panel__summary">
                  <span>当前区域：{{ focusedVisualRegion?.region_label || `第 ${focusedVisualAsset.page_number || '-'} 页截图` }}</span>
                  <span>对照区域：{{ compareVisualRegion?.region_label || `第 ${compareVisualAsset.page_number || '-'} 页截图` }}</span>
                  <span>历史版本区域数：{{ compareVisualRegionsFor(compareVisualAsset).length }}</span>
                  <span>变化像素：{{ (visualDiffState.changedRatio * 100).toFixed(1) }}%</span>
                </div>
                <div class="visual-compare-grid">
                  <article class="visual-compare-card">
                    <div class="visual-compare-card__meta">
                      <strong>{{ document.version_label || '当前版本' }}</strong>
                      <span>{{ focusedVisualRegion?.region_label || '当前截图区域' }}</span>
                    </div>
                    <canvas ref="currentVisualCompareCanvas" class="visual-compare-canvas"></canvas>
                  </article>
                  <article class="visual-compare-card">
                    <div class="visual-compare-card__meta">
                      <strong>{{ selectedVersionRecord?.version_label || '对照版本' }}</strong>
                      <span>{{ compareVisualRegion?.region_label || '自动回退到同页截图' }}</span>
                    </div>
                    <canvas ref="compareVisualCompareCanvas" class="visual-compare-canvas"></canvas>
                  </article>
                  <article class="visual-compare-card visual-compare-card--diff">
                    <div class="visual-compare-card__meta">
                      <strong>变化热区</strong>
                      <span v-if="visualDiffState.bounds">橙框代表主要变化区域</span>
                      <span v-else>未检测到明显像素变化</span>
                    </div>
                    <canvas ref="visualDiffCanvas" class="visual-compare-canvas"></canvas>
                  </article>
                </div>
              </template>
            </div>
          </el-collapse-item>

          <el-collapse-item name="events" title="处理事件">
            <DocumentEvents :items="events" title="处理事件" description="" />
          </el-collapse-item>
        </el-collapse>
      </template>
    </div>

    <el-drawer
      v-model="editDrawerVisible"
      title="编辑文档"
      size="380px"
      destroy-on-close
      @close="cancelEditDocument"
    >
      <el-form label-position="top" style="padding: 0 16px">
        <el-form-item label="文件名">
          <el-input v-model="documentForm.file_name" placeholder="文件名" />
        </el-form-item>
        <el-form-item label="分类">
          <el-input v-model="documentForm.category" placeholder="分类" />
        </el-form-item>
        <el-divider content-position="left">版本治理</el-divider>
        <el-form-item label="版本家族 Key">
          <el-input v-model="documentForm.version_family_key" placeholder="同一份文档不同版本建议保持一致" />
        </el-form-item>
        <el-form-item label="版本标签">
          <el-input v-model="documentForm.version_label" placeholder="例如 v2 / 2026-Q1" />
        </el-form-item>
        <el-form-item label="版本号">
          <el-input-number v-model="documentForm.version_number" :min="1" :max="100000" style="width: 100%" />
        </el-form-item>
        <el-form-item label="版本状态">
          <el-select v-model="documentForm.version_status" style="width: 100%">
            <el-option v-for="item in versionStatusOptions" :key="item" :label="item" :value="item" />
          </el-select>
        </el-form-item>
        <el-form-item label="当前版本">
          <el-switch v-model="documentForm.is_current_version" />
        </el-form-item>
        <el-form-item label="生效开始">
          <el-date-picker
            v-model="documentForm.effective_from"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss[Z]"
            placeholder="可选"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="生效结束">
          <el-date-picker
            v-model="documentForm.effective_to"
            type="datetime"
            value-format="YYYY-MM-DDTHH:mm:ss[Z]"
            placeholder="可选"
            style="width: 100%"
          />
        </el-form-item>
        <el-form-item label="被当前版本替代的旧文档 ID">
          <el-input v-model="documentForm.supersedes_document_id" placeholder="可选，用于建立新旧版本关系" />
        </el-form-item>
        <el-form-item>
          <el-button type="primary" :disabled="!canWrite" @click="saveDocument">保存</el-button>
          <el-button @click="cancelEditDocument">取消</el-button>
        </el-form-item>
      </el-form>
    </el-drawer>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, reactive, ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { ElMessage, ElMessageBox } from 'element-plus';
import { Loading } from '@element-plus/icons-vue';
import DocumentEvents from '@/components/DocumentEvents.vue';
import EnhancedEmpty from '@/components/EnhancedEmpty.vue';
import PageHeaderCompact from '@/components/PageHeaderCompact.vue';
import { useAuthStore } from '@/store/auth';
import {
  deleteKBDocument,
  getKBDocument,
  getKBDocumentEvents,
  getKBDocumentVersionContent,
  getKBDocumentVersionDiff,
  getKBDocumentVersions,
  getKBVisualAssetRegions,
  getKBDocumentVisualAssets,
  retryKBIngestJob,
  updateKBDocument
} from '@/api/kb';
import { buildKbChatRouteQuery } from '@/views/chat/chatRoutePresets';
import { buildCompareVersionsFocus, buildSingleVersionFocus, buildVisualFocus } from '@/views/kb/kbChatFocus';
import { computePixelDiffMask, findBestMatchingCompareVisual, resolveVisualRegionBox } from '@/views/kb/kbVisualCompare';
import { buildVersionSummary } from '@/views/kb/kbVersionSummary';
import { formatBytes } from '@/utils/format';
import { statusMeta } from '@/utils/status';

const route = useRoute();
const router = useRouter();
const authStore = useAuthStore();

const document = ref<any | null>(null);
const events = ref<any[]>([]);
const visualAssets = ref<any[]>([]);
const visualRegionsByAsset = ref<Record<string, any[]>>({});
const compareVisualAssets = ref<any[]>([]);
const compareVisualRegionsByAsset = ref<Record<string, any[]>>({});
const compareVisualBundleLoading = ref(false);
const compareVisualDiffLoading = ref(false);
const compareVisualDiffError = ref('');
const focusedVisualAssetId = ref('');
const focusedVisualRegionId = ref('');
const versionHistory = ref<any[]>([]);
const selectedVersionId = ref('');
const selectedVersionContent = ref<any | null>(null);
const selectedVersionDiff = ref<any | null>(null);
const versionInspectorTab = ref<'summary' | 'content' | 'diff'>('content');
const questionDraft = ref('');
const retryingJob = ref(false);
const editDrawerVisible = ref(false);
const activeCollapse = ref<string[]>(['versions', 'chunks', 'visuals']);
const versionStatusOptions = ['active', 'draft', 'superseded', 'archived'];
const currentVisualCompareCanvas = ref<HTMLCanvasElement | null>(null);
const compareVisualCompareCanvas = ref<HTMLCanvasElement | null>(null);
const visualDiffCanvas = ref<HTMLCanvasElement | null>(null);
const visualDiffState = reactive({
  changedRatio: 0,
  changedPixels: 0,
  totalPixels: 0,
  bounds: null as { left: number; top: number; right: number; bottom: number } | null
});
const visualBundleCache = new Map<string, { assets: any[]; regionsByAsset: Record<string, any[]> }>();

const documentForm = reactive({
  file_name: '',
  category: '',
  version_family_key: '',
  version_label: '',
  version_number: 1,
  version_status: 'active',
  is_current_version: true,
  effective_from: '',
  effective_to: '',
  supersedes_document_id: ''
});

const sectionPreview = computed(() => document.value?.stats_json?.section_preview || []);
const canWrite = computed(() => authStore.hasPermission('kb.write'));
const canManage = computed(() => authStore.hasPermission('kb.manage'));
const selectedVersionSummary = computed(() => buildVersionSummary(selectedVersionContent.value, {
  maxItems: 5,
  maxChars: 180
}));
const selectedVersionRecord = computed(() => {
  const selectedId = String(selectedVersionId.value || document.value?.id || '');
  return versionHistory.value.find((item: any) => String(item.id) === selectedId) || document.value || null;
});
const compareVersionReady = computed(() => Boolean(document.value?.id && selectedVersionRecord.value?.id && String(selectedVersionRecord.value.id) !== String(document.value.id)));
const focusedVisualAsset = computed(() => visualAssets.value.find((item: any) => String(item.asset_id) === focusedVisualAssetId.value) || null);
const focusedVisualRegion = computed(() => {
  if (!focusedVisualAsset.value) {
    return null;
  }
  return visualRegionsFor(focusedVisualAsset.value).find((item: any) => String(item.region_id) === focusedVisualRegionId.value) || null;
});
const focusedVisualDocumentRecord = computed(() => {
  const assetDocumentId = String(focusedVisualAsset.value?.document_id || '');
  if (!assetDocumentId) {
    return document.value || null;
  }
  return (
    versionHistory.value.find((item: any) => String(item.id) === assetDocumentId)
    || (String(document.value?.id || '') === assetDocumentId ? document.value : null)
    || document.value
    || null
  );
});
const activeVisualFocusHint = computed(() => {
  const asset = focusedVisualAsset.value;
  if (!document.value || !asset) {
    return undefined;
  }
  return buildVisualFocus({
    documentId: String(asset.document_id || focusedVisualDocumentRecord.value?.id || document.value.id || ''),
    assetId: String(asset.asset_id || ''),
    regionId: String(focusedVisualRegion.value?.region_id || ''),
    regionLabel: String(focusedVisualRegion.value?.region_label || ''),
    pageNumber: Number(focusedVisualRegion.value?.page_number || asset.page_number || 0) || undefined,
    versionLabel: String(focusedVisualDocumentRecord.value?.version_label || document.value.version_label || '')
  });
});
const compareVisualReady = computed(() => Boolean(compareVersionReady.value && activeVisualFocusHint.value?.asset_id));
const visualCompareEligible = computed(() => Boolean(compareVersionReady.value && focusedVisualAsset.value));
const compareVisualMatch = computed(() => findBestMatchingCompareVisual({
  sourceAsset: focusedVisualAsset.value,
  sourceRegion: focusedVisualRegion.value,
  compareAssets: compareVisualAssets.value,
  compareRegionsByAsset: compareVisualRegionsByAsset.value
}));
const compareVisualAsset = computed(() => compareVisualMatch.value.asset);
const compareVisualRegion = computed(() => compareVisualMatch.value.region);
const compareVisualModeLabel = computed(() => {
  if (compareVisualMatch.value.strategy === 'region') {
    return '自动匹配对应区域';
  }
  if (compareVisualMatch.value.strategy === 'asset') {
    return '按同页截图区域回退';
  }
  return '未找到对照截图';
});
const smartQuestionPlaceholder = computed(() => {
  if (activeVisualFocusHint.value?.display_text) {
    return `补充你想问的具体问题，系统会自动带上 ${activeVisualFocusHint.value.display_text} 的截图焦点。`;
  }
  if (compareVersionReady.value) {
    return '补充你想比较的问题，例如：这个版本相对当前版本改了什么，影响哪些流程？';
  }
  return '补充你想问的具体问题；留空时会用系统预设问题作为保底。';
});
const activeQuestionContext = computed(() => {
  if (activeVisualFocusHint.value?.display_text) {
    return `截图焦点：${activeVisualFocusHint.value.display_text}`;
  }
  if (compareVersionReady.value) {
    return `版本比较：${String(document.value?.version_label || '当前版本')} vs ${String(selectedVersionRecord.value?.version_label || '所选版本')}`;
  }
  return `当前版本：${String(selectedVersionRecord.value?.version_label || document.value?.version_label || '未命名版本')}`;
});

const smartQuestionPlaceholderV2 = computed(() => {
  if (compareVisualReady.value && activeVisualFocusHint.value?.display_text) {
    return `补充你想比较的截图变化，例如：当前版本与所选版本在 ${activeVisualFocusHint.value.display_text} 里改了什么？`;
  }
  if (activeVisualFocusHint.value?.display_text) {
    return `补充你想问的具体问题，系统会自动带上 ${activeVisualFocusHint.value.display_text} 的截图焦点。`;
  }
  if (compareVersionReady.value) {
    return '补充你想比较的问题，例如：这个版本相对当前版本改了什么，影响哪些流程？';
  }
  return '补充你想问的具体问题；留空时会用系统预设问题作为保底。';
});
const activeQuestionContextV2 = computed(() => {
  if (compareVisualReady.value) {
    return `截图版本比较：${String(document.value?.version_label || '当前版本')} vs ${String(selectedVersionRecord.value?.version_label || '所选版本')} / ${String(activeVisualFocusHint.value?.region_label || activeVisualFocusHint.value?.display_text || '当前截图区域')}`;
  }
  if (activeVisualFocusHint.value?.display_text) {
    return `截图焦点：${activeVisualFocusHint.value.display_text}`;
  }
  if (compareVersionReady.value) {
    return `版本比较：${String(document.value?.version_label || '当前版本')} vs ${String(selectedVersionRecord.value?.version_label || '所选版本')}`;
  }
  return `当前版本：${String(selectedVersionRecord.value?.version_label || document.value?.version_label || '未命名版本')}`;
});

void smartQuestionPlaceholder;
void activeQuestionContext;

const syncDocumentForm = () => {
  documentForm.file_name = String(document.value?.file_name || '');
  documentForm.category = String(document.value?.stats_json?.category || '');
  documentForm.version_family_key = String(document.value?.version_family_key || document.value?.id || '');
  documentForm.version_label = String(document.value?.version_label || '');
  documentForm.version_number = Number(document.value?.version_number || 1);
  documentForm.version_status = String(document.value?.version_status || 'active');
  documentForm.is_current_version = Boolean(document.value?.is_current_version);
  documentForm.effective_from = formatDateTimeInput(document.value?.effective_from);
  documentForm.effective_to = formatDateTimeInput(document.value?.effective_to);
  documentForm.supersedes_document_id = String(document.value?.supersedes_document_id || '');
};

const clearCanvas = (canvas: HTMLCanvasElement | null) => {
  if (!canvas) {
    return;
  }
  const context = canvas.getContext('2d');
  canvas.width = 1;
  canvas.height = 1;
  context?.clearRect(0, 0, 1, 1);
};

const resetVisualDiffState = () => {
  visualDiffState.changedRatio = 0;
  visualDiffState.changedPixels = 0;
  visualDiffState.totalPixels = 0;
  visualDiffState.bounds = null;
  compareVisualDiffError.value = '';
  clearCanvas(currentVisualCompareCanvas.value);
  clearCanvas(compareVisualCompareCanvas.value);
  clearCanvas(visualDiffCanvas.value);
};

const visualRegionsFor = (asset: any) => {
  const assetId = String(asset?.asset_id || '');
  return visualRegionsByAsset.value[assetId] || [];
};

const compareVisualRegionsFor = (asset: any) => {
  const assetId = String(asset?.asset_id || '');
  return compareVisualRegionsByAsset.value[assetId] || [];
};

const visualAssetDomId = (assetId: string) => `visual-asset-${String(assetId || '').trim()}`;
const visualRegionDomId = (regionId: string) => `visual-region-${String(regionId || '').trim()}`;
const isFocusedAsset = (assetId: string) => String(assetId || '').trim() && String(assetId || '').trim() === focusedVisualAssetId.value;
const isFocusedRegion = (regionId: string) => String(regionId || '').trim() && String(regionId || '').trim() === focusedVisualRegionId.value;
const focusedRegionForAsset = (asset: any) => visualRegionsFor(asset).find((region: any) => isFocusedRegion(region.region_id)) || null;
const focusedRegionBoxStyle = (asset: any) => {
  const region = focusedRegionForAsset(asset);
  const bbox = Array.isArray(region?.bbox) ? region.bbox : [];
  if (bbox.length !== 4) {
    return {};
  }
  const [left, top, right, bottom] = bbox.map((item: number) => Math.max(0, Math.min(1, Number(item))));
  return {
    left: `${left * 100}%`,
    top: `${top * 100}%`,
    width: `${Math.max(0, right - left) * 100}%`,
    height: `${Math.max(0, bottom - top) * 100}%`,
  };
};

const ensureVisualCollapseOpen = () => {
  if (!activeCollapse.value.includes('visuals')) {
    activeCollapse.value = [...activeCollapse.value, 'visuals'];
  }
};

const scrollToVisualAnchor = async () => {
  const targetId = focusedVisualRegionId.value
    ? visualRegionDomId(focusedVisualRegionId.value)
    : focusedVisualAssetId.value
      ? visualAssetDomId(focusedVisualAssetId.value)
      : '';
  if (!targetId) {
    return;
  }
  ensureVisualCollapseOpen();
  await nextTick();
  const target = globalThis.document?.getElementById(targetId)
    || (focusedVisualAssetId.value ? globalThis.document?.getElementById(visualAssetDomId(focusedVisualAssetId.value)) : null);
  target?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

const syncVisualFocusFromRoute = async () => {
  focusedVisualAssetId.value = String(route.query.assetId || '').trim();
  focusedVisualRegionId.value = String(route.query.regionId || '').trim();
  const routeVersionId = String(route.query.versionId || '').trim();
  if (routeVersionId && routeVersionId !== selectedVersionId.value) {
    const targetVersion = versionHistory.value.find((item: any) => String(item.id) === routeVersionId);
    if (targetVersion) {
      await inspectVersion(targetVersion, false);
    }
  }
  if (focusedVisualAssetId.value || focusedVisualRegionId.value) {
    await scrollToVisualAnchor();
  }
};

const updateVisualFocusQuery = async (assetId: string, regionId: string = '') => {
  const nextQuery = {
    ...route.query,
    assetId: assetId || undefined,
    regionId: regionId || undefined,
  };
  await router.replace({ path: route.path, query: nextQuery });
};

const focusVisualAsset = async (assetId: string) => {
  const normalizedAssetId = String(assetId || '').trim();
  if (!normalizedAssetId) {
    return;
  }
  focusedVisualAssetId.value = normalizedAssetId;
  focusedVisualRegionId.value = '';
  await updateVisualFocusQuery(normalizedAssetId);
  await scrollToVisualAnchor();
  await renderCrossVersionVisualDiff();
};

const focusVisualRegion = async (assetId: string, regionId: string) => {
  const normalizedAssetId = String(assetId || '').trim();
  const normalizedRegionId = String(regionId || '').trim();
  if (!normalizedAssetId || !normalizedRegionId) {
    return;
  }
  focusedVisualAssetId.value = normalizedAssetId;
  focusedVisualRegionId.value = normalizedRegionId;
  await updateVisualFocusQuery(normalizedAssetId, normalizedRegionId);
  await scrollToVisualAnchor();
  await renderCrossVersionVisualDiff();
};

const buildVisualRegionsMap = async (assets: any[]) => {
  const targets = assets.filter((item: any) => String(item?.asset_id || '').trim());
  if (!targets.length) {
    return {};
  }
  const results: any[] = await Promise.all(
    targets.map((asset: any) =>
      getKBVisualAssetRegions(String(asset.asset_id)).catch(() => ({ items: [] }))
    )
  );
  const nextMap: Record<string, any[]> = {};
  targets.forEach((asset: any, index: number) => {
    nextMap[String(asset.asset_id)] = (results[index]?.items || []) as any[];
  });
  return nextMap;
};

const loadVisualRegions = async (assets: any[]) => {
  visualRegionsByAsset.value = await buildVisualRegionsMap(assets);
};

const loadVisualBundleForDocument = async (documentId: string) => {
  const normalizedDocumentId = String(documentId || '').trim();
  if (!normalizedDocumentId) {
    return { assets: [], regionsByAsset: {} };
  }
  const cached = visualBundleCache.get(normalizedDocumentId);
  if (cached) {
    return cached;
  }
  const visualResult: any = await getKBDocumentVisualAssets(normalizedDocumentId);
  const assets = (visualResult?.items || []) as any[];
  const regionsByAsset = await buildVisualRegionsMap(assets);
  const bundle = { assets, regionsByAsset };
  visualBundleCache.set(normalizedDocumentId, bundle);
  return bundle;
};

const loadCompareVisualBundle = async (documentId: string) => {
  const normalizedDocumentId = String(documentId || '').trim();
  if (!normalizedDocumentId || normalizedDocumentId === String(document.value?.id || '')) {
    compareVisualAssets.value = [];
    compareVisualRegionsByAsset.value = {};
    resetVisualDiffState();
    return;
  }
  compareVisualBundleLoading.value = true;
  try {
    const bundle = await loadVisualBundleForDocument(normalizedDocumentId);
    compareVisualAssets.value = bundle.assets;
    compareVisualRegionsByAsset.value = bundle.regionsByAsset;
  } finally {
    compareVisualBundleLoading.value = false;
  }
};

const resolveCropRect = (image: HTMLImageElement, bbox: number[]) => {
  const safeBox = (bbox.length === 4 ? bbox : [0, 0, 1, 1]) as [number, number, number, number];
  const imageWidth = Math.max(1, Number(image.naturalWidth || image.width || 1));
  const imageHeight = Math.max(1, Number(image.naturalHeight || image.height || 1));
  const sourceX = Math.floor(safeBox[0] * imageWidth);
  const sourceY = Math.floor(safeBox[1] * imageHeight);
  const sourceWidth = Math.max(1, Math.floor((safeBox[2] - safeBox[0]) * imageWidth));
  const sourceHeight = Math.max(1, Math.floor((safeBox[3] - safeBox[1]) * imageHeight));
  return {
    x: sourceX,
    y: sourceY,
    width: Math.min(sourceWidth, imageWidth - sourceX),
    height: Math.min(sourceHeight, imageHeight - sourceY)
  };
};

const resolveCompareCanvasSize = (leftRect: { width: number; height: number }, rightRect: { width: number; height: number }) => {
  const aspectCandidates = [
    leftRect.width / Math.max(1, leftRect.height),
    rightRect.width / Math.max(1, rightRect.height)
  ].filter((value) => Number.isFinite(value) && value > 0);
  const aspect = aspectCandidates.length ? aspectCandidates.reduce((sum, value) => sum + value, 0) / aspectCandidates.length : (4 / 3);
  let width = 320;
  let height = Math.round(width / aspect);
  if (height > 220) {
    height = 220;
    width = Math.round(height * aspect);
  }
  return {
    width: Math.max(140, width),
    height: Math.max(96, height)
  };
};

const drawCropPreview = (
  canvas: HTMLCanvasElement | null,
  image: HTMLImageElement,
  cropRect: { x: number; y: number; width: number; height: number },
  size: { width: number; height: number }
) => {
  if (!canvas) {
    return null;
  }
  const context = canvas.getContext('2d');
  if (!context) {
    return null;
  }
  canvas.width = size.width;
  canvas.height = size.height;
  context.clearRect(0, 0, size.width, size.height);
  context.drawImage(image, cropRect.x, cropRect.y, cropRect.width, cropRect.height, 0, 0, size.width, size.height);
  return context;
};

const drawDiffBounds = (context: CanvasRenderingContext2D | null, bounds: { left: number; top: number; right: number; bottom: number } | null) => {
  if (!context || !bounds) {
    return;
  }
  const width = Math.max(1, bounds.right - bounds.left);
  const height = Math.max(1, bounds.bottom - bounds.top);
  context.save();
  context.lineWidth = 2;
  context.strokeStyle = '#f97316';
  context.setLineDash([6, 4]);
  context.strokeRect(bounds.left, bounds.top, width, height);
  context.restore();
};

const loadImageElement = (src: string) => new Promise<HTMLImageElement>((resolve, reject) => {
  const image = new Image();
  image.onload = () => resolve(image);
  image.onerror = () => reject(new Error(`failed to load image: ${src}`));
  image.src = src;
});

const renderCrossVersionVisualDiff = async () => {
  resetVisualDiffState();
  if (!visualCompareEligible.value || !focusedVisualAsset.value || !compareVisualAsset.value) {
    return;
  }
  const currentSource = String(focusedVisualAsset.value.thumbnail_url || '');
  const compareSource = String(compareVisualAsset.value.thumbnail_url || '');
  if (!currentSource || !compareSource) {
    compareVisualDiffError.value = '当前版本或对照版本缺少截图预览，无法生成差异高亮。';
    return;
  }
  compareVisualDiffLoading.value = true;
  try {
    await nextTick();
    const [currentImage, compareImage] = await Promise.all([
      loadImageElement(currentSource),
      loadImageElement(compareSource)
    ]);
    const currentBox = resolveVisualRegionBox(focusedVisualRegion.value);
    const compareBox = resolveVisualRegionBox(compareVisualRegion.value);
    const fallbackBox = currentBox.length === 4 ? currentBox : [];
    const currentCrop = resolveCropRect(currentImage, currentBox);
    const compareCrop = resolveCropRect(compareImage, compareBox.length === 4 ? compareBox : fallbackBox);
    const canvasSize = resolveCompareCanvasSize(currentCrop, compareCrop);
    const currentContext = drawCropPreview(currentVisualCompareCanvas.value, currentImage, currentCrop, canvasSize);
    const compareContext = drawCropPreview(compareVisualCompareCanvas.value, compareImage, compareCrop, canvasSize);
    if (!currentContext || !compareContext || !visualDiffCanvas.value) {
      return;
    }
    const leftImageData = currentContext.getImageData(0, 0, canvasSize.width, canvasSize.height);
    const rightImageData = compareContext.getImageData(0, 0, canvasSize.width, canvasSize.height);
    const diffResult = computePixelDiffMask(leftImageData.data, rightImageData.data, canvasSize.width, canvasSize.height);
    visualDiffState.changedRatio = diffResult.changed_ratio;
    visualDiffState.changedPixels = diffResult.changed_pixels;
    visualDiffState.totalPixels = diffResult.total_pixels;
    visualDiffState.bounds = diffResult.bounds;

    const diffContext = visualDiffCanvas.value.getContext('2d');
    if (!diffContext) {
      return;
    }
    visualDiffCanvas.value.width = canvasSize.width;
    visualDiffCanvas.value.height = canvasSize.height;
    diffContext.putImageData(new ImageData(new Uint8ClampedArray(diffResult.mask), canvasSize.width, canvasSize.height), 0, 0);
    drawDiffBounds(currentContext, diffResult.bounds);
    drawDiffBounds(compareContext, diffResult.bounds);
    drawDiffBounds(diffContext, diffResult.bounds);
  } catch (error) {
    compareVisualDiffError.value = '跨版本截图对比失败，请稍后重试。';
  } finally {
    compareVisualDiffLoading.value = false;
  }
};

const load = async () => {
  const id = String(route.params.id || '');
  document.value = await getKBDocument(id);
  const [eventsResult, visualResult, versionsResult]: any[] = await Promise.all([
    getKBDocumentEvents(id),
    getKBDocumentVisualAssets(id),
    getKBDocumentVersions(id)
  ]);
  events.value = eventsResult.items || [];
  visualAssets.value = visualResult.items || [];
  await loadVisualRegions(visualAssets.value);
  visualBundleCache.set(String(document.value.id || ''), {
    assets: visualAssets.value,
    regionsByAsset: visualRegionsByAsset.value
  });
  versionHistory.value = versionsResult.items || [];
  const defaultVersion = versionHistory.value.find((item: any) => String(item.id) === String(document.value?.id || '')) || versionHistory.value[0];
  if (defaultVersion) {
    await inspectVersion(defaultVersion, false);
  }
  syncDocumentForm();
  await syncVisualFocusFromRoute();
};

const inspectVersion = async (item: any, openDiff: boolean = false) => {
  if (!document.value) return;
  selectedVersionId.value = String(item.id || '');
  versionInspectorTab.value = openDiff ? 'diff' : 'content';
  const [contentResult, diffResult]: any[] = await Promise.all([
    getKBDocumentVersionContent(String(document.value.id), String(item.id)),
    getKBDocumentVersionDiff(String(document.value.id), String(item.id))
  ]);
  selectedVersionContent.value = contentResult.document || null;
  selectedVersionDiff.value = diffResult || null;
  await loadCompareVisualBundle(String(item.id || ''));
  await renderCrossVersionVisualDiff();
};

const resolveQuestion = (fallback: string) => questionDraft.value.trim() || fallback;

const openChatWithQuery = (query: Record<string, string>) => {
  router.push({
    path: '/workspace/chat',
    query
  });
};

const goChat = (documentId: string = '') => {
  if (!document.value) return;
  const target = versionHistory.value.find((item: any) => String(item.id) === String(documentId || document.value.id || '')) || document.value;
  openChatWithQuery(buildKbChatRouteQuery({
    baseId: String(document.value.base_id || ''),
    documentId: String(target.id || document.value.id || ''),
    question: resolveQuestion('请基于当前版本回答我的问题。'),
    focusHint: buildSingleVersionFocus({
      documentId: String(target.id || document.value.id || ''),
      versionLabel: String(target.version_label || ''),
      versionFamilyKey: String(target.version_family_key || document.value.version_family_key || ''),
      fileName: String(target.file_name || document.value.file_name || '')
    })
  }));
};

const goFocusedVisualChat = () => {
  if (!document.value || !activeVisualFocusHint.value) return;
  openChatWithQuery(buildKbChatRouteQuery({
    baseId: String(document.value.base_id || ''),
    documentId: String(activeVisualFocusHint.value.primary_document_id || document.value.id || ''),
    question: resolveQuestion('请结合当前截图焦点回答我的问题。'),
    focusHint: activeVisualFocusHint.value
  }));
};

const applyQuestionTemplate = (template: string) => {
  questionDraft.value = template;
};

const goCompareChat = (compareDocumentId: string = '') => {
  if (!document.value) return;
  const compareTarget = versionHistory.value.find((item: any) => String(item.id) === String(compareDocumentId || selectedVersionRecord.value?.id || '')) || null;
  if (!compareTarget || String(compareTarget.id) === String(document.value.id)) {
    goChat(String(document.value.id || ''));
    return;
  }
  const visualContext = activeVisualFocusHint.value;
  const compareQuestion = resolveQuestion(
    visualContext?.asset_id
      ? `请先比较 ${String(document.value.version_label || '当前版本')} 与 ${String(compareTarget.version_label || '所选版本')} 在当前截图焦点上的变化，再回答我的问题。`
      : `请先比较 ${String(document.value.version_label || '当前版本')} 与 ${String(compareTarget.version_label || '所选版本')} 的正文差异，再回答我的问题。`
  );
  const compareFocusHint = buildCompareVersionsFocus({
    primaryDocumentId: String(document.value.id || ''),
    compareDocumentId: String(compareTarget.id || ''),
    primaryVersionLabel: String(document.value.version_label || ''),
    compareVersionLabel: String(compareTarget.version_label || ''),
    versionFamilyKey: String(document.value.version_family_key || compareTarget.version_family_key || ''),
    assetId: String(visualContext?.asset_id || ''),
    regionId: String(visualContext?.region_id || ''),
    regionLabel: String(visualContext?.region_label || ''),
    pageNumber: Number(visualContext?.page_number || 0) || undefined
  });
  openChatWithQuery(buildKbChatRouteQuery(Object.assign({
    baseId: String(document.value.base_id || ''),
    documentId: String(document.value.id || ''),
    compareDocumentId: String(compareTarget.id || ''),
    question: resolveQuestion(`请先比较 ${String(document.value.version_label || '当前版本')} 与 ${String(compareTarget.version_label || '所选版本')} 的正文差异，再回答我的问题。`),
    ...{},
    focusHint: buildCompareVersionsFocus({
      primaryDocumentId: String(document.value.id || ''),
      compareDocumentId: String(compareTarget.id || ''),
      primaryVersionLabel: String(document.value.version_label || ''),
      compareVersionLabel: String(compareTarget.version_label || ''),
      versionFamilyKey: String(document.value.version_family_key || compareTarget.version_family_key || '')
    })
  }, { question: compareQuestion, focusHint: compareFocusHint })));
};

const openEditDrawer = () => {
  if (!canWrite.value || !document.value) return;
  syncDocumentForm();
  editDrawerVisible.value = true;
};

const cancelEditDocument = () => {
  syncDocumentForm();
  editDrawerVisible.value = false;
};

const saveDocument = async () => {
  if (!canWrite.value || !document.value) return;
  if (!documentForm.file_name.trim()) {
    ElMessage.warning('请填写文件名');
    return;
  }
  document.value = await updateKBDocument(String(document.value.id), {
    file_name: documentForm.file_name.trim(),
    category: documentForm.category.trim(),
    version_family_key: documentForm.version_family_key.trim(),
    version_label: documentForm.version_label.trim(),
    version_number: Number(documentForm.version_number || 1),
    version_status: documentForm.version_status,
    is_current_version: documentForm.is_current_version,
    effective_from: documentForm.effective_from || null,
    effective_to: documentForm.effective_to || null,
    supersedes_document_id: documentForm.supersedes_document_id.trim() || null
  });
  await load();
  editDrawerVisible.value = false;
  ElMessage.success('已更新');
};

const handleRetryIngest = async () => {
  if (!canManage.value || !document.value?.latest_job?.job_id) return;
  retryingJob.value = true;
  try {
    await retryKBIngestJob(String(document.value.latest_job.job_id));
    await load();
    ElMessage.success('已重新入队');
  } finally {
    retryingJob.value = false;
  }
};

const handleDeleteDocument = async () => {
  if (!canWrite.value || !document.value) return;
  try {
    await ElMessageBox.confirm(
      `删除文档「${document.value.file_name}」？此操作不可恢复。`,
      '删除',
      { type: 'warning', confirmButtonText: '确认', cancelButtonText: '取消' }
    );
  } catch {
    return;
  }
  const baseId = String(document.value.base_id || '');
  await deleteKBDocument(String(document.value.id));
  ElMessage.success('已删除');
  router.push({ path: '/workspace/kb/upload', query: baseId ? { baseId } : {} });
};

const formatDateTimeInput = (value: string | Date | null | undefined) => {
  if (!value) return '';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '';
  return date.toISOString().slice(0, 19) + 'Z';
};

const formatDateTime = (value: string | Date | null | undefined) => {
  if (!value) return '-';
  const date = value instanceof Date ? value : new Date(value);
  if (Number.isNaN(date.getTime())) return '-';
  return date.toLocaleString('zh-CN', { hour12: false });
};

watch(
  () => [
    focusedVisualAssetId.value,
    focusedVisualRegionId.value,
    selectedVersionId.value,
    compareVisualMatch.value.asset?.asset_id || '',
    compareVisualMatch.value.region?.region_id || ''
  ],
  () => {
    void renderCrossVersionVisualDiff();
  }
);

watch(
  () => [route.query.assetId, route.query.regionId, route.query.versionId],
  () => {
    void syncVisualFocusFromRoute();
  }
);

onMounted(() => void load());
</script>

<style scoped>
.doc-page {
  gap: var(--content-gap, 16px);
  overflow: hidden;
}

.doc-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.doc-loading {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 12px;
  padding: 48px;
  color: var(--text-muted);
}

.doc-info-row {
  display: flex;
  flex-wrap: wrap;
  gap: 16px;
  align-items: center;
  padding: 12px 0;
  margin-bottom: 12px;
}

.smart-ask-panel {
  display: grid;
  gap: 14px;
  margin-bottom: 16px;
  padding: 18px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 18%, var(--border-color));
  border-radius: 14px;
  background:
    radial-gradient(circle at top right, rgba(37, 99, 235, 0.08), transparent 36%),
    linear-gradient(180deg, #f8fbff 0%, #ffffff 100%);
}

.smart-ask-panel__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.smart-ask-panel__header h3 {
  margin: 0 0 4px;
  font-size: 16px;
  color: var(--text-primary);
}

.smart-ask-panel__header p {
  margin: 0;
  font-size: 13px;
  line-height: 1.6;
  color: var(--text-secondary);
}

.smart-ask-panel__tags {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.smart-ask-panel__presets {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.smart-ask-preset {
  padding: 8px 12px;
  border: 1px solid #d9e5fb;
  border-radius: 999px;
  background: #fff;
  color: #275dad;
  font-size: 12px;
  cursor: pointer;
  transition: transform 0.2s ease, border-color 0.2s ease, box-shadow 0.2s ease;
}

.smart-ask-preset:hover {
  transform: translateY(-1px);
  border-color: #8bb6ff;
  box-shadow: 0 6px 16px rgba(37, 99, 235, 0.08);
}

.smart-ask-panel__actions {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}

.info-item {
  font-size: 14px;
  color: var(--text-secondary);
}

.chunk-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(200px, 1fr));
  gap: 10px;
}

.chunk-node {
  display: flex;
  flex-direction: column;
  gap: 6px;
  padding: 12px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel-muted);
  font-size: 13px;
}

.chunk-index {
  font-family: var(--font-mono);
  font-size: 11px;
  color: var(--text-muted);
}

.chunk-text {
  color: var(--text-primary);
  line-height: 1.5;
  display: -webkit-box;
  -webkit-line-clamp: 3;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.chunk-meta {
  font-size: 11px;
  color: var(--text-muted);
}

.chunk-empty {
  padding: 32px 20px !important;
}

.version-list {
  display: grid;
  gap: 12px;
}

.version-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border: 1px solid var(--border-color);
  border-radius: 10px;
  background: var(--bg-panel);
}

.version-card--active {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 1px color-mix(in srgb, var(--el-color-primary) 25%, transparent);
}

.version-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.version-card__tags {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.version-card__meta {
  display: grid;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.version-card__actions {
  display: flex;
  gap: 8px;
  flex-wrap: wrap;
}

.version-inspector {
  display: grid;
  gap: 12px;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid var(--border-color);
  border-radius: 12px;
  background: var(--bg-panel-muted);
}

.version-inspector__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
}

.version-inspector__sub {
  display: block;
  margin-top: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.version-sections {
  display: grid;
  gap: 12px;
}

.version-summary {
  display: grid;
  gap: 12px;
}

.version-summary__meta {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 13px;
  color: var(--text-secondary);
}

.version-summary__hint {
  margin: 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.version-summary-card {
  display: grid;
  gap: 8px;
  padding: 14px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.version-summary-card--fallback {
  background: var(--bg-panel-muted);
}

.version-summary-card__header {
  display: flex;
  justify-content: space-between;
  gap: 12px;
  align-items: center;
  font-size: 13px;
}

.version-summary-card__header span {
  color: var(--text-secondary);
}

.version-summary-card p {
  margin: 0;
  color: var(--text-primary);
  line-height: 1.7;
}

.version-section {
  display: grid;
  gap: 8px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.version-section pre,
.version-diff-text {
  margin: 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-family: var(--font-mono);
  font-size: 12px;
  line-height: 1.6;
}

.version-diff-summary {
  display: flex;
  gap: 12px;
  flex-wrap: wrap;
  font-size: 12px;
  color: var(--text-secondary);
}

.visual-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(220px, 1fr));
  gap: 12px;
}

.visual-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
  transition: border-color 0.2s ease, box-shadow 0.2s ease, transform 0.2s ease;
}

.visual-card--focused {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--el-color-primary) 18%, transparent);
  transform: translateY(-1px);
}

.visual-thumb-wrap {
  position: relative;
  overflow: hidden;
  border-radius: 8px;
  background: var(--bg-panel-muted);
  border: 1px solid var(--border-color);
}

.visual-thumb {
  display: block;
  width: 100%;
  aspect-ratio: 4 / 3;
  object-fit: cover;
  cursor: pointer;
}

.visual-region-box {
  position: absolute;
  border: 2px solid #d92d20;
  background: rgba(217, 45, 32, 0.14);
  border-radius: 6px;
  box-shadow: 0 0 0 1px rgba(255, 255, 255, 0.9) inset;
  pointer-events: none;
}

.visual-thumb--empty {
  display: grid;
  place-items: center;
  color: var(--text-muted);
}

.visual-meta {
  display: grid;
  gap: 4px;
  font-size: 13px;
  color: var(--text-secondary);
}

.visual-meta strong {
  color: var(--text-primary);
}

.visual-region-list {
  display: grid;
  gap: 8px;
}

.visual-region-item {
  display: grid;
  gap: 4px;
  padding: 10px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel-muted);
  font-size: 12px;
  color: var(--text-secondary);
  cursor: pointer;
  transition: border-color 0.2s ease, box-shadow 0.2s ease, background 0.2s ease;
}

.visual-region-item--focused {
  border-color: var(--el-color-primary);
  box-shadow: 0 0 0 2px color-mix(in srgb, var(--el-color-primary) 18%, transparent);
  background: color-mix(in srgb, var(--el-color-primary-light-9, #ecf5ff) 70%, white);
}

.visual-region-item strong {
  color: var(--text-primary);
}

.visual-compare-panel {
  display: grid;
  gap: 14px;
  margin-top: 16px;
  padding: 16px;
  border: 1px solid color-mix(in srgb, var(--el-color-primary) 18%, var(--border-color));
  border-radius: 12px;
  background:
    radial-gradient(circle at top right, rgba(249, 115, 22, 0.08), transparent 32%),
    linear-gradient(180deg, #fffdf8 0%, #ffffff 100%);
}

.visual-compare-panel__header {
  display: flex;
  justify-content: space-between;
  gap: 16px;
  align-items: flex-start;
}

.visual-compare-panel__header p {
  margin: 4px 0 0;
  font-size: 12px;
  color: var(--text-secondary);
}

.visual-compare-panel__summary {
  display: flex;
  flex-wrap: wrap;
  gap: 10px 16px;
  font-size: 12px;
  color: var(--text-secondary);
}

.visual-compare-panel__loading {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 12px 0;
  color: var(--text-secondary);
}

.visual-compare-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(220px, 1fr));
  gap: 12px;
}

.visual-compare-card {
  display: grid;
  gap: 10px;
  padding: 12px;
  border-radius: 10px;
  border: 1px solid var(--border-color);
  background: var(--bg-panel);
}

.visual-compare-card--diff {
  background: color-mix(in srgb, #fff7ed 60%, white);
}

.visual-compare-card__meta {
  display: grid;
  gap: 4px;
  font-size: 12px;
  color: var(--text-secondary);
}

.visual-compare-card__meta strong {
  color: var(--text-primary);
}

.visual-compare-canvas {
  width: 100%;
  min-height: 120px;
  border-radius: 8px;
  border: 1px solid var(--border-color);
  background: #0f172a;
}
</style>
