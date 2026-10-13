/// <reference types="vite/client" />
/// <reference types="vitest/config" />

interface ImportMetaEnv {
  readonly VITE_DEMO_ADMIN_EMAIL?: string;
  readonly VITE_DEMO_ADMIN_PASSWORD?: string;
  readonly VITE_DEMO_MEMBER_EMAIL?: string;
  readonly VITE_DEMO_MEMBER_PASSWORD?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
