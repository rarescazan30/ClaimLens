/// <reference types="vite/client" />

interface ImportMetaEnv {
  /** Address of the ClaimLens backend, without a trailing slash. Default: http://localhost:8000 */
  readonly VITE_API_URL?: string;
}
interface ImportMeta {
  readonly env: ImportMetaEnv;
}
