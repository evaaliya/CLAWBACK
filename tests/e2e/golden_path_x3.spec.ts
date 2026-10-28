import { test } from "@playwright/test";
import { runGoldenPath } from "./golden_path";

test("e2e_golden_path_x3", async ({ page, request, baseURL }) => {
  const origin = baseURL ?? "http://127.0.0.1:8000";
  for (let i = 0; i < 3; i++) {
    await runGoldenPath(page, request, origin);
  }
});
