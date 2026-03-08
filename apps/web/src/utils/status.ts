export interface StatusMeta {
  label: string;
  type: '' | 'success' | 'info' | 'warning' | 'danger';
}

const MAP: Record<string, StatusMeta> = {
  pending_upload: { label: '等待上传', type: 'info' },
  uploading: { label: '上传中', type: 'warning' },
  uploaded: { label: '已接收', type: 'info' },
  parsing_fast: { label: '快速解析', type: 'warning' },
  parsing: { label: '解析中', type: 'warning' },
  fast_index_ready: { label: '快速可查', type: 'success' },
  hybrid_ready: { label: '混合检索就绪', type: 'success' },
  enhancing: { label: '深度增强', type: 'warning' },
  ready: { label: '稳定问答', type: 'success' },
  failed: { label: '失败', type: 'danger' }
};

export function statusMeta(status: string | undefined | null): StatusMeta {
  if (!status) {
    return { label: '未知状态', type: 'info' };
  }
  return MAP[status] || { label: status, type: 'info' };
}
