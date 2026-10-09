import { defineConfig, globalIgnores } from 'eslint/config';
import typescript from 'typescript-eslint';
import hooks from 'eslint-plugin-react-hooks';
export default defineConfig([...typescript.configs.recommended,
  { files: ['src/**/*.{ts,tsx}'], ...hooks.configs.flat.recommended },
  globalIgnores(['.next/**', 'out/**', 'next-env.d.ts'])]);
