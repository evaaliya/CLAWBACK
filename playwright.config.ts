import { defineConfig } from "@playwright/test";

// E2E suites land in M5/M6. Config kept so `make install` / `make e2e` resolve.
export default defineConfig({
  testDir: "tests/e2e",
  timeout: 60_000,
  use: {
    baseURL: process.env.PLAYWRIGHT_BASE_URL ?? "http://127.0.0.1:8000",
  },
});
