import { test } from "@playwright/test";
import { runGoldenPath } from "./golden_path";

test("e2e_golden_path_offline", async ({ page, request, baseURL }) => {
  await runGoldenPath(page, request, baseURL ?? "http://127.0.0.1:8000");
});
