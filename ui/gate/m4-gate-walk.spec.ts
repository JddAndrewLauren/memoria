import { appendFileSync } from "node:fs";
import { expect, test, type Page } from "@playwright/test";

/**
 * The M4 gate walk's browser half (`docs/gates/m4-gate-walk.md`).
 *
 * The gate's three acts are the record extractor's, and `gate/m4/records.py`
 * walks them in the core. What only a browser can answer is the one clause
 * "clicking it lands on the sentence in which you decided": that the
 * Section view's decision opens the slide-over on the author's turn, that
 * the decided sentence - and not the turn as a whole - is marked and on
 * screen, and that the reader underneath kept their place. jsdom can prove
 * the mechanism (`SectionPage.test.tsx`: the chip opens the panel, no route
 * changed) and never the geometry, which is why this file exists.
 *
 * Two phases, because act 3 changes the entry between them
 * (`scripts/gate-m4.sh` runs `records.py after` in the middle):
 *   default               steps 1-4, the Section view and the click-through
 *   MEMORIA_GATE_PHASE=after   step 5, the entry after the hand edit and the note
 *
 * Inputs, all set by `scripts/gate-m4.sh`:
 *   MEMORIA_GATE_URL       the server, over the prepared scratch repository
 *   MEMORIA_GATE_ARTIFACT  the markdown file each step records itself in
 */

const SECTION_PATH = "/sections/SEC-0001";
const ENTRY_PATH = "/subjects/SUB-people/entries/skilling";
const SESSION_ID = "SES-20260903-1000";
const DECISION_CITATION = `${SESSION_ID}#T003`;
const MUSING_CITATION = `${SESSION_ID}#T001`;

// The same words gate/m4/records.py recorded - the walk checks the page
// against what the extractor wrote, and these are what it wrote.
const MUSING = "Maybe the deck went up unchanged because nobody below Skilling dared to touch it.";
const DECISION = "Let's keep it ambiguous whether Skilling read the deck until the Friday thread.";
const HAND_EDITED =
  "The deck reached Skilling without anyone below him editing it, and he read it that night.";
const CONFLICT = "A later message in the thread has the deck revised twice before it went up.";
const NOTE_CLOSE = "The author text has been left unchanged.";

// The rail sits at the top of the page, so the chip is visible from y=0 and
// a baseline of 0 would be the vacuous one gate/README.md warns about. The
// walk scrolls the window itself - half way down to the chip, so the chip
// stays on screen - and then requires the offset to have actually moved.

const artifactPath = requireEnv("MEMORIA_GATE_ARTIFACT");
const phase = process.env.MEMORIA_GATE_PHASE ?? "before";

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. This spec is run by scripts/gate-m4.sh, which ` +
        "prepares the repository and the server it walks over.",
    );
  }
  return value;
}

function record(step: string, detail: string): void {
  appendFileSync(artifactPath, `- **${step}** — ${detail}\n`, "utf-8");
}

async function markPage(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as Record<string, unknown>).__gateSentinel = "m4";
  });
}

async function sentinelSurvived(page: Page): Promise<boolean> {
  return page.evaluate(
    () => (window as unknown as Record<string, unknown>).__gateSentinel === "m4",
  );
}

test.describe.configure({ mode: "serial" });

test.describe("M4 gate walk", () => {
  let page: Page;
  let scrollAtCitation = -1;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("1. the Section view shows the decision and the open musing, each citing its turn", async () => {
    test.skip(phase !== "before");
    await page.goto(SECTION_PATH);
    await expect(page.getByRole("heading", { name: "SEC-0001", level: 1 })).toBeVisible();

    const decisions = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Decisions", exact: true }),
    });
    await expect(decisions.getByText(DECISION)).toBeVisible();
    await expect(decisions.getByText("DEC-0001")).toBeVisible();
    await expect(decisions.getByRole("button", { name: DECISION_CITATION, exact: true })).toBeVisible();
    // The musing is not among the decisions - it is an open question.
    await expect(decisions.getByText(MUSING)).toHaveCount(0);

    const questions = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Open questions", exact: true }),
    });
    await expect(questions.getByText(MUSING)).toBeVisible();
    await expect(questions.getByRole("button", { name: MUSING_CITATION, exact: true })).toBeVisible();

    record(
      "Step 1 — the Section view",
      `\`DEC-0001\` is in the Decisions card citing \`${DECISION_CITATION}\`; the ` +
        `musing is in Open questions citing \`${MUSING_CITATION}\` and nowhere among ` +
        "the decisions",
    );
  });

  test("2. clicking the decision's citation opens the slide-over without navigating", async () => {
    test.skip(phase !== "before");
    const chip = page.getByRole("button", { name: DECISION_CITATION, exact: true });
    const chipBox = await chip.boundingBox();
    expect(chipBox).not.toBeNull();
    await page.evaluate((offset) => window.scrollTo(0, offset), Math.floor(chipBox!.y / 2));
    const scrolledTo = await page.evaluate(() => window.scrollY);
    expect(scrolledTo, "the Section page must actually scroll for step 4 to mean anything").toBeGreaterThan(0);
    scrollAtCitation = scrolledTo;
    await expect(chip).toBeInViewport();
    await markPage(page);
    const urlBefore = page.url();
    await chip.click();

    const panel = page.getByRole("dialog", { name: "Citation" });
    await expect(panel).toBeVisible();
    expect(page.url()).toBe(urlBefore);
    await expect(panel.getByText(DECISION_CITATION, { exact: true })).toBeVisible();

    record(
      "Step 2 — the citation opens the panel",
      `scrolled the reader to y=${scrolledTo}px, clicked \`${DECISION_CITATION}\`; the ` +
        "slide-over opened on that turn and the URL did not change",
    );
  });

  test("3. the panel lands on the sentence the author decided in", async () => {
    test.skip(phase !== "before");
    const panel = page.getByRole("dialog", { name: "Citation" });
    await expect(panel.getByText("Transcript turn")).toBeVisible();

    // The turn the API serves is the turn the panel drew - whole, not the
    // decided sentence alone.
    const served = await (
      await page.request.get(`/api/read?ref=${encodeURIComponent(DECISION_CITATION)}`)
    ).json();
    const turn = panel.locator("p").first();
    await expect(turn).toHaveText(served.text);
    expect(served.text).not.toBe(DECISION);
    expect(served.text).toContain(DECISION);

    // One sentence is marked, it is the decision's, and it is on screen.
    const marks = panel.getByTestId("cited-sentence");
    await expect(marks).toHaveCount(1);
    await expect(marks.first()).toHaveText(new RegExp(`^\\s*${DECISION.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}\\s*$`));
    const box = await marks.first().boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);

    record(
      "Step 3 — the exact sentence",
      `the panel drew the same text \`/api/read?ref=${DECISION_CITATION}\` served ` +
        `(${served.text.length} chars, three sentences); exactly one sentence is marked, ` +
        `it reads “${DECISION}”, and it sits inside the viewport at y=${Math.round(box!.y)}px`,
    );
  });

  test("4. closing the panel costs the reader nothing", async () => {
    test.skip(phase !== "before");
    const scrollWhileOpen = await page.evaluate(() => window.scrollY);
    expect(scrollWhileOpen, "the page underneath must not move when the panel opens").toBe(scrollAtCitation);
    const urlBefore = page.url();

    await page.getByRole("dialog", { name: "Citation" }).getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog", { name: "Citation" })).toBeHidden();

    expect(await page.evaluate(() => window.scrollY), "the reader must be left where they clicked from").toBe(
      scrollAtCitation,
    );
    expect(page.url()).toBe(urlBefore);
    expect(await sentinelSurvived(page)).toBe(true);
    await expect(page.getByRole("heading", { name: "SEC-0001", level: 1 })).toBeVisible();

    record(
      "Step 4 — the reader's place",
      `panel opened and closed without moving the page; \`window.scrollY\` is still the ` +
        `${scrollAtCitation}px step 2 clicked from, the URL is unchanged, and the pre-click ` +
        "sentinel on `window` survived, so the section underneath was never remounted",
    );
  });

  test("5. the entry shows the author's edited statement, and the note beneath it", async () => {
    test.skip(phase !== "after");
    await page.goto(ENTRY_PATH);
    await expect(page.getByRole("heading", { name: "skilling", level: 1 })).toBeVisible();

    const body = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Audit-visible body", exact: true }),
    });
    await expect(body.getByText(HAND_EDITED)).toBeVisible();

    const notes = page.locator("section").filter({
      has: page.getByRole("heading", { name: "Memoria notes", exact: true }),
    });
    await expect(notes.getByText(CONFLICT)).toBeVisible();
    await expect(notes.getByText(NOTE_CLOSE)).toBeVisible();
    // The note is outside the audit-visible body: nothing of it is in there.
    await expect(body.getByText(CONFLICT)).toHaveCount(0);

    record(
      "Step 5 — the entry after the note",
      "the audit-visible body shows the author's hand-edited statement, word for word; " +
        `the Memoria notes region shows the Curator's conflict (“${CONFLICT}”) ending ` +
        `“${NOTE_CLOSE}”, and none of the note is in the audit-visible body`,
    );
  });
});
