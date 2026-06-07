export const KB_REBUILD_PROXY_CONTEXT = '^/api/knowledge_base/rebuild(?:\\?.*)?$';

export function createApiProxy(gatewayOrigin: string) {
  return {
    [KB_REBUILD_PROXY_CONTEXT]: {
      target: gatewayOrigin,
      changeOrigin: true
    },
    '/api/v1': {
      target: gatewayOrigin,
      changeOrigin: true
    }
  };
}
