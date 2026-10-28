import { expect, test } from "@playwright/test";

test("e2e_claim_card", async ({ page }) => {
  await page.goto("/");

  // Claim draft card from chat bootstrap (seeded by scripts/e2e_seed_claim.py).
  const card = page.locator(".card[data-type='claim_draft']").first();
  await expect(card).toBeVisible({ timeout: 15_000 });

  await expect(card.getByRole("button", { name: "Send" })).toBeVisible();
  await expect(card.getByRole("button", { name: "Reject" })).toBeVisible();

  const source = card.locator(".sources a").first();
  await expect(source).toBeVisible();
  await expect(source).toHaveAttribute("href", /https?:\/\//);
});
