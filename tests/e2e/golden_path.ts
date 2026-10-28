import { expect, type APIRequestContext, type Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

const RECEIPT = path.resolve("demo/receipts/soundhub-order-48213.txt");

/** Abort any request that leaves the app origin (T20 offline). */
export async function blockExternalNetwork(page: Page, baseURL: string) {
  const origin = new URL(baseURL).origin;
  await page.route("**/*", async (route) => {
    const url = route.request().url();
    if (url.startsWith(origin) || url.startsWith("data:") || url.startsWith("blob:")) {
      await route.continue();
      return;
    }
    await route.abort();
  });
}

export async function resetDemo(request: APIRequestContext) {
  const res = await request.post("/api/demo/reset");
  expect(res.ok()).toBeTruthy();
}

async function cancelMerchant(page: Page, merchant: string) {
  const pending = page
    .locator(`.card[data-type='cancel_plan'][data-merchant='${merchant}']`)
    .filter({ hasText: "Confirm" })
    .last();
  await expect(pending).toBeVisible({ timeout: 15_000 });
  await pending.getByRole("button", { name: "Confirm" }).click();

  const plan = page
    .locator(`.card[data-type='cancel_plan'][data-merchant='${merchant}']`)
    .last();
  await expect(plan).toBeVisible({ timeout: 15_000 });
  await plan.getByRole("button", { name: "Confirm" }).click();
  await expect(page.getByText(`Cancelled ${merchant}`)).toBeVisible({
    timeout: 15_000,
  });
}

async function cancelFitPulseViaApi(request: APIRequestContext) {
  const subs = await request.get("/api/subscriptions");
  expect(subs.ok()).toBeTruthy();
  const body = await subs.json();
  const fit = (body.subscriptions || []).find(
    (s: { merchant: string; status: string }) =>
      s.merchant === "FitPulse" && s.status !== "cancelled"
  );
  expect(fit).toBeTruthy();
  const start = await request.post(`/api/subscriptions/${fit.id}/cancel`);
  expect(start.ok()).toBeTruthy();
  const confirm = await request.post(
    `/api/subscriptions/${fit.id}/cancel/confirm`
  );
  expect(confirm.ok()).toBeTruthy();
}

/**
 * Golden Path against a recorded-mode server: $96 → cancels + claim → $847.
 * FitPulse is cancelled via API (not flagged unused, so no cancel card).
 */
export async function runGoldenPath(
  page: Page,
  request: APIRequestContext,
  baseURL: string
) {
  await resetDemo(request);
  await blockExternalNetwork(page, baseURL);

  // Receipt ingest uses FakeLLM recording (receipt:soundhub-order-48213.txt).
  const receiptBuf = fs.readFileSync(RECEIPT);
  const ingest = await request.post("/api/ingest/receipts", {
    multipart: {
      files: {
        name: "soundhub-order-48213.txt",
        mimeType: "text/plain",
        buffer: receiptBuf,
      },
    },
  });
  if (!ingest.ok()) {
    throw new Error(`ingest failed: ${ingest.status()} ${await ingest.text()}`);
  }

  const scan = await request.post("/api/jobs/scan");
  expect(scan.ok()).toBeTruthy();

  await page.goto("/");
  await expect(page.locator("#recorded-badge")).toBeVisible({ timeout: 15_000 });
  await expect(page.locator("#recorded-badge")).not.toHaveClass(/hidden/);
  await expect(page.locator("#savings-money")).toHaveText("$96.00", {
    timeout: 15_000,
  });

  await cancelMerchant(page, "StreamFlix");
  await cancelMerchant(page, "CloudNest");

  // Deadline alert → Prepare claim → Send (auto-refund in recorded mode).
  const deadline = page.locator(".card[data-type='deadline_alert']").first();
  await expect(deadline).toBeVisible({ timeout: 15_000 });
  await deadline.getByRole("button", { name: "Prepare claim" }).click();

  const claim = page.locator(".card[data-type='claim_draft']").first();
  await expect(claim).toBeVisible({ timeout: 20_000 });
  await expect(claim.locator(".sources a").first()).toBeVisible();
  await claim.getByRole("button", { name: "Send" }).click();

  await cancelFitPulseViaApi(request);
  await page.reload();
  await expect(page.locator("#savings-money")).toHaveText("$847.00", {
    timeout: 20_000,
  });
  await expect(page.locator("#savings-time")).toHaveText("6h");
}
