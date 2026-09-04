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
let loadError;
for (const candidate of candidates) {
  try {
    ({ chromium } = require(candidate));
    break;
  } catch (error) {
    loadError = error;
  }
}
if (!chromium) throw new Error(`Unable to load Playwright: ${loadError?.message || "unknown"}`);

const appUrl = process.env.MEMORY_STARGRAPH_URL;
const cdpUrl = process.env.MEMORY_STARGRAPH_CDP_URL || "http://127.0.0.1:9333";
if (!appUrl) throw new Error("MEMORY_STARGRAPH_URL is required");

const browser = await chromium.connectOverCDP(cdpUrl);
const context = browser.contexts()[0];
const initialPages = context.pages();
const targetOrigin = new URL(appUrl).origin;
let page = initialPages.find((candidate) => {
  try {
    return new URL(candidate.url()).origin === targetOrigin;
  } catch {
    return false;
  }
});
if (!page) page = initialPages.find((candidate) => candidate.url() === "about:blank");
const createdPage = !page;
if (!page) page = await context.newPage();
const closePage = createdPage || (page.url() === "about:blank" && process.env.MEMORY_STARGRAPH_OWN_EXISTING_BLANK === "1");

const errors = [];
let expectedFailureConsole = false;
let expectedFailureConsoleCount = 0;
let responseDelayMs = 1200;
let failNext = false;
let requestCount = 0;
const syntheticEntries = [
  {
    slug: "index",
    captured_at: "2026-09-04T03:20:00-07:00",
    request_id: "sg0228-global-request",
    environment: "test",
    synthetic: true,
    test_run: true,
    pair_id: "sg0228-global-pair",
    diagnostics: { selected_slug: "index", source: "gbrain_think", model_status: "success", request_id: "sg0228-global-request" },
  },
  {
    slug: "products/memory-stargraph",
    captured_at: "2026-09-04T03:19:00-07:00",
    request_id: "sg0228-second-request",
    environment: "production",
    synthetic: false,
    test_run: false,
    pair_id: "sg0228-second-pair",
    diagnostics: { selected_slug: "products/memory-stargraph", source: "gbrain_think", model_status: "success", request_id: "sg0228-second-request" },
  },
];

await page.route("**/api/yoda-logs?*", async (route) => {
  requestCount += 1;
  if (responseDelayMs) await new Promise((resolve) => setTimeout(resolve, responseDelayMs));
  if (failNext) {
    failNext = false;
    await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error: "private backend detail must stay hidden" }) });
    return;
  }
  const requestUrl = new URL(route.request().url());
  const slug = requestUrl.searchParams.get("slug");
  const entries = slug ? syntheticEntries.filter((entry) => entry.slug === slug) : syntheticEntries;
  await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ ok: true, entries }) });
});

page.on("pageerror", (error) => errors.push(error.message || String(error)));
page.on("console", (message) => {
  if (message.type() !== "error") return;
  const text = message.text();
  if (expectedFailureConsole && /status of 503/i.test(text)) {
    expectedFailureConsoleCount += 1;
    return;
  }
  errors.push(text);
});

async function openGlobalLog() {
  await page.click("#navSettingsButton");
  await page.waitForSelector("#settingsYodaLogButton", { state: "visible", timeout: 10000 });
  await page.click("#settingsYodaLogButton");
}

async function waitForLogText(text) {
  await page.waitForFunction((expected) => document.querySelector(".yoda-log-window")?.textContent?.includes(expected), text, { timeout: 15000 });
}

try {
  await page.setViewportSize({ width: 1280, height: 900 });
  await page.goto(appUrl, { waitUntil: "domcontentloaded", timeout: 120000 });
  await page.reload({ waitUntil: "domcontentloaded", timeout: 120000 });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__?.getState?.().graph?.nodes?.length > 0, null, { timeout: 120000 });
  await page.waitForFunction(() => Boolean(window.__MEMORY_STARGRAPH__?.getState?.().focusSlug), null, { timeout: 30000 });

  await openGlobalLog();
  const initial = await page.evaluate(() => ({
    version: document.querySelector("#uiVersion")?.textContent?.trim() || "",
    message: document.querySelector("#modalMessage")?.textContent || "",
    log: document.querySelector(".yoda-log-window")?.textContent || "",
    busy: document.querySelector(".yoda-log-window")?.getAttribute("aria-busy") || "",
  }));
  if (initial.version !== "V1.0.216" || initial.busy !== "true" || !initial.log.includes("Loading persisted") || initial.log.includes("No Ask Yoda diagnostic entries")) {
    throw new Error(`View Log did not open in a truthful loading state: ${JSON.stringify(initial)}`);
  }
  await waitForLogText("test_pair: sg0228-global-pair");
  const globalLoaded = await page.evaluate(() => ({
    log: document.querySelector(".yoda-log-window")?.textContent || "",
    filters: document.querySelectorAll(".yoda-log-filter select").length,
    retryVisible: Boolean(document.querySelector(".yoda-log-toolbar button")),
  }));
  if (globalLoaded.filters !== 3 || globalLoaded.retryVisible || !globalLoaded.log.includes("selected_slug: products/memory-stargraph")) {
    throw new Error(`Global persisted logs did not reactively render: ${JSON.stringify(globalLoaded)}`);
  }
  await page.selectOption('.yoda-log-filter select[data-filter="environment"]', "test");
  await waitForLogText("environment: Test / synthetic");
  const filtered = await page.locator(".yoda-log-window").textContent();
  if (filtered.includes("selected_slug: products/memory-stargraph")) throw new Error("Global environment filter leaked a non-test entry.");
  await page.click("#modalPrimaryButton");

  responseDelayMs = 300;
  await page.evaluate(() => window.__MEMORY_STARGRAPH__.loadEntity("index"));
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__.getState().focusSlug === "index", null, { timeout: 30000 });
  await page.click("#selectionAskYodaButton");
  await page.waitForSelector("#operationModal.ask-yoda-modal:not([hidden])", { state: "visible", timeout: 30000 });
  const selectedSlug = await page.evaluate(() => window.__MEMORY_STARGRAPH__.getState().focusSlug);
  await page.click("#modalYodaLogButton");
  await waitForLogText(`selected_slug: ${selectedSlug}`);
  const nodeLoaded = await page.locator(".yoda-log-window").textContent();
  if (nodeLoaded.includes("selected_slug: products/memory-stargraph") && selectedSlug !== "products/memory-stargraph") {
    throw new Error("Node-scoped View Log rendered another node's entry.");
  }
  await page.click("#modalPrimaryButton");
  await page.waitForSelector("#operationModal.ask-yoda-modal:not([hidden])", { state: "visible", timeout: 30000 });
  await page.click("#modalCancelButton");

  await new Promise((resolve) => setTimeout(resolve, 2200));
  responseDelayMs = 0;
  failNext = true;
  expectedFailureConsole = true;
  await openGlobalLog();
  await page.waitForFunction(() => document.querySelector("#modalMessage")?.textContent?.includes("unavailable"), null, { timeout: 10000 });
  expectedFailureConsole = false;
  const failed = await page.evaluate(() => ({
    message: document.querySelector("#modalMessage")?.textContent || "",
    log: document.querySelector(".yoda-log-window")?.textContent || "",
    retry: document.querySelector(".yoda-log-toolbar button")?.textContent || "",
    leaksBackend: /private backend detail/i.test(document.querySelector("#operationModal")?.textContent || ""),
  }));
  if (failed.retry !== "Retry" || failed.leaksBackend || failed.log.includes("No Ask Yoda diagnostic entries")) {
    throw new Error(`View Log error state was not truthful, retryable, and private: ${JSON.stringify(failed)}`);
  }
  await page.click(".yoda-log-toolbar button");
  await waitForLogText("test_pair: sg0228-global-pair");

  await page.setViewportSize({ width: 390, height: 844 });
  const mobile = await page.evaluate(() => {
    const panel = document.querySelector("#operationModal .modal-panel");
    const log = document.querySelector(".yoda-log-window");
    const panelBox = panel?.getBoundingClientRect();
    const logBox = log?.getBoundingClientRect();
    return {
      panelVisible: Boolean(panelBox && panelBox.width > 0 && panelBox.height > 0),
      panelWithinViewport: Boolean(panelBox && panelBox.left >= 0 && panelBox.right <= innerWidth && panelBox.top >= 0 && panelBox.bottom <= innerHeight),
      logVisible: Boolean(logBox && logBox.width > 0 && logBox.height > 0),
      horizontalOverflow: Boolean(panel && panel.scrollWidth > panel.clientWidth + 1),
    };
  });
  if (!mobile.panelVisible || !mobile.panelWithinViewport || !mobile.logVisible || mobile.horizontalOverflow) {
    throw new Error(`Mobile View Log is not bounded: ${JSON.stringify(mobile)}`);
  }

  const result = {
    ok: true,
    initialPageCount: initialPages.length,
    finalPageCount: context.pages().length,
    createdPage,
    requestCount,
    expectedFailureConsoleCount,
    initial,
    globalLoaded: { filters: globalLoaded.filters },
    selectedSlug,
    failed,
    mobile,
    errors,
  };
  console.log(JSON.stringify(result, null, 2));
  if (expectedFailureConsoleCount !== 1) throw new Error(`Expected one injected 503 console signal, received ${expectedFailureConsoleCount}.`);
  if (errors.length) throw new Error(`Browser errors: ${JSON.stringify(errors)}`);
} finally {
  if (closePage) await page.close().catch(() => {});
  await browser.close().catch(() => {});
}
