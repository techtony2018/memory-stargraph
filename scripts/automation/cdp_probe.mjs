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
const targetOrigin = new URL(appUrl).origin;
let page = context.pages().find((candidate) => {
  try {
    return new URL(candidate.url()).origin === targetOrigin;
  } catch {
    return false;
  }
});
const createdPage = !page;
if (!page) page = await context.newPage();
const originalViewport = page.viewportSize();
const errors = [];
let phase = "startup";
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
    followupsNestedUnderAutopilot: Boolean(document.querySelector("#autopilotFlyout > #autopilotFindingsButton")),
    followupsTopLevelCount: document.querySelectorAll(".nav-rail > #autopilotFindingsButton").length,
    navRailOrder: [...document.querySelectorAll(".nav-rail > button")].map((item) => item.id),
    nativeTitleCount: document.querySelectorAll("[title]").length,
    relationshipTypePopupCss: getComputedStyle(document.querySelector(".graph-panel")).getPropertyValue("--hud-border").trim(),
    noPlannedFlightRailButton: ![...document.querySelectorAll(".nav-rail-button")].some((item) => /planned flight/i.test(item.textContent || "")),
    expectedVersion,
  }), version);
  const assetVersion = version.replace(/^V/, "");
  const expectedToolbar = ["autopilotModeIcon", "tourPlanButton", "tourButton", "tourPrevButton", "tourNextButton", "tourStopButton", "tourCounter"];
  const expectedNavOrder = ["navStargraphButton", "navSearchButton", "navAutopilotButton", "navTakeReviewButton", "navResolverButton", "autopilotFindingsButton", "navSettingsButton"];
  if (probe.uiVersion !== version || probe.graphVersion !== version) throw new Error(`version mismatch: ${JSON.stringify(probe)}`);
  if (probe.scriptSrc !== `/app.js?v=${assetVersion}` || probe.cssHref !== `/styles.css?v=${assetVersion}`) throw new Error(`asset mismatch: ${JSON.stringify(probe)}`);
  if (probe.autopilotToolbarOrder.length !== expectedToolbar.length || expectedToolbar.some((id, index) => probe.autopilotToolbarOrder[index] !== id)) throw new Error(`autopilot toolbar order mismatch: ${JSON.stringify(probe)}`);
  if (probe.takeReviewNestedUnderAutopilot || probe.takeReviewTopLevelCount !== 1) throw new Error(`take review placement mismatch: ${JSON.stringify(probe)}`);
  if (probe.followupsNestedUnderAutopilot || probe.followupsTopLevelCount !== 1) throw new Error(`follow-ups placement mismatch: ${JSON.stringify(probe)}`);
  if (expectedNavOrder.some((id, index) => probe.navRailOrder[index] !== id)) throw new Error(`nav rail order mismatch: ${JSON.stringify(probe)}`);
  if (probe.nativeTitleCount !== 0) throw new Error(`native title attributes remain: ${JSON.stringify(probe)}`);
  if (!probe.relationshipTypePopupCss) throw new Error(`HUD CSS variables missing: ${JSON.stringify(probe)}`);
  if (!probe.noPlannedFlightRailButton) throw new Error(`unexpected separate Planned Flight rail button: ${JSON.stringify(probe)}`);
  if (errors.length) throw new Error(`browser runtime errors: ${errors.join(" | ")}`);

  phase = "followups";
  await page.click("#autopilotFindingsButton");
  await page.waitForFunction(() => (
    !document.querySelector("#operationModal")?.hidden
    && document.querySelector("#modalTitle")?.textContent === "Autopilot Follow-ups"
    && !window.__MEMORY_STARGRAPH__?.getState()?.autopilotFindings?.loading
  ), null, { timeout: 30000 });
  const followups = await page.evaluate(() => {
    const followupState = window.__MEMORY_STARGRAPH__.getState().autopilotFindings;
    const modalText = document.querySelector("#operationModal")?.textContent || "";
    const state = followupState.message
      ? "error"
      : followupState.findings.length
        ? "loaded"
        : "empty";
    return {
      state,
      total: followupState.total,
      visible: !document.querySelector("#operationModal")?.hidden,
      active: document.querySelector("#autopilotFindingsButton")?.classList.contains("is-active"),
      expanded: document.querySelector("#autopilotFindingsButton")?.getAttribute("aria-expanded"),
      terminalText: state === "loaded"
        ? modalText.includes("durable follow-up")
        : state === "empty"
          ? modalText.includes("No follow-ups match this state.")
          : followupState.message,
    };
  });
  if (!followups.visible || !followups.active || followups.expanded !== "true" || !followups.terminalText) {
    throw new Error(`follow-ups terminal state invalid: ${JSON.stringify(followups)}`);
  }
  if (followups.state === "error") throw new Error(`follow-ups backend error: ${JSON.stringify(followups)}`);
  await page.click("#modalCloseButton");

  phase = "search";
  await page.click("#navSearchButton");
  await page.waitForFunction(() => {
    const input = document.querySelector("#searchInput");
    return Boolean(
      input
      && !document.querySelector("#searchFlyout")?.hidden
      && !input.disabled
      && input.offsetParent !== null
      && document.activeElement === input
    );
  }, null, { timeout: 1000 });
  await page.fill("#searchInput", "SG-0231");
  const search = await page.evaluate(() => ({
    value: document.querySelector("#searchInput")?.value || "",
    focused: document.activeElement === document.querySelector("#searchInput"),
    expanded: document.querySelector("#navSearchButton")?.getAttribute("aria-expanded"),
  }));
  if (search.value !== "SG-0231" || !search.focused || search.expanded !== "true") {
    throw new Error(`search surface invalid: ${JSON.stringify(search)}`);
  }

  phase = "history";
  const history = await page.evaluate(async () => {
    const api = window.__MEMORY_STARGRAPH__;
    const state = api.getState();
    const first = state.focusSlug;
    const second = state.nodes.find((node) => node.slug !== first && !state.hiddenSlugs.has(node.slug))?.slug;
    if (!first || !second) return null;
    await api.loadEntity(first);
    await api.loadEntity(second);
    const afterSecond = state.focusSlug;
    await api.navigateSelectionHistory(-1);
    const afterBack = state.focusSlug;
    await api.navigateSelectionHistory(1);
    return { first, second, afterSecond, afterBack, afterForward: state.focusSlug };
  });
  if (!history || history.afterSecond !== history.second || history.afterBack !== history.first || history.afterForward !== history.second) {
    throw new Error(`history navigation invalid: ${JSON.stringify(history)}`);
  }

  phase = "mobile";
  await page.setViewportSize({ width: 390, height: 844 });
  await page.click("#autopilotFindingsButton");
  await page.waitForFunction(() => !document.querySelector("#operationModal")?.hidden, null, { timeout: 5000 });
  const mobile = await page.evaluate(() => {
    const modal = document.querySelector("#operationModal")?.getBoundingClientRect();
    const followupsButton = document.querySelector("#autopilotFindingsButton")?.getBoundingClientRect();
    return {
      modalWithinViewport: Boolean(modal && modal.left >= 0 && modal.right <= innerWidth && modal.top >= 0 && modal.bottom <= innerHeight),
      followupsButtonVisible: Boolean(followupsButton && followupsButton.width > 0 && followupsButton.height > 0),
      horizontalOverflow: document.documentElement.scrollWidth > innerWidth,
    };
  });
  if (!mobile.modalWithinViewport || !mobile.followupsButtonVisible || mobile.horizontalOverflow) {
    throw new Error(`mobile bounds invalid: ${JSON.stringify(mobile)}`);
  }
  await page.click("#modalCloseButton");

  console.log(JSON.stringify({ ok: true, appUrl, cdpUrl, probe, followups, search, history, mobile, errors }, null, 2));
} catch (error) {
  console.error(JSON.stringify({
    ok: false,
    appUrl,
    cdpUrl,
    phase,
    createdPage,
    error: error.message || String(error),
    browserErrors: errors,
  }, null, 2));
  throw error;
} finally {
  if (!createdPage && originalViewport) await page.setViewportSize(originalViewport).catch(() => {});
  if (createdPage) await page.close().catch(() => {});
  await browser.close().catch(() => {});
}
