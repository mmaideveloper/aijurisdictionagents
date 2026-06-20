/// <reference types="vite/client" />

interface ImportMetaEnv {
  readonly VITE_AUTH_GOOGLE_START_URL?: string;
  readonly VITE_AUTH_X_START_URL?: string;
  readonly VITE_API_BASE_URL?: string;
  readonly VITE_API_KEY?: string;
  readonly VITE_API_COUNTRY?: string;
  readonly VITE_API_LANGUAGE?: string;
  readonly VITE_ASSISTANT_GATEWAY_URL?: string;
}

interface ImportMeta {
  readonly env: ImportMetaEnv;
}
