import { defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    pool: '@cloudflare/vitest-pool-workers',
    globals: true,
    poolOptions: {
      workers: {
        miniflare: {
          compatibilityDate: '2024-12-05',
          compatibilityFlags: ['nodejs_compat'],
        },
      },
    },
  },
});
