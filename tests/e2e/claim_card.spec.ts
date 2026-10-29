import { expect, test } from "@playwright/test";
import { resetDemo } from "./golden_path";

test("e2e_claim_card", async ({ page, request }) => {
  // Self-contained: reset + draft claim so order vs golden-path specs does not matter.
  await resetDemo(request);
  const seeded = await request.post("/api/demo/seed-claim");
  expect(seeded.ok()).toBeTruthy();

  await page.goto("/");

  const card = page.locator(".card[data-type='claim_draft']").first();
  await expect(card).toBeVisible({ timeout: 15_000 });

  await expect(card.getByRole("button", { name: "Send claim" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Reject" })).toBeVisible();
  await expect(
    card.getByText(/test outbox|not a real company/i)
  ).toBeVisible();

  const source = card.locator(".sources a").first();
  await expect(source).toBeVisible();
  await expect(source).toHaveAttribute("href", /https?:\/\//);
});
