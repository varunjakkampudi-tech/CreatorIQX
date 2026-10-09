import { expect, test } from "@playwright/test";
import AxeBuilder from "@axe-core/playwright";

/**
 * P0-083 acceptance test: "axe has zero serious or critical findings on the
 * stories." Runs against the static Storybook build (playwright.storybook.
 * config.ts), not the addon-a11y panel - that's an interactive aid for
 * browsing, this is the part CI actually gates on. Reads index.json for the
 * full story list so a new story is covered automatically, the same
 * enumerate-don't-hand-list approach the P0-054 cross-tenant harness uses
 * for routes.
 */

interface StorybookIndexEntry {
  type?: string;
  id: string;
  name: string;
  title: string;
}

interface StorybookIndex {
  entries?: Record<string, StorybookIndexEntry>;
  stories?: Record<string, StorybookIndexEntry>;
}

async function listStoryIds(
  request: import("@playwright/test").APIRequestContext,
  baseURL: string,
): Promise<string[]> {
  const response = await request.get(`${baseURL}/index.json`);
  expect(response.ok()).toBe(true);
  const index = (await response.json()) as StorybookIndex;
  const entries = index.entries ?? index.stories ?? {};
  return Object.values(entries)
    .filter((entry) => (entry.type ?? "story") === "story")
    .map((entry) => entry.id);
}

test("every story has zero serious or critical axe findings", async ({
  page,
  request,
  baseURL,
}) => {
  const storyIds = await listStoryIds(request, baseURL!);
  expect(storyIds.length).toBeGreaterThan(0);

  const failures: string[] = [];

  for (const id of storyIds) {
    await page.goto(`/iframe.html?id=${id}&viewMode=story`);
    const results = await new AxeBuilder({ page }).analyze();
    const serious = results.violations.filter(
      (violation) =>
        violation.impact === "serious" || violation.impact === "critical",
    );
    if (serious.length > 0) {
      failures.push(
        `${id}: ${serious.map((v) => `${v.id} (${v.impact})`).join(", ")}`,
      );
    }
  }

  expect(failures, failures.join("\n")).toEqual([]);
});
