import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const candidates = [
  process.env.PLAYWRIGHT_MODULE,
  "playwright",
  ...(process.env.PATH || "")
    .split(path.delimiter)
    .filter((entry) => path.basename(entry) === ".bin")
    .map((entry) => path.join(path.dirname(entry), "playwright")),
].filter(Boolean);

let chromium;
let lastError;
for (const candidate of candidates) {
  try {
    ({ chromium } = require(candidate));
    break;
  } catch (error) {
    lastError = error;
  }
}
if (!chromium) throw new Error(`Unable to load Playwright: ${lastError?.message || "unknown"}`);

const appUrl = process.env.MEMORY_STARGRAPH_URL || "https://127.0.0.1:8788";
const screenshotPath = process.env.MEMORY_STARGRAPH_SCREENSHOT_PATH || "";
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const page = await browser.newPage({ viewport: { width: 1280, height: 900 }, ignoreHTTPSErrors: true });

try {
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__?.getState().graph?.nodes?.length > 0, null, { timeout: 120000 });
  const firstSlug = await page.evaluate(() => window.__MEMORY_STARGRAPH__.getState().graph.nodes[0].slug);
  await page.evaluate((slug) => window.__MEMORY_STARGRAPH__.loadEntity(slug), firstSlug);
  await page.waitForFunction((slug) => window.__MEMORY_STARGRAPH__.getState().focusSlug === slug, firstSlug, { timeout: 30000 });

  const versions = await page.evaluate(() => ({
    stargraph: document.querySelector("#uiVersion")?.textContent?.trim() || "",
    gbrain: document.querySelector("#gbrainVersion")?.textContent?.trim() || "",
    visible: Boolean(document.querySelector("#gbrainVersion")?.offsetParent),
  }));
  if (versions.stargraph !== "V1.0.204" || !/^GBrain V\d+/.test(versions.gbrain) || !versions.visible) {
    throw new Error(`Runtime version row is not current and visible: ${JSON.stringify(versions)}`);
  }

  await page.click("#selectionAskYodaButton");
  await page.waitForSelector("#operationModal.ask-yoda-modal:not([hidden])", { state: "visible", timeout: 30000 });
  const askLayout = await page.evaluate(() => {
    const panel = document.querySelector("#operationModal .modal-panel");
    const log = document.querySelector("#modalChatLog");
    const input = document.querySelector("#modalChatInput");
    const actions = document.querySelector("#operationModal .modal-actions");
    const panelBox = panel?.getBoundingClientRect();
    const logBox = log?.getBoundingClientRect();
    const inputBox = input?.getBoundingClientRect();
    const actionsBox = actions?.getBoundingClientRect();
    return {
      panelHeight: panelBox?.height || 0,
      logHeight: logBox?.height || 0,
      inputVisible: Boolean(inputBox && inputBox.bottom <= innerHeight && inputBox.height > 40),
      actionsVisible: Boolean(actionsBox && actionsBox.bottom <= innerHeight && actionsBox.height > 20),
    };
  });
  if (askLayout.panelHeight < 700 || askLayout.logHeight < 250 || !askLayout.inputVisible || !askLayout.actionsVisible) {
    throw new Error(`Ask Yoda did not use the available viewport safely: ${JSON.stringify(askLayout)}`);
  }
  await page.click("#modalCancelButton");

  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__.getState().askYodaLogs.size > 0, null, { timeout: 30000 });
  await page.click("#navSettingsButton");
  await page.waitForSelector("#settingsYodaLogButton", { state: "visible", timeout: 10000 });
  await page.click("#settingsYodaLogButton");
  await page.waitForSelector(".yoda-log-toolbar", { state: "visible", timeout: 10000 });
  const logProof = await page.evaluate(() => {
    const environment = document.querySelector('.yoda-log-filter select[data-filter="environment"]');
    const options = Array.from(environment?.options || []).map((option) => option.value);
    return {
      filters: document.querySelectorAll(".yoda-log-filter select").length,
      options,
      text: document.querySelector(".yoda-log-window")?.textContent || "",
    };
  });
  if (logProof.filters !== 3 || !logProof.options.includes("test") || !logProof.text.includes("environment:")) {
    throw new Error(`Ask Yoda provenance controls are incomplete: ${JSON.stringify(logProof)}`);
  }
  await page.selectOption('.yoda-log-filter select[data-filter="environment"]', "test");
  await page.waitForFunction(() => document.querySelector(".yoda-log-window")?.textContent?.includes("environment: Test / synthetic"));
  await page.click("#modalPrimaryButton");

  await page.setViewportSize({ width: 390, height: 844 });
  await page.evaluate((slug) => window.__MEMORY_STARGRAPH__.loadEntity(slug), firstSlug);
  await page.waitForSelector(".detail-panel.is-map-overlay", { state: "visible", timeout: 30000 });
  const collapsed = await page.evaluate(() => {
    const panel = document.querySelector(".detail-panel.is-map-overlay");
    const title = document.querySelector("#detailTitle");
    const toggle = document.querySelector("#selectionContextToggle");
    const box = panel?.getBoundingClientRect();
    return {
      width: box?.width || 0,
      left: box?.left || 0,
      right: box?.right || 0,
      bottom: box?.bottom || 0,
      title: title?.textContent?.trim() || "",
      toggleVisible: Boolean(toggle?.offsetParent),
      expanded: toggle?.getAttribute("aria-expanded"),
    };
  });
  if (collapsed.width < 300 || collapsed.left < 0 || collapsed.right > 390 || collapsed.bottom > 844 || !collapsed.title || !collapsed.toggleVisible || collapsed.expanded !== "false") {
    throw new Error(`Collapsed mobile context is not readable and bounded: ${JSON.stringify(collapsed)}`);
  }
  await page.click("#selectionContextToggle");
  const expanded = await page.evaluate(() => ({
    expanded: document.querySelector("#selectionContextToggle")?.getAttribute("aria-expanded"),
    panelExpanded: document.querySelector(".detail-panel.is-map-overlay")?.classList.contains("is-context-expanded"),
    summary: document.querySelector("#detailSummary")?.textContent?.trim() || "",
  }));
  if (expanded.expanded !== "true" || !expanded.panelExpanded || !expanded.summary) {
    throw new Error(`Expanded mobile context did not expose selection content: ${JSON.stringify(expanded)}`);
  }

  if (screenshotPath) await page.screenshot({ path: screenshotPath, fullPage: true });
  console.log(JSON.stringify({ ok: true, versions, askLayout, logProof: { filters: logProof.filters, options: logProof.options }, collapsed, expanded }, null, 2));
} finally {
  await browser.close();
}
