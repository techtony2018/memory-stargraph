import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const playwrightCandidates = [
  process.env.PLAYWRIGHT_MODULE,
  "playwright",
  ...(process.env.PATH || "")
    .split(path.delimiter)
    .filter((entry) => path.basename(entry) === ".bin")
    .map((entry) => path.join(path.dirname(entry), "playwright")),
].filter(Boolean);

let chromium;
let loadError;
for (const candidate of playwrightCandidates) {
  try {
    ({ chromium } = require(candidate));
    break;
  } catch (error) {
    loadError = error;
  }
}
if (!chromium) {
  throw new Error(`Unable to load Playwright. Last error: ${loadError?.message || "unknown"}`);
}

const appUrl = process.env.MEMORY_STARGRAPH_URL || "https://127.0.0.1:8788";
const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const query = "optional timeout telemetry is not a todo";
const archivedExactIds = new Map([
  ["SG-0200", "notes/memory-starmap-todo-list/refresh-settings-readiness-cards-from-current-readiness-apis"],
  ["SG-0201", "notes/memory-starmap-todo-list/include-persist-identity-metadata-in-sre-decision-bundles"],
]);
const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 1000 }, ignoreHTTPSErrors: true });

try {
  const apiResponse = await page.request.get(`${appUrl}/api/search?q=${encodeURIComponent(query)}`, { ignoreHTTPSErrors: true, timeout: 30000 });
  if (!apiResponse.ok()) {
    throw new Error(`API search failed with HTTP ${apiResponse.status()}`);
  }
  const apiPayload = await apiResponse.json();
  const apiCoverage = apiPayload.graph?.source?.coverage || {};
  const apiTopSlug = apiCoverage.search_slugs?.[0] || "";
  if (!apiTopSlug) throw new Error(`API did not return a top search slug: ${JSON.stringify(apiCoverage)}`);

  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__?.getState().graph?.nodes?.length > 0, null, { timeout: 120000 });
  await page.click("#navSearchButton");
  await page.waitForFunction(() => {
    const input = document.querySelector("#searchInput");
    const flyout = document.querySelector("#searchFlyout");
    return Boolean(input && flyout && !flyout.hidden && !input.disabled && input.offsetParent !== null && document.activeElement === input);
  }, null, { timeout: 1000 });
  await page.fill("#searchInput", query);
  await page.press("#searchInput", "Enter");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 60000 });
  await page.waitForFunction((expectedTopSlug) => {
    const state = window.__MEMORY_STARGRAPH__?.getState();
    const coverage = state?.graph?.source?.coverage || {};
    const firstVisible = (coverage.search_slugs || []).find((slug) => state?.nodeMap?.has(slug)) || "";
    return coverage.last_search_query === "optional timeout telemetry is not a todo"
      && coverage.search_slugs?.[0] === expectedTopSlug
      && (state.focusSlug === expectedTopSlug || firstVisible === expectedTopSlug);
  }, apiTopSlug, { timeout: 15000 });
  const state = await page.evaluate((expectedTopSlug) => {
    const appState = window.__MEMORY_STARGRAPH__.getState();
    const coverage = appState.graph.source?.coverage || {};
    const feedback = document.querySelector("#hoverLabel")?.textContent || "";
    return {
      apiTopSlug: expectedTopSlug,
      uiTopSlug: coverage.search_slugs?.[0] || "",
      focusSlug: appState.focusSlug,
      firstVisibleSearchResult: (coverage.search_slugs || []).find((slug) => appState.nodeMap.has(slug)) || "",
      searchStatus: coverage.search_status,
      primaryStatus: coverage.search_primary_status,
      feedback,
      inputEnabled: !document.querySelector("#searchInput")?.disabled,
      searchRailOpen: !document.querySelector("#searchFlyout")?.hidden,
    };
  }, apiTopSlug);
  console.log(JSON.stringify(state, null, 2));
  if (
    state.uiTopSlug !== state.apiTopSlug
    || (state.focusSlug !== state.apiTopSlug && state.firstVisibleSearchResult !== state.apiTopSlug)
    || !state.feedback.includes(state.apiTopSlug)
    || !state.inputEnabled
    || !state.searchRailOpen
  ) {
    throw new Error(`API/UI search parity failed: ${JSON.stringify(state)}`);
  }

  for (const [todoId, expectedSlug] of archivedExactIds) {
    const exactApiResponse = await page.request.get(`${appUrl}/api/search?q=${encodeURIComponent(todoId)}`, { ignoreHTTPSErrors: true, timeout: 30000 });
    if (!exactApiResponse.ok()) {
      throw new Error(`${todoId} API search failed with HTTP ${exactApiResponse.status()}`);
    }
    const exactApiPayload = await exactApiResponse.json();
    const exactApiCoverage = exactApiPayload.graph?.source?.coverage || {};
    const exactApiTopSlug = exactApiCoverage.search_slugs?.[0] || "";
    if (exactApiTopSlug !== expectedSlug) {
      throw new Error(`${todoId} API did not return archived child slug first: ${JSON.stringify({ exactApiTopSlug, expectedSlug, exactApiCoverage })}`);
    }
    await page.click("#navSearchButton");
    await page.fill("#searchInput", todoId);
    await page.press("#searchInput", "Enter");
    await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 60000 });
    await page.waitForFunction(({ queryId, expected }) => {
      const appState = window.__MEMORY_STARGRAPH__?.getState();
      const coverage = appState?.graph?.source?.coverage || {};
      const firstVisible = (coverage.search_slugs || []).find((slug) => appState?.nodeMap?.has(slug)) || "";
      return coverage.last_search_query === queryId
        && coverage.search_slugs?.[0] === expected
        && (appState.focusSlug === expected || firstVisible === expected);
    }, { queryId: todoId, expected: expectedSlug }, { timeout: 15000 });
    const exactUiState = await page.evaluate((expected) => {
      const appState = window.__MEMORY_STARGRAPH__.getState();
      const coverage = appState.graph.source?.coverage || {};
      return {
        topSlug: coverage.search_slugs?.[0] || "",
        focusSlug: appState.focusSlug,
        firstVisibleSearchResult: (coverage.search_slugs || []).find((slug) => appState.nodeMap.has(slug)) || "",
        exactTodoStatus: coverage.search_exact_todo_id_status,
        feedback: document.querySelector("#hoverLabel")?.textContent || "",
        expected,
      };
    }, expectedSlug);
    console.log(JSON.stringify({ todoId, exactUiState }, null, 2));
    if (
      exactUiState.topSlug !== expectedSlug
      || (exactUiState.focusSlug !== expectedSlug && exactUiState.firstVisibleSearchResult !== expectedSlug)
      || exactUiState.exactTodoStatus !== "complete"
      || !exactUiState.feedback.includes(expectedSlug)
    ) {
      throw new Error(`${todoId} UI did not focus/list archived exact match: ${JSON.stringify(exactUiState)}`);
    }
  }

  const missingResponse = await page.request.get(`${appUrl}/api/search?q=SG-9999`, { ignoreHTTPSErrors: true, timeout: 30000 });
  const missingPayload = await missingResponse.json();
  const missingCoverage = missingPayload.graph?.source?.coverage || {};
  if ((missingCoverage.search_slugs || []).length !== 0 || missingCoverage.search_exact_todo_id_status !== "complete") {
    throw new Error(`SG-9999 should remain a truthful no-result exact TODO search: ${JSON.stringify(missingCoverage)}`);
  }
} finally {
  await browser.close();
}
