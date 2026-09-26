import { test, expect } from "@playwright/test";
import worker from "../worker/index";

// Exercise the real UI and Worker preview path without spending live provider quota.
test.beforeEach(async ({ page }) => {
  await page.route("**/api/**", async route => {
    const incoming = route.request();
    const response = await worker.fetch(new Request(incoming.url(), {
      method: incoming.method(),
      ...(incoming.method() === "POST" ? { body: incoming.postData() } : {}),
    }), {} as Parameters<typeof worker.fetch>[1]);
    await route.fulfill({ status: response.status, contentType: "application/json", body: await response.text() });
  });
});

test("opens on the map with compact navigation and optional dataset setup", async ({ page }) => {
  await page.goto("/");
  await expect(page.locator(".leaflet-container")).toBeVisible();
  await expect(page.getByRole("button", { name: "map", exact: true })).toHaveAttribute("aria-current", "page");
  await expect(page.locator("#dataset-panel")).toBeHidden();
  await expect(page.locator(".hero, .welcome")).toHaveCount(0);
  await page.screenshot({ path: "test-results/map-first-desktop.png", fullPage: true });
  await page.getByRole("button", { name: "Upload CSV", exact: true }).click();
  await expect(page.locator("#dataset-panel")).toBeVisible();
  await page.getByRole("button", { name: "Close settings" }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  await expect(page.locator(".leaflet-container")).toBeVisible();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/map-first-mobile.png", fullPage: true });
});

test("streamed locations preserve manual zoom and tab navigation preserves the map", async ({ page }) => {
  let releaseSecond!: () => void;
  const secondGate = new Promise<void>(resolve => { releaseSecond = resolve; });
  let locationCalls = 0;
  await page.route("**/api/locations", async route => {
    locationCalls++;
    if (locationCalls === 2) await secondGate;
    const incoming = route.request();
    const response = await worker.fetch(new Request(incoming.url(), {
      method: "POST", body: incoming.postData(),
    }), {} as Parameters<typeof worker.fetch>[1]);
    await route.fulfill({ status: response.status, contentType: "application/json", body: await response.text() });
  });
  await page.goto("/");
  const tweets = Array.from({ length: 21 }, (_, i) => `Flood warning in ${i < 10 ? "Calgary" : "Edmonton"} report ${i}`);
  await page.getByLabel("Upload CSV").setInputFiles({ name: "stream.csv", mimeType: "text/csv", buffer: Buffer.from("tweet\n" + tweets.join("\n")) });
  await page.getByRole("button", { name: "Analyze dataset" }).click();
  const map = page.locator(".map-stage .leaflet-container");
  await expect(map.locator("path.leaflet-interactive")).toHaveCount(1);
  const marker = map.locator("path.leaflet-interactive").first();
  const unzoomed = await marker.getAttribute("d");
  await map.locator(".leaflet-control-zoom-in").click();
  // Wait for Leaflet's zoom animation to settle before comparing geographic geometry.
  await expect(marker).not.toHaveAttribute("d", unzoomed!);
  await expect(map).not.toHaveClass(/leaflet-zoom-anim/);
  const before = await marker.getAttribute("d");
  // Groups are sorted by report count, so their DOM order may change as batches arrive.
  const unchangedMarker = map.locator(`path.leaflet-interactive[d="${before}"]`);
  releaseSecond();
  await expect(page.getByText("Analysis complete", { exact: true })).toBeVisible();
  await expect(map.locator("path.leaflet-interactive")).toHaveCount(2);
  await expect(unchangedMarker).toHaveCount(1);
  await page.getByRole("button", { name: "reports", exact: true }).click();
  await page.locator(".tweet-text").first().click();
  await page.getByRole("button", { name: "map", exact: true }).click();
  await expect(unchangedMarker).toHaveCount(1);
  await map.getByRole("button", { name: "Fit places" }).click();
  await expect(unchangedMarker).toHaveCount(0);
});
test("complete supplied dataset, linked views, export, mobile layout", async ({ page }) => {
  const errors: string[] = [];
  page.on("pageerror", error => errors.push(error.message));
  await page.goto("/");
  await page.getByRole("button", { name: "Use supplied dataset" }).click();
  await expect(page.getByText("8,024", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Analyze dataset" }).click();
  await expect(page.getByText("Analysis complete", { exact: true })).toBeVisible({ timeout: 100000 });
  await expect(page.locator(".dataset-totals")).toContainText("8,024");
  await page.getByRole("button", { name: "reports", exact: true }).click();
  await expect(page.locator(".report-list article")).toHaveCount(30);
  await page.getByRole("button", { name: "Next", exact: true }).click();
  await expect(page.getByText(/Page 2 \//)).toBeVisible();
  await page.getByLabel("Search reports").fill("Siksika");
  await expect(page.getByText(/Page 1 \//)).toBeVisible();
  await page.getByRole("button", { name: "map", exact: true }).click();
  await expect(page.locator(".leaflet-container")).toBeVisible();
  await expect(page.locator(".place-directory")).toContainText("Siksika");
  await page.getByRole("button", { name: "overview", exact: true }).click();
  await expect(page.locator(".summary-card")).toContainText("Siksika");
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export filtered CSV" }).click();
  expect((await download).suggestedFilename()).toBe("flood-reports.csv");
  await page.screenshot({ path: "test-results/desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/mobile.png", fullPage: true });
  expect(errors).toEqual([]);
});
test("unseen column, embedded newline, blanks, no results and failed-batch retry", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Upload CSV").setInputFiles({ name: "custom.csv", mimeType: "text/csv", buffer: Buffer.from('message,extra\n"Flooding in Calgary\nbridge closed",a\nCamping tomorrow,b\n,c') });
  await expect(page.getByLabel("Report text column")).toHaveValue("message");
  await page.route("**/api/classify", route => route.fulfill({ status: 503, body: "{}" }));
  await page.getByRole("button", { name: "Analyze dataset" }).click();
  await expect(page.getByRole("button", { name: /Retry incomplete/ })).toBeVisible();
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await page.getByRole("combobox", { name: "Relevance", exact: true }).selectOption("failed");
  await expect(page.locator(".view-count")).toHaveText("2 matching reports");
  await page.unroute("**/api/classify");
  await page.getByRole("button", { name: /Retry incomplete/ }).click();
  await expect(page.getByText("Analysis complete", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "Reset filters" }).click();
  await expect(page.locator(".view-count")).toHaveText("1 matching reports");
  await page.getByLabel("Search reports").fill("notpresentanywhere");
  await page.getByRole("button", { name: "overview", exact: true }).click();
  await expect(page.locator(".summary-card")).toContainText("No reports match");
  await page.getByRole("button", { name: "map", exact: true }).click();
  await expect(page.getByText(/No resolved places in this selection/)).toBeVisible();
});
test("cancellation preserves results and changed column clears stale analysis", async ({ page }) => {
  await page.goto("/");
  await page.getByRole("button", { name: "Use supplied dataset" }).click();
  await page.route("**/api/classify", async route => { await new Promise(resolve => setTimeout(resolve, 100)); await route.continue().catch(() => {}); });
  await page.getByRole("button", { name: "Analyze dataset" }).click();
  await page.getByRole("button", { name: "Cancel analysis" }).click();
  await expect(page.getByText("Cancelled · completed results are preserved")).toBeVisible();
  await expect(page.getByRole("button", { name: /Retry incomplete/ })).toBeVisible();
  await page.getByLabel("Upload CSV").setInputFiles({ name: "new.csv", mimeType: "text/csv", buffer: Buffer.from("tweet\nHello world") });
  await expect(page.locator(".report-list article")).toHaveCount(0);
  await expect(page.getByRole("button", { name: "Analyze dataset" })).toBeVisible();
});

test("community investigation preserves corrections, links places and exports reviewed evidence", async ({ page }) => {
  await page.goto("/");
  const csv = 'tweet\n"Clothing is no longer needed in Siksika. #abflood"\n"Our Calgary office is accepting donations for Siksika. #abflood"\n"There is NO risk of a dam breach in Calgary. #yycflood"\n"Can anyone confirm the Calgary bridge is closed? #yycflood"';
  await page.getByLabel("Upload CSV").setInputFiles({ name: "evidence.csv", mimeType: "text/csv", buffer: Buffer.from(csv) });
  await page.getByRole("button", { name: "Analyze dataset" }).click();
  await expect(page.getByText("Analysis complete", { exact: true })).toBeVisible();
  await page.getByRole("button", { name: "investigate", exact: true }).click();
  await expect(page.locator(".investigation")).toBeVisible();
  await page.getByRole("button", { name: /Corrections & reassurance/ }).click();
  await expect(page.locator(".investigation-list > article")).toHaveCount(2);
  await expect(page.locator(".evidence-detail")).toContainText("no longer needed");
  await expect(page.locator(".signal-detail").first()).toContainText("correction");
  await page.getByLabel("Review note", { exact: true }).fill("Confirm with community before sending supplies.");
  await page.getByLabel("Flag location as incorrect").check();
  await page.getByRole("checkbox", { name: "Include record 2 in briefing", exact: true }).check();
  const downloaded = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export briefing (1)", exact: true }).click();
  const file = await downloaded;
  const { readFile } = await import("node:fs/promises");
  const text = await readFile((await file.path())!, "utf8");
  expect(text).toContain("LOCATION DISPUTED");
  expect(text).toContain("Confirm with community");
  expect(text).toContain("Clothing is no longer needed");
  await page.getByRole("button", { name: /Offers/ }).click();
  await expect(page.locator(".evidence-detail")).toContainText("Possible beneficiary");
  await page.locator(".evidence-detail").getByRole("button", { name: "Siksika Nation", exact: true }).click();
  await page.getByRole("button", { name: "Filters", exact: true }).click();
  await expect(page.getByRole("combobox", { name: "Place", exact: true })).toHaveValue("Siksika Nation");
  await page.screenshot({ path: "test-results/investigation-desktop.png", fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBeTruthy();
  await page.screenshot({ path: "test-results/investigation-mobile.png", fullPage: true });
});
