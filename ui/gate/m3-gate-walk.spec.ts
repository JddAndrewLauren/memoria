import { appendFileSync, readFileSync, writeFileSync } from "node:fs";
import { join } from "node:path";
import { expect, test, type Page } from "@playwright/test";

/**
 * The M3 gate walk (`docs/gates/m3-gate-walk.md`), driven in a real browser.
 *
 * Why this is not a vitest test. The gate's question is "can a person follow
 * a claim to its evidence without losing their place", and its last step is
 * "compare a sentence against the raw original". Both are layout facts.
 * jsdom has no `scrollIntoView` and every measurement it takes reads 0, so
 * `EntryPage.test.tsx` can prove only the *mechanism* behind place
 * preservation - that the page underneath never navigates - and never the
 * thing itself. This file asserts real `window.scrollY` and real viewport
 * geometry, which is the whole reason it exists.
 *
 * It is deliberately one serial sequence: step 6 asks where step 4 left the
 * page. Each step appends what it observed to the run's artifact, so the
 * output of a pass is a readable record and not just a green tick.
 *
 * Inputs, all set by `scripts/gate-m3.sh`:
 *   MEMORIA_GATE_URL       the server, over a prepared scratch repository
 *   MEMORIA_GATE_REPO      that repository's root, for the out-of-band edit
 *   MEMORIA_GATE_ARTIFACT  the markdown file each step records itself in
 */

const ENTRY_PATH = "/subjects/SUB-people/entries/skilling";
const ENTRY_FILE = "subjects/people/skilling.md";

// The citation the walk is driven through. It is the *second* chip on the
// page on purpose: it sits below the fold, so scrolling to it produces a
// scroll position step 6 can actually check for.
const CITED_ANCHOR = "src-000006-p1";

const repoRoot = requireEnv("MEMORIA_GATE_REPO");
const artifactPath = requireEnv("MEMORIA_GATE_ARTIFACT");

function requireEnv(name: string): string {
  const value = process.env[name];
  if (!value) {
    throw new Error(
      `${name} is not set. This spec is run by scripts/gate-m3.sh, which ` +
        "prepares the repository and the server it walks over; running " +
        "`npx playwright test` by hand skips that preparation.",
    );
  }
  return value;
}

/** One observed fact, in the artifact, in walk order. */
function record(step: string, detail: string): void {
  appendFileSync(artifactPath, `- **${step}** — ${detail}\n`, "utf-8");
}

const entryFilePath = join(repoRoot, ENTRY_FILE);

/**
 * A sentinel on `window`, set once and checked after the panel closes.
 * "Nothing reloaded" is otherwise unobservable: a full remount would restore
 * the same URL and the same text, and only a value that could not have
 * survived it tells the two apart.
 */
async function markPage(page: Page): Promise<void> {
  await page.evaluate(() => {
    (window as unknown as Record<string, unknown>).__gateSentinel = "m3";
  });
}

async function sentinelSurvived(page: Page): Promise<boolean> {
  return page.evaluate(
    () => (window as unknown as Record<string, unknown>).__gateSentinel === "m3",
  );
}

test.describe.configure({ mode: "serial" });

test.describe("M3 gate walk", () => {
  let page: Page;

  /**
   * Where the reader was standing when they clicked the citation, recorded
   * by step 4 and checked by step 6.
   *
   * It has to be read *before* the click, not after the panel opens. A
   * scroll-lock on the page underneath - `position: fixed` on `body` is the
   * usual one - moves the page to the top the moment the panel appears, and
   * a baseline sampled after that is already the wrong number: the step then
   * compares 0 to 0 and passes over a reader who lost their place
   * completely. That is the vacuous assertion `gate/README.md` warns about,
   * one level up from where step 4's `scrolledTo > 0` guard catches it.
   */
  let scrollAtCitation = -1;

  test.beforeAll(async ({ browser }) => {
    page = await browser.newPage();
  });

  test.afterAll(async () => {
    await page.close();
  });

  test("1. the entry opens, and every region is drawn", async () => {
    await page.goto(ENTRY_PATH);
    await expect(page.getByRole("heading", { name: "skilling", level: 1 })).toBeVisible();

    // Every region present - a region with nothing in it yet names the
    // milestone that fills it rather than being hidden or stubbed.
    for (const label of [
      "Audit-visible body",
      "Outside the audit-visible body",
      "Memoria notes",
      "Match terms",
      "Gathered set",
      "Appearances",
    ]) {
      await expect(
        page.getByRole("heading", { name: label, level: 2, exact: true }),
      ).toBeVisible();
    }
    await expect(page.getByText("Settlements", { exact: true })).toBeVisible();

    // The `[open]` line is rendered *outside* the audit-visible body. Its
    // region is the one it must be in, so the assertion is containment,
    // not mere presence anywhere on the page.
    const outside = page
      .locator("section")
      .filter({ has: page.getByRole("heading", { name: "Outside the audit-visible body", exact: true }) });
    await expect(outside.getByText("Which of these threads did he actually read?")).toBeVisible();
    await expect(outside.getByText("open", { exact: true })).toBeVisible();

    record(
      "Step 1 — the entry opens",
      "all six regions drawn; Settlements and Memoria notes name M4; the " +
        "`[open]` line renders inside the “Outside the audit-visible body” region",
    );
  });

  test("2. a match term is added, and the write is durable", async () => {
    await page.getByLabel("New match term").fill("Jeffrey Skilling");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByRole("button", { name: "Save" }).click();
    await expect(page.getByText("Saved.")).toBeVisible();

    // Durable means on disk, not merely acknowledged in the UI. The commit
    // itself is checked by scripts/gate-m3.sh, which owns the git repository.
    const onDisk = readFileSync(entryFilePath, "utf-8");
    expect(onDisk).toContain("Jeffrey Skilling");

    record(
      "Step 2 — the first durable write",
      "`Jeffrey Skilling` added and saved; the term is in " +
        "`subjects/people/skilling.md` on disk",
    );
  });

  test("3. a file changed underneath is refused, and nothing is written", async () => {
    // The other editor. This is the whole point of the step: the browser is
    // still holding the token it was served, and the file no longer matches
    // it.
    const outOfBand = [
      "---",
      "id: SUB-people/skilling",
      "match_terms:",
      "- Skilling",
      "- Edited in another editor",
      "---",
      "Jeff Skilling, CEO.",
      "",
      "[open] Which of these threads did he actually read?",
      "",
    ].join("\n");
    writeFileSync(entryFilePath, outOfBand, "utf-8");

    await page.getByLabel("New match term").fill("Written after the conflict");
    await page.getByRole("button", { name: "Add", exact: true }).click();
    await page.getByRole("button", { name: "Save" }).click();

    await expect(
      page.getByText("This entry changed on disk since it was opened"),
    ).toBeVisible();

    // Refused *and* nothing written: the file is byte-for-byte what the
    // other editor left, and the author's rejected edits are still in the
    // browser rather than lost.
    expect(readFileSync(entryFilePath, "utf-8")).toBe(outOfBand);
    await expect(page.getByText("Written after the conflict")).toBeVisible();

    record(
      "Step 3 — the staleness check",
      "an out-of-band edit made the held token stale; the save was refused, " +
        "the file on disk is byte-for-byte what the other editor left, and " +
        "the rejected term is still in the editor",
    );
  });

  test("4. a citation opens the slide-over without navigating", async () => {
    const chip = page.getByRole("button", { name: CITED_ANCHOR, exact: true });
    await chip.scrollIntoViewIfNeeded();

    const scrolledTo = await page.evaluate(() => window.scrollY);
    // The guard against a vacuous step 6: on a page that never scrolled,
    // "the scroll position is unchanged" is 0 === 0 and proves nothing.
    expect(scrolledTo, "the entry page must actually scroll for step 6 to mean anything").toBeGreaterThan(0);
    scrollAtCitation = scrolledTo;

    await markPage(page);
    const urlBefore = page.url();
    await chip.click();

    const panel = page.getByRole("dialog", { name: "Citation" });
    await expect(panel).toBeVisible();
    expect(page.url()).toBe(urlBefore);

    // The scrim starts past the sidebar, so the sidebar stays lit (§19.9).
    const scrim = page.locator("[role=presentation]").filter({ has: panel });
    expect((await scrim.boundingBox())?.x).toBe(232);

    record(
      "Step 4 — the citation opens the panel",
      `scrolled to y=${scrolledTo}px, clicked \`${CITED_ANCHOR}\`; the ` +
        "slide-over opened over a scrim starting at the sidebar's edge, and " +
        "the URL did not change",
    );
  });

  test("5. the panel lands on the exact cited paragraph", async () => {
    const panel = page.getByRole("dialog", { name: "Citation" });
    await expect(panel.getByText("SRC-000006 ¶1")).toBeVisible();

    // What the API served for this anchor, and what the panel drew, have to
    // be the same text - not a truncation of it and not a re-flow.
    const served = await (
      await page.request.get(`/api/read?ref=${CITED_ANCHOR}`)
    ).json();
    const paragraph = panel.locator("p").first();
    await expect(paragraph).toHaveText(served.text);

    // Landed *on* it: visible in the viewport, not merely present in the DOM.
    // This is the assertion jsdom cannot make.
    const box = await paragraph.boundingBox();
    const viewport = page.viewportSize();
    expect(box).not.toBeNull();
    expect(box!.y).toBeGreaterThanOrEqual(0);
    expect(box!.y + box!.height).toBeLessThanOrEqual(viewport!.height);

    // The record's badge row, and the backlink rail - never stubbed.
    await expect(panel.getByText("SRC-000006", { exact: true })).toBeVisible();
    await expect(panel.getByText("Contemporaneous")).toBeVisible();
    await expect(panel.getByText("email", { exact: true })).toBeVisible();
    await expect(panel.getByText("Cited by")).toBeVisible();
    await expect(panel.getByRole("button", { name: "people/skilling" })).toBeVisible();

    record(
      "Step 5 — the exact paragraph",
      `the panel drew the same text \`/api/read?ref=${CITED_ANCHOR}\` served, ` +
        `fully inside the viewport at y=${Math.round(box!.y)}px, with the ` +
        "record's badge row and a `Cited by` backlink to people/skilling",
    );
  });

  test("6. closing the panel costs the reader nothing", async () => {
    // Measured against step 4's *pre-click* offset, not against a reading
    // taken now: opening the panel is itself a place the scroll position can
    // be lost, and a baseline sampled after the loss cannot see it.
    const scrollWhileOpen = await page.evaluate(() => window.scrollY);
    expect(scrollWhileOpen, "the page underneath must not move when the panel opens").toBe(
      scrollAtCitation,
    );
    const urlBefore = page.url();

    await page.getByRole("dialog", { name: "Citation" }).getByRole("button", { name: "Close" }).click();
    await expect(page.getByRole("dialog", { name: "Citation" })).toBeHidden();

    expect(
      await page.evaluate(() => window.scrollY),
      "the reader must be left where they clicked from",
    ).toBe(scrollAtCitation);
    expect(page.url()).toBe(urlBefore);
    // Nothing reloaded: a remount would have restored the same URL and the
    // same scroll position and lost this.
    expect(await sentinelSurvived(page)).toBe(true);
    await expect(page.getByRole("heading", { name: "skilling", level: 1 })).toBeVisible();

    record(
      "Step 6 — the reader's place",
      `panel opened and closed without moving the page; \`window.scrollY\` is ` +
        `still the ${scrollAtCitation}px step 4 clicked from, the URL is ` +
        "unchanged, and the pre-click sentinel on `window` survived, so the " +
        "page underneath was never remounted",
    );
  });

  test("7. the original opens, and normalization invented nothing", async () => {
    // Re-open the panel: step 6 closed it, and this step reads from it.
    await page.getByRole("button", { name: CITED_ANCHOR, exact: true }).click();
    const panel = page.getByRole("dialog", { name: "Citation" });
    await expect(panel).toBeVisible();
    const servedParagraph = (await panel.locator("p").first().textContent()) ?? "";
    expect(servedParagraph.trim().length).toBeGreaterThan(0);

    const [rawTab] = await Promise.all([
      page.context().waitForEvent("page"),
      panel.getByRole("link", { name: /Open original/ }).click(),
    ]);
    await rawTab.waitForLoadState();

    // Its own tab, on the raw route - the reading surface underneath was
    // not navigated away from.
    expect(rawTab.url()).toContain("/sources/SRC-000006/raw");
    expect(page.url()).toContain(ENTRY_PATH);

    await expect(rawTab.getByText("Original locator")).toBeVisible();
    await expect(rawTab.getByText("message 1 of 1")).toBeVisible();

    // The comparison the gate exists for. The raw file is an .eml with its
    // headers, its CRLFs and its quoted reply still in it; the record kept
    // one paragraph of it. That paragraph has to be *in* the original,
    // verbatim, or normalization wrote something nobody said.
    const rawText = (await rawTab.locator("pre").textContent()) ?? "";
    expect(rawText).toContain("Microsoft Mail Internet Headers Version 2.0");
    expect(rawText).toContain(servedParagraph);

    // And the converter's own excision is visible in the difference: the
    // quoted reply is in the original and not in what was served.
    expect(rawText).toContain("-----Original Message-----");
    expect(servedParagraph).not.toContain("-----Original Message-----");

    await rawTab.close();

    const firstLine = servedParagraph.split("\n")[0];
    record(
      "Step 7 — the original",
      "“Open original ↗” opened `/sources/SRC-000006/raw` in its own tab " +
        "with the entry still open behind it; the served paragraph " +
        `(“${firstLine}…”) appears verbatim in the raw \`.eml\`, whose ` +
        "headers and quoted reply the record does not carry",
    );
  });
});
