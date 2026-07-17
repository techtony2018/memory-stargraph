import { createRequire } from "node:module";
import path from "node:path";

const require = createRequire(import.meta.url);
const pathPlaywrightCandidates = (process.env.PATH || "")
  .split(path.delimiter)
  .filter((entry) => path.basename(entry) === ".bin")
  .map((entry) => path.join(path.dirname(entry), "playwright"));
const playwrightCandidates = [
  process.env.PLAYWRIGHT_MODULE,
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
async function openSearchFlyout() {
  await page.evaluate(() => {
    const flyout = document.querySelector("#searchFlyout");
    if (flyout?.hidden) document.querySelector("#navSearchButton")?.click();
  });
  await page.waitForFunction(() => !document.querySelector("#searchFlyout")?.hidden, null, { timeout: 5000 });
}
const runtimeErrors = [];
page.on("pageerror", (error) => {
  runtimeErrors.push(error.message || String(error));
});
page.on("console", (message) => {
  if (message.type() === "error") runtimeErrors.push(message.text());
});

try {
  await page.goto(appUrl, { waitUntil: "domcontentloaded" });
  await page.waitForFunction(() => window.__MEMORY_STARGRAPH__ && window.__MEMORY_STARGRAPH__.getState().graph, null, { timeout: 120000 });
  await page.waitForTimeout(1000);

  const initial = await page.evaluate(() => {
    window.__MEMORY_STARGRAPH__.setHover(null);
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
      categoryLegendItems: document.querySelectorAll("#categoryLegend button").length,
      hubClusterItems: document.querySelectorAll("#hubClusterLegend button").length,
      categoryLimit: document.querySelector("#categoryLimitInput")?.value,
      clusterLimit: document.querySelector("#clusterLimitInput")?.value,
      viewOptionsPanelPresent: [...document.querySelectorAll(".panel-label")].some((item) => item.textContent === "View Options"),
      filtersPresent: Boolean(!document.querySelector("#categoryFilter") && !document.querySelector("#tagFilter") && document.querySelector("#minDegreeFilter") && !document.querySelector("#clearFiltersButton")),
      compactTopControls: {
        noSearchLabel: !document.body.textContent.includes("Search entities"),
        matchesOnlyText: document.querySelector(".toggle-wrap span")?.textContent,
        noStatusLegend: !document.body.textContent.includes("focused")
          && !document.body.textContent.includes("neighborhood")
          && !document.body.textContent.includes("search match"),
        minLinksInline: document.querySelector(".filter-wrap.short")?.getBoundingClientRect().height <= 40,
        noConstellationView: !document.body.textContent.includes("Constellation View"),
        favicon: document.querySelector('link[rel="icon"]')?.getAttribute("href"),
        brandLogo: Boolean(document.querySelector(".nav-logo")),
        brandWordmark: Boolean(document.querySelector(".graph-wordmark")),
        brandWordmarkLink: document.querySelector(".graph-wordmark-link")?.getAttribute("href"),
        brandWordmarkSrc: document.querySelector(".graph-wordmark")?.getAttribute("src"),
        versionLink: document.querySelector("#uiVersion")?.getAttribute("href"),
        hasTooltip: Boolean(document.querySelector(".has-tooltip")),
        searchInputNoTooltip: !document.querySelector(".search-wrap.has-tooltip"),
        noCategoryFilter: !document.querySelector("#categoryFilter"),
        noTagFilter: !document.querySelector("#tagFilter"),
      },
      zoomControlsPresent: Boolean(document.querySelector("#zoomInButton") && document.querySelector("#zoomOutButton") && document.querySelector("#zoomLevel")),
      zoomControlsInline: Boolean(document.querySelector(".graph-canvas-wrap .graph-floating-controls .zoom-floating #zoomInButton")),
      historyControlsPresent: Boolean(document.querySelector("#historyBackButton") && document.querySelector("#historyForwardButton") && document.querySelector("#floatingHistoryBackButton") && document.querySelector("#floatingHistoryForwardButton")),
      historyControlsDisabledInitially: Boolean(document.querySelector("#historyBackButton")?.disabled && document.querySelector("#historyForwardButton")?.disabled),
      clusteringFloating: Boolean(document.querySelector(".graph-canvas-wrap .graph-floating-controls #cloudModeButton.cluster-icon-button")),
      clusteringIconOnly: document.querySelector("#cloudModeButton")?.textContent.trim() === "",
      newButtonFloating: Boolean(document.querySelector(".graph-canvas-wrap .new-node-floating #newNodeButton.new-node-icon-button")),
      newButtonIconOnly: document.querySelector("#newNodeButton")?.textContent.trim() === "",
      newButtonOpacity: Number.parseFloat(getComputedStyle(document.querySelector(".new-node-floating")).opacity),
      newButtonText: document.querySelector("#newNodeButton")?.textContent,
      autopilotToolbarOrder: [...document.querySelectorAll("#autopilotFlyout > button, #autopilotFlyout > span")].map((item) => item.id),
      noPlannedFlightRailButton: ![...document.querySelectorAll(".nav-rail-button")].some((item) => /planned flight/i.test(item.textContent || "")),
      toolbarAboveMap: (() => {
        const toolbar = document.querySelector("#metrics")?.getBoundingClientRect();
        const map = document.querySelector(".graph-canvas-wrap")?.getBoundingClientRect();
        return Boolean(toolbar && map && toolbar.right <= map.right && toolbar.bottom <= map.bottom && toolbar.left >= map.left && toolbar.top >= map.top);
      })(),
      graphFloatingOpacity: Number.parseFloat(getComputedStyle(document.querySelector(".graph-floating-controls")).opacity),
      mapControlsInsideMap: (() => {
        const map = document.querySelector(".graph-canvas-wrap")?.getBoundingClientRect();
        const floating = document.querySelector(".graph-floating-controls")?.getBoundingClientRect();
        const create = document.querySelector(".new-node-floating")?.getBoundingClientRect();
        return Boolean(map && floating && create
          && floating.top >= map.top && floating.left >= map.left && floating.right <= map.right && floating.bottom <= map.bottom
          && create.top >= map.top && create.left >= map.left && create.right <= map.right && create.bottom <= map.bottom);
      })(),
      mapControlsPositioned: (() => {
        const map = document.querySelector(".graph-canvas-wrap")?.getBoundingClientRect();
        const floating = document.querySelector(".graph-floating-controls")?.getBoundingClientRect();
        const create = document.querySelector(".new-node-floating")?.getBoundingClientRect();
        const cluster = document.querySelector("#cloudModeButton")?.getBoundingClientRect();
        const zoom = document.querySelector(".zoom-floating")?.getBoundingClientRect();
        return Boolean(map && floating && create && cluster && zoom
          && Math.abs(floating.left - map.left - 18) <= 2
          && Math.abs(floating.top - map.top - 18) <= 2
          && Math.abs(create.right - map.right + 18) <= 2
          && Math.abs(create.top - map.top - 18) <= 2
          && Math.abs(cluster.top - zoom.top) <= 4);
      })(),
      modalAboveMapControls: Number.parseInt(getComputedStyle(document.querySelector("#operationModal")).zIndex, 10) > Number.parseInt(getComputedStyle(document.querySelector(".graph-floating-controls")).zIndex, 10),
      cloudModePresent: Boolean(document.querySelector("#cloudModeToggle")?.checked),
      timelinePresent: !document.querySelector("#autopilotFlyout #timelineDaysInput") && !document.querySelector("#autopilotFlyout #timelineValue"),
      tourPresent: Boolean(document.querySelector("#tourPlanButton") && document.querySelector("#tourButton") && document.querySelector("#tourPrevButton") && document.querySelector("#tourNextButton") && document.querySelector("#tourStopButton")),
      directLinksPanelPresent: Boolean(document.querySelector("#detailLinks")),
      pointerHint: document.querySelector("#hoverLabel")?.textContent,
      hasDarshaGhost: slugs.includes("people/darsha-krana"),
      uiVersion: document.querySelector("#uiVersion")?.textContent,
      searchButtonPresent: Boolean(document.querySelector("#searchButton")),
      hiddenListText: document.querySelector("#hiddenList")?.textContent,
      metricsColumns: getComputedStyle(document.querySelector("#metrics")).gridTemplateColumns.split(" ").length,
      sourceControlsInGraphSource: Boolean(document.querySelector(".source-control-stack #sourceBadge") && document.querySelector(".source-control-stack #cacheLimitInput") && document.querySelector(".source-control-stack #flushCacheButton")),
      settingsSections: [...document.querySelectorAll("#settingsFlyout .settings-section h3")].map((item) => item.textContent.trim()),
      flushCachePresent: Boolean(document.querySelector("#flushCacheButton")),
      lastRefreshPresent: Boolean(document.querySelector("#lastRefresh")),
      refreshInlineControls: Boolean(document.querySelector(".refresh-inline-controls #autoRefreshToggle") && document.querySelector(".refresh-inline-controls #autoRefreshInterval")),
      selectionYodaPresent: Boolean(document.querySelector("#selectionAskYodaButton")),
      searchControlsInHeaderWorkflow: Boolean(document.querySelector("#searchFlyout .search-group") && document.querySelector("#searchFlyout #matchesOnlyToggle") && document.querySelector("#searchFlyout #minDegreeFilter")),
      tooltipZIndex: Number.parseInt(getComputedStyle(document.querySelector("#graphTooltip")).zIndex, 10),
      animationRunning: Boolean(state.animationHandle),
      canvasNonBlank: (() => {
        const canvas = document.querySelector("#graphCanvas");
        const context = canvas?.getContext("2d");
        if (!canvas || !context) return false;
        const points = [
          [0.25, 0.35],
          [0.38, 0.45],
          [0.5, 0.5],
          [0.62, 0.45],
          [0.75, 0.35],
        ];
        for (const [xRatio, yRatio] of points) {
          const x = Math.max(0, Math.floor(canvas.width * xRatio) - 28);
          const y = Math.max(0, Math.floor(canvas.height * yRatio) - 28);
          const sample = context.getImageData(x, y, 56, 56).data;
          for (let index = 0; index < sample.length; index += 4) {
            if (sample[index] || sample[index + 1] || sample[index + 2] || sample[index + 3]) return true;
          }
        }
        return false;
      })(),
    };
  });
  if (runtimeErrors.length) {
    throw new Error(`Expected no frontend runtime errors, got: ${runtimeErrors.join(" | ")}`);
  }
  if (initial.filtered < 1 || !initial.canvasNonBlank) {
    throw new Error(`Expected graph to render visible nodes on canvas: ${JSON.stringify(initial)}`);
  }
  if (initial.hasBlockedTonyGu) {
    throw new Error("Blocked people/tony-gu entity is visible in the graph");
  }
  if (initial.hasDarshaGhost) {
    throw new Error("Deleted people/darsha-krana ghost entity is visible in the graph");
  }
  if (initial.datedUsageNodeCount > 0) {
    throw new Error("Expected dated gbrain usage reports to collapse into one usage node");
  }
  if (initial.categoryLegendItems !== 5 || initial.hubClusterItems > 5 || initial.categoryLimit !== "5" || initial.clusterLimit !== "5") {
    throw new Error(`Expected Category to default to top 5 and Clusters to show up to top 5 hubs: ${JSON.stringify(initial)}`);
  }
  if (!initial.cloudModePresent || !initial.timelinePresent || !initial.tourPresent || initial.directLinksPanelPresent || initial.viewOptionsPanelPresent) {
    throw new Error(`Expected top-row cloud mode, timeline, Memory Tour, no View Options panel, and no Direct Links panel: ${JSON.stringify(initial)}`);
  }
  if (!initial.pointerHint?.includes("Hover for full names. Click to select") || initial.pointerHint.includes("Long-press")) {
    throw new Error(`Expected desktop pointer hint to use hover/click wording: ${initial.pointerHint}`);
  }
  if (initial.lastRefreshPresent || initial.refreshInlineControls || JSON.stringify(initial.settingsSections) !== JSON.stringify(["Display", "Yoda", "Setup", "Cache"]) || !initial.flushCachePresent || !initial.selectionYodaPresent) {
    throw new Error(`Expected Settings Display/Yoda/Setup/Cache with Flush, no refresh controls, no Last refresh, and selection Yoda button: ${JSON.stringify(initial)}`);
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
  if (!initial.sourceControlsInGraphSource) {
    throw new Error("Expected source/cache controls to render in Settings");
  }
  if (!initial.filtersPresent) {
    throw new Error("Expected only the min-link filter to render");
  }
  if (
    !initial.compactTopControls.noSearchLabel
    || initial.compactTopControls.matchesOnlyText !== "Matches"
    || !initial.compactTopControls.noStatusLegend
    || !initial.compactTopControls.minLinksInline
    || !initial.compactTopControls.noConstellationView
    || initial.compactTopControls.favicon !== "/assets/brand/logo-circle-transparent.png"
    || !initial.compactTopControls.brandLogo
    || !initial.compactTopControls.brandWordmark
    || initial.compactTopControls.brandWordmarkLink !== "https://github.com/techtony2018/memory-stargraph"
    || initial.compactTopControls.brandWordmarkSrc !== "/assets/brand/wordmark-line-small.png"
    || initial.compactTopControls.versionLink !== "https://github.com/techtony2018/memory-stargraph"
    || !initial.compactTopControls.hasTooltip
    || !initial.compactTopControls.searchInputNoTooltip
    || !initial.compactTopControls.noCategoryFilter
    || !initial.compactTopControls.noTagFilter
  ) {
    throw new Error(`Expected compact top controls with no category/tag filters: ${JSON.stringify(initial.compactTopControls)}`);
  }
  const expectedTourOrder = ["autopilotModeIcon", "tourPlanButton", "tourButton", "tourPrevButton", "tourNextButton", "tourStopButton", "tourCounter"];
  if (!initial.zoomControlsPresent || !initial.zoomControlsInline || !initial.historyControlsPresent || !initial.historyControlsDisabledInitially || !initial.clusteringFloating || !initial.clusteringIconOnly || !initial.newButtonFloating || !initial.newButtonIconOnly || initial.newButtonOpacity > 0.4 || !initial.tourPresent || !initial.noPlannedFlightRailButton || expectedTourOrder.some((id, index) => initial.autopilotToolbarOrder[index] !== id) || !initial.toolbarAboveMap || initial.graphFloatingOpacity > 0.4 || !initial.mapControlsInsideMap || !initial.modalAboveMapControls) {
    throw new Error(`Expected map-contained metrics, Memory Tour group to wrap days, transparent controls, history navigation, and right-top New control: ${JSON.stringify(initial)}`);
  }
  if (initial.metricsColumns !== 1) {
    throw new Error("Expected graph statistics to render as compact radar widget");
  }
  if (!initial.sourceControlsInGraphSource || !initial.searchControlsInHeaderWorkflow || initial.tooltipZIndex < 20) {
    throw new Error(`Expected source controls in Graph source, search controls beside wordmark, and graph tooltip above graph marks: ${JSON.stringify(initial)}`);
  }

  await page.setViewportSize({ width: 1024, height: 900 });
  await page.waitForTimeout(250);
  const mediumHeaderLayout = await page.evaluate(() => {
    const workflow = document.querySelector(".workspace")?.getBoundingClientRect();
    const nav = document.querySelector(".nav-rail")?.getBoundingClientRect();
    const graph = document.querySelector(".graph-canvas-wrap")?.getBoundingClientRect();
    const search = document.querySelector("#searchFlyout")?.getBoundingClientRect();
    const tour = document.querySelector("#autopilotFlyout")?.getBoundingClientRect();
    const viewportWidth = document.documentElement.clientWidth;
    return {
      viewportWidth,
      workflowRight: workflow?.right,
      navWidth: Math.round(nav?.width || 0),
      graphWidth: Math.round(graph?.width || 0),
      searchHidden: Boolean(search && document.querySelector("#searchFlyout")?.hidden),
      tourHidden: Boolean(tour && document.querySelector("#autopilotFlyout")?.hidden),
      contained: Boolean(workflow && graph && workflow.left >= 0 && workflow.right <= viewportWidth + 1 && graph.right <= viewportWidth + 1),
    };
  });
  if (!mediumHeaderLayout.contained || mediumHeaderLayout.navWidth < 50 || mediumHeaderLayout.graphWidth < 700 || !mediumHeaderLayout.searchHidden || !mediumHeaderLayout.tourHidden) {
    throw new Error(`Expected compact nav-rail and hidden flyout controls to stay contained at 1024px: ${JSON.stringify(mediumHeaderLayout)}`);
  }
  await page.setViewportSize({ width: 1440, height: 1700 });
  await page.waitForTimeout(250);

  await openSearchFlyout();
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
    document.querySelector("#minDegreeFilter").value = "1";
    document.querySelector("#minDegreeFilter").dispatchEvent(new Event("input", { bubbles: true }));
    const filtered = [...state.filteredSlugs].map((slug) => state.nodeMap.get(slug)).filter(Boolean);
    const minPasses = filtered.every((node) => (node.degree || 0) >= 1);
    document.querySelector("#minDegreeFilter").value = "0";
    document.querySelector("#minDegreeFilter").dispatchEvent(new Event("input", { bubbles: true }));
    return {
      filteredCount: filtered.length,
      minPasses,
      noCategoryFilter: !document.querySelector("#categoryFilter"),
      noClearButton: !document.querySelector("#clearFiltersButton"),
      noTagFilter: !document.querySelector("#tagFilter"),
      clearedMin: document.querySelector("#minDegreeFilter").value,
      queryAfterClear: state.query,
    };
  });
  if (!filters.minPasses || !filters.noCategoryFilter || !filters.noClearButton || !filters.noTagFilter || filters.clearedMin !== "0" || filters.queryAfterClear !== "tony") {
    throw new Error("Expected Min Links to filter independently with category/tag filters removed");
  }

  await openSearchFlyout();
  await page.fill("#searchInput", "聊天室");
  await page.press("#searchInput", "Enter");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 30000 });
  await page.waitForTimeout(300);
  const unicodeSearch = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const focused = state.nodeMap.get(state.focusSlug);
    return {
      query: state.query,
      matches: state.matchSlugs.size,
      focus: state.focusSlug,
      title: focused?.label,
    };
  });
  if (unicodeSearch.query !== "聊天室" || unicodeSearch.matches < 1 || unicodeSearch.focus === "people/tony-guan") {
    throw new Error(`Expected Chinese search to surface backend search matches and move focus: ${JSON.stringify(unicodeSearch)}`);
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
      magnifierButtons: Number(Boolean(document.querySelector("#zoomInButton svg"))) + Number(Boolean(document.querySelector("#zoomOutButton svg"))),
      historyButtons: document.querySelectorAll(".zoom-floating .history-nav-button").length,
      label: document.querySelector("#zoomLevel")?.textContent,
    };
  });
  if (!(zoom.afterButton > zoom.before) || !(zoom.afterWheel < zoom.afterButton) || zoom.magnifierButtons !== 2 || zoom.historyButtons !== 2 || !zoom.label?.endsWith("%")) {
    throw new Error("Expected two floating magnifier zoom buttons, two history buttons, ratio label, and Cmd+wheel gesture to update graph zoom");
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

  await page.evaluate(() => {
    const panel = document.querySelector("#mapFilterPanel");
    if (panel && !panel.classList.contains("is-hidden")) {
      panel.classList.add("is-hidden");
      document.querySelector("#filterDrawerHandle")?.classList.remove("is-hidden");
    }
  });
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
  await page.waitForFunction(
    () => {
      const state = window.__MEMORY_STARGRAPH__.getState();
      const focus = state.nodeMap.get(state.focusSlug);
      const directSlugs = new Set(focus?.links || []);
      const visibleLabels = new Set(state.visibleLabelSlugs || []);
      return [...directSlugs].every((slug) => visibleLabels.has(slug));
    },
    null,
    { timeout: 5000 },
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
      everyDirectLinkHasLabel: [...directSlugs].every((slug) => visibleLabels.has(slug)),
    };
  });
  if (!afterClick.everyDirectLinkHasLabel) {
    throw new Error("Expected all directly linked nodes to have visible labels after selection");
  }

  const historyNav = await page.evaluate(async () => {
    const api = window.__MEMORY_STARGRAPH__;
    const state = api.getState();
    const first = state.focusSlug;
    const secondNode = state.nodes.find((node) => node.slug !== first && state.filteredSlugs.has(node.slug) && !state.hiddenSlugs.has(node.slug));
    if (!first || !secondNode) return null;
    await api.loadEntity(secondNode.slug);
    const afterSecond = state.focusSlug;
    const backEnabled = !document.querySelector("#historyBackButton")?.disabled
      && !document.querySelector("#floatingHistoryBackButton")?.disabled;
    await api.navigateSelectionHistory(-1);
    const afterBack = state.focusSlug;
    const forwardEnabled = !document.querySelector("#historyForwardButton")?.disabled
      && !document.querySelector("#floatingHistoryForwardButton")?.disabled;
    await api.navigateSelectionHistory(1);
    return {
      first,
      afterSecond,
      afterBack,
      afterForward: state.focusSlug,
      historyLength: state.selectionHistory.slugs.length,
      historyIndex: state.selectionHistory.index,
      backEnabled,
      forwardEnabled,
    };
  });
  if (!historyNav || historyNav.afterSecond === historyNav.first || historyNav.afterBack !== historyNav.first || historyNav.afterForward !== historyNav.afterSecond || !historyNav.backEnabled || !historyNav.forwardEnabled || historyNav.historyLength > 20) {
    throw new Error(`Expected selection history back/forward navigation to work from sidebar and floating buttons: ${JSON.stringify(historyNav)}`);
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
  await page.waitForFunction(() => document.querySelector("#modalMarkdown")?.textContent.length > 0, null, { timeout: 20000 });
  const doubleClickModal = await page.evaluate(() => ({
    title: document.querySelector("#modalTitle")?.textContent,
    markdownVisible: !document.querySelector("#modalMarkdown")?.hidden,
    editorHidden: document.querySelector("#modalEditor")?.hidden,
    cancelHidden: document.querySelector("#modalCancelButton")?.hidden,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
  }));
  if (!doubleClickModal.markdownVisible || !doubleClickModal.editorHidden || !doubleClickModal.cancelHidden || doubleClickModal.primary !== "Close") {
    throw new Error("Expected double-clicking a node to open rendered read-only details");
  }
  await page.click("#modalCloseButton");

  await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    state.query = "";
    state.matchesOnly = false;
    state.filters.minDegree = 0;
    state.timelineDays = 0;
    state.hiddenClusters.clear();
    state.hiddenHubConnections.clear();
    const searchInput = document.querySelector("#searchInput");
    const matchesOnlyToggle = document.querySelector("#matchesOnlyToggle");
    const minDegreeFilter = document.querySelector("#minDegreeFilter");
    const timelineDaysInput = document.querySelector("#timelineDaysInput");
    if (searchInput) searchInput.value = "";
    if (matchesOnlyToggle) matchesOnlyToggle.checked = false;
    if (minDegreeFilter) minDegreeFilter.value = "0";
    if (timelineDaysInput) timelineDaysInput.value = "0";
    searchInput?.dispatchEvent(new Event("input", { bubbles: true }));
    matchesOnlyToggle?.dispatchEvent(new Event("change", { bubbles: true }));
    minDegreeFilter?.dispatchEvent(new Event("input", { bubbles: true }));
    timelineDaysInput?.dispatchEvent(new Event("input", { bubbles: true }));
  });
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="view"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#modalMarkdown")?.textContent.length > 0, null, { timeout: 20000 });
  const operationModal = await page.evaluate(() => ({
    documentTitle: document.title,
    title: document.querySelector("#modalTitle")?.textContent,
    contentLength: document.querySelector("#modalMarkdown")?.textContent.length,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
    markdownVisible: !document.querySelector("#modalMarkdown")?.hidden,
    editorHidden: document.querySelector("#modalEditor")?.hidden,
    cancelHidden: document.querySelector("#modalCancelButton")?.hidden,
    slugLine: document.querySelector("#modalMessage .modal-slug-inline")?.textContent || "",
    modifyButton: document.querySelector("#modalMessage .inline-action-button")?.textContent || "",
    messageText: document.querySelector("#modalMessage")?.textContent || "",
  }));
  if (!operationModal.markdownVisible || !operationModal.editorHidden || !operationModal.cancelHidden || operationModal.primary !== "Close" || !operationModal.slugLine.startsWith("slug: ") || operationModal.modifyButton !== "Modify markdown" || operationModal.messageText.includes("Rendered from gbrain markdown")) {
    throw new Error("Expected View to render markdown with no Cancel button and a Close action");
  }
  if (operationModal.documentTitle !== "Memory Stargraph" || !operationModal.title) {
    throw new Error(`Expected View to keep browser title as Memory Stargraph and update modal title: ${JSON.stringify(operationModal)}`);
  }
  await page.evaluate(() => {
    window.__slugCopyProbe = [];
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__slugCopyProbe.push(value);
        },
      },
    });
  });
  const viewSlug = operationModal.slugLine.replace(/^slug:\s*/, "");
  await page.dblclick("#modalMessage .modal-slug-inline");
  await page.waitForFunction(() => document.querySelector("#modalMessage .modal-slug-inline")?.classList.contains("is-copy-confirmed"));
  const viewCopy = await page.evaluate(() => ({
    copied: window.__slugCopyProbe.at(-1),
    status: document.querySelector("#slugCopyStatus")?.textContent,
  }));
  if (viewCopy.copied !== viewSlug || viewCopy.status !== `Copied slug: ${viewSlug}`) {
    throw new Error(`Expected View slug double-click to copy the exact slug: ${JSON.stringify({ viewSlug, viewCopy })}`);
  }
  await page.click("#modalCloseButton");
  const previewSlug = await page.textContent("#selectionSlugAlways");
  await page.dblclick("#selectionSlugAlways");
  await page.waitForFunction(() => document.querySelector("#selectionSlugAlways")?.classList.contains("is-copy-confirmed"));
  const previewCopy = await page.evaluate(() => ({
    copied: window.__slugCopyProbe.at(-1),
    status: document.querySelector("#slugCopyStatus")?.textContent,
  }));
  if (previewCopy.copied !== previewSlug || previewCopy.status !== `Copied slug: ${previewSlug}`) {
    throw new Error(`Expected preview slug double-click to copy the exact slug: ${JSON.stringify({ previewSlug, previewCopy })}`);
  }
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async () => {
          throw new Error("permission denied");
        },
      },
    });
  });
  await page.dblclick("#selectionSlugAlways");
  await page.waitForFunction(() => document.querySelector("#selectionSlugAlways")?.classList.contains("is-copy-failed"));
  const failedCopy = await page.evaluate(() => ({
    copied: window.__slugCopyProbe.at(-1),
    status: document.querySelector("#slugCopyStatus")?.textContent,
  }));
  if (failedCopy.copied !== previewSlug || failedCopy.status !== `Copy failed for slug: ${previewSlug}`) {
    throw new Error(`Expected clipboard failure to stay truthful: ${JSON.stringify({ previewSlug, failedCopy })}`);
  }
  await page.evaluate(() => {
    Object.defineProperty(navigator, "clipboard", {
      configurable: true,
      value: {
        writeText: async (value) => {
          window.__slugCopyProbe.push(value);
        },
      },
    });
  });
  const markdownFormatting = await page.evaluate(() => {
    window.__MEMORY_STARGRAPH__.renderMarkdownView([
      "# Format Probe",
      "",
      "A [[Signal Foundry]] link with **bold**, *italic*, ***both***, `code`, and ~~old~~ text.",
      "Source file: /Users/tony/work/WeChat/MSN Blogs/blog.txt",
      "Timeline link: 2023-11-01T00:00:00.000Z HHS recap [posts/tony-guan-2023-year-in-review-good-fight-good-life-2023-12-31]",
      "Unicode slug link: [人物/张三]",
      "",
      "> Quoted note",
      "",
      "1. Ordered item",
      "",
      "| Name | Value |",
      "| --- | --- |",
      "| Status | **Ready** |",
    ].join("\n"));
    const root = document.querySelector("#modalMarkdown");
    return {
      wiki: root.querySelector("a[data-entity-query]")?.dataset.entityQuery,
      bracketSlug: [...root.querySelectorAll("a[data-entity-query]")].find((link) => link.dataset.entityQuery?.startsWith("posts/"))?.dataset.entityQuery,
      unicodeSlug: [...root.querySelectorAll("a[data-entity-query]")].find((link) => link.dataset.entityQuery === "人物/张三")?.textContent,
      strong: root.querySelector("strong")?.textContent,
      em: root.querySelector("em")?.textContent,
      code: root.querySelector("code")?.textContent,
      del: root.querySelector("del")?.textContent,
      quote: root.querySelector("blockquote")?.textContent,
      ordered: root.querySelector("ol li")?.textContent,
      tableRows: root.querySelectorAll("table tr").length,
      fileLinkHref: root.querySelector('a[href^="file:///Users/tony/work/WeChat/MSN%20Blogs/blog.txt"]')?.getAttribute("href"),
      fileLinkTarget: root.querySelector('a[href^="file:///Users/tony/work/WeChat/MSN%20Blogs/blog.txt"]')?.target,
    };
  });
  if (
    markdownFormatting.wiki !== "Signal Foundry" ||
    markdownFormatting.bracketSlug !== "posts/tony-guan-2023-year-in-review-good-fight-good-life-2023-12-31" ||
    markdownFormatting.unicodeSlug !== "人物/张三" ||
    markdownFormatting.strong !== "bold" ||
    markdownFormatting.em !== "italic" ||
    markdownFormatting.code !== "code" ||
    markdownFormatting.del !== "old" ||
    markdownFormatting.quote !== "Quoted note" ||
    markdownFormatting.ordered !== "Ordered item" ||
    markdownFormatting.tableRows !== 2 ||
    markdownFormatting.fileLinkHref !== "file:///Users/tony/work/WeChat/MSN%20Blogs/blog.txt" ||
    markdownFormatting.fileLinkTarget !== "_blank"
  ) {
    throw new Error(`Expected rendered markdown formatting support: ${JSON.stringify(markdownFormatting)}`);
  }
  await page.click("#modalMessage .inline-action-button");
  await page.waitForFunction(() => document.querySelector("#modalKicker")?.textContent === "Modify gbrain page", null, { timeout: 20000 });
  await page.waitForFunction(() => document.querySelector("#modalEditor")?.value.length > 0, null, { timeout: 20000 });
  const editJump = await page.evaluate(() => ({
    kicker: document.querySelector("#modalKicker")?.textContent,
    editorHidden: document.querySelector("#modalEditor")?.hidden,
    markdownHidden: document.querySelector("#modalMarkdown")?.hidden,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
    editorLength: document.querySelector("#modalEditor")?.value.length,
  }));
  if (editJump.editorHidden || !editJump.markdownHidden || editJump.primary !== "Save" || editJump.editorLength < 1) {
    throw new Error(`Expected Modify markdown link to reopen edit mode: ${JSON.stringify(editJump)}`);
  }
  await page.click("#modalCloseButton");

  const msnBlogSlug = "blogs/tony-guan/msn/20051115-untitled-f35cfca7";
  await page.evaluate((slug) => window.__MEMORY_STARGRAPH__.loadEntity(slug), msnBlogSlug);
  await page.waitForFunction(
    (slug) => window.__MEMORY_STARGRAPH__.getState().focusSlug === slug
      && !document.querySelector("#detailType")?.textContent?.includes("loading"),
    msnBlogSlug,
    { timeout: 30000 },
  );
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="view"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  await page.waitForFunction(() => document.querySelector("#modalTitle")?.textContent === "老夫的性格被分类了"
    && (document.querySelector("#modalMarkdown")?.textContent || "").trim().length > 0, null, { timeout: 20000 });
  const exactMsnView = await page.evaluate(() => ({
    documentTitle: document.title,
    modalTitle: document.querySelector("#modalTitle")?.textContent,
    markdownLength: (document.querySelector("#modalMarkdown")?.textContent || "").trim().length,
  }));
  if (exactMsnView.documentTitle !== "Memory Stargraph" || exactMsnView.modalTitle !== "老夫的性格被分类了" || exactMsnView.markdownLength < 1) {
    throw new Error(`Expected exact MSN blog View title and rendered markdown: ${JSON.stringify(exactMsnView)}`);
  }
  await page.click("#modalCloseButton");

  const noiseCollectionSlug = "collections/savemysunnysky-noise-notes-2017-2019";
  await page.evaluate((slug) => window.__MEMORY_STARGRAPH__.loadEntity(slug), noiseCollectionSlug);
  await page.waitForFunction(
    (slug) => window.__MEMORY_STARGRAPH__.getState().focusSlug === slug
      && !document.querySelector("#detailType")?.textContent?.includes("loading"),
    noiseCollectionSlug,
    { timeout: 30000 },
  );
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="backlinks"]');
  await page.waitForSelector(".backlink-from-link", { timeout: 30000 });
  const exactBacklinks = await page.evaluate(() => ({
    firstSlug: document.querySelector(".backlink-from-link")?.getAttribute("data-backlink-slug") || "",
    firstSlugText: document.querySelector(".backlink-from-link")?.textContent || "",
    relation: document.querySelector(".backlink-relation")?.textContent || "",
    relationshipButton: document.querySelector(".backlink-link-back")?.textContent || "",
  }));
  if (!exactBacklinks.firstSlug.startsWith(`${noiseCollectionSlug}/`) || !exactBacklinks.firstSlugText || !exactBacklinks.relation || exactBacklinks.relationshipButton !== "+") {
    throw new Error(`Expected exact collection backlinks to show clickable source slug, relation, and compact Add relationship icon: ${JSON.stringify(exactBacklinks)}`);
  }
  await page.click("#modalCloseButton");

  const gbrainOperationTemplates = [];
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  const firstMenuActions = await page.evaluate(() => [...document.querySelectorAll("#contextMenu button")].slice(0, 12).map((button) => button.dataset.action));
  const expectedMenuPrefix = ["view", "ask-yoda", "media", "view-relationships", "backlinks", "tags", "attach-file", "graph-query", "timeline-view", "history", "embed", "hide"];
  if (JSON.stringify(firstMenuActions) !== JSON.stringify(expectedMenuPrefix)) {
    throw new Error(`Expected node menu order ${expectedMenuPrefix.join(", ")}, got ${firstMenuActions.join(", ")}`);
  }
  const removedMenuActions = await page.evaluate(() => ({
    copy: Boolean(document.querySelector('#contextMenu button[data-action="copy"]')),
    addLink: Boolean(document.querySelector('#contextMenu button[data-action="add-link"]')),
    removeLink: Boolean(document.querySelector('#contextMenu button[data-action="remove-link"]')),
  }));
  if (removedMenuActions.copy || removedMenuActions.addLink || removedMenuActions.removeLink) {
    throw new Error(`Expected Copy/Add/Remove relationship to be removed from the node menu: ${JSON.stringify(removedMenuActions)}`);
  }
  await page.click("body", { position: { x: 6, y: 6 } });
  for (const action of ["ask-yoda", "media", "view-relationships", "backlinks", "tags", "attach-file", "graph-query", "history", "timeline-view", "embed"]) {
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
      graphControls: {
        linkType: Boolean(document.querySelector("#operationGraphLinkType")),
        direction: [...document.querySelectorAll("#operationGraphDirection option")].map((option) => option.value),
        depth: [...document.querySelectorAll("#operationGraphDepth option")].map((option) => option.value),
        summary: document.querySelector(".operation-summary")?.textContent || "",
      },
    }));
    gbrainOperationTemplates.push({ action, menuText, modal });
    await page.click("#modalCloseButton");
  }
  if (!gbrainOperationTemplates.every((item) => item.modal.primary && (item.modal.editor.trim() || item.modal.editorHidden))) {
    throw new Error(`Expected gbrain operation modals to render templates: ${JSON.stringify(gbrainOperationTemplates)}`);
  }
  const timelineTemplate = gbrainOperationTemplates.find((item) => item.action === "timeline-view");
  if (!timelineTemplate || timelineTemplate.menuText !== "Timeline" || timelineTemplate.modal.primary !== "Add timeline event" || !timelineTemplate.modal.editorHidden) {
    throw new Error(`Expected Timeline to open a read-only rendered view with an add-event button: ${JSON.stringify(timelineTemplate)}`);
  }
  const relationshipsTemplate = gbrainOperationTemplates.find((item) => item.action === "view-relationships");
  if (!relationshipsTemplate || relationshipsTemplate.menuText !== "Relationships" || relationshipsTemplate.modal.kicker !== "Relationships" || relationshipsTemplate.modal.primary !== "Close") {
    throw new Error(`Expected Relationships menu to open the Relationships view: ${JSON.stringify(relationshipsTemplate)}`);
  }
  const graphQueryTemplate = gbrainOperationTemplates.find((item) => item.action === "graph-query");
  if (
    graphQueryTemplate?.menuText !== "Query" ||
    graphQueryTemplate?.modal.kicker !== "Query" ||
    !graphQueryTemplate?.modal.graphControls.linkType ||
    graphQueryTemplate.modal.graphControls.direction.join(",") !== "both,outgoing,incoming" ||
    graphQueryTemplate.modal.graphControls.depth.join(",") !== "1,2,3" ||
    !graphQueryTemplate.modal.graphControls.summary.includes("depth 1") ||
    !graphQueryTemplate.modal.editorHidden
  ) {
    throw new Error(`Expected Graph query to use guided controls: ${JSON.stringify(graphQueryTemplate)}`);
  }
  const historyTemplate = gbrainOperationTemplates.find((item) => item.action === "history");
  if (!historyTemplate || historyTemplate.menuText !== "History" || historyTemplate.modal.kicker !== "History") {
    throw new Error(`Expected History menu label and modal kicker: ${JSON.stringify(historyTemplate)}`);
  }
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="graph-query"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  await page.selectOption("#operationGraphDirection", "both");
  await page.selectOption("#operationGraphDepth", "1");
  await page.click("#modalPrimaryButton");
  await page.waitForFunction(() => document.querySelector("#modalKicker")?.textContent === "Graph query results", null, { timeout: 30000 });
  const graphQueryResult = await page.evaluate(() => ({
    markdownVisible: !document.querySelector("#modalMarkdown")?.hidden,
    editorHidden: document.querySelector("#modalEditor")?.hidden,
    textLength: document.querySelector("#modalMarkdown")?.textContent.length || 0,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
  }));
  if (!graphQueryResult.markdownVisible || !graphQueryResult.editorHidden || graphQueryResult.primary !== "Close" || graphQueryResult.textLength < 1) {
    throw new Error(`Expected Graph query results to render readably: ${JSON.stringify(graphQueryResult)}`);
  }
  await page.click("#modalCloseButton");
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="timeline-view"]');
  await page.waitForSelector("#operationModal:not([hidden])");
  const viewTimelineFields = await page.evaluate(() => ({
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
  }));
  await page.click("#modalPrimaryButton");
  await page.waitForFunction(() => document.querySelector("#modalKicker")?.textContent === "Add timeline event", null, { timeout: 10000 });
  const addTimelineFields = await page.evaluate(() => ({
    dateType: document.querySelector("#operationTimelineDate")?.type,
    dateValue: document.querySelector("#operationTimelineDate")?.value,
    summary: Boolean(document.querySelector("#operationTimelineSummary")),
    detail: Boolean(document.querySelector("#operationTimelineDetail")),
    source: Boolean(document.querySelector("#operationTimelineSource")),
    editorHidden: document.querySelector("#modalEditor")?.hidden,
  }));
  if (viewTimelineFields.primary !== "Add timeline event" || addTimelineFields.dateType !== "date" || !addTimelineFields.dateValue || !addTimelineFields.summary || !addTimelineFields.detail || !addTimelineFields.source || !addTimelineFields.editorHidden) {
    throw new Error(`Expected guided Add timeline event form: ${JSON.stringify({ viewTimelineFields, addTimelineFields })}`);
  }
  await page.click("#modalCloseButton");

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

  await page.evaluate(async (slug) => {
    const items = [...document.querySelectorAll(".hidden-item")];
    const item = items.find((candidate) => candidate.textContent.includes(slug));
    const button = item?.querySelector("button");
    if (button) {
      button.click();
    } else {
      await window.__MEMORY_STARGRAPH__.showNode(slug);
    }
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
  if (hiddenAfterShow.hidden || hiddenAfterShow.listText?.includes(hideTargetSlug)) {
    throw new Error(`Expected Show action to restore hidden node to the galaxy: ${JSON.stringify({ hideTargetSlug, hiddenAfterShow })}`);
  }

  const rotationBefore = await page.evaluate(() => ({ ...window.__MEMORY_STARGRAPH__.getState().rotation }));
  await page.evaluate(() => {
    const canvas = document.querySelector("#graphCanvas");
    const rect = canvas.getBoundingClientRect();
    const start = { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 };
    const end = { x: start.x + 140, y: start.y + 30 };
    const eventBase = { bubbles: true, cancelable: true, button: 0, buttons: 1, pointerId: 1, pointerType: "mouse" };
    canvas.dispatchEvent(new PointerEvent("pointerdown", { ...eventBase, clientX: start.x, clientY: start.y }));
    canvas.dispatchEvent(new PointerEvent("pointermove", { ...eventBase, clientX: end.x, clientY: end.y }));
    canvas.dispatchEvent(new PointerEvent("pointerup", { ...eventBase, buttons: 0, clientX: end.x, clientY: end.y }));
  });
  await page.waitForTimeout(100);
  const rotationAfter = await page.evaluate(() => ({ ...window.__MEMORY_STARGRAPH__.getState().rotation }));

  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled, null, { timeout: 30000 });
  await openSearchFlyout();
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
      hasCollapsedMetric: Boolean(document.querySelector("#metricCollapsed")),
      sourceStatus: state.graph.source.status,
      searchResults: state.graph.source.coverage?.search_results,
    };
  });
  if (partSearch.matches < 1) {
    throw new Error("Expected old part title search to find a collapsed parent node");
  }
  if (partSearch.hasCollapsedMetric) {
    throw new Error("Expected Parts to be removed from the statistics row");
  }
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled, null, { timeout: 30000 });
  await openSearchFlyout();
  await page.fill("#searchInput", "Tony Guan");
  await page.press("#searchInput", "Enter");
  await page.waitForFunction(() => !document.querySelector("#searchInput")?.disabled && !document.querySelector("#searchButton")?.disabled, null, { timeout: 30000 });
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.getState().focusSlug === "people/tony-guan",
    null,
    { timeout: 15000 },
  );
  await page.waitForFunction(
    () => !document.querySelector("#timelineBadge")?.hidden,
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
      timelineBadgeVisible: !document.querySelector("#timelineBadge")?.hidden,
      timelineBadgeText: document.querySelector("#timelineBadge")?.textContent,
      summary: document.querySelector("#detailSummary")?.textContent,
    };
  });
  if (tonySearch.focus !== "people/tony-guan" || !tonySearch.match || !tonySearch.filtered || !tonySearch.title?.toLowerCase().includes("tony") || !tonySearch.timelineBadgeVisible || tonySearch.timelineBadgeText !== "Timeline" || !(tonySearch.summary || "").trim()) {
    throw new Error(`Expected Tony Guan search to focus, show timeline badge, and render summary text: ${JSON.stringify(tonySearch)}`);
  }
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="backlinks"]');
  await page.waitForSelector(".backlink-from-link", { timeout: 30000 });
  const backlinksControls = await page.evaluate(() => {
    const firstSlug = document.querySelector(".backlink-from-link")?.getAttribute("data-backlink-slug") || "";
    return {
      firstSlug,
      slugButtons: document.querySelectorAll(".backlink-from-link[data-backlink-slug]").length,
      linkBackButtons: [...document.querySelectorAll(".backlink-link-back")].map((button) => button.textContent),
      editorHidden: document.querySelector("#modalEditor")?.hidden,
      markdownVisible: !document.querySelector("#modalMarkdown")?.hidden,
    };
  });
  if (!backlinksControls.firstSlug || backlinksControls.slugButtons < 1 || !backlinksControls.linkBackButtons.includes("+") || !backlinksControls.editorHidden || !backlinksControls.markdownVisible) {
    throw new Error(`Expected backlinks to render clickable slugs and compact Add relationship controls: ${JSON.stringify(backlinksControls)}`);
  }
  await page.click(".backlink-link-back");
  await page.waitForFunction(() => document.querySelector("#modalKicker")?.textContent === "Add typed relationship", null, { timeout: 10000 });
  const reverseLink = await page.evaluate(() => ({
    source: document.querySelector("#modalTitle")?.textContent,
    target: document.querySelector("#operationTarget")?.value,
    primary: document.querySelector("#modalPrimaryButton")?.textContent,
  }));
  if (reverseLink.source !== "Tony Guan" || reverseLink.target !== backlinksControls.firstSlug || reverseLink.primary !== "Add relationship") {
    throw new Error(`Expected Add relationship to prefill a reverse relationship from Tony Guan: ${JSON.stringify({ backlinksControls, reverseLink })}`);
  }
  await page.click("#modalCloseButton");
  await page.evaluate(() => window.__MEMORY_STARGRAPH__.loadEntity("people/tony-guan"));
  await page.waitForFunction(
    () => window.__MEMORY_STARGRAPH__.getState().focusSlug === "people/tony-guan"
      && !document.querySelector("#detailType")?.textContent?.includes("loading"),
    null,
    { timeout: 30000 },
  );
  await page.click("#nodeMenuButton");
  await page.waitForSelector("#contextMenu:not([hidden])");
  await page.click('#contextMenu button[data-action="view-relationships"]');
  await page.waitForSelector(".relationship-wiki-list", { timeout: 10000 });
  const relationshipView = await page.evaluate(() => ({
    title: document.querySelector("#modalKicker")?.textContent,
    rows: document.querySelectorAll(".relationship-wiki-row").length,
    firstSlug: document.querySelector(".relationship-source-link")?.getAttribute("data-entity-query") || "",
    relation: document.querySelector(".relationship-type")?.textContent || "",
    addButton: document.querySelector(".relationship-add-backlink")?.textContent || "",
    addSelectedButton: document.querySelector(".relationship-add-selected")?.textContent || "",
    removeButton: document.querySelector(".relationship-remove")?.textContent || "",
    hasAuthoredBy: [...document.querySelectorAll(".relationship-type")].some((item) => /authored_by/i.test(item.textContent || "")),
  }));
  if (relationshipView.title !== "Relationships" || relationshipView.rows < 1 || !relationshipView.firstSlug || !relationshipView.relation || relationshipView.addSelectedButton !== "+" || relationshipView.addButton !== "+" || relationshipView.removeButton !== "×") {
    throw new Error(`Expected Relationships to render compact outgoing wiki rows with add/remove controls: ${JSON.stringify(relationshipView)}`);
  }
  if (relationshipView.hasAuthoredBy) {
    throw new Error(`Expected Relationships to exclude incoming authored_by backlinks: ${JSON.stringify(relationshipView)}`);
  }
  await page.click("#modalCloseButton");
  const clusterToggle = await page.evaluate(() => {
    const button = document.querySelector("#categoryLegend button");
    const cluster = button?.dataset.cluster;
    const beforeCount = window.__MEMORY_STARGRAPH__.getState().filteredSlugs.size;
    button?.click();
    const afterHideCount = window.__MEMORY_STARGRAPH__.getState().filteredSlugs.size;
    const hidden = window.__MEMORY_STARGRAPH__.getState().hiddenClusters.has(cluster);
    const dimmed = document.querySelector(`#categoryLegend button[data-cluster="${CSS.escape(cluster)}"]`)?.classList.contains("is-dimmed");
    document.querySelector(`#categoryLegend button[data-cluster="${CSS.escape(cluster)}"]`)?.click();
    const afterShowCount = window.__MEMORY_STARGRAPH__.getState().filteredSlugs.size;
    return { cluster, beforeCount, afterHideCount, afterShowCount, hidden, dimmed };
  });
  if (!clusterToggle.cluster || !clusterToggle.hidden || !clusterToggle.dimmed || !(clusterToggle.afterHideCount < clusterToggle.beforeCount) || clusterToggle.afterShowCount !== clusterToggle.beforeCount) {
    throw new Error(`Expected clicking a cluster to hide/show its whole cloud: ${JSON.stringify(clusterToggle)}`);
  }
  const hubClusterToggle = await page.evaluate(() => {
    const state = window.__MEMORY_STARGRAPH__.getState();
    const button = [...document.querySelectorAll("#hubClusterLegend button")]
      .find((candidate) => (state.nodeMap.get(candidate.dataset.hub)?.links || []).some((slug) => state.filteredSlugs.has(slug)));
    const hub = button?.dataset.hub;
    const neighbor = (state.nodeMap.get(hub)?.links || []).find((slug) => state.filteredSlugs.has(slug));
    const before = state.filteredSlugs.has(neighbor);
    button?.click();
    const hidden = state.hiddenHubConnections.has(hub);
    const afterHide = state.filteredSlugs.has(neighbor);
    document.querySelector(`#hubClusterLegend button[data-hub="${CSS.escape(hub)}"]`)?.click();
    const afterShow = state.filteredSlugs.has(neighbor);
    return { hub, neighbor, before, hidden, afterHide, afterShow };
  });
  if (!hubClusterToggle.hub || !hubClusterToggle.neighbor || !hubClusterToggle.before || !hubClusterToggle.hidden || hubClusterToggle.afterHide || !hubClusterToggle.afterShow) {
    throw new Error(`Expected clicking a hub cluster to hide/show direct connections: ${JSON.stringify(hubClusterToggle)}`);
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
  console.log(JSON.stringify({ initial, search, filters, zoom, cferSearch, expansionProbe, hover, clickPoint, afterClick, historyNav, doubleClickModal, operationModal, gbrainOperationTemplates, deleteConfirmInitial, hiddenAfterHide, hiddenAfterReload, hiddenAfterShow, rotationBefore, rotationAfter, partSearch, tonySearch, relationshipView, screenshot: "/private/tmp/memory-stargraph-browser.png" }, null, 2));
} finally {
  await browser.close();
}
