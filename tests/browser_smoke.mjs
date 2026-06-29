import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const pathPlaywrightCandidates = (process.env.PATH || "")
  .split(path.delimiter)
  .filter((entry) => path.basename(entry) === ".bin")
  .map((entry) => path.join(path.dirname(entry), "playwright"));
const playwrightCandidates = [
  process.env.PLAYWRIGHT_MODULE,
  "/Users/tony/.cache/codex-runtimes/codex-primary-runtime/dependencies/node/node_modules/playwright",
  "playwright",
  ...pathPlaywrightCandidates,
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
  throw new Error(`Unable to load Playwright. Try: npx --yes --package playwright node tests/browser_smoke.mjs. Last error: ${loadError?.message || "unknown"}`);
}

const chromePath = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome";
const browser = await chromium.launch({ headless: true, executablePath: chromePath });
const page = await browser.newPage({ viewport: { width: 1440, height: 1700 }, deviceScaleFactor: 1 });
const appUrl = process.env.MEMORY_STARGRAPH_URL || "http://127.0.0.1:8788";

try {
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__ && window.__MEMORY_STARGRAPH__.getState().graph, null, { timeout: 120000 });
  await page.waitForTimeout(1000);

  const initial = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const slugs = state.graph.nodes.map((node) => node.slug);
    const usageNode = state.graph.nodes.find((node) => node.slug === "agent/reports/gbrain-usage");
    const datedUsageNodes = slugs.filter((slug) => /^agent\/reports\/gbrain-usage-\d{4}-\d{2}-\d{2}$/i.test(slug));
    return {
      title: document.title,
      h1: document.querySelector("h1")?.textContent,
      nodes: state.graph.stats.nodes,
      edges: state.graph.stats.edges,
      focus: state.focusSlug,
      source: state.graph.source,
      hasBlockedTonyGu: slugs.includes("people/tony-gu"),
      usageNode: usageNode ? {
        label: usageNode.label,
        reportCount: usageNode.report_count,
      } : null,
      datedUsageNodeCount: datedUsageNodes.length,
      categoryLegendItems: document.querySelectorAll("#categoryLegend span").length,
      lastRefreshText: document.querySelector("#lastRefresh")?.textContent,
      autoRefreshPresent: Boolean(document.querySelector("#autoRefreshToggle") && document.querySelector("#autoRefreshInterval")),
      autoRefreshInTopRight: Boolean(document.querySelector(".status-block #autoRefreshToggle") && document.querySelector(".status-block #autoRefreshInterval")),
      filtersPresent: Boolean(document.querySelector("#categoryFilter") && document.querySelector("#typeFilter") && document.querySelector("#minDegreeFilter") && document.querySelector("#clearFiltersButton")),
      zoomControlsPresent: Boolean(document.querySelector("#zoomInButton") && document.querySelector("#zoomOutButton") && document.querySelector("#zoomLevel")),
      zoomText: document.querySelector("#zoomLevel")?.textContent,
      hasDarshaGhost: slugs.includes("people/darsha-krana"),
      uiVersion: document.querySelector("#uiVersion")?.textContent,
      searchButtonPresent: Boolean(document.querySelector("#searchButton")),
      hiddenListText: document.querySelector("#hiddenList")?.textContent,
      metricsColumns: getComputedStyle(document.querySelector("#metrics")).gridTemplateColumns.split(" ").length,
    };
  });
  if (initial.hasBlockedTonyGu) {
    throw new Error("Blocked people/tony-gu entity is visible in the graph");
  }
  if (initial.hasDarshaGhost) {
    throw new Error("Deleted people/darsha-krana ghost entity is visible in the graph");
  }
  if (initial.datedUsageNodeCount > 0) {
    throw new Error("Expected dated gbrain usage reports to collapse into one usage node");
  }
  if (initial.categoryLegendItems < 2) {
    throw new Error("Expected category legend to render in the right panel");
  }
  if (!initial.lastRefreshText?.includes("Last refresh:")) {
    throw new Error("Expected latest refresh time to render");
  }
  if (!initial.autoRefreshPresent) {
    throw new Error("Expected auto refresh controls to render");
  }
  if (!/^V1\.0\.\d+$/.test(initial.uiVersion || "")) {
    throw new Error(`Expected UI version like V1.0.x to render, got ${initial.uiVersion}`);
  }
  if (!initial.searchButtonPresent) {
    throw new Error("Expected explicit Search button to render next to the search input");
  }
  if (!initial.source?.coverage?.root_index_loaded || !initial.source?.coverage?.expanded_slugs?.includes("index")) {
    throw new Error("Expected root index to be loaded eagerly in the seed graph");
  }
  if (!initial.autoRefreshInTopRight) {
    throw new Error("Expected auto refresh controls to render in the top-right status block");
  }
  if (!initial.filtersPresent) {
    throw new Error("Expected category, type, min-link, and clear filters to render");
  }
  if (!initial.zoomControlsPresent || initial.zoomText !== "100%") {
    throw new Error("Expected zoom controls to render at 100%");
  }
  if (initial.metricsColumns !== 4) {
    throw new Error("Expected statistics to render in one row on desktop");
  }

  await page.fill("#searchInput", "tony");
  await page.press("#searchInput", "Enter");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 30000 });
  await page.waitForTimeout(300);
  const search = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      query: state.query,
      matches: state.matchSlugs.size,
      filtered: state.filteredSlugs.size,
    };
  });

  const filters = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const category = [...document.querySelector("#categoryFilter").options].map((option) => option.value).find((value) => value && state.nodes.some((node) => node.category === value));
    const type = [...document.querySelector("#typeFilter").options].map((option) => option.value).find((value) => value && state.nodes.some((node) => node.type === value && (!category || node.category === category)));
    document.querySelector("#categoryFilter").value = category || "";
    document.querySelector("#categoryFilter").dispatchEvent(new Event("change", { bubbles: true }));
    document.querySelector("#typeFilter").value = type || "";
    document.querySelector("#typeFilter").dispatchEvent(new Event("change", { bubbles: true }));
    document.querySelector("#minDegreeFilter").value = "1";
    document.querySelector("#minDegreeFilter").dispatchEvent(new Event("input", { bubbles: true }));
    const filtered = [...state.filteredSlugs].map((slug) => state.nodeMap.get(slug)).filter(Boolean);
    const andPasses = filtered.every((node) => (
      (!category || node.category === category)
      && (!type || node.type === type)
      && (node.degree || 0) >= 1
    ));
    document.querySelector("#clearFiltersButton").click();
    return {
      category,
      type,
      filteredCount: filtered.length,
      andPasses,
      clearedCategory: document.querySelector("#categoryFilter").value,
      clearedType: document.querySelector("#typeFilter").value,
      clearedMin: document.querySelector("#minDegreeFilter").value,
      queryAfterClear: state.query,
    };
  });
  if (!filters.category || !filters.type || !filters.andPasses || filters.clearedCategory || filters.clearedType || filters.clearedMin !== "0" || filters.queryAfterClear !== "tony") {
    throw new Error("Expected filters to AND together and Clear Filters to reset only filter controls");
  }

  const zoom = await page.evaluate(() => {
    const before = window.__MEMORY_STARGRAPH__.getState().zoom;
    document.querySelector("#zoomInButton").click();
    const afterButton = window.__MEMORY_STARGRAPH__.getState().zoom;
    document.querySelector("#graphCanvas").dispatchEvent(new WheelEvent("wheel", { deltaY: 180, metaKey: true, bubbles: true, cancelable: true }));
    const afterWheel = window.__MEMORY_STARGRAPH__.getState().zoom;
    return {
      before,
      afterButton,
      afterWheel,
      label: document.querySelector("#zoomLevel")?.textContent,
    };
  });
  if (!(zoom.afterButton > zoom.before) || !(zoom.afterWheel < zoom.afterButton) || !zoom.label?.endsWith("%")) {
    throw new Error("Expected zoom buttons and Cmd+wheel gesture to update graph zoom");
  }

  const expansionProbe = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const candidate = state.nodes.find((node) => !node.expanded && state.filteredSlugs.has(node.slug));
    if (!candidate) return null;
    window.__pendingExpansionProbe = window.__MEMORY_STARGRAPH__.loadEntity(candidate.slug);
    return {
      slug: candidate.slug,
      summary: document.querySelector("#detailSummary")?.textContent,
      type: document.querySelector("#detailType")?.textContent,
      expanding: state.expandingSlugs.has(candidate.slug),
    };
  });
  if (expansionProbe && (!expansionProbe.summary?.includes("Loading direct neighbors") || !expansionProbe.type?.includes("loading direct links") || !expansionProbe.expanding)) {
    throw new Error("Expected selecting an unloaded node to show direct-neighbor loading status");
  }
  if (expansionProbe) {
    await page.evaluate(() => window.__pendingExpansionProbe);
  }

  const clickPoint = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const rect = document.querySelector("#graphCanvas").getBoundingClientRect();
    const node = state.nodes.find((item) => item.slug !== state.focusSlug && state.filteredSlugs.has(item.slug)) || state.nodes[0];
    return { x: rect.left + node.screenX, y: rect.top + node.screenY, slug: node.slug, degree: node.degree, size: node.size };
  });
  await page.mouse.move(clickPoint.x, clickPoint.y);
  await page.waitForTimeout(200);

  const hover = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      hover: state.hoverSlug,
      label: document.querySelector("#hoverLabel")?.textContent,
    };
  });
  await page.mouse.click(clickPoint.x, clickPoint.y);
  await page.waitForFunction(
    (slug) => {
      const state = window.__MEMORY_STARGRAPH__.getState();
      const node = state.nodeMap.get(slug);
      return state.focusSlug === slug && document.querySelector("#detailTitle")?.textContent === (node?.label || slug);
    },
    clickPoint.slug,
    { timeout: 20000 },
  );
  await page.waitForFunction(
    () => !document.querySelector("#detailType")?.textContent?.includes("loading"),
    null,
    { timeout: 20000 },
  );

  const afterClick = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const focus = state.nodeMap.get(state.focusSlug);
    const directSlugs = new Set(focus?.links || []);
    const visibleLabels = new Set(state.visibleLabelSlugs || []);
    return {
      focus: state.focusSlug,
      title: document.querySelector("#detailTitle")?.textContent,
      type: document.querySelector("#detailType")?.textContent,
      directLinks: [...document.querySelectorAll("#detailLinks button")].map((button) => button.textContent).slice(0, 8),
      everyDirectLinkHasLabel: [...directSlugs].every((slug) => visibleLabels.has(slug)),
    };
  });
  if (!afterClick.everyDirectLinkHasLabel) {
    throw new Error("Expected all directly linked nodes to have visible labels after selection");
  }

  await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const node = state.nodeMap.get(state.focusSlug) || state.nodes[0];
    const rect = document.querySelector("#graphCanvas").getBoundingClientRect();
    document.querySelector("#graphCanvas").dispatchEvent(new MouseEvent("dblclick", {
      clientX: rect.left + node.screenX,
      clientY: rect.top + node.screenY,
      bubbles: true,
      cancelable: true,
    }));
  });
  await page.waitForSelector("#operationModal:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#modalEditor")?.value.length > 0, null, { timeout: 20000 });
  const doubleClickModal = await page.evaluate(() => ({
    title: document.querySelector("#modalTitle")?.textContent,
    editorReadOnly: document.querySelector("#modalEditor")?.readOnly,
    cancelHidden: document.querySelector("#modalCancelButton")?.hidden,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
  }));
  if (!doubleClickModal.editorReadOnly || !doubleClickModal.cancelHidden || doubleClickModal.primary !== "Close") {
    throw new Error("Expected double-clicking a node to open read-only raw details");
  }
  await page.click("#modalCloseButton");

  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="view"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#modalEditor")?.value.length > 0, null, { timeout: 20000 });
  const operationModal = await page.evaluate(() => ({
    title: document.querySelector("#modalTitle")?.textContent,
    contentLength: document.querySelector("#modalEditor")?.value.length,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
    editorReadOnly: document.querySelector("#modalEditor")?.readOnly,
    cancelHidden: document.querySelector("#modalCancelButton")?.hidden,
  }));
  if (!operationModal.editorReadOnly || !operationModal.cancelHidden || operationModal.primary !== "Close") {
    throw new Error("Expected View raw details to be read-only with no Cancel button and a Close action");
  }
  await page.click("#modalCloseButton");

  const gbrainOperationTemplates = [];
  const firstMenuAction = await page.evaluate(() => document.querySelector("#contextMenu button")?.dataset.action);
  if (firstMenuAction !== "ask") {
    throw new Error("Expected Ask GBrain to be the first node menu action");
  }
  for (const action of ["ask", "media", "backlinks", "graph-query", "history", "add-link", "remove-link", "tags", "timeline", "attach-file", "embed"]) {
    await page.click("#nodeMenuButton");
    await page.waitForSelector("#contextMenu:not([hidden])");
    const menuText = await page.evaluate((value) => document.querySelector(`#contextMenu button[data-action="${value}"]`)?.textContent, action);
    if (!menuText) {
      throw new Error(`Expected context menu to include ${action}`);
    }
    await page.click(`#contextMenu button[data-action="${action}"]`);
    await page.waitForSelector("#operationModal:not([hidden])");
    const modal = await page.evaluate(() => ({
      kicker: document.querySelector("#modalKicker")?.textContent,
      primary: document.querySelector("#modalPrimaryButton")?.textContent,
      editor: document.querySelector("#modalEditor")?.value,
      editorHidden: document.querySelector("#modalEditor")?.hidden,
    }));
    gbrainOperationTemplates.push({ action, menuText, modal });
    await page.click("#modalCloseButton");
  }
  if (!gbrainOperationTemplates.every((item) => item.modal.primary && (item.modal.editor.includes(":") || item.modal.editorHidden))) {
    throw new Error(`Expected gbrain operation modals to render templates: ${JSON.stringify(gbrainOperationTemplates)}`);
  }

  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="delete"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  const deleteConfirmInitial = await page.evaluate(() => ({
    title: document.querySelector("#modalTitle")?.textContent,
    message: document.querySelector("#modalMessage")?.textContent,
    inputHidden: document.querySelector("#modalConfirmInput")?.hidden,
    deleteDisabled: document.querySelector("#modalPrimaryButton")?.disabled,
  }));
  if (!deleteConfirmInitial.deleteDisabled || deleteConfirmInitial.inputHidden) {
    throw new Error("Expected delete to require exact node-name confirmation before enabling");
  }
  const deleteExpectedLabel = await page.evaluate(() => document.querySelector("#modalConfirmInput")?.dataset.expected || "");
  await page.fill("#modalConfirmInput", `${deleteExpectedLabel}x`);
  const deleteConfirmWrong = await page.evaluate(() => document.querySelector("#modalPrimaryButton")?.disabled);
  if (!deleteConfirmWrong) {
    throw new Error("Expected delete to stay disabled when the confirmation name is not exact");
  }
  await page.fill("#modalConfirmInput", deleteExpectedLabel);
  await page.waitForFunction(() => document.querySelector("#modalPrimaryButton")?.disabled === false, null, { timeout: 10000 });
  const deleteConfirmExact = await page.evaluate(() => document.querySelector("#modalPrimaryButton")?.disabled);
  if (deleteConfirmExact) {
    throw new Error("Expected delete to enable after exact node-name confirmation");
  }
  await page.click("#modalCloseButton");

  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  const hideTargetSlug = await page.evaluate(() => window.__MEMORY_STARGRAPH__.getState().focusSlug);
  const hideMenuText = await page.evaluate(() => document.querySelector('#contextMenu button[data-action="hide"]')?.textContent);
  if (hideMenuText !== "Hide") {
    throw new Error("Expected context menu to include Hide action");
  }
  await page.click('#contextMenu button[data-action="hide"]');
  await page.waitForFunction((slug) => window.__MEMORY_STARGRAPH__.getState().hiddenSlugs.has(slug), hideTargetSlug, { timeout: 10000 });
  const hiddenAfterHide = await page.evaluate((slug) => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      hidden: state.hiddenSlugs.has(slug),
      filtered: state.filteredSlugs.has(slug),
      listText: document.querySelector("#hiddenList")?.textContent,
      hiddenButtons: [...document.querySelectorAll("#hiddenList button")].map((button) => button.textContent),
    };
  }, hideTargetSlug);
  if (!hiddenAfterHide.hidden || hiddenAfterHide.filtered || !hiddenAfterHide.listText?.includes(hideTargetSlug) || !hiddenAfterHide.hiddenButtons.includes("Show")) {
    throw new Error("Expected hidden node to leave galaxy and appear in Hidden List with Show action");
  }

  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__ && window.__MEMORY_STARGRAPH__.getState().graph, null, { timeout: 120000 });
  const hiddenAfterReload = await page.evaluate((slug) => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      hidden: state.hiddenSlugs.has(slug),
      filtered: state.filteredSlugs.has(slug),
      listText: document.querySelector("#hiddenList")?.textContent,
    };
  }, hideTargetSlug);
  if (!hiddenAfterReload.hidden || hiddenAfterReload.filtered || !hiddenAfterReload.listText?.includes(hideTargetSlug)) {
    throw new Error("Expected hidden node to persist across page reload");
  }

  await page.evaluate((slug) => {
    const items = [...document.querySelectorAll(".hidden-item")];
    const item = items.find((candidate) => candidate.textContent.includes(slug));
    item?.querySelector("button")?.click();
  }, hideTargetSlug);
  await page.waitForFunction((slug) => !window.__MEMORY_STARGRAPH__.getState().hiddenSlugs.has(slug), hideTargetSlug, { timeout: 10000 });
  const hiddenAfterShow = await page.evaluate((slug) => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      hidden: state.hiddenSlugs.has(slug),
      filtered: state.filteredSlugs.has(slug),
      listText: document.querySelector("#hiddenList")?.textContent,
    };
  }, hideTargetSlug);
  if (hiddenAfterShow.hidden || !hiddenAfterShow.filtered || hiddenAfterShow.listText?.includes(hideTargetSlug)) {
    throw new Error("Expected Show action to restore hidden node to the galaxy");
  }

  const rotationBefore = await page.evaluate(() => ({ ...window.__MEMORY_STARGRAPH__.getState().rotation }));
  await page.mouse.move(clickPoint.x, clickPoint.y);
  await page.mouse.down();
  await page.mouse.move(clickPoint.x + 140, clickPoint.y + 30, { steps: 8 });
  await page.mouse.up();
  await page.waitForTimeout(200);
  const rotationAfter = await page.evaluate(() => ({ ...window.__MEMORY_STARGRAPH__.getState().rotation }));

  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled, null, { timeout: 30000 });
  await page.fill("#searchInput", "RFC - JTuner - Part 03");
  await page.click("#searchButton");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 30000 });
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.getState().matchSlugs.has("products/jtuner/rfc"),
    null,
    { timeout: 10000 },
  );
  const partSearch = await page.evaluate(async () => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      matches: state.matchSlugs.size,
      slugs: [...state.matchSlugs].slice(0, 8),
      collapsedMetric: document.querySelector("#metricCollapsed")?.textContent,
      sourceStatus: state.graph.source.status,
      searchResults: state.graph.source.coverage?.search_results,
    };
  });
  if (partSearch.matches < 1) {
    throw new Error("Expected old part title search to find a collapsed parent node");
  }
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled, null, { timeout: 30000 });
  await page.fill("#searchInput", "Tony Guan");
  await page.press("#searchInput", "Enter");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 30000 });
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.getState().focusSlug === "people/tony-guan",
    null,
    { timeout: 15000 },
  );
  const tonySearch = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    return {
      focus: state.focusSlug,
      title: document.querySelector("#detailTitle")?.textContent,
      match: state.matchSlugs.has("people/tony-guan"),
      filtered: state.filteredSlugs.has("people/tony-guan"),
      expanded: state.nodeMap.get("people/tony-guan")?.expanded,
    };
  });
  if (!tonySearch.match || !tonySearch.filtered || !tonySearch.title?.toLowerCase().includes("tony")) {
    throw new Error("Expected Tony Guan search to focus and show people/tony-guan");
  }
  await page.evaluate(() => window.__MEMORY_STARGRAPH__.loadEntity("people/tony-guan"));
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.getState().focusSlug === "people/tony-guan"
      && !document.querySelector("#detailType")?.textContent?.includes("loading"),
    null,
    { timeout: 30000 },
  );
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.relationshipTypes("people/tony-guan", "companies/azul-systems").includes("employed by"),
    null,
    { timeout: 30000 },
  );
  const relationshipLabels = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const company = state.nodeMap.get("companies/azul-systems");
    window.__MEMORY_STARGRAPH__.setHover("companies/azul-systems");
    return {
      label: window.__MEMORY_STARGRAPH__.labelForNode(company),
      types: window.__MEMORY_STARGRAPH__.relationshipTypes("people/tony-guan", "companies/azul-systems"),
      hover: document.querySelector("#hoverLabel")?.textContent,
    };
  });
  if (relationshipLabels.label !== "Azul Systems") {
    throw new Error("Expected focused-neighbor canvas labels to show the company name instead of category/count text");
  }
  if (!relationshipLabels.types.includes("employed by") || !relationshipLabels.hover?.includes("relationship: employed by")) {
    throw new Error(`Expected hovering a direct linked company to show the link type: ${JSON.stringify(relationshipLabels)}`);
  }
  const directLinkHover = await page.evaluate(() => {
    const buttons = [...document.querySelectorAll("#detailLinks button")];
    const button = buttons.find((candidate) => candidate.textContent.includes("Azul Systems"));
    if (!button) return null;
    button.focus();
    const relationship = getComputedStyle(button.querySelector(".direct-link-relationship")).display;
    return {
      text: button.textContent,
      title: button.title,
      relationshipDisplay: relationship,
      hover: document.querySelector("#hoverLabel")?.textContent,
    };
  });
  if (!directLinkHover?.text?.includes("relationship: employed by") || directLinkHover.relationshipDisplay === "none" || !directLinkHover.hover?.includes("relationship: employed by")) {
    throw new Error(`Expected direct-link chip hover to visibly show employed by: ${JSON.stringify(directLinkHover)}`);
  }
  if (rotationBefore.x === rotationAfter.x && rotationBefore.y === rotationAfter.y) {
    throw new Error("Expected drag to change 3D rotation");
  }

  const cferSearch = await page.evaluate(async () => {
    const response = await fetch("/api/entity-expand/organizations%2Fcfer-foundation", { method: "POST" });
    const payload = await response.json();
    const cfer = payload.graph.nodes.find((node) => node.slug === "organizations/cfer-foundation");
    const entityResponse = await fetch("/api/entity/organizations%2Fcfer-foundation");
    const entityPayload = await entityResponse.json();
    return {
      degree: cfer?.degree,
      peopleLinks: (cfer?.links || []).filter((slug) => slug.startsWith("people/")).length,
      directPeopleNeighbors: (entityPayload.neighbors || []).filter((node) => node.slug.startsWith("people/")).length,
      title: entityPayload.entity?.label,
    };
  });
  if (cferSearch.peopleLinks !== 18 || cferSearch.directPeopleNeighbors !== 18) {
    throw new Error("Expected CFER Foundation to load all 18 linked people from backlinks");
  }

  await page.screenshot({ path: "/private/tmp/memory-stargraph-browser.png", fullPage: true });
  console.log(JSON.stringify({ initial, search, filters, zoom, cferSearch, expansionProbe, hover, clickPoint, afterClick, doubleClickModal, operationModal, gbrainOperationTemplates, deleteConfirmInitial, hiddenAfterHide, hiddenAfterReload, hiddenAfterShow, rotationBefore, rotationAfter, partSearch, tonySearch, relationshipLabels, screenshot: "/private/tmp/memory-stargraph-browser.png" }, null, 2));
} finally {
  await browser.close();
}
