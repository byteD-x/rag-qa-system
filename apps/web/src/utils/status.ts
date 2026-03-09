export interface StatusMeta {
  label: string;
  type: '' | 'success' | 'info' | 'warning' | 'danger';
}

const MAP: Record<string, StatusMeta> = {
  pending_upload: { label: '等待上传', type: 'info' },
  uploading: { label: '上传中', type: 'warning' },
  uploaded: { label: '已接收', type: 'info' },
  parsing_fast: { label: '快速解析', type: 'warning' },
  parsing: { label: '深度解析', type: 'warning' },
  fast_index_ready: { label: '快速可查', type: 'success' },
  hybrid_ready: { label: '混合检索就绪', type: 'success' },
  enhancing: { label: '增强处理中', type: 'warning' },
  ready: { label: '可问答', type: 'success' },
  failed: { label: '处理失败', type: 'danger' }
};

export function statusMeta(status: string | undefined | null): StatusMeta {
  if (!status) {
    return { label: '未知状态', type: 'info' };
  }

  return MAP[status] || { label: status, type: 'info' };
}
