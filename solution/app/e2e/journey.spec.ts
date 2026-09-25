// The whole customer-control journey in a browser (LEASH-125), against the fake Viseca platform:
// instruction → clarification → platform draft → confirm → purchases → step_up → reload → answer → payment
// detail → tighten → a later run, started from the app, gets the new version while the first keeps its snapshot →
// the cockpit switches between the two runs (LEASH-133) → revoke. The first run is started through the same API
// the app's start-run card uses (LEASH-066); the later one through the card itself.
import { expect, test, type APIRequestContext, type Page } from "@playwright/test";

const INSTRUCTION = "Buy the 27-inch monitor I chose, from a seller I have bought from before, for CHF 400 or less. "
  + "Do not add anything I did not ask for. Ask me when uncertain.";

type Run = { run_id: string; mandate_version: number; status: string; counters?: Record<string, number> };

async function startRun(request: APIRequestContext, scenario: string): Promise<Run> {
  const mandates = await (await request.get("/api/mandates")).json();
  const started = await request.post("/api/runs", { data: { scenario_id: scenario, mandate_id: mandates.current_mandate_id } });
  expect(started.ok(), await started.text()).toBeTruthy();
  return started.json();
}

async function runOf(request: APIRequestContext, id: string): Promise<Run> {
  return (await request.get(`/api/runs/${id}`)).json();
}

// LEASH-194: the redesign is reviewed at phone size; each redesigned surface is captured for a human to compare
// with the v4 handoff (test-results/…/redesign-*.png).
test.use({ viewport: { width: 390, height: 800 } });
const shot = (page: Page, name: string) => page.screenshot({ path: test.info().outputPath(`redesign-${name}.png`) });

const prompt = (page: Page) => page.getByRole("dialog", { name: "Payment waiting for your answer" });

// Every purchase of the run has its engine decision (asks may still be waiting for the customer: a run stays
// "running" until they are answered or time out, which can take the whole human window).
async function allDecided(request: APIRequestContext, runId: string) {
  await expect.poll(async () => {
    const c = (await runOf(request, runId)).counters ?? {};
    return c.total !== undefined && c.decided === c.total;
  }, { timeout: 60_000 }).toBe(true);
}

// Answers every ask the prompt shows: the double charge (CHF 289.00) is rejected, the converted USD order is
// confirmed, anything else is left for later. Ends once every purchase is decided and the prompt stays closed.
async function answerAsks(page: Page, request: APIRequestContext, runId: string) {
  const answered: Record<string, string> = {};
  const deadline = Date.now() + 90_000;
  let decided = false;
  let lastSeen = Date.now();
  while (Date.now() < deadline) {
    const dialog = prompt(page);
    if (!(await dialog.isVisible())) {
      if (!decided) { await allDecided(request, runId); decided = true; lastSeen = Date.now(); continue; }
      if (Date.now() - lastSeen > 1_500) break;
      await page.waitForTimeout(250);
      continue;
    }
    lastSeen = Date.now();
    const ok = dialog.getByRole("button", { name: "OK" });
    if (await ok.isVisible()) { await ok.click(); continue; }
    const amount = (await dialog.locator(".p-amt").textContent()) ?? "";
    if (amount.includes("289.00") && !answered["289.00"]) {
      await dialog.getByRole("button", { name: "Reject" }).click();
      await expect(dialog.getByText(/CHF 289.00: The payment was not made/)).toBeVisible();
      answered["289.00"] = "rejected";
    } else if (amount.includes("391.50") && !answered["391.50"]) {
      await expect(dialog.getByText("USD 450.00", { exact: false })).toBeVisible();
      await dialog.getByRole("button", { name: "Confirm payment" }).click();
      await expect(dialog.getByText(/CHF 391.50: The payment was made/)).toBeVisible();
      answered["391.50"] = "approved";
    } else {
      await dialog.getByRole("button", { name: "Decide later" }).click();
    }
  }
  return answered;
}

async function dismissAsks(page: Page) {
  let quietSince = Date.now();
  while (Date.now() - quietSince < 1_500) {
    if (!(await prompt(page).isVisible())) { await page.waitForTimeout(250); continue; }
    const ok = prompt(page).getByRole("button", { name: "OK" });
    await (await ok.isVisible() ? ok : prompt(page).getByRole("button", { name: "Decide later" })).click();
    quietSince = Date.now();
  }
}

test("the customer controls the agent from instruction to revoke", async ({ page, request }) => {
  await page.goto("/");
  await expect(page.getByRole("heading", { name: "Hello" })).toBeVisible();  // Home (LEASH-198)
  await shot(page, "0-home-no-permission");

  // 1. Instruction → clarification → the exact platform draft → confirm.
  await page.getByRole("button", { name: "Agent", exact: true }).click();
  await expect(page.getByLabel("What may the agent buy?")).toBeVisible();
  await shot(page, "1-agent-empty");
  await page.getByLabel("What may the agent buy?").fill(INSTRUCTION);
  await page.getByRole("button", { name: "Read my instruction" }).click();
  const rules = page.getByRole("list", { name: "Rules as I read them" });
  await expect(rules.getByText(/At most CHF 400.00 per order/)).toBeVisible();
  await shot(page, "2-agent-clarifying");
  const split = page.getByRole("group", { name: /split in two/ });
  await split.getByRole("button", { name: "Yes, ask me" }).click();
  await expect(split).toBeHidden();
  await page.getByRole("button", { name: "Review permission" }).click();
  const posted = page.getByRole("region", { name: "What Viseca received" });
  await posted.getByText(/^Exact rules/).click();  // the exact posted rules sit behind a disclosure (LEASH-191)
  await expect(posted.getByText("items.item_id in IT0017")).toBeVisible();
  await expect(posted.getByText(/When unsure: ask me/)).toBeVisible();
  await shot(page, "3-agent-summary");
  expect((await (await request.get("/api/mandates")).json()).current_mandate_id).toBeFalsy();  // nothing active yet
  await page.getByRole("button", { name: "Confirm permission" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Confirmed. Version 1 is active" })).toBeVisible();
  await shot(page, "4-agent-active");

  // 2. A run with this permission: the step-up prompt opens by itself.
  const first = await startRun(request, "SCEN0004");
  expect(first.mandate_version).toBe(1);
  await expect(prompt(page)).toBeVisible({ timeout: 60_000 });
  const shown = await prompt(page).locator(".p-amt").textContent();
  await shot(page, "5-step-up");

  // 3. Reloading mid-journey loses no open ask: every ask waiting before is still offered after (more may arrive).
  const waiting = async () => ((await (await request.get("/api/asks")).json()).asks as { authorization_id: string }[])
    .map((a) => a.authorization_id);
  const before = await waiting();
  expect(before.length).toBeGreaterThan(0);
  await page.reload();
  await expect(prompt(page)).toBeVisible();
  await expect(prompt(page).locator(".p-amt")).toHaveText(shown ?? "");
  expect(await waiting()).toEqual(expect.arrayContaining(before));
  const offered = Number((await prompt(page).locator(".chip.agent").textContent())?.match(/of (\d+)/)?.[1] ?? 1);
  expect(offered).toBeGreaterThanOrEqual(before.length);

  // 4. Answer: reject the double charge, confirm the converted order.
  const answered = await answerAsks(page, request, first.run_id);
  expect(answered).toEqual({ "289.00": "rejected", "391.50": "approved" });
  await dismissAsks(page);

  // 5. The Cockpit shows the outcomes; the manipulated order's detail shows the shop's text as untrusted.
  await page.getByRole("button", { name: "Home", exact: true }).click();
  await expect(page.getByRole("button", { name: /PixelHarbor.*CHF 289.00.*You declined/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /HarborByte.*CHF 391.50.*Approved · you approved/ })).toBeVisible();
  await page.evaluate(() => document.querySelector(".view")?.scrollTo(0, 0));
  await shot(page, "6-home");
  await page.getByRole("button", { name: /PixelHarbor.*CHF 520.00.*Blocked/ }).click();
  const detail = page.getByRole("dialog", { name: "Payment details" });
  await expect(detail.getByText("Engine: declined")).toBeVisible();
  await expect(detail.getByText("Shop's text · untrusted")).toBeVisible();
  await shot(page, "7-payment-detail");
  await detail.getByRole("button", { name: "Close" }).click();

  // 6. Tighten: a lower limit, for runs started from now on.
  await page.getByRole("button", { name: "Permission", exact: true }).click();
  await expect(page.getByLabel("New limit per order (CHF)")).toBeVisible();
  await shot(page, "8-permission");
  await page.getByLabel("New limit per order (CHF)").fill("300");
  await page.getByRole("button", { name: "Lower the limit" }).click();
  await expect(page.getByRole("status")).toHaveText(/The limit is now CHF 300.00 per order/);
  await expect(page.getByText("Version 2", { exact: true })).toBeVisible();

  // 7. A later run, started from the app, gets version 2; the first run keeps the snapshot it started with.
  await page.getByLabel("Scenario").fill("SCEN0004");
  await page.getByRole("button", { name: "Start a run" }).click();
  const started = page.getByRole("status").filter({ hasText: /^Run RUN-\S+ started with version 2 of your permission\.$/ });
  await expect(started).toBeVisible();
  const later = await runOf(request, (await started.textContent())!.split(" ")[1]);
  expect(later.mandate_version).toBe(2);
  expect((await runOf(request, first.run_id)).mandate_version).toBe(1);
  await expect(prompt(page)).toBeVisible({ timeout: 60_000 });
  await allDecided(request, later.run_id);
  await dismissAsks(page);

  // 7b. The cockpit shows one run at a time and switches between them (LEASH-133): the converted order the customer
  // confirmed in the first run is over the new CHF 300 limit in the later one.
  await page.getByRole("button", { name: "Home", exact: true }).click();
  const runPicker = page.getByLabel("Run", { exact: true });
  await runPicker.selectOption(later.run_id);
  await expect(page.getByRole("button", { name: /HarborByte.*CHF 391.50.*Blocked/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /Approved · you approved/ })).toHaveCount(0);
  await runPicker.selectOption(first.run_id);
  await expect(page.getByRole("button", { name: /HarborByte.*CHF 391.50.*Approved · you approved/ })).toBeVisible();
  await expect(page.getByRole("button", { name: /PixelHarbor.*CHF 289.00.*You declined/ })).toBeVisible();
  await expect(runPicker).toHaveValue(first.run_id);
  await page.getByRole("button", { name: "Permission", exact: true }).click();

  // 8. Revoke, shown only once Viseca confirms.
  await page.getByRole("button", { name: "Revoke permission" }).click();
  await expect(page.getByRole("dialog", { name: "Revoke permission?" })).toBeVisible();
  await shot(page, "9-revoke-sheet");
  await page.getByRole("button", { name: "Yes, revoke" }).click();
  await expect(page.getByRole("status")).toHaveText("Revoked. Viseca confirmed: the agent can no longer pay.");
});
