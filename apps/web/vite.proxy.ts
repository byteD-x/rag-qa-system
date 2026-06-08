export const KB_REBUILD_PROXY_CONTEXT = '^/api/knowledge_base/rebuild(?:\\?.*)?$';
export const KB_BATCH_DRY_RUN_PROXY_CONTEXT = '^/api/knowledge_base/batch-dry-run(?:\\?.*)?$';
export const KB_BATCH_INGEST_PROXY_CONTEXT = '^/api/knowledge_base/batch-ingest(?:\\?.*)?$';

export function createApiProxy(gatewayOrigin: string) {
  return {
    [KB_REBUILD_PROXY_CONTEXT]: {
      target: gatewayOrigin,
      changeOrigin: true
    },
    [KB_BATCH_DRY_RUN_PROXY_CONTEXT]: {
      target: gatewayOrigin,
      changeOrigin: true
    },
    [KB_BATCH_INGEST_PROXY_CONTEXT]: {
      target: gatewayOrigin,
      changeOrigin: true
    },
    '/api/v1': {
      target: gatewayOrigin,
      changeOrigin: true
    }
  };
}
