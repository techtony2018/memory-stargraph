import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const version = process.argv[2] || "";
const appUrl = process.argv[3] || process.env.MEMORY_STARGRAPH_URL || "http://127.0.0.1:8788";
const cdpUrl = process.env.MEMORY_STARGRAPH_CDP_URL || "http://127.0.0.1:9333";

if (!version) {
  throw new Error("usage: node scripts/automation/cdp_probe.mjs V1.0.xx [app-url]");
}

const pathPlaywrightCandidates = (process.env.PATH || "")
  .split(path.delimiter)
  .filter((entry) => path.basename(entry) === ".bin")
  .map((entry) => path.join(path.dirname(entry), "playwright"));
const candidates = [process.env.PLAYWRIGHT_MODULE, "playwright", ...pathPlaywrightCandidates].filter(Boolean);

let chromium;
let loadError;
for (const candidate of candidates) {
  try {
    ({ chromium } = require(candidate));
    break;
  } catch (error) {
    loadError = error;
  }
}
if (!chromium) {
  throw new Error(`Unable to load Playwright for CDP probe. Try: npx --yes --package playwright node scripts/automation/cdp_probe.mjs ${version}. Last error: ${loadError?.message || "unknown"}`);
}

const browser = await chromium.connectOverCDP(cdpUrl);
const context = browser.contexts()[0] || await browser.newContext();
const page = await context.newPage();
const errors = [];
page.on("pageerror", (error) => errors.push(error.message || String(error)));
page.on("console", (message) => {
  if (message.type() === "error") errors.push(message.text());
});

try {
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  // Verify the deployed build after a real browser refresh, not a stale tab.
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__?.getState().graph, null, { timeout: 120000 });
  await page.waitForTimeout(750);
  const probe = await page.evaluate((expectedVersion) => ({
    uiVersion: document.querySelector("#uiVersion")?.textContent || "",
    graphVersion: window.__MEMORY_STARGRAPH__?.getState()?.graph?.ui_version || "",
    scriptSrc: document.querySelector('script[src*="app.js"]')?.getAttribute("src") || "",
    cssHref: document.querySelector('link[href*="styles.css"]')?.getAttribute("href") || "",
    focusSlug: window.__MEMORY_STARGRAPH__?.getState()?.focusSlug || "",
    mapYodaButtonPresent: Boolean(document.querySelector("#mapAskYodaButton")),
    autopilotToolbarOrder: [...document.querySelectorAll("#autopilotFlyout > button, #autopilotFlyout > span")].map((item) => item.id),
    takeReviewNestedUnderAutopilot: Boolean(document.querySelector("#autopilotFlyout > #navTakeReviewButton")),
    takeReviewTopLevelCount: document.querySelectorAll(".nav-rail > #navTakeReviewButton").length,
    navRailOrder: [...document.querySelectorAll(".nav-rail > button")].map((item) => item.id),
    nativeTitleCount: document.querySelectorAll("[title]").length,
    relationshipTypePopupCss: getComputedStyle(document.querySelector(".graph-panel")).getPropertyValue("--hud-border").trim(),
    noPlannedFlightRailButton: ![...document.querySelectorAll(".nav-rail-button")].some((item) => /planned flight/i.test(item.textContent || "")),
    expectedVersion,
  }), version);
  const assetVersion = version.replace(/^V/, "");
  const expectedToolbar = ["autopilotModeIcon", "tourPlanButton", "tourButton", "tourPrevButton", "tourNextButton", "tourStopButton", "tourCounter"];
  const expectedNavOrder = ["navStargraphButton", "navSearchButton", "navAutopilotButton", "navTakeReviewButton", "navResolverButton", "navSettingsButton"];
  if (probe.uiVersion !== version || probe.graphVersion !== version) throw new Error(`version mismatch: ${JSON.stringify(probe)}`);
  if (probe.scriptSrc !== `/app.js?v=${assetVersion}` || probe.cssHref !== `/styles.css?v=${assetVersion}`) throw new Error(`asset mismatch: ${JSON.stringify(probe)}`);
  if (expectedToolbar.some((id, index) => probe.autopilotToolbarOrder[index] !== id)) throw new Error(`autopilot toolbar order mismatch: ${JSON.stringify(probe)}`);
  if (probe.takeReviewNestedUnderAutopilot || probe.takeReviewTopLevelCount !== 1) throw new Error(`take review placement mismatch: ${JSON.stringify(probe)}`);
  if (expectedNavOrder.some((id, index) => probe.navRailOrder[index] !== id)) throw new Error(`nav rail order mismatch: ${JSON.stringify(probe)}`);
  if (probe.nativeTitleCount !== 0) throw new Error(`native title attributes remain: ${JSON.stringify(probe)}`);
  if (!probe.relationshipTypePopupCss) throw new Error(`HUD CSS variables missing: ${JSON.stringify(probe)}`);
  if (!probe.noPlannedFlightRailButton) throw new Error(`unexpected separate Planned Flight rail button: ${JSON.stringify(probe)}`);
  console.log(JSON.stringify({ ok: true, appUrl, cdpUrl, probe, errors }, null, 2));
} finally {
  await page.close().catch(() => {});
  await browser.close().catch(() => {});
}
