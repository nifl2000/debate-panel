import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    globals: true,
  },
});
