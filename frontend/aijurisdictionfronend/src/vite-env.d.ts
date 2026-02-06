/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_GOOGLE_START_URL?: string;
  readonly VITE_AUTH_X_START_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
