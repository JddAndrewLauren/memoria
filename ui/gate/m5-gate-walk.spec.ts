import { appendFileSync, readdirSync, statSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * The M5 gate walk's browser half (`docs/gates/m5-gate-walk.md`).
 *
 * The gate's acts - the legacy import, the brief and its assembly, the
 * authorized draft, the trace, the audit - are facts about files, commits
 * and ledgers, and `gate/m5/records.py` walks them in the core. What only
 * a browser can answer: that the not-current tint is *painted* on the
 * legacy chapter and on the fresh draft; that the supplied-context surface
 * names the fallback, is live while open and absent while closed; that a
 * finding is settled *from its button*; and that settling did not clear
 * the tint - only the re-audit did. jsdom cannot paint and cannot poll a
 * server, which is why this file exists.
 *
 * Three phases, because the core acts between them change what the page
 * shows (`scripts/gate-m5.sh` runs `records.py audit` and `reaudit` in
 * between):
 *   default                   steps 1-3: the tints, the supplied context
 *   MEMORIA_GATE_PHASE=audit  steps 4-6: the audit's results, the Settle
 *                             click, and the tint that returned
 *   MEMORIA_GATE_PHASE=after  step 7: current only through re-audit
 *
 * Inputs, all set by `scripts/gate-m5.sh`:
 *   MEMORIA_GATE_URL       the server, over the prepared scratch repository
 *   MEMORIA_GATE_REPO      the scratch repository, for the one ledger append
 *                          step 3 makes to see the surface refresh
 *   MEMORIA_GATE_ARTIFACT  the markdown file each step records itself in
 */

const LEGACY_PATH = "/sections/SEC-0001";
const SECTION_PATH = "/sections/SEC-0002";
const REVIEW_PATH = "/sections/SEC-0002/review";
const ENTRY_PATH = "/subjects/SUB-people/entries/skilling";
const ENTRY_ID = "SUB-people/skilling";
const SESSION_ID = "SES-20260903-1100";
const LEGACY_PARAGRAPHS = 8;
const DRAFT_PARAGRAPHS = 24;

// The same words gate/m5/records.py wrote and recorded.
const FINDING_STATEMENT =
  "The draft has Skilling reading the deck the night it went up; the thread has it " +
  "revised twice before it reached him.";
const FALLBACK_TEXT =
  "“Fastow” named no entry. Assembly fell back to the unpromoted candidate CAN-0001 under " +
  "SUB-people — its identity only; nothing of it was loaded.";
const PROPOSITION = "the deck was revised twice before Skilling saw it";
const REASON = "the thread is contemporaneous and the draft was from memory";

const artifactPath = requireEnv("MEMORIA_GATE_ARTIFACT");
const repoPath = requireEnv("MEMORIA_GATE_REPO");
const phase = process.env.MEMORIA_GATE_PHASE ?? "before";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. This spec is run by scripts/gate-m5.sh, which ` +
        "prepares the repository and the server it walks over.",
    );
  }
  return value;
}

function record(step: string, detail: string): void {
  appendFileSync(artifactPath, `- **${step}** — ${detail}\n`, "utf-8");
}

function findLedger(dir: string): string | null {
  for (const name of readdirSync(dir)) {
    const path = join(dir, name);
    if (statSync(path).isDirectory()) {
      const found = findLedger(path);
      if (found) return found;
    } else if (name === "events.jsonl" && path.includes(SESSION_ID)) {
      return path;
    }
  }
  return null;
}

async function tintedParagraphs(page: Page): Promise<number> {
  return page.locator("div.prose p.not-current").count();
}

test.describe.configure({ mode: "serial" });

test.describe("M5 gate walk", () => {
  let page: Page;
  let tintBeforeSettle = -1;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("1. the legacy chapter wears an unconfirmed brief and a not-current tint", async () => {
    test.skip(phase !== "before");
    await page.goto(LEGACY_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0001", level: 1 })).toBeVisible();
    await expect(page.getByText("unconfirmed brief", { exact: true })).toBeVisible();
    await expect(
      page.getByText(`${LEGACY_PARAGRAPHS} of ${LEGACY_PARAGRAPHS} paragraphs not current`, { exact: false }),
    ).toBeVisible();

    const paragraphs = page.locator("div.prose p");
    await expect(paragraphs).toHaveCount(LEGACY_PARAGRAPHS);
    expect(await tintedParagraphs(page)).toBe(LEGACY_PARAGRAPHS);
    // The tint is paint, not a class name: an inset amber rule on each one.
    const shadow = await paragraphs.first().evaluate((p) => getComputedStyle(p).boxShadow);
    expect(shadow).toMatch(/inset/);
    expect(shadow).not.toBe("none");
    const causes = page.locator("li", { hasText: /never audited/ });
    expect(await causes.count()).toBeGreaterThanOrEqual(LEGACY_PARAGRAPHS);
    await expect(causes.first()).toContainText(ENTRY_ID);

    // The page agrees with the API it read from.
    const served = await (await page.request.get("/api/sections/SEC-0001")).json();
    expect(served.unconfirmed).toBe(true);
    expect(served.paragraphs.every((p: { not_current: unknown[] }) => p.not_current.length > 0)).toBe(true);

    record(
      "Step 1 — the legacy chapter",
      `\`SEC-0001\` shows the \`unconfirmed brief\` badge and “${LEGACY_PARAGRAPHS} of ` +
        `${LEGACY_PARAGRAPHS} paragraphs not current”; all ${LEGACY_PARAGRAPHS} paragraphs are ` +
        `tinted (computed box-shadow “${shadow}”), each with a “never audited · ${ENTRY_ID}” ` +
        "row; `/api/sections/SEC-0001` says the same",
    );
  });

  test("2. the piece's fresh draft is tinted never-audited, and the opener carries no count", async () => {
    test.skip(phase !== "before");
    await page.goto(SECTION_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0002", level: 1 })).toBeVisible();
    await expect(page.getByText("unconfirmed brief", { exact: true })).toHaveCount(0);
    await expect(page.locator("div.prose p")).toHaveCount(DRAFT_PARAGRAPHS);
    expect(await tintedParagraphs(page)).toBe(DRAFT_PARAGRAPHS);
    await expect(
      page.getByText(`${DRAFT_PARAGRAPHS} of ${DRAFT_PARAGRAPHS} paragraphs not current`, { exact: false }),
    ).toBeVisible();

    const opener = page.getByRole("link", { name: /Supplied context/ });
    await expect(opener).toBeVisible();
    const openerText = (await opener.textContent()) ?? "";
    expect(openerText).not.toMatch(/\d/);

    record(
      "Step 2 — the piece's section",
      `\`SEC-0002\` has no unconfirmed badge; all ${DRAFT_PARAGRAPHS} draft paragraphs are ` +
        `tinted never-audited; the “${openerText.trim()}” opener carries no count and no digit`,
    );
  });

  test("3. the supplied context names the fallback, is live while open and absent while closed", async () => {
    test.skip(phase !== "before");
    const requests: string[] = [];
    page.on("request", (request) => {
      if (request.url().includes("/supplied-context")) requests.push(request.url());
    });
    await page.getByRole("link", { name: /Supplied context/ }).click();
    await expect(page.getByRole("heading", { name: /What Memoria supplied for SEC-0002/ })).toBeVisible();

    const summary = page.getByText(/1 brief · 1 entry · 1 fallback · \d+ sources? served since/);
    await expect(summary).toBeVisible();
    const summaryText = ((await summary.textContent()) ?? "").trim();
    const working = page.getByRole("region", { name: "Working context" });
    await expect(working.getByText(FALLBACK_TEXT, { exact: true })).toBeVisible();
    await expect(working.getByText(/named by skilling/)).toBeVisible();
    await expect(working.getByText(/reported as identifiers, not loaded/)).toBeVisible();
    const body = (await page.locator("main, body").first().textContent()) ?? "";
    expect(body).not.toMatch(/\d+\s*(tokens?|bytes?|%|percent)/i);

    // Live while open: one more read lands on the session's ledger, and the
    // surface picks it up without being touched.
    const ledger = findLedger(join(repoPath, "sessions"));
    expect(ledger, "the session's ledger must exist in the scratch repository").not.toBeNull();
    const servedBefore = await page.getByRole("region", { name: "Served since assembly" }).locator("li").count();
    appendFileSync(
      ledger as string,
      JSON.stringify({
        session_id: SESSION_ID,
        timestamp: "2026-09-03T11:30:00+00:00",
        tool: "read",
        ref: "SUB-people/skilling",
        served: ["SUB-people/skilling"],
        tokens: 12,
      }) + "\n",
      "utf-8",
    );
    const servedRegion = page.getByRole("region", { name: "Served since assembly" });
    await expect(servedRegion.locator("li")).toHaveCount(servedBefore + 1, { timeout: 15_000 });
    const refreshesWhileOpen = requests.length;
    expect(refreshesWhileOpen).toBeGreaterThan(1);

    // Absent while closed: navigate back and count requests over a window
    // longer than the refresh interval.
    await page.getByRole("link", { name: "SEC-0002" }).first().click();
    await expect(page.getByRole("heading", { name: "SEC-0002", level: 1 })).toBeVisible();
    const afterClose = requests.length;
    await page.waitForTimeout(7_000);
    expect(requests.length).toBe(afterClose);

    record(
      "Step 3 — the supplied context",
      `opened from the section: “${summaryText}”; the working context names the entry ` +
        `(“named by skilling”, gathered set reported as identifiers, not loaded) and the ` +
        `fallback verbatim: “${FALLBACK_TEXT}”; no token, byte or percentage figure on the ` +
        `page; one read appended to the ledger appeared in “Served since” without a click ` +
        `(${servedBefore} → ${servedBefore + 1} rows, ${refreshesWhileOpen} reads while open); ` +
        "after closing, no request in 7s",
    );
  });

  test("4. the audit's results: the section is current, the review shows the finding", async () => {
    test.skip(phase !== "audit");
    await page.goto(SECTION_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0002", level: 1 })).toBeVisible();
    await expect(page.getByText("Every paragraph is current.", { exact: true })).toBeVisible();
    await expect(page.locator("div.prose p")).toHaveCount(DRAFT_PARAGRAPHS);
    tintBeforeSettle = await tintedParagraphs(page);
    expect(tintBeforeSettle).toBe(0);

    await page.getByRole("link", { name: /Review audit results/ }).click();
    await expect(page.getByText(/Results of the audit you ran on/)).toBeVisible();
    await expect(page.getByText("1 finding", { exact: true })).toBeVisible();
    await expect(page.getByText(`${DRAFT_PARAGRAPHS} judgements current · 0 not current`)).toBeVisible();
    const card = page.locator("li").filter({ hasText: FINDING_STATEMENT });
    await expect(card).toHaveCount(1);
    await expect(card.getByText("¶3", { exact: true })).toBeVisible();
    await expect(card.getByText("high confidence")).toBeVisible();
    await expect(card.getByText("raised by SUB-people")).toBeVisible();
    await expect(card.getByRole("link", { name: `entry · ${ENTRY_ID}` })).toBeVisible();
    await expect(card.getByRole("button", { name: /^source · / })).toBeVisible();
    for (const side of ["entry", "source", "passage"]) {
      await expect(card.getByText(`settle toward the ${side}`, { exact: true })).toBeVisible();
    }
    await expect(card.getByRole("button", { name: "Settle" })).toBeEnabled();

    record(
      "Step 4 — the audit's results",
      `after the audit, \`SEC-0002\` reads “Every paragraph is current.” with 0 tinted ` +
        `paragraphs (the baseline step 6 compares against); Review shows 1 finding on ¶3, ` +
        `high confidence, raised by SUB-people, its three chips and three settle resolutions, ` +
        "and Settle is enabled",
    );
  });

  test("5. one finding is settled from its button", async () => {
    test.skip(phase !== "audit");
    const card = page.locator("li").filter({ hasText: FINDING_STATEMENT });
    await card.getByRole("button", { name: "Settle" }).click();
    const form = card.getByRole("form", { name: "Settle this finding" });
    await expect(form).toBeVisible();
    await expect(form.getByRole("button", { name: "Record settlement" })).toBeDisabled();
    await form.getByRole("radio", { name: "the entry" }).check();
    await form.getByLabel("Proposition").fill(PROPOSITION);
    await form.getByLabel("Reason").fill(REASON);
    await form.getByLabel("Session").selectOption(SESSION_ID);
    await form.getByRole("button", { name: "Record settlement" }).click();

    // The record of the act outlives its card: the settled finding leaves
    // the review on the re-read, and the page keeps the notice.
    const settledList = page.getByRole("list", { name: "Settled this visit" });
    await expect(settledList.getByText(new RegExp(`Settled on ${ENTRY_ID} as CLM-0001`))).toBeVisible();
    // The review re-read itself: the finding is silenced and nothing is current.
    await expect(page.locator("li").filter({ hasText: FINDING_STATEMENT })).toHaveCount(0);
    await expect(page.getByText("0 findings", { exact: true })).toBeVisible();
    // Every judgement against the entry is stale now, so the surface reads
    // as one no audit has been run over - recorded as observed.
    await expect(page.getByText("no judgements current", { exact: true })).toBeVisible();

    await page.goto(ENTRY_PATH);
    const body = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Audit-visible body", exact: true }),
    });
    await expect(body.getByText(PROPOSITION, { exact: false })).toBeVisible();
    await expect(body.getByText(REASON, { exact: false })).toBeVisible();

    record(
      "Step 5 — settled from its button",
      `clicked Settle on the ¶3 finding, chose the entry, wrote “${PROPOSITION}” for ` +
        `“${REASON}” in \`${SESSION_ID}\`, recorded; the card reports the settlement on ` +
        `\`${ENTRY_ID}\` as \`CLM-0001\` in the page's “Settled this visit” list, which outlives ` +
        `the card; the finding is gone from Review and the summary ` +
        `asserts “0 findings” and “no judgements current” separately; the entry's ` +
        "audit-visible body shows the settled line",
    );
  });

  test("6. settling did not clear the tint", async () => {
    test.skip(phase !== "audit");
    expect(tintBeforeSettle, "step 4 must have read the baseline").toBe(0);
    await page.goto(SECTION_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0002", level: 1 })).toBeVisible();
    await expect(
      page.getByText(`${DRAFT_PARAGRAPHS} of ${DRAFT_PARAGRAPHS} paragraphs not current`, { exact: false }),
    ).toBeVisible();
    const tinted = await tintedParagraphs(page);
    expect(tinted).toBe(DRAFT_PARAGRAPHS);
    expect(tinted).toBeGreaterThan(tintBeforeSettle);
    const causes = page.locator("li", { hasText: /entry changed since/ });
    expect(await causes.count()).toBeGreaterThanOrEqual(DRAFT_PARAGRAPHS);
    await expect(causes.first()).toContainText(ENTRY_ID);
    await expect(page.getByText("Every paragraph is current.", { exact: true })).toHaveCount(0);

    record(
      "Step 6 — settling did not clear the tint",
      `back on \`SEC-0002\`: ${tinted} of ${DRAFT_PARAGRAPHS} paragraphs tinted where step 4 ` +
        `read ${tintBeforeSettle}, every one with a “not current · entry changed since · ` +
        `${ENTRY_ID}” row - the settlement moved the entry, and nothing pretended the section ` +
        "was still current",
    );
  });

  test("7. only the re-audit clears it, and the legacy chapter is untouched", async () => {
    test.skip(phase !== "after");
    await page.goto(SECTION_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0002", level: 1 })).toBeVisible();
    await expect(page.getByText("Every paragraph is current.", { exact: true })).toBeVisible();
    expect(await tintedParagraphs(page)).toBe(0);

    await page.goto(REVIEW_PATH);
    await expect(page.getByText(/The audit found nothing to disagree with/)).toBeVisible();
    await expect(page.getByText(`${DRAFT_PARAGRAPHS} judgements current · 0 not current`)).toBeVisible();

    await page.goto(LEGACY_PATH);
    await expect(
      page.getByText(`${LEGACY_PARAGRAPHS} of ${LEGACY_PARAGRAPHS} paragraphs not current`, { exact: false }),
    ).toBeVisible();
    expect(await tintedParagraphs(page)).toBe(LEGACY_PARAGRAPHS);

    record(
      "Step 7 — current only through re-audit",
      `after the re-audit \`SEC-0002\` reads “Every paragraph is current.” with 0 tinted ` +
        `paragraphs, Review finds nothing to disagree with at ${DRAFT_PARAGRAPHS} judgements ` +
        `current; the legacy \`SEC-0001\` is still ${LEGACY_PARAGRAPHS} of ${LEGACY_PARAGRAPHS} ` +
        "not current - no pass reached it unasked",
    );
  });
});
