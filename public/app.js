const UI_VERSION = "V1.0.113";
const RELATIONSHIP_PAGE_SIZE = 10;
let tourNodeLoadTimeoutMs = 20 * 1000;
const NODE_CACHE_DEFAULT_BYTES = 10 * 1024 * 1024;
const NODE_CACHE_MAX_BYTES = 20 * 1024 * 1024;
const NODE_CACHE_STORAGE_KEY = "memory-stargraph.node-cache.v1";
const NODE_CACHE_LIMIT_KEY = "memory-stargraph.node-cache-limit-bytes";
const FLOWING_EDGE_EFFECT_KEY = "memory-stargraph.flowing-edge-effect";
const YODA_CONTEXT_DEPTH_KEY = "memory-stargraph.yoda-context-depth";
const PLANNED_PLAYBACK_KEY = "memory-stargraph.planned-playback.v1";

const state = {
  graph: null,
  filteredSlugs: new Set(),
  matchSlugs: new Set(),
  hiddenSlugs: new Set(),
  expandingSlugs: new Set(),
  focusSlug: null,
  hoverSlug: null,
  query: "",
  matchesOnly: false,
  filters: { minDegree: 0 },
  nodes: [],
  edges: [],
  edgeTypeMap: new Map(),
  nodeMap: new Map(),
  visibleLabelSlugs: [],
  animationHandle: null,
  renderDirty: true,
  isRefreshing: false,
  lastRefreshAt: null,
  pendingSettings: null,
  mediaSlugs: new Set(),
  cloudMode: true,
  flowingEdges: readBooleanSetting(FLOWING_EDGE_EFFECT_KEY, true),
  yodaDepth: readNumberSetting(YODA_CONTEXT_DEPTH_KEY, 4, 1, 6),
  mapFiltersVisible: false,
  hiddenClusters: new Set(),
  hiddenHubConnections: new Set(),
  categoryLimit: 5,
  clusterLimit: 5,
  timelineDays: 0,
  tour: {
    active: false,
    mode: "auto",
    slugs: [],
    index: 0,
    timer: null,
    pending: false,
    timeoutTimer: null,
    toolbarPinned: false,
    planSlugs: readJsonSetting(PLANNED_PLAYBACK_KEY, []),
    planDraft: null,
    fillPlanConfirming: false,
    clearPlanConfirming: false,
    partialTimeoutSlugs: new Set(),
    useAutoList: true,
    loop: true,
    delaySeconds: 5,
  },
  selectionHistory: { slugs: [], index: -1, navigating: false },
  lazySearch: { timer: null, query: "", loading: false },
  menuSlug: null,
  modalAction: null,
  askYodaChats: new Map(),
  askYodaLogs: new Map(),
  yodaLogReturn: null,
  slugSelectorSearch: new Map(),
  relationshipTargetSearch: { loading: false, liveOptions: [] },
  relationshipPages: new Map(),
  backlinkPages: new Map(),
  relationshipReturnView: null,
  busyOperations: new Map(),
  busyOperationId: 0,
  animationTick: 0,
  entityLoadId: 0,
  selectionVersion: 0,
  zoom: 1,
  rotation: { x: -0.34, y: 0.58, vx: 0, vy: 0 },
  drag: { active: false, moved: false, lastX: 0, lastY: 0, pointerId: null },
  mobileTooltipTimer: null,
  viewport: { width: 1200, height: 760, dpr: Math.max(1, window.devicePixelRatio || 1) },
};

const canvas = document.getElementById("graphCanvas");
const ctx = canvas.getContext("2d");
const workspace = document.querySelector(".workspace");
const graphCanvasWrap = document.querySelector(".graph-canvas-wrap");
const detailPanel = document.querySelector(".detail-panel");
const hoverLabel = document.getElementById("hoverLabel");
const graphTooltip = document.getElementById("graphTooltip");
const navStargraphButton = document.getElementById("navStargraphButton");
const navSearchButton = document.getElementById("navSearchButton");
const navAutopilotButton = document.getElementById("navAutopilotButton");
const navSettingsButton = document.getElementById("navSettingsButton");
const searchFlyout = document.getElementById("searchFlyout");
const autopilotFlyout = document.getElementById("autopilotFlyout");
const settingsFlyout = document.getElementById("settingsFlyout");
const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const matchesOnlyToggle = document.getElementById("matchesOnlyToggle");
const refreshButton = document.getElementById("refreshButton");
const flowingEdgesToggle = document.getElementById("flowingEdgesToggle");
const yodaDepthInput = document.getElementById("yodaDepthInput");
const lastRefresh = document.getElementById("lastRefresh");
const flushCacheButton = document.getElementById("flushCacheButton");
const minDegreeFilter = document.getElementById("minDegreeFilter");
const newNodeButton = document.getElementById("newNodeButton");
const mapViewButton = document.getElementById("mapViewButton");
const mapAskYodaButton = document.getElementById("mapAskYodaButton");
const filterDrawerHandle = document.getElementById("filterDrawerHandle");
const mapFilterToggleButton = document.getElementById("mapFilterToggleButton");
const mapFilterPanel = document.getElementById("mapFilterPanel");
const zoomOutButton = document.getElementById("zoomOutButton");
const zoomInButton = document.getElementById("zoomInButton");
const zoomLevel = document.getElementById("zoomLevel");
const cloudModeButton = document.getElementById("cloudModeButton");
const cloudModeToggle = document.getElementById("cloudModeToggle");
const timelineDaysInput = document.getElementById("timelineDaysInput");
const timelineValue = document.getElementById("timelineValue");
const tourPlanButton = document.getElementById("tourPlanButton");
const tourButton = document.getElementById("tourButton");
const tourPrevButton = document.getElementById("tourPrevButton");
const tourNextButton = document.getElementById("tourNextButton");
const tourStopButton = document.getElementById("tourStopButton");
const tourCounter = document.getElementById("tourCounter");
const settingsOkButton = document.getElementById("settingsOkButton");
const settingsCancelButton = document.getElementById("settingsCancelButton");
const historyBackButton = document.getElementById("historyBackButton");
const historyForwardButton = document.getElementById("historyForwardButton");
const floatingHistoryBackButton = document.getElementById("floatingHistoryBackButton");
const compactSelectionQuery = window.matchMedia("(max-width: 720px)");
const floatingHistoryForwardButton = document.getElementById("floatingHistoryForwardButton");

const detailTitle = document.getElementById("detailTitle");
const timelineBadge = document.getElementById("timelineBadge");
const selectionViewButton = document.getElementById("selectionViewButton");
const selectionAskYodaButton = document.getElementById("selectionAskYodaButton");
const detailType = document.getElementById("detailType");
const detailSummary = document.getElementById("detailSummary");
const selectionSlugAlways = document.getElementById("selectionSlugAlways");
const selectionMediaPreview = document.getElementById("selectionMediaPreview");
const selectionMediaSlug = document.getElementById("selectionMediaSlug");
const detailLinks = document.getElementById("detailLinks") || document.createElement("div");
const detailSecondRing = document.getElementById("detailSecondRing") || document.createElement("div");
const sourceBadge = document.getElementById("sourceBadge");
const sourceMessage = document.getElementById("sourceMessage");
const sourceWarnings = document.getElementById("sourceWarnings");
const categoryLegend = document.getElementById("categoryLegend");
const hubClusterLegend = document.getElementById("hubClusterLegend");
const categoryLimitInput = document.getElementById("categoryLimitInput");
const clusterLimitInput = document.getElementById("clusterLimitInput");
const hiddenList = document.getElementById("hiddenList");
const uiVersion = document.getElementById("uiVersion");
const nodeMenuButton = document.getElementById("nodeMenuButton");
const contextMenu = document.getElementById("contextMenu");
const operationModal = document.getElementById("operationModal");
const modalKicker = document.getElementById("modalKicker");
const modalTitle = document.getElementById("modalTitle");
const modalMessage = document.getElementById("modalMessage");
const modalConfirmInput = document.getElementById("modalConfirmInput");
const modalFileInput = document.getElementById("modalFileInput");
const modalForm = document.getElementById("modalForm");
const modalEditor = document.getElementById("modalEditor");
const modalAttach = document.getElementById("modalAttach");
const modalAttachDescription = document.getElementById("modalAttachDescription");
const modalAttachStatus = document.getElementById("modalAttachStatus");
const modalMarkdown = document.getElementById("modalMarkdown");
const modalMedia = document.getElementById("modalMedia");
const modalChat = document.getElementById("modalChat");
const modalChatLog = document.getElementById("modalChatLog");
const modalChatInput = document.getElementById("modalChatInput");
const modalYodaDepth = document.getElementById("modalYodaDepth");
const modalYodaDepthWrap = document.getElementById("modalYodaDepthWrap");
const modalYodaLogButton = document.getElementById("modalYodaLogButton");
const settingsYodaLogButton = document.getElementById("settingsYodaLogButton");
const modalCloseButton = document.getElementById("modalCloseButton");
const modalCancelButton = document.getElementById("modalCancelButton");
const modalPrimaryButton = document.getElementById("modalPrimaryButton");
const busyIndicator = document.getElementById("busyIndicator");
const busyIndicatorLabel = document.getElementById("busyIndicatorLabel");

const metricNodes = document.getElementById("metricNodes");
const metricEdges = document.getElementById("metricEdges");
const metricDegree = document.getElementById("metricDegree");
const metricMode = document.getElementById("metricMode");
const radarCacheUsage = document.getElementById("radarCacheUsage");

const CATEGORY_PALETTE = [
  "#88f6ff",
  "#ffc66f",
  "#8f7cff",
  "#6fe8a8",
  "#ff8fb3",
  "#7fb4ff",
  "#e6f06f",
  "#ff9c73",
  "#b8f7d4",
  "#d8b7ff",
];

function stableHash(value) {
  let hash = 0;
  const text = String(value || "");
  for (let index = 0; index < text.length; index += 1) {
    hash = (hash * 31 + text.charCodeAt(index)) >>> 0;
  }
  return hash;
}

function hexToRgba(hex, alpha) {
  const cleaned = hex.replace("#", "");
  const expanded = cleaned.length === 3
    ? cleaned.split("").map((char) => `${char}${char}`).join("")
    : cleaned;
  const value = Number.parseInt(expanded, 16);
  const r = (value >> 16) & 255;
  const g = (value >> 8) & 255;
  const b = value & 255;
  return `rgba(${r}, ${g}, ${b}, ${alpha})`;
}

function resizeCanvas() {
  const rect = canvas.getBoundingClientRect();
  state.viewport.width = rect.width;
  state.viewport.height = rect.height;
  state.viewport.dpr = Math.max(1, window.devicePixelRatio || 1);
  canvas.width = Math.round(rect.width * state.viewport.dpr);
  canvas.height = Math.round(rect.height * state.viewport.dpr);
  ctx.setTransform(state.viewport.dpr, 0, 0, state.viewport.dpr, 0, 0);
  requestRender();
}

function safeJsonParse(value, fallback) {
  try {
    return JSON.parse(value);
  } catch (_error) {
    return fallback;
  }
}

function readJsonSetting(key, fallback) {
  const value = window.localStorage?.getItem(key);
  if (!value) return fallback;
  const parsed = safeJsonParse(value, fallback);
  return Array.isArray(parsed) ? parsed : fallback;
}

function readBooleanSetting(key, fallback = false) {
  const value = window.localStorage?.getItem(key);
  if (value === "true") return true;
  if (value === "false") return false;
  return fallback;
}

function readNumberSetting(key, fallback, min, max) {
  const value = Number.parseInt(window.localStorage?.getItem(key) || "", 10);
  if (!Number.isFinite(value)) return fallback;
  return Math.max(min, Math.min(max, value));
}

function setYodaDepth(value) {
  state.yodaDepth = Math.max(1, Math.min(6, Number.parseInt(value, 10) || 4));
  window.localStorage?.setItem(YODA_CONTEXT_DEPTH_KEY, String(state.yodaDepth));
  syncYodaDepthControl();
}

function syncYodaDepthControl() {
  if (yodaDepthInput) yodaDepthInput.value = String(state.yodaDepth);
  if (modalYodaDepth) modalYodaDepth.value = String(state.yodaDepth);
}

function cacheLimitBytes() {
  const stored = Number.parseInt(window.localStorage?.getItem(NODE_CACHE_LIMIT_KEY) || "", 10);
  if (Number.isFinite(stored)) return Math.max(0, Math.min(NODE_CACHE_MAX_BYTES, stored));
  return NODE_CACHE_DEFAULT_BYTES;
}

function cacheStore() {
  return safeJsonParse(window.localStorage?.getItem(NODE_CACHE_STORAGE_KEY) || "", { entries: {} });
}

function saveCacheStore(store) {
  window.localStorage?.setItem(NODE_CACHE_STORAGE_KEY, JSON.stringify(store));
}

function cacheableGetUrl(url) {
  return /^\/api\/entity(?:-raw|-media)?\/[^?]+$/.test(String(url || ""));
}

function cacheUrlsForSlug(slug) {
  const encoded = encodeURIComponent(slug || "");
  return [
    `/api/entity/${encoded}`,
    `/api/entity-raw/${encoded}`,
    `/api/entity-media/${encoded}`,
  ];
}

function invalidateNodeCacheForSlug(slug) {
  if (!slug) return;
  const store = cacheStore();
  const entries = store.entries || {};
  cacheUrlsForSlug(slug).forEach((url) => {
    delete entries[url];
  });
  store.entries = entries;
  saveCacheStore(store);
  updateCacheSettingsView();
}

function invalidateRelationshipEndpointCache(leftSlug, rightSlug) {
  invalidateNodeCacheForSlug(leftSlug);
  invalidateNodeCacheForSlug(rightSlug);
}

function flushNodeCache() {
  saveCacheStore({ entries: {} });
  updateCacheSettingsView();
  hoverLabel.textContent = "Local node/media cache flushed.";
}

function cacheUsedBytes(store = cacheStore()) {
  return JSON.stringify(store.entries || {}).length;
}

function formatBytes(bytes) {
  if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
  if (bytes >= 1024) return `${Math.round(bytes / 1024)} KB`;
  return `${bytes} B`;
}

function cacheGet(url) {
  if (!cacheableGetUrl(url) || cacheLimitBytes() <= 0) return null;
  const store = cacheStore();
  const entry = store.entries?.[url];
  if (!entry) return null;
  entry.lastAccessed = Date.now();
  saveCacheStore(store);
  return { ok: true, status: 200, data: entry.data, cached: true };
}

function enforceCacheLimit(store = cacheStore()) {
  const limit = cacheLimitBytes();
  if (limit <= 0) {
    saveCacheStore({ entries: {} });
    return { entries: {} };
  }
  const entries = Object.entries(store.entries || {}).sort((left, right) => (left[1].lastAccessed || 0) - (right[1].lastAccessed || 0));
  while (JSON.stringify(store.entries || {}).length > limit && entries.length) {
    const [key] = entries.shift();
    delete store.entries[key];
  }
  saveCacheStore(store);
  return store;
}

function cacheSet(url, data) {
  if (!cacheableGetUrl(url) || cacheLimitBytes() <= 0) return;
  const store = cacheStore();
  store.entries = store.entries || {};
  store.entries[url] = { data, lastAccessed: Date.now() };
  enforceCacheLimit(store);
  updateCacheSettingsView();
}

function apiGet(url) {
  const cached = cacheGet(url);
  if (cached) return Promise.resolve(cached);
  if (typeof window.fetch === "function") {
    return window.fetch(url).then(async (response) => {
      const result = {
        ok: response.ok,
        status: response.status,
        data: await response.json(),
      };
      if (result.ok) cacheSet(url, result.data);
      return result;
    });
  }

  return new Promise((resolve, reject) => {
    const request = new XMLHttpRequest();
    request.open("GET", url, true);
    request.responseType = "text";
    request.onreadystatechange = () => {
      if (request.readyState !== XMLHttpRequest.DONE) {
        return;
      }
      if (request.status >= 200 && request.status < 300) {
        try {
          const data = JSON.parse(request.responseText);
          cacheSet(url, data);
          resolve({
            ok: true,
            status: request.status,
            data,
          });
        } catch (error) {
          reject(error);
        }
        return;
      }
      reject(new Error(`Request failed for ${url} with status ${request.status}`));
    };
    request.onerror = () => reject(new Error(`Network error while loading ${url}`));
    request.send();
  });
}

function apiPost(url, payload = {}) {
  return window.fetch(url, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  }).then(async (response) => ({
    ok: response.ok,
    status: response.status,
    data: await response.json(),
  }));
}

function apiPostForm(url, formData) {
  return window.fetch(url, {
    method: "POST",
    body: formData,
  }).then(async (response) => ({
    ok: response.ok,
    status: response.status,
    data: await response.json(),
  }));
}

function formatRefreshTime(value) {
  if (!value) return "Last refresh: —";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Last refresh: —";
  return `Last refresh: ${date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" })}`;
}

function setRefreshing(active) {
  state.isRefreshing = active;
  if (refreshButton) {
    refreshButton.disabled = active;
    refreshButton.textContent = active ? "Refreshing..." : "Refresh Graph";
  }
}

function setBusyIndicator(label = "") {
  if (!busyIndicator) return;
  const active = state.busyOperations.size > 0;
  const latest = [...state.busyOperations.values()].at(-1) || label || "Working";
  busyIndicator.hidden = !active;
  busyIndicator.setAttribute("aria-busy", active ? "true" : "false");
  if (busyIndicatorLabel) busyIndicatorLabel.textContent = latest;
}

function beginBusyOperation(label) {
  state.busyOperationId += 1;
  const token = state.busyOperationId;
  state.busyOperations.set(token, label || "Working");
  setBusyIndicator(label);
  return token;
}

function setBusyOperationLabel(token, label) {
  if (!token || !state.busyOperations.has(token)) return;
  state.busyOperations.set(token, label || "Working");
  setBusyIndicator(label);
}

function endBusyOperation(token) {
  if (token) state.busyOperations.delete(token);
  setBusyIndicator();
}

function updateCacheSettingsView() {
  const input = document.getElementById("cacheLimitInput");
  const usage = document.getElementById("cacheUsageValue");
  if (input) input.value = String(Math.round(cacheLimitBytes() / (1024 * 1024)));
  if (usage) usage.textContent = `Used ${formatBytes(cacheUsedBytes())}`;
  updateRadarCacheUsage();
}

function updateRadarCacheUsage() {
  if (!radarCacheUsage) return;
  radarCacheUsage.textContent = `Cache ${formatBytes(cacheUsedBytes())}`;
}

function snapshotSettings() {
  return {
    cacheLimitBytes: cacheLimitBytes(),
    flowingEdges: state.flowingEdges,
    yodaDepth: state.yodaDepth,
  };
}

function applySettingsFromControls() {
  const cacheInput = document.getElementById("cacheLimitInput");
  const mb = Math.max(0, Math.min(20, Number.parseInt(cacheInput?.value || "0", 10) || 0));
  window.localStorage?.setItem(NODE_CACHE_LIMIT_KEY, String(mb * 1024 * 1024));
  state.flowingEdges = Boolean(flowingEdgesToggle?.checked);
  setYodaDepth(yodaDepthInput?.value || state.yodaDepth);
  window.localStorage?.setItem(FLOWING_EDGE_EFFECT_KEY, state.flowingEdges ? "true" : "false");
  enforceCacheLimit();
  updateCacheSettingsView();
  hideFloatingPanels();
}

function cancelSettingsChanges() {
  const snapshot = state.pendingSettings || snapshotSettings();
  window.localStorage?.setItem(NODE_CACHE_LIMIT_KEY, String(snapshot.cacheLimitBytes));
  state.flowingEdges = Boolean(snapshot.flowingEdges);
  state.yodaDepth = Math.max(1, Math.min(6, Number.parseInt(snapshot.yodaDepth || "4", 10) || 4));
  if (flowingEdgesToggle) flowingEdgesToggle.checked = state.flowingEdges;
  window.localStorage?.setItem(YODA_CONTEXT_DEPTH_KEY, String(state.yodaDepth));
  syncYodaDepthControl();
  updateCacheSettingsView();
  hideFloatingPanels();
}

function updateLastRefresh(source) {
  state.lastRefreshAt = source?.updated_at || new Date().toISOString();
  if (lastRefresh) lastRefresh.textContent = formatRefreshTime(state.lastRefreshAt);
}

function shouldAnimateContinuously() {
  return Boolean(
    state.drag.active
    || state.tour.active
    || state.flowingEdges
    || state.expandingSlugs.size
    || Math.abs(state.rotation.vx) > 0.00002
    || Math.abs(state.rotation.vy) > 0.00002,
  );
}

function ensureRenderLoop() {
  if (state.animationHandle) return;
  state.animationHandle = requestAnimationFrame(render);
}

function requestRender() {
  state.renderDirty = true;
  ensureRenderLoop();
}

function clampZoom(value) {
  return Math.max(0.45, Math.min(2.4, value));
}

function setZoom(value) {
  state.zoom = clampZoom(value);
  if (zoomLevel) zoomLevel.textContent = `${Math.round(state.zoom * 100)}%`;
  projectAll();
  requestRender();
}

function updateCloudModeControl() {
  if (!cloudModeButton) return;
  cloudModeButton.classList.toggle("is-on", state.cloudMode);
  cloudModeButton.classList.toggle("is-off", !state.cloudMode);
  cloudModeButton.setAttribute("aria-pressed", state.cloudMode ? "true" : "false");
  cloudModeButton.setAttribute("aria-label", state.cloudMode ? "Clustering on" : "Clustering off");
  const tooltip = state.cloudMode ? "Clustering is on. Click to turn it off." : "Clustering is off. Click to turn it on.";
  cloudModeButton.dataset.tooltip = tooltip;
  cloudModeButton.title = tooltip;
  if (cloudModeToggle) cloudModeToggle.checked = state.cloudMode;
}

function updateMapFilterPanel() {
  mapFilterPanel?.classList.toggle("is-hidden", !state.mapFiltersVisible);
  mapFilterToggleButton?.classList.toggle("is-on", state.mapFiltersVisible);
  mapFilterToggleButton?.setAttribute("aria-pressed", state.mapFiltersVisible ? "true" : "false");
}

function showFilterSidebar() {
  const activationZone = "right side middle third";
  state.mapFiltersVisible = true;
  updateMapFilterPanel();
  return activationZone;
}

function hideFilterSidebar() {
  state.mapFiltersVisible = false;
  updateMapFilterPanel();
}

function pointerStayedInsideFilterSidebar(target) {
  return Boolean(
    target
    && (
      mapFilterPanel?.contains(target)
      || filterDrawerHandle?.contains(target)
      || target === mapFilterPanel
      || target === filterDrawerHandle
    ),
  );
}

function yodaLogSlug() {
  return state.modalAction?.slug || state.focusSlug;
}

function zoomBy(direction) {
  const factor = direction > 0 ? 1.14 : 1 / 1.14;
  setZoom(state.zoom * factor);
}

function historyCanMove(delta) {
  const nextIndex = state.selectionHistory.index + delta;
  return nextIndex >= 0 && nextIndex < state.selectionHistory.slugs.length;
}

function updateSelectionHistoryControls() {
  const canBack = historyCanMove(-1) && !state.selectionHistory.navigating;
  const canForward = historyCanMove(1) && !state.selectionHistory.navigating;
  [historyBackButton, floatingHistoryBackButton].forEach((button) => {
    if (!button) return;
    button.disabled = !canBack;
    button.setAttribute("aria-disabled", canBack ? "false" : "true");
  });
  [historyForwardButton, floatingHistoryForwardButton].forEach((button) => {
    if (!button) return;
    button.disabled = !canForward;
    button.setAttribute("aria-disabled", canForward ? "false" : "true");
  });
}

function updateAskYodaButtons() {
  const hasSelection = Boolean(state.focusSlug);
  [selectionAskYodaButton, mapAskYodaButton, mapViewButton, selectionViewButton].forEach((button) => {
    if (!button) return;
    button.disabled = !hasSelection;
    button.setAttribute("aria-disabled", hasSelection ? "false" : "true");
    button.classList.toggle("is-disabled", !hasSelection);
  });
}

function recordSelectionHistory(slug) {
  if (!slug || state.selectionHistory.navigating) {
    updateSelectionHistoryControls();
    return;
  }
  const currentSlug = state.selectionHistory.slugs[state.selectionHistory.index];
  if (currentSlug === slug) {
    updateSelectionHistoryControls();
    return;
  }
  if (state.selectionHistory.index < state.selectionHistory.slugs.length - 1) {
    state.selectionHistory.slugs = state.selectionHistory.slugs.slice(0, state.selectionHistory.index + 1);
  }
  state.selectionHistory.slugs.push(slug);
  if (state.selectionHistory.slugs.length > 20) {
    state.selectionHistory.slugs = state.selectionHistory.slugs.slice(-20);
  }
  state.selectionHistory.index = state.selectionHistory.slugs.length - 1;
  updateSelectionHistoryControls();
}

async function navigateSelectionHistory(delta) {
  if (!historyCanMove(delta) || state.selectionHistory.navigating) return;
  state.selectionHistory.index += delta;
  const slug = state.selectionHistory.slugs[state.selectionHistory.index];
  state.selectionHistory.navigating = true;
  updateSelectionHistoryControls();
  try {
    await loadEntity(slug, { source: "history", recordHistory: false });
  } finally {
    state.selectionHistory.navigating = false;
    updateSelectionHistoryControls();
  }
}

function buildTourSlugs() {
  const seenCategories = new Set();
  const candidates = visibleGraphNodes()
    .filter((node) => state.filteredSlugs.has(node.slug))
    .sort((left, right) => (right.degree || 0) - (left.degree || 0));
  const diverse = [];
  candidates.forEach((node) => {
    const category = node.category || node.type || "entity";
    if (seenCategories.has(category) || diverse.length >= 10) return;
    seenCategories.add(category);
    diverse.push(node.slug);
  });
  candidates.forEach((node) => {
    if (diverse.length >= 14) return;
    if (!diverse.includes(node.slug)) diverse.push(node.slug);
  });
  return diverse;
}

function autoPlanSlugs() {
  return buildTourSlugs().slice(0, 14);
}

function isValidPlanSlug(slug) {
  return Boolean(slug && state.nodeMap.has(slug) && !isHidden(slug));
}

function plannedPlaybackSlugs() {
  return state.tour.planSlugs.filter((slug) => isValidPlanSlug(slug));
}

function persistPlannedPlayback() {
  const slugs = [...new Set(state.tour.planSlugs.map((slug) => String(slug || "").trim()).filter(Boolean))];
  state.tour.planSlugs = slugs;
  window.localStorage?.setItem(PLANNED_PLAYBACK_KEY, JSON.stringify(slugs));
}

async function showTourStop(index) {
  if (!state.tour.slugs.length || state.tour.pending) return;
  state.tour.pending = true;
  state.tour.index = (index + state.tour.slugs.length) % state.tour.slugs.length;
  const slug = state.tour.slugs[state.tour.index];
  const recoveryTimer = window.setTimeout(() => clearTourPending(slug), tourNodeLoadTimeoutMs + 5000);
  const node = state.nodeMap.get(slug);
  if (!node) {
    window.clearTimeout(recoveryTimer);
    clearTourPending(slug);
    return;
  }
  hoverLabel.textContent = `Autopilot ${state.tour.index + 1}/${state.tour.slugs.length}: ${node.label}`;
  updateTourControls();
  try {
    const loadStep = (async () => {
      let result;
      try {
        result = await loadEntity(slug, { source: "system" });
      } catch (error) {
        result = handleTourNodeError(slug, error);
      }
      if (result?.status === "partial" || result?.status === "error") {
        handleTourNodeTimeout(slug);
        return "timeout";
      }
      await waitForTourSelectionLoad(slug);
      return "loaded";
    })();
    const timeoutStep = new Promise((resolve) => {
      state.tour.timeoutTimer = window.setTimeout(() => {
        resolve(handleTourNodeTimeout(slug));
      }, tourNodeLoadTimeoutMs);
    });
    await Promise.race([loadStep, timeoutStep]);
  } finally {
    window.clearTimeout(recoveryTimer);
    if (state.tour.timeoutTimer) {
      window.clearTimeout(state.tour.timeoutTimer);
      state.tour.timeoutTimer = null;
    }
    clearTourPending(slug);
  }
  if (state.tour.active) scheduleNextTourStop();
}

function clearTourPending(slug = state.focusSlug) {
  state.tour.pending = false;
  updateTourCounter(slug);
}

function handleTourNodeTimeout(slug) {
  const node = state.nodeMap.get(slug);
  state.tour.partialTimeoutSlugs.add(slug);
  hoverLabel.textContent = `Partial info loaded for ${node?.label || slug}, moving to next node`;
  return "timeout";
}

function handleTourNodeError(slug, error) {
  const node = state.nodeMap.get(slug);
  state.tour.partialTimeoutSlugs.add(slug);
  hoverLabel.textContent = `Partial info loaded for ${node?.label || slug}, moving to next node`;
  console.warn("Autopilot node load failed", slug, error);
  return { status: "error", slug, error };
}

function selectionIsLoadedForTour(slug) {
  return state.focusSlug === slug
    && detailTitle.textContent.trim().length > 0
    && detailType.textContent.trim().length > 0
    && detailSummary.textContent.trim().length > 0;
}

function waitForTourSelectionLoad(slug) {
  return new Promise((resolve) => {
    const check = () => {
      if (selectionIsLoadedForTour(slug)) {
        resolve();
        return;
      }
      window.setTimeout(check, 120);
    };
    check();
  });
}

function scheduleNextTourStop() {
  if (!state.tour.active) return;
  if (state.tour.mode === "planned" && !state.tour.loop && state.tour.index >= state.tour.slugs.length - 1) {
    pauseTour();
    return;
  }
  if (state.tour.timer) window.clearTimeout(state.tour.timer);
  state.tour.timer = window.setTimeout(() => {
    void showTourStop(state.tour.index + 1);
  }, Math.max(1, state.tour.delaySeconds || 5) * 1000);
}

function stopTour() {
  state.tour.active = false;
  state.tour.mode = "auto";
  state.tour.toolbarPinned = false;
  if (state.tour.timer) {
    window.clearTimeout(state.tour.timer);
    state.tour.timer = null;
  }
  if (state.tour.timeoutTimer) {
    window.clearTimeout(state.tour.timeoutTimer);
    state.tour.timeoutTimer = null;
  }
  state.tour.pending = false;
  updateTourControls();
}

function pauseTour() {
  state.tour.active = false;
  state.tour.toolbarPinned = true;
  if (state.tour.timer) {
    window.clearTimeout(state.tour.timer);
    state.tour.timer = null;
  }
  if (state.tour.timeoutTimer) {
    window.clearTimeout(state.tour.timeoutTimer);
    state.tour.timeoutTimer = null;
  }
  state.tour.pending = false;
  updateTourControls();
}

async function startTour() {
  state.tour.slugs = buildTourSlugs();
  if (!state.tour.slugs.length) return;
  state.tour.mode = "auto";
  state.tour.active = true;
  state.tour.toolbarPinned = true;
  updateTourControls();
  await showTourStop(state.tour.index || 0);
}

async function startPlannedPlayback() {
  const planned = state.tour.useAutoList ? autoPlanSlugs() : plannedPlaybackSlugs();
  if (!planned.length) {
    state.tour.slugs = buildTourSlugs();
    if (!state.tour.slugs.length) return;
    state.tour.mode = "auto";
  } else {
    state.tour.slugs = planned;
    state.tour.mode = state.tour.useAutoList ? "auto" : "planned";
  }
  state.tour.index = Math.max(0, Math.min(state.tour.index || 0, state.tour.slugs.length - 1));
  state.tour.active = true;
  state.tour.toolbarPinned = true;
  updateTourControls();
  await showTourStop(state.tour.index);
}

function toggleTour() {
  if (state.tour.active) {
    pauseTour();
    return;
  }
  void startPlannedPlayback();
}

function moveTour(delta) {
  const wasActive = state.tour.active;
  if (!state.tour.slugs.length || state.tour.mode === "planned" || state.tour.useAutoList) {
    const planned = state.tour.useAutoList ? autoPlanSlugs() : plannedPlaybackSlugs();
    state.tour.slugs = planned.length ? planned : buildTourSlugs();
    state.tour.mode = state.tour.useAutoList || !planned.length ? "auto" : "planned";
  }
  pauseTour();
  state.tour.active = wasActive;
  updateTourControls();
  void showTourStop(state.tour.index + delta);
}

function updateTourControls() {
  if (!tourButton) return;
  const tourDocked = state.tour.active || state.tour.toolbarPinned;
  const stopText = `Autopilot ${state.tour.index + 1 || 1}/${Math.max(1, state.tour.slugs.length)}`;
  const modeText = state.tour.mode === "planned" ? "planned playback" : "automatic tour";
  const tooltip = state.tour.active ? `${stopText}. Click to pause ${modeText}.` : `Play ${state.tour.useAutoList ? "automatic tour" : plannedPlaybackSlugs().length ? "planned playback" : "automatic tour"}.`;
  if (autopilotFlyout) {
    autopilotFlyout.hidden = !tourDocked && !navAutopilotButton?.classList.contains("is-open");
  }
  tourButton.classList.toggle("is-active", state.tour.active);
  tourButton.setAttribute("aria-pressed", state.tour.active ? "true" : "false");
  tourButton.setAttribute("aria-label", state.tour.active ? "Pause Autopilot" : "Play Autopilot");
  tourButton.dataset.tooltip = tooltip;
  tourButton.title = tooltip;
  tourButton.innerHTML = state.tour.active
    ? '<svg class="autopilot-icon pause-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14"></path><path d="M16 5v14"></path></svg>'
    : '<svg class="autopilot-icon play-icon" viewBox="0 0 24 24" aria-hidden="true"><path d="M8 5v14l11-7z"></path></svg>';
  if (metricMode) metricMode.textContent = state.tour.active ? "Autopilot" : "Manual";
  tourButton.closest(".autopilot-flyout")?.classList.toggle("tour-active", state.tour.active);
  tourButton.closest(".autopilot-flyout")?.classList.toggle("tour-docked", tourDocked);
  if (autopilotFlyout && !autopilotFlyout.hidden) {
    positionFloatingPanel(autopilotFlyout, navAutopilotButton);
  }
  updateTourCounter();
  updateNavModeState();
}

function updateTourCounter(_slug = state.focusSlug) {
  if (!tourCounter) return;
  const total = state.tour.slugs.length;
  const current = total ? state.tour.index + 1 : 0;
  const plannedTotal = state.tour.useAutoList ? autoPlanSlugs().length : plannedPlaybackSlugs().length;
  tourCounter.textContent = state.tour.active || total ? `${current}/${total}` : `0/${plannedTotal || 0}`;
  tourCounter.hidden = false;
}

function setSearchLoading(active) {
  state.lazySearch.loading = active;
  searchInput.disabled = active;
  searchButton.disabled = active;
  searchButton.setAttribute("aria-label", active ? "Searching" : "Run search");
  searchButton.dataset.tooltip = active ? "Searching memory nodes." : "Run search and load the best matching entity.";
  searchButton.title = searchButton.dataset.tooltip;
}

async function runLazySearch(query) {
  if (state.lazySearch.loading) return;
  const submittedQuery = String(query || "").trim();
  if (submittedQuery.length < 2) return;
  const busyToken = beginBusyOperation("Searching");
  const searchStartedAt = performance.now();
  setSearchLoading(true);
  const selectionVersion = state.selectionVersion;
  try {
    const exactSlugLoaded = await tryExactSlugSearch(submittedQuery);
    if (exactSlugLoaded) {
      reportSearchTiming(searchStartedAt);
      return;
    }
    const response = await apiGet(`/api/search?q=${encodeURIComponent(submittedQuery)}`);
    if (!response.ok) return;
    const preferredFocus = pickSearchFocus(response.data.graph, submittedQuery) || state.focusSlug;
    const focusSlug = selectionVersion === state.selectionVersion ? preferredFocus : state.focusSlug;
    applyGraphPayload(response.data.graph, focusSlug);
    if (selectionVersion === state.selectionVersion && preferredFocus && state.focusSlug === preferredFocus) {
      await loadEntity(preferredFocus, { source: "search" });
    }
    reportSearchTiming(searchStartedAt);
  } finally {
    setSearchLoading(false);
    endBusyOperation(busyToken);
    searchInput.focus();
  }
}

async function submitSearch() {
  const query = state.query.trim();
  if (!query || query.length < 2 || state.lazySearch.loading) return;
  await runLazySearch(query);
}

async function searchEntityLink(query) {
  const value = String(query || "").trim();
  if (value.length < 2 || state.lazySearch.loading) return;
  closeModal();
  state.query = value;
  searchInput.value = value;
  matchesOnlyToggle.checked = false;
  state.matchesOnly = false;
  await runLazySearch(value);
}

const flyoutPairs = [
  { panel: searchFlyout, button: navSearchButton },
  { panel: autopilotFlyout, button: navAutopilotButton },
  { panel: settingsFlyout, button: navSettingsButton },
];

function setFlyoutOpen(panel, button, open) {
  if (!panel || !button) return;
  if (open) positionFloatingPanel(panel, button);
  panel.hidden = !open;
  button.setAttribute("aria-expanded", open ? "true" : "false");
  button.classList.toggle("is-open", open);
  if (panel === settingsFlyout && open) {
    state.pendingSettings = snapshotSettings();
    if (flowingEdgesToggle) flowingEdgesToggle.checked = state.flowingEdges;
    syncYodaDepthControl();
    updateCacheSettingsView();
  }
  updateNavModeState();
}

function hideFloatingPanels(exceptPanel = null) {
  flyoutPairs.forEach(({ panel, button }) => {
    if (panel && panel !== exceptPanel) {
      if (panel === autopilotFlyout && state.tour.active) {
        return;
      }
      if (panel === autopilotFlyout && state.tour.toolbarPinned) {
        return;
      }
      setFlyoutOpen(panel, button, false);
    }
  });
}

function toggleFloatingPanel(panel, button) {
  if (!panel || !button) return;
  const willOpen = panel.hidden;
  hideFloatingPanels(panel);
  setFlyoutOpen(panel, button, willOpen);
}

function positionFloatingPanel(panel, button) {
  const wrap = canvas?.parentElement;
  if (!panel || !button || !wrap) return;
  const wrapRect = wrap.getBoundingClientRect();
  const buttonRect = button.getBoundingClientRect();
  const top = Math.max(12, Math.min(wrapRect.height - 80, buttonRect.top - wrapRect.top));
  if (panel === settingsFlyout) {
    panel.style.left = "22px";
    panel.style.right = "auto";
    panel.style.top = "52px";
    panel.style.transform = "";
    return;
  }
  if (panel === autopilotFlyout && (state.tour.active || state.tour.toolbarPinned)) {
    panel.style.left = "50%";
    panel.style.right = "auto";
    panel.style.top = "18px";
    panel.style.transform = "translateX(-50%)";
    return;
  }
  panel.style.left = "12px";
  panel.style.right = "auto";
  panel.style.top = `${Math.round(top)}px`;
  panel.style.transform = "";
}

function showFloatingPanel(panel, button) {
  hideFloatingPanels(panel);
  setFlyoutOpen(panel, button, true);
}

function targetIsInsideFloatingPanel(target) {
  return flyoutPairs.some(({ panel, button }) => (
    (panel && panel.contains(target)) || (button && button.contains(target))
  ));
}

function updateNavModeState() {
  const searchOpen = Boolean(searchFlyout && !searchFlyout.hidden);
  const settingsOpen = Boolean(settingsFlyout && !settingsFlyout.hidden);
  const autopilotOpen = Boolean(autopilotFlyout && !autopilotFlyout.hidden);
  navStargraphButton?.classList.toggle("is-active", !state.tour.active && !searchOpen && !settingsOpen && !autopilotOpen);
  navStargraphButton?.classList.toggle("is-flashing", !state.tour.active && !searchOpen && !settingsOpen && !autopilotOpen);
  navSearchButton?.classList.toggle("is-active", searchOpen);
  navSearchButton?.classList.toggle("is-flashing", searchOpen);
  navSettingsButton?.classList.toggle("is-active", settingsOpen);
  navSettingsButton?.classList.toggle("is-flashing", settingsOpen);
  navAutopilotButton?.classList.toggle("is-active", state.tour.active || autopilotOpen);
  navAutopilotButton?.classList.toggle("is-flashing", state.tour.active || autopilotOpen);
}

function updateResponsiveSelectionPlacement() {
  if (!detailPanel || !workspace || !graphCanvasWrap) return;
  const compact = compactSelectionQuery.matches;
  if (compact) {
    if (detailPanel.parentElement !== graphCanvasWrap) {
      graphCanvasWrap.appendChild(detailPanel);
    }
    detailPanel.classList.add("is-map-overlay");
  } else {
    if (detailPanel.parentElement !== workspace) {
      workspace.appendChild(detailPanel);
    }
    detailPanel.classList.remove("is-map-overlay");
  }
}

function isHidden(slug) {
  return state.hiddenSlugs.has(slug);
}

function visibleGraphNodes() {
  return state.nodes.filter((node) => !isHidden(node.slug) && !isClusterHidden(node));
}

function normalizeSearchText(value) {
  return String(value || "").toLocaleLowerCase().replace(/[^\p{L}\p{N}]+/gu, " ").trim();
}

function looksLikeExactSlug(value) {
  const text = String(value || "").trim();
  const slugSegmentPattern = "[A-Za-z0-9][A-Za-z0-9" + "._-]*";
  const exactSlugPattern = new RegExp(`^${slugSegmentPattern}(?:\\/${slugSegmentPattern})+$`);
  return exactSlugPattern.test(text)
    && !text.includes(" ")
    && !text.startsWith("/")
    && !text.endsWith("/");
}

function reportSearchTiming(searchStartedAt) {
  const elapsed = Math.max(0, Math.round(performance.now() - searchStartedAt));
  hoverLabel.textContent = `Search completed in ${elapsed}ms`;
}

async function tryExactSlugSearch(slug) {
  if (!looksLikeExactSlug(slug)) return false;
  const response = await apiPost(`/api/entity-expand/${encodeURIComponent(slug)}`);
  if (!response.ok || !response.data?.graph) return false;
  applyGraphPayload(response.data.graph, slug);
  requestRender();
  await loadEntity(slug, { source: "search" });
  return true;
}

function pickSearchFocus(graph, query) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return null;
  const queryTerms = normalizedQuery.split(/\s+/).filter(Boolean);
  const coverage = graph?.source?.coverage || {};
  const orderedSearchSlugs = normalizeSearchText(coverage.last_search_query || "") === normalizedQuery
    ? coverage.search_slugs || []
    : [];
  const searchSlugs = new Set(orderedSearchSlugs);
  const searchRank = new Map(orderedSearchSlugs.map((slug, index) => [slug, index]));
  const candidates = (graph.nodes || [])
    .filter((node) => !isHidden(node.slug) && (searchSlugs.has(node.slug) || matchesQuery(node, normalizedQuery)))
    .map((node) => {
      const label = normalizeSearchText(node.label);
      const slug = normalizeSearchText(node.slug);
      const categoryBoost = (node.category || node.type || "").toLowerCase() === "people" ? 25 : 0;
      const exactBoost = label === normalizedQuery || slug === normalizedQuery ? 100 : 0;
      const phraseBoost = label.includes(normalizedQuery) || slug.includes(normalizedQuery) ? 50 : 0;
      const termBoost = queryTerms.every((term) => label.includes(term) || slug.includes(term)) ? 20 : 0;
      const backendBoost = searchSlugs.has(node.slug) ? 35 : 0;
      const backendRankBoost = searchRank.has(node.slug) ? Math.max(0, 1000 - (searchRank.get(node.slug) || 0) * 20) : 0;
      return { node, score: exactBoost + phraseBoost + termBoost + backendBoost + backendRankBoost + categoryBoost + (node.degree || 0) };
    })
    .sort((left, right) => right.score - left.score || (right.node.degree || 0) - (left.node.degree || 0));
  return candidates[0]?.node.slug || null;
}

function updateUiVersion(graph) {
  uiVersion.textContent = UI_VERSION || graph?.ui_version || "";
}

function buildRuntimeGraph(graph) {
  const width = state.viewport.width || 1200;
  const height = state.viewport.height || 760;
  (graph.nodes || []).forEach((node) => {
    if (node.has_media || node.media_count > 0 || node.media?.length || node.attachments?.length) {
      state.mediaSlugs.add(node.slug);
    }
  });
  const categories = [...new Set(graph.nodes.map((node) => node.category || node.type || "entity"))];
  const categoryIndex = new Map(categories.map((category, index) => [category, index]));
  const categorySlots = new Map();
  const visibleSpan = Math.min(width, height);
  const cloudRadius = Math.max(170, visibleSpan * 0.3);
  const maxDegree = Math.max(1, graph.stats?.max_degree || 1);
  const nodes = graph.nodes.map((node, index) => {
    const category = node.category || node.type || "entity";
    const bandIndex = categoryIndex.get(category) || 0;
    const bandAngle = (Math.PI * 2 * bandIndex) / Math.max(categories.length, 1);
    const slot = categorySlots.get(category) || 0;
    categorySlots.set(category, slot + 1);
    const localAngle = slot * 2.399963229728653 + bandIndex * 0.37;
    const degreeRatio = (node.degree || 0) / maxDegree;
    const hierarchyDepth = Math.min(3, Math.max(0, (node.slug.match(/\//g) || []).length));
    const clusterCore = state.cloudMode ? cloudRadius * 1.02 : 0;
    const radius = state.cloudMode
      ? cloudRadius * (0.14 + hierarchyDepth * 0.05 + (1 - degreeRatio) * 0.17)
      : cloudRadius * (0.46 + hierarchyDepth * 0.18 + (1 - degreeRatio) * 0.22);
    const verticalLift = state.cloudMode ? Math.sin(bandAngle * 1.7) * cloudRadius * 0.1 : 0;
    const x3 = Math.cos(bandAngle) * clusterCore + Math.cos(localAngle) * radius;
    const y3 = Math.sin(localAngle * 0.73) * radius * 0.58 + verticalLift;
    const z3 = Math.sin(bandAngle) * clusterCore + Math.sin(localAngle) * radius;
    const timeValue = Date.parse(node.updated_at || node.date || node.modified_at || "");
    return {
      ...node,
      category,
      x3,
      y3,
      z3,
      timeMs: Number.isNaN(timeValue) ? null : timeValue,
      screenX: width / 2,
      screenY: height / 2,
      depth: 0,
      depthScale: 1,
      pulseOffset: (stableHash(node.slug) % 6283) / 1000,
    };
  });
  const nodeMap = new Map(nodes.map((node) => [node.slug, node]));
  const edges = graph.edges
    .map((edge) => ({
      source: nodeMap.get(edge.source),
      target: nodeMap.get(edge.target),
      types: edge.types || [],
    }))
    .filter((edge) => edge.source && edge.target);
  const edgeTypeMap = new Map();
  edges.forEach((edge) => {
    const key = relationshipKey(edge.source.slug, edge.target.slug);
    edgeTypeMap.set(key, edge.types || []);
  });
  state.nodes = nodes;
  state.edges = edges;
  state.edgeTypeMap = edgeTypeMap;
  state.nodeMap = nodeMap;
  projectAll();
}

function projectPoint(x, y, z) {
  const sinX = Math.sin(state.rotation.x);
  const cosX = Math.cos(state.rotation.x);
  const sinY = Math.sin(state.rotation.y);
  const cosY = Math.cos(state.rotation.y);
  const y1 = y * cosX - z * sinX;
  const z1 = y * sinX + z * cosX;
  const x2 = x * cosY + z1 * sinY;
  const z2 = -x * sinY + z1 * cosY;
  const camera = 900;
  const scale = camera / Math.max(220, camera + z2);
  const zoomedScale = scale * state.zoom;
  return {
    x: state.viewport.width / 2 + x2 * zoomedScale,
    y: state.viewport.height / 2 + y1 * zoomedScale,
    depth: z2,
    scale: zoomedScale,
  };
}

function projectAll() {
  state.nodes.forEach((node) => {
    const projected = projectPoint(node.x3, node.y3, node.z3);
    node.screenX = projected.x;
    node.screenY = projected.y;
    node.depth = projected.depth;
    node.depthScale = projected.scale;
    node.x = projected.x;
    node.y = projected.y;
  });
}

function updateMetrics(graph) {
  const visibleSlugs = state.filteredSlugs.size
    ? new Set([...state.filteredSlugs].filter((slug) => !isHidden(slug)))
    : new Set(graph.nodes.filter((node) => !isHidden(node.slug)).map((node) => node.slug));
  const visibleNodes = graph.nodes.filter((node) => visibleSlugs.has(node.slug));
  const visibleEdges = graph.edges.filter((edge) => visibleSlugs.has(edge.source) && visibleSlugs.has(edge.target));
  metricNodes.textContent = visibleNodes.length;
  metricEdges.textContent = visibleEdges.length;
  metricDegree.textContent = Math.max(0, ...visibleNodes.map((node) => node.degree || 0));
  if (metricMode) metricMode.textContent = state.tour.active ? "Autopilot" : "Manual";
}

function updateSource(source) {
  if (sourceBadge) sourceBadge.textContent = "";
  if (sourceMessage) sourceMessage.textContent = "";
  sourceWarnings.innerHTML = "";
  const warnings = [...(source.warnings || []), ...(source.errors || [])].slice(0, 6);
  warnings.forEach((warning) => {
    const item = document.createElement("li");
    item.textContent = warning;
    sourceWarnings.appendChild(item);
  });
}

function getCategoryColor(category) {
  const value = category || "entity";
  return CATEGORY_PALETTE[stableHash(value) % CATEGORY_PALETTE.length];
}

function updateCategoryLegend(graph) {
  if (!graph) return;
  categoryLegend.innerHTML = "";
  const counts = new Map();
  graph.nodes.forEach((node) => {
    if (isHidden(node.slug)) return;
    const category = node.category || node.type || "entity";
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .slice(0, state.categoryLimit)
    .forEach(([category, count]) => {
      const item = document.createElement("button");
      item.type = "button";
      item.dataset.cluster = category;
      item.className = state.hiddenClusters.has(category) ? "is-dimmed" : "is-active";
      item.title = state.hiddenClusters.has(category)
        ? `Click to show ${category} cluster`
        : `Click to hide ${category} cluster`;
      const label = document.createElement("span");
      label.className = "cluster-label";
      const swatch = document.createElement("i");
      swatch.style.backgroundColor = getCategoryColor(category);
      label.appendChild(swatch);
      label.append(category);
      const total = document.createElement("span");
      total.className = "cluster-count";
      total.textContent = count;
      item.append(label, total);
      item.addEventListener("click", () => {
        if (state.hiddenClusters.has(category)) {
          state.hiddenClusters.delete(category);
        } else {
          state.hiddenClusters.add(category);
        }
        updateCategoryLegend(state.graph);
        applyFilter();
      });
      categoryLegend.appendChild(item);
    });
}

function updateHubClusterLegend() {
  if (!hubClusterLegend) return;
  hubClusterLegend.innerHTML = "";
  const hubs = state.nodes
    .filter((node) => !isHidden(node.slug) && !isClusterHidden(node) && (node.degree || 0) > 0)
    .sort((left, right) => (right.degree || 0) - (left.degree || 0) || (left.label || left.slug).localeCompare(right.label || right.slug))
    .slice(0, state.clusterLimit);
  hubs.forEach((node) => {
    const item = document.createElement("button");
    item.type = "button";
    item.dataset.hub = node.slug;
    item.className = state.hiddenHubConnections.has(node.slug) ? "is-dimmed" : "is-active";
    item.title = state.hiddenHubConnections.has(node.slug)
      ? `Click to show direct connections of ${node.label || node.slug}`
      : `Click to hide direct connections of ${node.label || node.slug}`;
    const label = document.createElement("span");
    label.className = "cluster-label";
    const swatch = document.createElement("i");
    swatch.style.backgroundColor = getNodeColor(node);
    label.appendChild(swatch);
    label.append(shortLabel(node.label || node.slug, 24));
    const total = document.createElement("span");
    total.className = "cluster-count";
    total.textContent = node.degree || 0;
    item.append(label, total);
    item.addEventListener("click", () => {
      if (state.hiddenHubConnections.has(node.slug)) {
        state.hiddenHubConnections.delete(node.slug);
      } else {
        state.hiddenHubConnections.add(node.slug);
      }
      updateHubClusterLegend();
      applyFilter();
    });
    hubClusterLegend.appendChild(item);
  });
  if (!hubs.length) {
    const empty = document.createElement("p");
    empty.className = "hidden-empty";
    empty.textContent = "No hubs available";
    hubClusterLegend.appendChild(empty);
  }
}

function updateFilterOptions(graph) {
  return graph;
}

function updateHiddenList() {
  hiddenList.innerHTML = "";
  const hidden = [...state.hiddenSlugs]
    .map((slug) => state.nodeMap.get(slug) || { slug, label: slug, category: "hidden", type: "entity" })
    .sort((left, right) => (left.label || left.slug).localeCompare(right.label || right.slug));
  if (!hidden.length) {
    const empty = document.createElement("p");
    empty.className = "hidden-empty";
    empty.textContent = "No hidden nodes";
    hiddenList.appendChild(empty);
    return;
  }
  hidden.forEach((node) => {
    const item = document.createElement("div");
    item.className = "hidden-item";
    const text = document.createElement("div");
    const label = document.createElement("strong");
    label.textContent = node.label || node.slug;
    const slug = document.createElement("small");
    slug.textContent = `${node.category || node.type || "entity"} · ${node.slug}`;
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = "Show";
    button.addEventListener("click", () => {
      void showNode(node.slug);
    });
    text.append(label, slug);
    item.append(text, button);
    hiddenList.appendChild(item);
  });
}

function matchesQuery(node, query) {
  if (!query) {
    return true;
  }
  const coverage = state.graph?.source?.coverage || {};
  const lastSearchQuery = normalizeSearchText(coverage.last_search_query || "");
  const normalizedQuery = normalizeSearchText(query);
  if (lastSearchQuery && normalizedQuery && lastSearchQuery === normalizedQuery && (coverage.search_slugs || []).includes(node.slug)) {
    return true;
  }
  const haystack = [node.slug, node.label, node.type, node.category, node.summary, ...(node.tags || []), ...(node.collapsed_children || []), ...(node.collapsed_aliases || [])]
    .join(" ")
    .toLocaleLowerCase();
  const looseHaystack = normalizeSearchText(haystack);
  const looseQuery = normalizedQuery;
  const queryTerms = looseQuery.split(/\s+/).filter(Boolean);
  const contentTerms = queryTerms.filter((term) => term !== "part" && !/^\d{1,3}$/.test(term));
  return haystack.includes(query)
    || (looseQuery && looseHaystack.includes(looseQuery))
    || (queryTerms.length > 0 && queryTerms.every((term) => looseHaystack.includes(term)))
    || (contentTerms.length > 0 && contentTerms.every((term) => looseHaystack.includes(term)));
}

function timelineCutoffMs() {
  if (!state.timelineDays) return null;
  return Date.now() - state.timelineDays * 24 * 60 * 60 * 1000;
}

function passesTimeline(node) {
  const cutoff = timelineCutoffMs();
  if (!cutoff || !node.timeMs) return true;
  return node.timeMs >= cutoff;
}

function isClusterHidden(node) {
  return state.hiddenClusters.has(node.category || node.type || "entity");
}

function isHiddenByHubConnection(node) {
  if (!node || state.hiddenHubConnections.has(node.slug)) return false;
  for (const hubSlug of state.hiddenHubConnections) {
    const hub = state.nodeMap.get(hubSlug);
    if (hub?.links?.includes(node.slug) || node.links?.includes(hubSlug)) {
      return true;
    }
  }
  return false;
}

function updateTimelineLabel() {
  if (!timelineValue) return;
  timelineValue.textContent = "days";
  if (timelineDaysInput) timelineDaysInput.value = String(state.timelineDays);
}

function applyFilter() {
  const query = state.query.trim().toLowerCase();
  const { minDegree } = state.filters;
  const matchSlugs = new Set();
  const filteredSlugs = new Set();

  state.nodes.forEach((node) => {
    if (isHidden(node.slug) || isClusterHidden(node) || isHiddenByHubConnection(node)) return;
    const isMatch = matchesQuery(node, query);
    const passesDegree = (node.degree || 0) >= minDegree;
    const passesFilters = passesDegree && passesTimeline(node);
    if (isMatch) {
      matchSlugs.add(node.slug);
    }
    if (passesFilters && (!state.matchesOnly || isMatch)) {
      filteredSlugs.add(node.slug);
    }
  });

  state.matchSlugs = matchSlugs;
  state.filteredSlugs = filteredSlugs;

  if (state.focusSlug && !filteredSlugs.has(state.focusSlug)) {
    state.focusSlug = null;
  }
  if (state.graph) updateMetrics(state.graph);
  updateHubClusterLegend();
  requestRender();
}

function getNodeColor(node) {
  return getCategoryColor(node.category || node.type || "entity");
}

function relationshipKey(left, right) {
  return [left, right].sort().join("|||");
}

function relationshipTypes(left, right) {
  if (!left || !right) return [];
  return state.edgeTypeMap.get(relationshipKey(left, right)) || [];
}

function rememberRelationshipTypes(left, right, types) {
  if (!left || !right || !Array.isArray(types) || !types.length) return;
  const key = relationshipKey(left, right);
  const existing = new Set(state.edgeTypeMap.get(key) || []);
  types.forEach((type) => {
    const value = String(type || "").trim();
    if (value) existing.add(value);
  });
  if (existing.size) {
    state.edgeTypeMap.set(key, [...existing].sort());
  }
}

function isLinkedToFocus(node) {
  if (!state.focusSlug || node.slug === state.focusSlug) {
    return false;
  }
  const focused = state.nodeMap.get(state.focusSlug);
  return Boolean(node.links.includes(state.focusSlug) || focused?.links.includes(node.slug));
}

function nodeAlpha(node) {
  if (isHidden(node.slug)) {
    return 0;
  }
  if (isLinkedToFocus(node)) return 0.95;
  if (isClusterHidden(node) || isHiddenByHubConnection(node)) return 0;
  if (!state.filteredSlugs.has(node.slug)) {
    return 0.06;
  }
  if (node.slug === state.hoverSlug) return 1;
  if (!state.focusSlug) {
    return state.query ? (state.matchSlugs.has(node.slug) ? 1 : 0.2) : 0.92;
  }
  if (node.slug === state.focusSlug) return 1;
  if (node.links.includes(state.focusSlug)) return 0.95;
  const focused = state.nodeMap.get(state.focusSlug);
  if (focused && focused.links.includes(node.slug)) return 0.95;
  return state.matchSlugs.has(node.slug) ? 0.6 : 0.14;
}

function edgeAlpha(edge) {
  if (
    isHidden(edge.source.slug)
    || isHidden(edge.target.slug)
    || isClusterHidden(edge.source)
    || isClusterHidden(edge.target)
    || isHiddenByHubConnection(edge.source)
    || isHiddenByHubConnection(edge.target)
  ) return 0;
  const visible = state.filteredSlugs.has(edge.source.slug) && state.filteredSlugs.has(edge.target.slug);
  if (!visible) return 0;
  if (!state.focusSlug) {
    return state.query ? 0.18 : 0.22;
  }
  if (edge.source.slug === state.hoverSlug || edge.target.slug === state.hoverSlug) {
    return 0.82;
  }
  if (edge.source.slug === state.focusSlug || edge.target.slug === state.focusSlug) {
    return 0.72;
  }
  const isNear = edge.source.links.includes(state.focusSlug) || edge.target.links.includes(state.focusSlug);
  return isNear ? 0.2 : 0.06;
}

function edgeLayer(edge) {
  if (!state.focusSlug && !state.hoverSlug) return 0;
  if (edge.source.slug === state.hoverSlug || edge.target.slug === state.hoverSlug) return 2;
  if (edge.source.slug === state.focusSlug || edge.target.slug === state.focusSlug) return 2;
  if (edge.source.links.includes(state.focusSlug) || edge.target.links.includes(state.focusSlug)) return 1;
  return 0;
}

function tick() {
  if (!state.drag.active) {
    state.rotation.x += state.rotation.vx;
    state.rotation.y += state.rotation.vy;
    state.rotation.vx *= 0.992;
    state.rotation.vy *= 0.992;
  }
  projectAll();
}

function drawBackground() {
  const width = state.viewport.width;
  const height = state.viewport.height;
  ctx.clearRect(0, 0, width, height);

  const nebula = ctx.createRadialGradient(width * 0.28, height * 0.54, 20, width * 0.28, height * 0.54, width * 0.34);
  nebula.addColorStop(0, "rgba(168, 85, 247, 0.18)");
  nebula.addColorStop(0.42, "rgba(34, 211, 238, 0.055)");
  nebula.addColorStop(1, "rgba(4, 8, 18, 0)");
  ctx.fillStyle = nebula;
  ctx.fillRect(0, 0, width, height);

  const glow = ctx.createRadialGradient(width * 0.5, height * 0.48, 10, width * 0.5, height * 0.48, width * 0.44);
  glow.addColorStop(0, "rgba(34, 211, 238, 0.1)");
  glow.addColorStop(0.5, "rgba(59, 130, 246, 0.045)");
  glow.addColorStop(1, "rgba(4, 8, 18, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, width, height);

  ctx.save();
  ctx.strokeStyle = "rgba(34, 211, 238, 0.07)";
  ctx.lineWidth = 1;
  const radarX = width * 0.48;
  const radarY = height * 0.52;
  const maxRadius = Math.min(width, height) * 0.44;
  for (let radius = maxRadius * 0.25; radius <= maxRadius; radius += maxRadius * 0.18) {
    ctx.beginPath();
    ctx.arc(radarX, radarY, radius, 0, Math.PI * 2);
    ctx.stroke();
  }
  for (let index = 0; index < 10; index += 1) {
    const angle = (index / 10) * Math.PI * 2 + performance.now() / 24000;
    ctx.beginPath();
    ctx.moveTo(radarX, radarY);
    ctx.lineTo(radarX + Math.cos(angle) * maxRadius, radarY + Math.sin(angle) * maxRadius);
    ctx.stroke();
  }
  ctx.restore();

  for (let i = 0; i < 80; i += 1) {
    const x = ((i * 97) % width) + 0.5;
    const y = ((i * 57) % height) + 0.5;
    const twinkle = 0.35 + 0.25 * Math.sin((performance.now() / 900) + i);
    ctx.fillStyle = `rgba(255,255,255,${twinkle})`;
    ctx.beginPath();
    ctx.arc(x, y, i % 5 === 0 ? 1.4 : 0.8, 0, Math.PI * 2);
    ctx.fill();
  }
}

function degreeIntensity(node) {
  const maxDegree = Math.max(1, state.graph?.stats?.max_degree || 1);
  return Math.max(0, Math.min(1, (node.degree || 0) / maxDegree));
}

function drawClusterClouds() {
  if (!state.cloudMode || !state.filteredSlugs.size) return;
  const groups = new Map();
  drawableNodes().forEach((node) => {
    if (isClusterHidden(node) || isHiddenByHubConnection(node)) return;
    const alpha = nodeAlpha(node);
    if (alpha <= 0) return;
    const key = node.category || node.type || "entity";
    if (!groups.has(key)) groups.set(key, []);
    groups.get(key).push(node);
  });

  ctx.save();
  groups.forEach((nodes, category) => {
    if (nodes.length < 4) return;
    const color = getCategoryColor(category);
    const centerX = nodes.reduce((sum, node) => sum + node.screenX, 0) / nodes.length;
    const centerY = nodes.reduce((sum, node) => sum + node.screenY, 0) / nodes.length;
    const averageDistance = nodes.reduce((sum, node) => sum + Math.hypot(node.screenX - centerX, node.screenY - centerY), 0) / nodes.length;
    const hubBoost = Math.max(...nodes.map((node) => degreeIntensity(node)));
    const radius = Math.max(74, Math.min(260, averageDistance * 1.85 + hubBoost * 48));
    const cloud = ctx.createRadialGradient(centerX, centerY, 0, centerX, centerY, radius);
    cloud.addColorStop(0, hexToRgba(color, 0.16 + hubBoost * 0.08));
    cloud.addColorStop(0.55, hexToRgba(color, 0.07));
    cloud.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = cloud;
    ctx.beginPath();
    ctx.arc(centerX, centerY, radius, 0, Math.PI * 2);
    ctx.fill();
  });
  ctx.restore();
}

function nodeIsDrawable(node) {
  if (!node || isHidden(node.slug) || isClusterHidden(node) || isHiddenByHubConnection(node)) return false;
  if (!state.filteredSlugs.size || state.filteredSlugs.has(node.slug)) return true;
  if (node.slug === state.focusSlug || node.slug === state.hoverSlug) return true;
  if (isLinkedToFocus(node)) return true;
  if (state.query && state.matchSlugs.has(node.slug)) return true;
  return visibleTopHubs(8).includes(node.slug);
}

const drawableNodes = () => state.nodes.filter(nodeIsDrawable);
const drawableEdges = () => state.edges.filter((edge) => nodeIsDrawable(edge.source) && nodeIsDrawable(edge.target));

function nodeHasMediaMarker(node) {
  return Boolean(node && (state.mediaSlugs.has(node.slug) || node.has_media || node.media_count > 0 || node.media?.length || node.attachments?.length));
}

function rememberNodeMediaStatus(slug, items = []) {
  if (!slug) return;
  if (items.length) {
    state.mediaSlugs.add(slug);
  } else {
    state.mediaSlugs.delete(slug);
  }
  const node = state.nodeMap.get(slug);
  if (node) node.has_media = items.length > 0;
  requestRender();
}

function isImportantNodeForLod(node, topHubs = new Set()) {
  return node.slug === state.focusSlug
    || node.slug === state.hoverSlug
    || isLinkedToFocus(node)
    || topHubs.has(node.slug)
    || (node.degree || 0) >= Math.max(8, (state.graph?.stats?.max_degree || 1) * 0.18);
}

function flowingEdgeIsAnimated(edge) {
  if (!state.flowingEdges) return false;
  return edge.source.slug === state.focusSlug
    || edge.target.slug === state.focusSlug
    || edge.source.slug === state.hoverSlug
    || edge.target.slug === state.hoverSlug
    || isLinkedToFocus(edge.source)
    || isLinkedToFocus(edge.target);
}

function drawEdges() {
  const now = performance.now();
  drawableEdges().sort((left, right) => edgeLayer(left) - edgeLayer(right)).forEach((edge) => {
    const alpha = edgeAlpha(edge);
    if (alpha <= 0) return;
    const layer = edgeLayer(edge);
    const isHoveredFocusEdge = state.focusSlug
      && state.hoverSlug
      && edge.source.slug !== edge.target.slug
      && ((edge.source.slug === state.focusSlug && edge.target.slug === state.hoverSlug)
        || (edge.target.slug === state.focusSlug && edge.source.slug === state.hoverSlug));
    const depthAlpha = Math.max(0.28, Math.min(1, (edge.source.depthScale + edge.target.depthScale) / 2));
    const screenDistance = Math.hypot(edge.source.screenX - edge.target.screenX, edge.source.screenY - edge.target.screenY);
    const nearFactor = Math.max(0.25, 1 - screenDistance / Math.max(420, state.viewport.width * 0.55));
    const sameCluster = (edge.source.category || edge.source.type) === (edge.target.category || edge.target.type);
    const clusterColor = sameCluster ? getNodeColor(edge.source) : null;
    const baseAlpha = alpha * depthAlpha * (0.42 + nearFactor * 0.58);
    const strokeColor = layer === 2
      ? `rgba(255, 198, 111, ${Math.min(0.72, baseAlpha + 0.1)})`
      : layer === 1
        ? (clusterColor ? hexToRgba(clusterColor, Math.min(0.34, baseAlpha + 0.04)) : `rgba(136, 246, 255, ${Math.min(0.32, baseAlpha + 0.04)})`)
        : (clusterColor ? hexToRgba(clusterColor, Math.min(0.16, baseAlpha)) : `rgba(94, 112, 172, ${Math.min(0.14, baseAlpha)})`);
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = isHoveredFocusEdge
      ? 1.8
      : layer === 2 ? 1.25 + nearFactor * 0.35 : layer === 1 ? 0.72 + nearFactor * 0.32 : 0.32 + nearFactor * 0.24;
    ctx.beginPath();
    ctx.moveTo(edge.source.screenX, edge.source.screenY);
    ctx.lineTo(edge.target.screenX, edge.target.screenY);
    ctx.stroke();

    if (flowingEdgeIsAnimated(edge)) {
      ctx.save();
      ctx.setLineDash([6, 14]);
      ctx.lineDashOffset = -state.animationTick;
      ctx.strokeStyle = layer === 2
        ? `rgba(250, 204, 21, ${Math.min(0.45, baseAlpha + 0.08)})`
        : `rgba(34, 211, 238, ${Math.min(0.28, baseAlpha + 0.04)})`;
      ctx.lineWidth = Math.max(0.8, ctx.lineWidth * 0.86);
      ctx.beginPath();
      ctx.moveTo(edge.source.screenX, edge.source.screenY);
      ctx.lineTo(edge.target.screenX, edge.target.screenY);
      ctx.stroke();
      ctx.setLineDash([]);
      ctx.restore();
    }

    if (flowingEdgeIsAnimated(edge) && (layer > 0 || isHoveredFocusEdge)) {
      const phase = ((now / (900 + (edge.source.degree || 1) * 12)) + ((edge.source.pulseOffset || 0) % 1)) % 1;
      const particleX = edge.source.screenX + (edge.target.screenX - edge.source.screenX) * phase;
      const particleY = edge.source.screenY + (edge.target.screenY - edge.source.screenY) * phase;
      ctx.save();
      ctx.globalAlpha = Math.min(0.86, 0.28 + alpha * 0.58);
      ctx.fillStyle = layer === 2 ? "rgba(250, 204, 21, 0.95)" : "rgba(34, 211, 238, 0.86)";
      ctx.shadowColor = ctx.fillStyle;
      ctx.shadowBlur = 10;
      ctx.beginPath();
      ctx.arc(particleX, particleY, layer === 2 ? 2.4 : 1.7, 0, Math.PI * 2);
      ctx.fill();
      ctx.restore();
    }

    const linkTypes = isHoveredFocusEdge ? relationshipTypes(edge.source.slug, edge.target.slug) : [];
    if (linkTypes.length) {
      const label = shortLabel(linkTypes.join(", "), 34);
      const midX = (edge.source.screenX + edge.target.screenX) / 2;
      const midY = (edge.source.screenY + edge.target.screenY) / 2;
      const dx = edge.target.screenX - edge.source.screenX;
      const dy = edge.target.screenY - edge.source.screenY;
      const length = Math.max(1, Math.hypot(dx, dy));
      const labelX = midX + (-dy / length) * 16;
      const labelY = midY + (dx / length) * 16;
      ctx.save();
      ctx.font = "700 12px Rajdhani, Inter, sans-serif";
      const metrics = ctx.measureText(label);
      const pillWidth = metrics.width + 18;
      const pillHeight = 22;
      ctx.fillStyle = "rgba(5, 8, 22, 0.84)";
      ctx.strokeStyle = "rgba(255, 198, 111, 0.72)";
      ctx.lineWidth = 1;
      ctx.beginPath();
      ctx.roundRect(labelX - pillWidth / 2, labelY - pillHeight / 2, pillWidth, pillHeight, 11);
      ctx.fill();
      ctx.stroke();
      ctx.fillStyle = "rgba(255, 198, 111, 0.98)";
      ctx.textAlign = "center";
      ctx.textBaseline = "middle";
      ctx.fillText(label, labelX, labelY + 0.5);
      ctx.restore();
    }
  });
}

function shortLabel(text, limit = 26) {
  if (!text || text.length <= limit) {
    return text || "";
  }
  return `${text.slice(0, limit - 1).trim()}…`;
}

function briefSummary(node) {
  const text = String(node?.summary || "").replace(/\s+/g, " ").trim();
  if (!text || text === "No summary available." || ["summary", "metadata"].includes(text.toLowerCase())) {
    return "No summary available.";
  }
  return shortLabel(text, 150);
}

function displaySummary(text) {
  const value = String(text || "").replace(/\s+/g, " ").trim();
  if (!value || value === "No summary available." || ["summary", "metadata"].includes(value.toLowerCase())) {
    return "No meaningful summary is available for this node yet.";
  }
  return value;
}

function visibleSearchMatches() {
  return state.nodes
    .filter((node) => !isHidden(node.slug) && state.matchSlugs.has(node.slug))
    .sort((left, right) => (right.degree || 0) - (left.degree || 0))
    .slice(0, 5)
    .map((node) => node.slug);
}

function visibleTopHubs(limit = 8) {
  return state.nodes
    .filter((node) => !isHidden(node.slug) && !isClusterHidden(node) && state.filteredSlugs.has(node.slug))
    .sort((left, right) => (right.degree || 0) - (left.degree || 0))
    .slice(0, limit)
    .map((node) => node.slug);
}

function shouldShowLabel(node, topMatches, topHubs) {
  if (node.slug === state.focusSlug || node.slug === state.hoverSlug) return true;
  if (isLinkedToFocus(node)) {
    const focused = state.focusSlug ? state.nodeMap.get(state.focusSlug) : null;
    const focusedDegree = focused?.degree || 0;
    if (focusedDegree <= 80) return true;
    if (topHubs.has(node.slug)) return true;
    if ((node.degree || 0) >= 5) return true;
    return state.zoom >= 1.65;
  }
  if (state.query && topMatches.has(node.slug)) return true;
  if (topHubs.has(node.slug)) return true;
  if (state.zoom < 1.35) return false;
  const threshold = state.zoom >= 1.85
    ? Math.max(2, (state.graph?.stats?.max_degree || 1) * 0.12)
    : Math.max(5, (state.graph?.stats?.max_degree || 1) * 0.24);
  return (node.degree || 0) >= threshold;
}

function labelForNode(node) {
  if (node.slug === state.focusSlug || node.slug === state.hoverSlug) {
    return shortLabel(node.label, 34);
  }
  if (isLinkedToFocus(node)) {
    return shortLabel(node.label, 28);
  }
  if (state.query && state.matchSlugs.has(node.slug)) {
    return shortLabel(node.label, 24);
  }
  return shortLabel(node.label, state.zoom >= 1.85 ? 26 : 20);
}

function intersectsAny(rect, rects) {
  return rects.some((item) => !(
    rect.right < item.left
    || rect.left > item.right
    || rect.bottom < item.top
    || rect.top > item.bottom
  ));
}

function drawNodes() {
  const now = performance.now();
  const topMatches = new Set(visibleSearchMatches());
  const topHubs = new Set(visibleTopHubs());
  const ordered = drawableNodes().sort((left, right) => left.depth - right.depth);
  const visibleLabelSlugs = [];
  const labelRects = [];
  ordered.forEach((node) => {
    const alpha = nodeAlpha(node);
    if (alpha <= 0) return;
    const pulse = 1 + Math.sin(now / 700 + node.pulseOffset) * 0.06;
    const radius = Math.max(3.5, node.size * pulse * node.depthScale);
    const color = getNodeColor(node);
    const hubIntensity = degreeIntensity(node);
    const hubGlow = state.cloudMode ? hubIntensity : hubIntensity * 0.65;
    const important = isImportantNodeForLod(node, topHubs);

    ctx.save();
    ctx.globalAlpha = alpha;

    if (important) {
      const glow = ctx.createRadialGradient(node.screenX, node.screenY, 0, node.screenX, node.screenY, radius * (3.1 + hubGlow * 2.8));
      glow.addColorStop(0, hexToRgba(color, 0.28 + hubGlow * 0.32));
      glow.addColorStop(0.42, hexToRgba(color, 0.12 + hubGlow * 0.16));
      glow.addColorStop(1, "rgba(0, 0, 0, 0)");
      ctx.fillStyle = glow;
      ctx.beginPath();
      ctx.arc(node.screenX, node.screenY, radius * (3.1 + hubGlow * 2.8), 0, Math.PI * 2);
      ctx.fill();
    }

    ctx.fillStyle = color;
    ctx.shadowColor = important ? hexToRgba(color, 0.5 + hubGlow * 0.35) : "transparent";
    ctx.shadowBlur = important ? 4 + hubGlow * 18 : 0;
    ctx.beginPath();
    ctx.arc(node.screenX, node.screenY, radius * (1 + hubGlow * 0.1), 0, Math.PI * 2);
    ctx.fill();
    ctx.shadowBlur = 0;

    if (nodeHasMediaMarker(node)) {
      ctx.fillStyle = "rgba(255, 255, 255, 0.92)";
      ctx.beginPath();
      ctx.arc(node.screenX, node.screenY, Math.max(1.8, Math.min(4.5, radius * 0.34)), 0, Math.PI * 2);
      ctx.fill();
    }

    if (hubIntensity > 0.22) {
      ctx.fillStyle = `rgba(255, 255, 255, ${Math.min(0.52, 0.12 + hubIntensity * 0.42)})`;
      ctx.beginPath();
      ctx.arc(node.screenX - radius * 0.22, node.screenY - radius * 0.24, Math.max(1.4, radius * 0.28), 0, Math.PI * 2);
      ctx.fill();
    }

    const focusStroke = node.slug === state.focusSlug;
    const neighborStroke = isLinkedToFocus(node);
    const matchStroke = state.query && state.matchSlugs.has(node.slug);
    ctx.lineWidth = focusStroke ? 3 : neighborStroke || matchStroke ? 2 : 1;
    ctx.strokeStyle = focusStroke
      ? "rgba(255, 198, 111, 0.98)"
      : neighborStroke
        ? "rgba(255, 255, 255, 0.82)"
        : matchStroke
          ? "rgba(143, 124, 255, 0.9)"
          : "rgba(255, 255, 255, 0.25)";
    ctx.stroke();

    if (node.parts_count > 0) {
      ctx.fillStyle = "rgba(255, 198, 111, 0.9)";
      ctx.beginPath();
      ctx.arc(node.screenX + radius * 0.62, node.screenY - radius * 0.62, Math.max(2.6, radius * 0.22), 0, Math.PI * 2);
      ctx.fill();
    }

    if (state.expandingSlugs.has(node.slug)) {
      const dotRadius = Math.max(2.4, radius * 0.16);
      const orbitRadius = radius + 9;
      for (let index = 0; index < 3; index += 1) {
        const angle = now / 220 + index * ((Math.PI * 2) / 3);
        ctx.fillStyle = index === 0 ? "rgba(255, 198, 111, 0.98)" : "rgba(136, 246, 255, 0.86)";
        ctx.beginPath();
        ctx.arc(
          node.screenX + Math.cos(angle) * orbitRadius,
          node.screenY + Math.sin(angle) * orbitRadius,
          dotRadius,
          0,
          Math.PI * 2,
        );
        ctx.fill();
      }
    }

    if (shouldShowLabel(node, topMatches, topHubs)) {
      const labelX = node.screenX + radius + 8;
      const labelY = node.screenY - radius - 6;
      const label = labelForNode(node);
      ctx.font = "700 12px Rajdhani, Inter, sans-serif";
      const labelWidth = ctx.measureText(label).width;
      const rect = { left: labelX - 2, top: labelY - 13, right: labelX + labelWidth + 2, bottom: labelY + 4 };
      const required = node.slug === state.focusSlug || node.slug === state.hoverSlug || isLinkedToFocus(node);
      if (!required && intersectsAny(rect, labelRects)) {
        ctx.restore();
        return;
      }
      labelRects.push(rect);
      visibleLabelSlugs.push(node.slug);
      ctx.fillStyle = "rgba(238, 244, 255, 0.92)";
      ctx.fillText(label, labelX, labelY);
    }

    ctx.restore();
  });
  state.visibleLabelSlugs = visibleLabelSlugs;
}

function render() {
  state.animationHandle = null;
  if (!state.renderDirty && !shouldAnimateContinuously()) {
    return;
  }
  state.renderDirty = false;
  state.animationTick = (state.animationTick + 0.7) % 1000;
  drawBackground();
  tick();
  drawClusterClouds();
  drawEdges();
  drawNodes();
  if (!shouldAnimateContinuously()) {
    state.animationHandle = null;
    return;
  }
  state.animationHandle = requestAnimationFrame(render);
}

function setHover(slug) {
  state.hoverSlug = slug;
  requestRender();
  const node = slug ? state.nodeMap.get(slug) : null;
  const hasDesktopPointer = window.matchMedia?.("(hover: hover) and (pointer: fine)")?.matches;
  const idleHint = hasDesktopPointer
    ? "Drag to rotate. Hover for full names. Click to select."
    : "Drag to rotate. Tap for full names. Long-press a node to select.";
  const emptyHint = hasDesktopPointer
    ? "Search the sky, drag to rotate, hover for details, or click a node to select."
    : "Search the sky, drag to rotate, tap for details, or long-press a node to select.";
  const partText = node?.parts_count ? ` · ${node.parts_count} collapsed parts` : "";
  const reportText = node?.report_count ? ` · ${node.report_count} collapsed reports` : "";
  const linkTypes = node && state.focusSlug && node.slug !== state.focusSlug && isLinkedToFocus(node)
    ? relationshipTypes(state.focusSlug, node.slug)
    : [];
  const relationshipText = linkTypes.length ? ` · relationship: ${linkTypes.join(", ")}` : "";
  hoverLabel.textContent = node
    ? `${node.label} · ${node.category || node.type} · ${node.degree} direct link${node.degree === 1 ? "" : "s"}${partText}${reportText}${relationshipText}`
    : state.focusSlug
      ? idleHint
      : emptyHint;
}

function hideGraphTooltip() {
  graphTooltip.hidden = true;
  graphTooltip.innerHTML = "";
}

function positionGraphTooltip(clientX, clientY) {
  const panelRect = canvas.parentElement.getBoundingClientRect();
  const margin = 12;
  const offset = 16;
  let left = clientX - panelRect.left + offset;
  let top = clientY - panelRect.top + offset;
  const width = graphTooltip.offsetWidth || 280;
  const height = graphTooltip.offsetHeight || 96;
  left = Math.min(panelRect.width - width - margin, Math.max(margin, left));
  top = Math.min(panelRect.height - height - margin, Math.max(margin, top));
  graphTooltip.style.left = `${left}px`;
  graphTooltip.style.top = `${top}px`;
}

function showGraphTooltip(node, clientX, clientY) {
  if (!node) {
    hideGraphTooltip();
    return;
  }
  const linkTypes = state.focusSlug && node.slug !== state.focusSlug && isLinkedToFocus(node)
    ? relationshipTypes(state.focusSlug, node.slug)
    : [];
  graphTooltip.innerHTML = "";
  const title = document.createElement("strong");
  title.textContent = `${node.label} · ${node.category || node.type}`;
  const summary = document.createElement("span");
  summary.textContent = briefSummary(node);
  graphTooltip.append(title, summary);
  if (linkTypes.length) {
    const relationship = document.createElement("small");
    relationship.textContent = `relationship: ${linkTypes.join(", ")}`;
    graphTooltip.appendChild(relationship);
  }
  graphTooltip.hidden = false;
  positionGraphTooltip(clientX, clientY);
}

function hideContextMenu() {
  contextMenu.hidden = true;
  state.menuSlug = null;
}

function showContextMenu(slug, x, y) {
  state.menuSlug = slug || state.focusSlug;
  if (!state.menuSlug) return;
  const margin = 8;
  contextMenu.hidden = false;
  const rect = contextMenu.getBoundingClientRect();
  contextMenu.style.left = `${Math.min(window.innerWidth - rect.width - margin, Math.max(margin, x))}px`;
  contextMenu.style.top = `${Math.min(window.innerHeight - rect.height - margin, Math.max(margin, y))}px`;
}

function parseOperationFields(text) {
  const fields = {};
  String(text || "").split(/\n+/).forEach((line) => {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) return;
    const separator = trimmed.indexOf(":");
    if (separator < 0) return;
    const key = trimmed.slice(0, separator).trim().toLowerCase().replace(/[\s-]+/g, "_");
    const value = trimmed.slice(separator + 1).trim();
    fields[key] = value;
  });
  return fields;
}

function splitList(value) {
  return String(value || "")
    .split(/[,;\n]+/)
    .map((item) => item.trim())
    .filter(Boolean);
}

function mediaDisplayUrl(url) {
  let value = String(url || "").trim();
  if (!value) return "";
  if (value.startsWith("gbrain:files/")) {
    const relativePath = decodeURIComponent(value.slice("gbrain:files/".length));
    return `/media/${relativePath.replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/")}`;
  }
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return encodeURI(value);
  return `/media/${value.replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/")}`;
}

function mediaItemDisplayUrl(item) {
  if (item?.served_url) return item.served_url;
  return mediaDisplayUrl(item?.url || "");
}

function renderSingleMediaPreview(container, item, options = {}) {
  if (!container) return false;
  container.innerHTML = "";
  if (!item) return false;
  const displayUrl = mediaItemDisplayUrl(item);
  if (!displayUrl) return false;
  const canEmbed = Boolean(item.embeddable || item.served_available || item.served_url);
  let element = null;
  if (canEmbed && item.kind === "image") {
    element = document.createElement("img");
    element.src = displayUrl;
    element.alt = item.label || "Node media";
    element.loading = options.eager ? "eager" : "lazy";
  } else if (canEmbed && item.kind === "video") {
    element = document.createElement("video");
    element.src = displayUrl;
    element.controls = true;
    element.playsInline = true;
    element.muted = true;
  } else if (canEmbed && item.kind === "audio") {
    element = document.createElement("audio");
    element.src = displayUrl;
    element.controls = true;
  } else {
    element = document.createElement("a");
    element.href = displayUrl;
    element.target = "_blank";
    element.rel = "noopener noreferrer";
    element.textContent = item.label || item.url || "Open media";
  }
  container.appendChild(element);
  return true;
}

function renderSelectionMediaPreview(items = [], slug = state.focusSlug || "") {
  if (!selectionMediaPreview) return;
  if (selectionMediaSlug) {
    selectionMediaSlug.textContent = slug || "No selection";
    selectionMediaSlug.title = slug || "";
  }
  const first = [...items].find((item) => item && (item.served_url || item.url));
  const rendered = renderSingleMediaPreview(selectionMediaPreview, first, { eager: true });
  selectionMediaPreview.hidden = !rendered;
  selectionMediaPreview.closest(".selection-blueprint")?.classList.toggle("has-media", rendered);
}

async function loadSelectionMediaPreview(slug, loadId) {
  renderSelectionMediaPreview([], slug);
  try {
    const response = await apiGet(`/api/entity-media/${encodeURIComponent(slug)}`);
    if (loadId !== state.entityLoadId || state.focusSlug !== slug) return;
    const media = response.ok ? response.data.media || [] : [];
    rememberNodeMediaStatus(slug, media);
    renderSelectionMediaPreview(media, slug);
  } catch (_error) {
    if (loadId === state.entityLoadId && state.focusSlug === slug) {
      rememberNodeMediaStatus(slug, []);
      renderSelectionMediaPreview([], slug);
    }
  }
}

function cleanMarkdownDestination(value) {
  const text = String(value || "").trim();
  const title = text.match(/^(.+?)\s+"[^"]*"\s*$/);
  return (title ? title[1] : text).trim();
}

function localFileHrefForValue(value) {
  const path = String(value || "").trim().replace(/^`+|`+$/g, "");
  if (!path || !path.startsWith("/") || path.startsWith("//")) return "";
  if (/[\0\r\n]/.test(path) || /^[a-z][a-z0-9+.-]*:/i.test(path)) return "";
  const encodePathPart = (part) => encodeURIComponent(part).replace(/[!'()]/g, (char) => `%${char.charCodeAt(0).toString(16).toUpperCase()}`);
  const encodedPath = path.split("/").map((part, index) => (index === 0 ? "" : encodePathPart(part))).join("/");
  return `file://${encodedPath}`;
}

function appendLocalSourcePathLinks(parent, text) {
  const value = String(text || "");
  const match = value.match(/^(.*?\bLocal source path:\s*)(\/Users\/.+)$/i);
  if (!match) return false;
  appendInlineMarkdown(parent, match[1]);
  const fileHref = localFileHrefForValue(match[2]);
  if (!fileHref) {
    appendInlineMarkdown(parent, match[2]);
    return true;
  }
  const link = document.createElement("a");
  link.setAttribute("href", fileHref);
  link.textContent = match[2].replace(/^`+|`+$/g, "");
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  parent.appendChild(link);
  return true;
}

function appendTextWithBreaks(parent, text) {
  String(text || "").split(/ {2,}\n|\n/).forEach((part, index) => {
    if (index) parent.appendChild(document.createElement("br"));
    if (part) appendLocalFileLinks(parent, part);
  });
}

function localFileLinksAllowed() {
  return ["127.0.0.1", "localhost", "::1"].includes(window.location.hostname);
}

function localFileUrlFromPath(path) {
  const cleaned = String(path || "").trim().replace(/[.;:]+$/, "");
  if (!/^\/(?:Users|Volumes|private|tmp|var\/folders)\//.test(cleaned)) return "";
  return localFileHrefForValue(cleaned);
}

function appendLocalFileLink(parent, path) {
  const href = localFileLinksAllowed() ? localFileUrlFromPath(path) : "";
  if (!href) return false;
  parent.appendChild(document.createTextNode(" "));
  const link = document.createElement("a");
  link.setAttribute("href", href);
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  link.textContent = path;
  parent.appendChild(link);
  return true;
}

function appendLocalFileLinks(parent, text) {
  const value = String(text || "");
  const pattern = /\/(?:Users|Volumes|private|tmp|var\/folders)\/[^\r\n<>"`]+/g;
  let cursor = 0;
  value.replace(pattern, (match, offset) => {
    if (offset > cursor) parent.appendChild(document.createTextNode(value.slice(cursor, offset)));
    parent.appendChild(document.createTextNode(match));
    appendLocalFileLink(parent, match);
    cursor = offset + match.length;
    return match;
  });
  if (cursor < value.length) parent.appendChild(document.createTextNode(value.slice(cursor)));
}

function markdownTitleFromContent(content, fallback) {
  const text = String(content || "");
  const frontmatterTitle = text.match(/^---\s*[\s\S]*?\ntitle:\s*['"]?([^\n'"]+)['"]?\s*\n[\s\S]*?---/);
  if (frontmatterTitle?.[1]?.trim()) return frontmatterTitle[1].trim();
  const heading = text.match(/^#\s+(.+)$/m);
  if (heading?.[1]?.trim()) return heading[1].trim();
  return String(fallback || "Memory Stargraph").trim();
}

function createEntityMarkdownLink(query, label = query) {
  const link = document.createElement("a");
  const entityQuery = String(query || "").trim();
  link.href = `#entity:${encodeURIComponent(entityQuery)}`;
  link.dataset.entityQuery = entityQuery;
  link.textContent = String(label || query || "").trim();
  return link;
}

function appendInlineMarkdown(parent, text) {
  const pattern = /(!?)\[([^\]]+)\]\(([^)]+)\)|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]|\[([^\]\s/]+(?:\/[^\]\s/]+)+)\]|`([^`]+)`|\*\*\*([^*]+?)\*\*\*|\*\*([^*]+?)\*\*\*?|\*([^*]+?)\*|__([^_]+?)__|_([^_]+?)_|~~([^~]+?)~~/g;
  let cursor = 0;
  String(text || "").replace(pattern, (match, bang, label, url, wikiTarget, wikiLabel, bracketSlug, code, boldItalic, bold, italicStar, boldUnderscore, italicUnderscore, strike, offset) => {
    if (offset > cursor) appendTextWithBreaks(parent, text.slice(cursor, offset));
    if (code !== undefined) {
      const codeNode = document.createElement("code");
      codeNode.textContent = code;
      parent.appendChild(codeNode);
      appendLocalFileLink(parent, code);
    } else if (boldItalic !== undefined) {
      const strong = document.createElement("strong");
      const em = document.createElement("em");
      appendInlineMarkdown(em, boldItalic);
      strong.appendChild(em);
      parent.appendChild(strong);
    } else if (bold !== undefined || boldUnderscore !== undefined) {
      const strong = document.createElement("strong");
      appendInlineMarkdown(strong, bold ?? boldUnderscore);
      parent.appendChild(strong);
    } else if (italicStar !== undefined || italicUnderscore !== undefined) {
      const em = document.createElement("em");
      appendInlineMarkdown(em, italicStar ?? italicUnderscore);
      parent.appendChild(em);
    } else if (strike !== undefined) {
      const del = document.createElement("del");
      appendInlineMarkdown(del, strike);
      parent.appendChild(del);
    } else if (wikiTarget !== undefined) {
      parent.appendChild(createEntityMarkdownLink(wikiTarget, wikiLabel || wikiTarget));
    } else if (bracketSlug !== undefined) {
      parent.appendChild(createEntityMarkdownLink(bracketSlug));
    } else if (bang) {
      const image = document.createElement("img");
      image.src = mediaDisplayUrl(cleanMarkdownDestination(url));
      image.alt = label || "Markdown image";
      image.loading = "eager";
      parent.appendChild(image);
    } else {
      const link = document.createElement("a");
      link.href = mediaDisplayUrl(cleanMarkdownDestination(url));
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      link.textContent = label || url;
      parent.appendChild(link);
    }
    cursor = offset + match.length;
    return match;
  });
  if (cursor < String(text || "").length) appendTextWithBreaks(parent, String(text || "").slice(cursor));
}

function appendFieldValueMarkdown(parent, fieldName, value) {
  const strong = document.createElement("strong");
  strong.textContent = `${fieldName}: `;
  parent.appendChild(strong);
  if (fieldName === "source_path") {
    const fileHref = localFileHrefForValue(value);
    if (fileHref) {
      const link = document.createElement("a");
      link.setAttribute("href", fileHref);
      link.textContent = value;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      parent.appendChild(link);
      return;
    }
  }
  appendInlineMarkdown(parent, value);
}

function renderMarkdownView(markdown) {
  modalMarkdown.innerHTML = "";
  const lines = String(markdown || "").split(/\r?\n/);
  let list = null;
  let listType = "";
  let codeBlock = null;
  let table = null;
  let tableRows = [];

  function closeList() {
    list = null;
    listType = "";
  }

  function flushTable() {
    if (!tableRows.length) return;
    table = document.createElement("table");
    const header = document.createElement("thead");
    const headerRow = document.createElement("tr");
    tableRows[0].forEach((cell) => {
      const th = document.createElement("th");
      appendInlineMarkdown(th, cell.trim());
      headerRow.appendChild(th);
    });
    header.appendChild(headerRow);
    table.appendChild(header);
    const body = document.createElement("tbody");
    tableRows.slice(1).forEach((row) => {
      const tr = document.createElement("tr");
      row.forEach((cell) => {
        const td = document.createElement("td");
        appendInlineMarkdown(td, cell.trim());
        tr.appendChild(td);
      });
      body.appendChild(tr);
    });
    table.appendChild(body);
    modalMarkdown.appendChild(table);
    tableRows = [];
    table = null;
  }

  function parseTableRow(line) {
    const trimmed = line.trim();
    if (!trimmed.includes("|")) return null;
    const cells = trimmed.replace(/^\|/, "").replace(/\|$/, "").split("|");
    return cells.length > 1 ? cells : null;
  }

  function isTableSeparator(line) {
    const cells = parseTableRow(line);
    return Boolean(cells && cells.every((cell) => /^:?-{3,}:?$/.test(cell.trim())));
  }

  lines.forEach((line, index) => {
    if (line.trim().startsWith("```")) {
      closeList();
      flushTable();
      if (codeBlock) {
        codeBlock = null;
      } else {
        codeBlock = document.createElement("code");
        const pre = document.createElement("pre");
        pre.appendChild(codeBlock);
        modalMarkdown.appendChild(pre);
      }
      return;
    }
    if (codeBlock) {
      codeBlock.textContent += `${line}\n`;
      return;
    }
    const nextLine = lines[index + 1] || "";
    const tableRow = parseTableRow(line);
    if (tableRow && (tableRows.length || isTableSeparator(nextLine))) {
      closeList();
      if (!isTableSeparator(line)) tableRows.push(tableRow);
      return;
    }
    flushTable();
    if (!line.trim()) {
      closeList();
      return;
    }
    if (/^\s*---+\s*$/.test(line)) {
      closeList();
      modalMarkdown.appendChild(document.createElement("hr"));
      return;
    }
    const heading = line.match(/^(#{1,6})\s+(.+)$/);
    if (heading) {
      closeList();
      const node = document.createElement(`h${Math.min(3, heading[1].length)}`);
      appendInlineMarkdown(node, heading[2]);
      modalMarkdown.appendChild(node);
      return;
    }
    const quote = line.match(/^\s*>\s?(.+)$/);
    if (quote) {
      closeList();
      const blockquote = document.createElement("blockquote");
      appendInlineMarkdown(blockquote, quote[1]);
      modalMarkdown.appendChild(blockquote);
      return;
    }
    const bullet = line.match(/^\s*[-*]\s+(.+)$/);
    if (bullet) {
      if (!list || listType !== "ul") {
        list = document.createElement("ul");
        listType = "ul";
        modalMarkdown.appendChild(list);
      }
      const item = document.createElement("li");
      if (!appendLocalSourcePathLinks(item, bullet[1])) {
        appendInlineMarkdown(item, bullet[1]);
      }
      list.appendChild(item);
      return;
    }
    const ordered = line.match(/^\s*\d+[.)]\s+(.+)$/);
    if (ordered) {
      if (!list || listType !== "ol") {
        list = document.createElement("ol");
        listType = "ol";
        modalMarkdown.appendChild(list);
      }
      const item = document.createElement("li");
      if (!appendLocalSourcePathLinks(item, ordered[1])) {
        appendInlineMarkdown(item, ordered[1]);
      }
      list.appendChild(item);
      return;
    }
    closeList();
    const paragraph = document.createElement("p");
    if (!appendLocalSourcePathLinks(paragraph, line)) {
      appendInlineMarkdown(paragraph, line);
    }
    modalMarkdown.appendChild(paragraph);
  });
  flushTable();

  if (!modalMarkdown.childElementCount) {
    const empty = document.createElement("p");
    empty.textContent = "(Empty page)";
    modalMarkdown.appendChild(empty);
  }
}

function renderViewModalMessage(slug) {
  modalMessage.textContent = "";
  const slugText = document.createElement("span");
  slugText.className = "modal-slug-inline";
  slugText.textContent = `slug: ${slug}`;
  modalMessage.appendChild(slugText);
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "ghost-button compact-button inline-action-button";
  editButton.textContent = "Modify markdown";
  editButton.addEventListener("click", () => {
    void openNodeModal("edit", slug);
  });
  modalMessage.appendChild(editButton);
}

function parseBacklinkItems(rawOutput, selectedSlug) {
  const text = String(rawOutput || "").trim();
  if (!text || text === "(No backlinks)") return [];
  try {
    const parsed = JSON.parse(text);
    if (Array.isArray(parsed)) {
      return parsed
        .filter((item) => item && typeof item === "object")
        .map((item) => ({
          from_slug: String(item.from_slug || "").trim(),
          to_slug: String(item.to_slug || selectedSlug || "").trim(),
          link_type: String(item.link_type || "").trim(),
          link_source: String(item.link_source || "").trim(),
          context: String(item.context || "").trim(),
        }))
        .filter((item) => item.from_slug);
    }
  } catch (_error) {
    return [...text.matchAll(/from_slug["':\s]+([A-Za-z0-9_./-]+)/g)]
      .map((match) => ({ from_slug: match[1], to_slug: selectedSlug || "", link_type: "", link_source: "", context: "" }));
  }
  return [];
}

async function openReverseRelationshipModal(sourceSlug, targetSlug) {
  await openNodeModal("add-link", sourceSlug);
  const targetInput = modalForm.querySelector("#operationTarget");
  if (targetInput) {
    targetInput.value = targetSlug;
    targetInput.focus();
  }
}

async function openRemoveRelationshipModal(sourceSlug, targetSlug, linkType) {
  await openNodeModal("remove-link", sourceSlug);
  const input = modalForm.querySelector("#operationExistingRelationship");
  if (input) {
    input.value = `${targetSlug} | ${linkType || "all"}`;
    input.focus();
  }
}

async function reopenRelationshipsView(slug) {
  await openNodeModal("view-relationships", slug);
}

async function openSelectedRelationshipModal(slug) {
  state.relationshipReturnView = { action: "view-relationships", slug };
  await openNodeModal("add-link", slug);
}

async function refreshSelectedNodeAfterRelationshipMutation(slug, target, action) {
  invalidateRelationshipEndpointCache(slug, target);
  const returnView = state.relationshipReturnView;
  state.relationshipReturnView = null;
  await loadEntity(slug, { source: "system", recordHistory: false });
  if (action === "remove-link") {
    return;
  } else if (returnView?.action && returnView.slug) {
    await openNodeModal(returnView.action, returnView.slug);
  }
}

function currentRelationshipPage(slug) {
  return state.relationshipPages.get(slug) || 0;
}

function clampRelationshipPage(slug, itemCount) {
  const maxPage = Math.max(0, Math.ceil(itemCount / RELATIONSHIP_PAGE_SIZE) - 1);
  const page = Math.max(0, Math.min(maxPage, currentRelationshipPage(slug)));
  state.relationshipPages.set(slug, page);
  return page;
}

function relationshipPageWindow(page, totalPages) {
  const startPage = Math.max(0, Math.min(page - 4, Math.max(0, totalPages - 10)));
  const endPage = Math.min(totalPages, startPage + 10);
  return { startPage, endPage };
}

function renderRelationshipPager(page, totalPages, onPage) {
  const pager = document.createElement("div");
  pager.className = "relationship-pagination";
  const previous = document.createElement("button");
  previous.id = "relationshipPrevPage";
  previous.className = "ghost-button";
  previous.type = "button";
  previous.textContent = "Previous";
  previous.disabled = page <= 0;
  previous.addEventListener("click", () => onPage(page - 1));
  pager.appendChild(previous);

  const { startPage, endPage } = relationshipPageWindow(page, totalPages);
  for (let pageIndex = startPage; pageIndex < endPage; pageIndex += 1) {
    const button = document.createElement("button");
    button.className = "relationship-page-number";
    button.type = "button";
    button.textContent = String(pageIndex + 1);
    button.setAttribute("aria-current", pageIndex === page ? "page" : "false");
    button.disabled = pageIndex === page;
    button.addEventListener("click", () => onPage(pageIndex));
    pager.appendChild(button);
  }

  const count = document.createElement("span");
  count.className = "relationship-page-total";
  count.textContent = `of ${totalPages}`;
  pager.appendChild(count);

  const next = document.createElement("button");
  next.id = "relationshipNextPage";
  next.className = "ghost-button";
  next.type = "button";
  next.textContent = "Next";
  next.disabled = page >= totalPages - 1;
  next.addEventListener("click", () => onPage(page + 1));
  pager.appendChild(next);
  return pager;
}

function labelForSlug(slug) {
  const node = state.nodeMap.get(slug);
  return node?.label || slug;
}

function relationshipRow(sourceSlug, linkType, selectedSlug, options = {}) {
  const row = document.createElement("article");
  row.className = "relationship-wiki-row backlink-item";
  const link = createEntityMarkdownLink(sourceSlug, labelForSlug(sourceSlug));
  link.className = "relationship-source-link backlink-from-link";
  link.setAttribute("data-backlink-slug", sourceSlug);
  link.title = `Open ${sourceSlug}`;
  row.appendChild(link);

  const relation = document.createElement("span");
  relation.className = "relationship-type backlink-relation";
  relation.textContent = linkType || "related to";
  row.appendChild(relation);

  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "relationship-icon-button relationship-add-backlink backlink-link-back";
  addButton.textContent = "+";
  addButton.title = options.addTitle || "Add backlink";
  addButton.setAttribute("aria-label", "Add backlink");
  addButton.addEventListener("click", () => {
    state.relationshipReturnView = { action: "backlinks", slug: selectedSlug };
    void openReverseRelationshipModal(sourceSlug, selectedSlug);
  });
  row.appendChild(addButton);

  if (options.removable) {
    const removeButton = document.createElement("button");
    removeButton.type = "button";
    removeButton.className = "relationship-icon-button relationship-remove";
    removeButton.textContent = "×";
    removeButton.title = "Remove relationship";
    removeButton.setAttribute("aria-label", "Remove relationship");
    removeButton.addEventListener("click", () => {
      void openRemoveRelationshipModal(selectedSlug, sourceSlug, linkType);
    });
    row.appendChild(removeButton);
  }
  return row;
}

function renderRelationshipWikiList(items, selectedSlug, options = {}) {
  modalMarkdown.innerHTML = "";
  const page = clampRelationshipPage(selectedSlug, items.length);
  const start = page * RELATIONSHIP_PAGE_SIZE;
  const visibleItems = items.slice(start, start + RELATIONSHIP_PAGE_SIZE);
  const list = document.createElement("div");
  list.className = "relationship-wiki-list backlink-list";
  visibleItems.forEach((item) => {
    list.appendChild(relationshipRow(item.source_slug, item.link_type, selectedSlug, options));
  });
  if (!items.length) {
    const empty = document.createElement("p");
    empty.textContent = options.emptyText || "No relationships";
    list.appendChild(empty);
  }
  modalMarkdown.appendChild(list);
  if (items.length > RELATIONSHIP_PAGE_SIZE) {
    const totalPages = Math.ceil(items.length / RELATIONSHIP_PAGE_SIZE);
    modalMarkdown.appendChild(renderRelationshipPager(page, totalPages, (nextPage) => {
      state.relationshipPages.set(selectedSlug, nextPage);
      renderRelationshipWikiList(items, selectedSlug, options);
    }));
  }
}

function renderRelationshipsMessage(slug) {
  modalMessage.textContent = "";
  const text = document.createElement("span");
  text.textContent = "Outgoing direct relationships for this node.";
  modalMessage.appendChild(text);
  const addButton = document.createElement("button");
  addButton.type = "button";
  addButton.className = "ghost-button compact-button inline-action-button relationship-add-selected";
  addButton.textContent = "+";
  addButton.title = "Add relationship";
  addButton.setAttribute("aria-label", "Add relationship");
  addButton.addEventListener("click", () => {
    void openSelectedRelationshipModal(slug);
  });
  modalMessage.appendChild(addButton);
}

function renderBacklinksView(rawOutput, selectedSlug) {
  const items = parseBacklinkItems(rawOutput, selectedSlug);
  state.backlinkPages.set(selectedSlug, state.backlinkPages.get(selectedSlug) || 0);
  if (!items.length) {
    renderMarkdownView(rawOutput || "(No backlinks)");
    return;
  }
  const allTargetsAreSelected = items.every((item) => !item.to_slug || item.to_slug === selectedSlug);
  modalMarkdown.innerHTML = "";
  const totalPages = Math.max(1, Math.ceil(items.length / RELATIONSHIP_PAGE_SIZE));
  const currentPage = Math.max(0, Math.min(totalPages - 1, state.backlinkPages.get(selectedSlug) || 0));
  state.backlinkPages.set(selectedSlug, currentPage);
  const visibleItems = items.slice(currentPage * RELATIONSHIP_PAGE_SIZE, (currentPage + 1) * RELATIONSHIP_PAGE_SIZE);
  const list = document.createElement("div");
  list.className = "relationship-wiki-list backlink-list";
  visibleItems.forEach((item) => {
    const row = document.createElement("article");
    row.className = "relationship-wiki-row backlink-item";
    const link = createEntityMarkdownLink(item.from_slug, labelForSlug(item.from_slug));
    link.className = "relationship-source-link backlink-from-link";
    link.setAttribute("data-backlink-slug", item.from_slug);
    link.title = `Open ${item.from_slug}`;
    row.appendChild(link);
    const relation = document.createElement("span");
    relation.className = "relationship-type backlink-relation";
    relation.textContent = item.link_type || "related to";
    row.appendChild(relation);
    const linkBack = document.createElement("button");
    linkBack.type = "button";
    linkBack.className = "relationship-icon-button relationship-add-backlink backlink-link-back";
    linkBack.textContent = "+";
    linkBack.title = "Add relationship";
    linkBack.setAttribute("aria-label", "Add relationship");
    linkBack.addEventListener("click", () => {
      state.relationshipReturnView = { action: "backlinks", slug: selectedSlug };
      void openReverseRelationshipModal(selectedSlug, item.from_slug);
    });
    row.appendChild(linkBack);
    list.appendChild(row);
  });
  modalMarkdown.appendChild(list);
  if (items.length > RELATIONSHIP_PAGE_SIZE) {
    modalMarkdown.appendChild(renderRelationshipPager(currentPage, totalPages, (nextPage) => {
      state.backlinkPages.set(selectedSlug, nextPage);
      renderBacklinksView(rawOutput, selectedSlug);
    }));
  }
}

function parseOutgoingRelationshipItems(rawOutput) {
  return String(rawOutput || "")
    .split(/\r?\n/)
    .map((line) => {
      const match = line.match(/^\s*--(.+?)->\s+(\S+)/);
      if (!match) return null;
      const linkType = match[1].trim().replace(/_/g, " ");
      const targetSlug = match[2].trim();
      if (!targetSlug) return null;
      return {
        source_slug: targetSlug,
        link_type: linkType || "related to",
      };
    })
    .filter(Boolean);
}

function renderOutgoingRelationshipsView(slug, rawOutput = "") {
  const parsedItems = parseOutgoingRelationshipItems(rawOutput);
  const items = parsedItems.length ? parsedItems : outgoingRelationshipOptions(slug).map((option) => ({
    source_slug: option.targetSlug,
    link_type: option.type || "related to",
  }));
  renderRelationshipWikiList(items, slug, { removable: true, emptyText: "No outgoing relationships" });
}

async function loadHistoryForSlug(slug) {
  renderMarkdownView(`Slug: ${slug}\n\nLoading history...`);
  const busyToken = beginBusyOperation(`Loading history for ${slug}`);
  try {
    const response = await apiPost(`/api/entity-history/${encodeURIComponent(slug)}`, {});
    if (!response.ok) {
      modalMessage.textContent = `Unable to load history: ${response.data?.error || response.status}`;
      renderMarkdownView(`Slug: ${slug}\n\n${modalMessage.textContent}`);
      return;
    }
    modalMessage.textContent = "Page history for the selected node.";
    renderMarkdownView(`Slug: ${slug}\n\n${response.data.output || "(No history)"}`);
  } finally {
    endBusyOperation(busyToken);
  }
}

function timelineOutputHasEntries(output) {
  const text = String(output || "").trim();
  if (!text || text === "(No timeline entries)") return false;
  return !/no timeline/i.test(text);
}

function setTimelineBadge(slug, visible) {
  if (!timelineBadge) return;
  timelineBadge.hidden = !visible;
  timelineBadge.dataset.slug = visible ? slug : "";
}

function renderMediaItems(items) {
  modalMedia.innerHTML = "";
  if (!items.length) {
    const empty = document.createElement("span");
    empty.textContent = "No image, video, audio, or PDF links were found in this node's markdown.";
    modalMedia.appendChild(empty);
    return;
  }
  items.forEach((item) => {
    const displayUrl = mediaItemDisplayUrl(item);
    const card = document.createElement("div");
    card.className = "media-card";
    const label = document.createElement("span");
    label.textContent = `${item.kind || "media"} · ${item.label || item.url}`;
    card.appendChild(label);

    const preview = document.createElement("div");
    preview.className = "media-card-preview";
    if (renderSingleMediaPreview(preview, item)) {
      card.appendChild(preview);
    }

    const link = document.createElement("a");
    link.href = displayUrl;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = item.served_url ? "Open media URL" : item.embeddable ? "Open original" : "Reference path";
    card.appendChild(link);
    if (item.served_url && item.served_url !== item.url) {
      const note = document.createElement("span");
      note.textContent = item.served_available
        ? `Served from local media path: ${item.url}`
        : `Expected local media path: ${item.url}. Put the file under a configured media root to enable preview.`;
      card.appendChild(note);
    } else if (!item.embeddable) {
      const note = document.createElement("span");
      note.textContent = "This looks like a local path. Phones can only open it after it is exposed as an HTTP URL or stored in gbrain with a shareable URL.";
      card.appendChild(note);
    }
    modalMedia.appendChild(card);
  });
}

function chatHistoryFor(slug, label, options = {}) {
  const store = state.askYodaChats;
  if (!store.has(slug)) {
    store.set(slug, [
      {
        role: "system",
        content: `Ask Yoda about ${label}. Answers use an agent when available and fall back to GBrain context.`,
        timestamp: chatTimestamp(),
      },
    ]);
  }
  return store.get(slug);
}

function chatTimestamp() {
  return new Date().toLocaleString([], {
    month: "short",
    day: "numeric",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function renderMarkdownInline(text, parent) {
  const value = String(text || "");
  const slugPattern = /\b[A-Za-z0-9._-]+\/[A-Za-z0-9._/-]+\b/g;
  let cursor = 0;
  value.replace(slugPattern, (match, offset) => {
    if (offset > cursor) appendInlineMarkdown(parent, value.slice(cursor, offset));
    const link = createEntityMarkdownLink(match, match);
    link.className = "chat-slug-link";
    link.title = `Open ${match}`;
    parent.appendChild(link);
    cursor = offset + match.length;
    return match;
  });
  if (cursor < value.length) appendInlineMarkdown(parent, value.slice(cursor));
}

function renderAskChat(slug, label, options = {}) {
  const history = chatHistoryFor(slug, label, options);
  modalChatLog.innerHTML = "";
  if (!history.length) {
    const empty = document.createElement("div");
    empty.className = "chat-empty";
    empty.textContent = "Ask a question to start a GBrain conversation for this node.";
    modalChatLog.appendChild(empty);
    return;
  }
  history.forEach((message) => {
    const row = document.createElement("article");
    row.className = `chat-message ${message.role}`;

    const speaker = document.createElement("span");
    speaker.className = "chat-speaker";
    speaker.textContent = message.role === "user" ? "You" : message.role === "assistant" ? "Yoda" : "Context";
    row.appendChild(speaker);

    const timestamp = document.createElement("time");
    timestamp.className = "chat-timestamp";
    timestamp.textContent = message.timestamp || chatTimestamp();
    row.appendChild(timestamp);

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    renderMarkdownInline(message.content, bubble);
    if (message.pending) {
      const dots = document.createElement("span");
      dots.className = "thinking-dots";
      dots.setAttribute("aria-hidden", "true");
      dots.textContent = "...";
      bubble.appendChild(dots);
    }
    row.appendChild(bubble);

    modalChatLog.appendChild(row);
  });
  modalChatLog.scrollTop = modalChatLog.scrollHeight;
}

function yodaLogEntries(slug) {
  const entries = state.askYodaLogs.get(slug) || [];
  return Array.isArray(entries) ? entries : [entries].filter(Boolean);
}

function rememberYodaLog(slug, entry) {
  const entries = yodaLogEntries(slug);
  entries.unshift({ ...entry, captured_at: chatTimestamp() });
  state.askYodaLogs.set(slug, entries.slice(0, 8));
}

function formatYodaDiagnosticEntry(slug, log, index) {
  const diagnostics = log.diagnostics || {};
  const timings = diagnostics.timings || log.timings || {};
  const rows = [
    `Ask Yoda diagnostic log #${index + 1}`,
    `captured_at: ${log.captured_at || "unknown"}`,
    `request_id: ${log.request_id || diagnostics.request_id || "unknown"}`,
    `selected_slug: ${diagnostics.selected_slug || slug}`,
    `depth: ${diagnostics.depth || state.yodaDepth}`,
    `source: ${diagnostics.source || log.source || "unknown"}`,
    `fallback_used: ${Boolean(diagnostics.fallback_used || log.source === "fallback")}`,
    `model_status: ${diagnostics.model_status || "unknown"}`,
    `openclaw_status: ${diagnostics.openclaw_status || "unknown"}`,
    "timing phases:",
    `  prompt_ms: ${timings.prompt_ms ?? "unknown"}`,
    `  model_ms: ${timings.model_ms ?? "unknown"}`,
    `  total_ms: ${timings.total_ms ?? "unknown"}`,
  ];
  if (diagnostics.error_summary) rows.push(`error_summary: ${diagnostics.error_summary}`);
  if (diagnostics.stdout_preview) rows.push(`stdout_preview: ${diagnostics.stdout_preview}`);
  if (diagnostics.stderr_preview) rows.push(`stderr_preview: ${diagnostics.stderr_preview}`);
  return rows.join("\n");
}

function formatYodaDiagnosticLog(slug) {
  const entries = yodaLogEntries(slug);
  if (!entries.length) {
    return [
      "Ask Yoda diagnostic log",
      `selected_slug: ${slug || "unknown"}`,
      "No Ask Yoda diagnostic entries for this node yet.",
    ].join("\n");
  }
  return entries.map((entry, index) => formatYodaDiagnosticEntry(slug, entry, index)).join("\n\n---\n\n");
}

function openYodaLogWindow(slug = state.modalAction?.slug, options = {}) {
  const previous = state.modalAction;
  if (options.returnToAsk || previous?.action === "ask-yoda") {
    state.yodaLogReturn = { action: "ask-yoda", slug: previous?.slug || slug, label: previous?.label || state.nodeMap.get(slug)?.label || slug };
  } else {
    state.yodaLogReturn = null;
  }
  modalKicker.textContent = "Ask Yoda Log";
  modalTitle.textContent = "Ask Yoda Log";
  modalPrimaryButton.textContent = "Close";
  modalCancelButton.hidden = true;
  modalEditor.hidden = true;
  modalChat.hidden = true;
  modalMarkdown.hidden = false;
  modalMarkdown.innerHTML = "";
  const pre = document.createElement("pre");
  pre.className = "yoda-log-window";
  pre.textContent = formatYodaDiagnosticLog(slug);
  modalMarkdown.appendChild(pre);
  operationModal.hidden = false;
  state.modalAction = { action: "yoda-log", slug, label: "Ask Yoda Log" };
}

async function returnFromYodaLog() {
  const target = state.yodaLogReturn;
  state.yodaLogReturn = null;
  if (target?.action === "ask-yoda" && target.slug) {
    await openNodeModal("ask-yoda", target.slug);
    return;
  }
  closeModal();
}

function closeModalFromControl() {
  if (state.modalAction?.action === "yoda-log" && state.yodaLogReturn) {
    void returnFromYodaLog();
    return;
  }
  if (state.modalAction?.action === "tour-plan") {
    closeModal();
    showFloatingPanel(autopilotFlyout, navAutopilotButton);
    return;
  }
  closeModal();
}

function allKnownTags() {
  const tags = new Set();
  state.nodes.forEach((node) => (node.tags || []).forEach((tag) => {
    const value = String(tag || "").trim();
    if (value) tags.add(value);
  }));
  return [...tags].sort((left, right) => left.localeCompare(right));
}

function allKnownRelationshipTypes() {
  const types = new Set();
  state.edgeTypeMap.forEach((values) => (values || []).forEach((type) => {
    const value = String(type || "").trim();
    if (value) types.add(value);
  }));
  return [...types].sort((left, right) => left.localeCompare(right));
}

function nodeOptionsExcept(slug) {
  return state.nodes
    .filter((node) => node.slug !== slug && !isHidden(node.slug))
    .sort((left, right) => (left.label || left.slug).localeCompare(right.label || right.slug));
}

function cachedEntitySearchResults(query, sourceSlug) {
  const normalized = normalizeSearchText(query);
  const terms = normalized.split(/\s+/).filter(Boolean);
  return nodeOptionsExcept(sourceSlug)
    .map((node) => {
      const haystack = normalizeSearchText([node.slug, node.label, node.category, node.type, node.summary].join(" "));
      const exact = node.slug === query || (node.label || "").toLowerCase() === String(query || "").toLowerCase();
      const termMatch = !terms.length || terms.every((term) => haystack.includes(term));
      return { node, score: (exact ? 100 : 0) + (termMatch ? 30 : 0) + (node.degree || 0), source: "cached" };
    })
    .filter((item) => item.score > 0)
    .sort((left, right) => right.score - left.score)
    .slice(0, 30);
}

function slugSelectorState(selectorId) {
  if (!state.slugSelectorSearch.has(selectorId)) {
    state.slugSelectorSearch.set(selectorId, { loading: false, liveOptions: [] });
  }
  return state.slugSelectorSearch.get(selectorId);
}

function mergeSlugSelectorOptions(cachedOptions = [], liveOptions = []) {
  const merged = new Map();
  [...cachedOptions, ...liveOptions].forEach((item) => {
    const node = item?.node || item;
    if (!node?.slug || merged.has(node.slug)) return;
    merged.set(node.slug, { node, source: item.source || "live" });
  });
  return [...merged.values()];
}

function renderSlugSelectorOptions(selector) {
  const { input, list, sourceSlug = "", selectorId } = selector;
  if (!input || !list) return;
  const query = input.value.trim();
  const selectorData = slugSelectorState(selectorId);
  const cachedOptions = query.length >= 2 ? cachedEntitySearchResults(query, sourceSlug) : [];
  const options = mergeSlugSelectorOptions(cachedOptions, selectorData.liveOptions);
  list.innerHTML = "";
  options.forEach(({ node, source }) => {
    const item = document.createElement("option");
    item.value = node.slug;
    item.label = `${node.label || node.slug} · ${node.category || node.type || "entity"} · ${source}`;
    list.appendChild(item);
  });
}

async function runLiveSlugSelectorSearch(selector) {
  const { input, sourceSlug = "", selectorId, statusTarget = modalMessage } = selector;
  const query = input.value.trim();
  const selectorData = slugSelectorState(selectorId);
  if (!query || selectorData.loading) return;
  selectorData.loading = true;
  modalPrimaryButton.disabled = true;
  const busyToken = beginBusyOperation(`Searching targets for ${query}`);
  try {
    const response = await apiGet(`/api/search?q=${encodeURIComponent(query)}`);
    const nodes = response.ok ? response.data.graph?.nodes || [] : [];
    selectorData.liveOptions = nodes
      .filter((node) => node.slug && node.slug !== sourceSlug)
      .map((node) => ({ node, source: "live" }));
    renderSlugSelectorOptions(selector);
    if (statusTarget) statusTarget.textContent = nodes.length ? "Live GBrain search results merged into target list." : "No live GBrain matches found.";
  } finally {
    endBusyOperation(busyToken);
    selectorData.loading = false;
    modalPrimaryButton.disabled = false;
  }
}

function createSlugSelector({
  id,
  label = "Target entity",
  sourceSlug = "",
  value = "",
  placeholder = "Type two characters; press Return for live search",
  onInput = null,
  statusTarget = modalMessage,
}) {
  const input = document.createElement("input");
  input.id = id;
  input.value = value;
  input.setAttribute("list", `${id}Options`);
  input.placeholder = placeholder;
  input.autocomplete = "off";
  appendField(modalForm, label, input);
  const list = document.createElement("datalist");
  list.id = `${id}Options`;
  modalForm.appendChild(list);
  const selector = { selectorId: id, input, list, sourceSlug, statusTarget };
  renderSlugSelectorOptions(selector);
  input.addEventListener("input", () => {
    renderSlugSelectorOptions(selector);
    if (onInput) onInput(input.value);
  });
  input.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      event.preventDefault();
      void runLiveSlugSelectorSearch(selector);
    }
  });
  return { input, list, selector };
}

function mergeRelationshipTargetOptions(cachedOptions = [], liveOptions = []) {
  return mergeSlugSelectorOptions(cachedOptions, liveOptions);
}

function renderRelationshipTargetOptions(sourceSlug, query = "", liveOptions = state.relationshipTargetSearch.liveOptions) {
  const list = modalForm.querySelector("#operationTargetOptions");
  if (!list) return;
  const options = mergeRelationshipTargetOptions(query.length >= 2 ? cachedEntitySearchResults(query, sourceSlug) : [], liveOptions);
  list.innerHTML = "";
  options.forEach(({ node, source }) => {
    const item = document.createElement("option");
    item.value = node.slug;
    item.label = `${node.label || node.slug} · ${node.category || node.type || "entity"} · ${source}`;
    list.appendChild(item);
  });
}

async function runLiveRelationshipTargetSearch(sourceSlug, operationTarget) {
  const selector = {
    selectorId: "operationTarget",
    input: operationTarget,
    list: modalForm.querySelector("#operationTargetOptions"),
    sourceSlug,
    statusTarget: modalMessage,
  };
  const selectorData = slugSelectorState("operationTarget");
  selectorData.liveOptions = state.relationshipTargetSearch.liveOptions;
  await runLiveSlugSelectorSearch(selector);
  state.relationshipTargetSearch.liveOptions = selectorData.liveOptions;
}

function makeDatalist(id, options, valueFor, labelFor) {
  const list = document.createElement("datalist");
  list.id = id;
  options.forEach((option) => {
    const item = document.createElement("option");
    item.value = valueFor(option);
    item.label = labelFor(option);
    list.appendChild(item);
  });
  return list;
}

function appendField(container, labelText, input) {
  const label = document.createElement("label");
  label.className = "operation-field";
  const span = document.createElement("span");
  span.textContent = labelText;
  label.append(span, input);
  container.appendChild(label);
  return input;
}

function renderTimelineEventForm() {
  modalForm.innerHTML = "";
  const today = new Date().toISOString().slice(0, 10);

  const dateInput = document.createElement("input");
  dateInput.id = "operationTimelineDate";
  dateInput.type = "date";
  dateInput.value = today;
  appendField(modalForm, "Date", dateInput);

  const summaryInput = document.createElement("input");
  summaryInput.id = "operationTimelineSummary";
  summaryInput.placeholder = "Short timeline summary";
  summaryInput.autocomplete = "off";
  appendField(modalForm, "Summary", summaryInput);

  const detailInput = document.createElement("textarea");
  detailInput.id = "operationTimelineDetail";
  detailInput.placeholder = "Optional detail";
  appendField(modalForm, "Detail", detailInput);

  const sourceInput = document.createElement("input");
  sourceInput.id = "operationTimelineSource";
  sourceInput.placeholder = "Optional source";
  sourceInput.autocomplete = "off";
  appendField(modalForm, "Source", sourceInput);
}

function renderGraphQueryForm(slug) {
  modalForm.innerHTML = "";
  const node = state.nodeMap.get(slug);

  const typeInput = document.createElement("input");
  typeInput.id = "operationGraphLinkType";
  typeInput.setAttribute("list", "operationGraphLinkTypeOptions");
  typeInput.placeholder = "All relationship types";
  appendField(modalForm, "Relationship type", typeInput);
  modalForm.appendChild(makeDatalist(
    "operationGraphLinkTypeOptions",
    allKnownRelationshipTypes(),
    (type) => type,
    (type) => type,
  ));

  const directionSelect = document.createElement("select");
  directionSelect.id = "operationGraphDirection";
  [
    ["both", "Both directions"],
    ["outgoing", "Outgoing"],
    ["incoming", "Incoming"],
  ].forEach(([value, label]) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = label;
    directionSelect.appendChild(option);
  });
  appendField(modalForm, "Direction", directionSelect);

  const depthSelect = document.createElement("select");
  depthSelect.id = "operationGraphDepth";
  ["1", "2", "3"].forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value;
    depthSelect.appendChild(option);
  });
  depthSelect.value = "1";
  appendField(modalForm, "Depth", depthSelect);

  const summary = document.createElement("p");
  summary.className = "operation-summary";
  const updateSummary = () => {
    const relationship = typeInput.value.trim() || "all relationship types";
    summary.textContent = `${node?.label || slug} · ${directionSelect.selectedOptions[0]?.textContent || "Both directions"} · ${relationship} · depth ${depthSelect.value}`;
  };
  [typeInput, directionSelect, depthSelect].forEach((input) => input.addEventListener("input", updateSummary));
  updateSummary();
  modalForm.appendChild(summary);
}

function renderCheckboxGroup(container, title, values, name) {
  const group = document.createElement("div");
  group.className = "operation-group";
  const label = document.createElement("span");
  label.textContent = title;
  group.appendChild(label);
  if (!values.length) {
    const empty = document.createElement("p");
    empty.className = "operation-empty";
    empty.textContent = "No matching tags";
    group.appendChild(empty);
  } else {
    const grid = document.createElement("div");
    grid.className = "operation-choice-grid";
    values.forEach((value) => {
      const choice = document.createElement("label");
      choice.className = "operation-choice";
      const checkbox = document.createElement("input");
      checkbox.type = "checkbox";
      checkbox.name = name;
      checkbox.value = value;
      const text = document.createElement("span");
      text.textContent = value;
      choice.append(checkbox, text);
      grid.appendChild(choice);
    });
    group.appendChild(grid);
  }
  container.appendChild(group);
}

function renderTagOperationForm(slug) {
  modalForm.innerHTML = "";
  const node = state.nodeMap.get(slug);
  const applied = new Set((node?.tags || []).map((tag) => String(tag || "").trim()).filter(Boolean));
  const addable = allKnownTags().filter((tag) => !applied.has(tag));

  renderCheckboxGroup(modalForm, "Existing tags to add", addable, "addTag");
  const newTag = document.createElement("input");
  newTag.id = "operationNewTag";
  newTag.placeholder = "New tag";
  appendField(modalForm, "New tag", newTag);
  renderCheckboxGroup(modalForm, "Applied tags to remove", [...applied].sort(), "removeTag");
}

function renderAddRelationshipForm(slug) {
  modalForm.innerHTML = "";
  state.relationshipTargetSearch = { loading: false, liveOptions: [] };
  const { input: operationTarget } = createSlugSelector({
    id: "operationTarget",
    label: "Target entity",
    sourceSlug: slug,
    placeholder: "Type two characters; press Return for live search",
    onInput: () => {
      const selectorData = slugSelectorState("operationTarget");
      state.relationshipTargetSearch.liveOptions = selectorData.liveOptions;
      renderRelationshipTargetOptions(slug, operationTarget.value, state.relationshipTargetSearch.liveOptions);
    },
  });

  const typeInput = document.createElement("input");
  typeInput.id = "operationLinkType";
  typeInput.setAttribute("list", "operationLinkTypeOptions");
  typeInput.placeholder = "Search existing type or enter a new one";
  appendField(modalForm, "Relationship type", typeInput);
  modalForm.appendChild(makeDatalist(
    "operationLinkTypeOptions",
    allKnownRelationshipTypes(),
    (type) => type,
    (type) => type,
  ));

  const contextInput = document.createElement("textarea");
  contextInput.id = "operationContext";
  contextInput.placeholder = "Optional context";
  appendField(modalForm, "Context", contextInput);
}

function planDraftSlugs() {
  if (!Array.isArray(state.tour.planDraft)) state.tour.planDraft = [...state.tour.planSlugs];
  return state.tour.planDraft;
}

function renderAutopilotPlanForm() {
  modalForm.innerHTML = "";
  state.slugSelectorSearch.clear();
  const draft = planDraftSlugs();

  const timingRow = document.createElement("div");
  timingRow.className = "plan-timing-row";

  const loopLabel = document.createElement("label");
  loopLabel.className = "plan-toggle";
  const loopInput = document.createElement("input");
  loopInput.id = "plannedLoopToggle";
  loopInput.type = "checkbox";
  loopInput.checked = state.tour.loop;
  loopInput.addEventListener("change", () => {
    state.tour.loop = loopInput.checked;
  });
  loopLabel.append(loopInput, document.createTextNode("Loop"));
  timingRow.appendChild(loopLabel);

  const delayInput = document.createElement("input");
  delayInput.id = "plannedDelaySeconds";
  delayInput.type = "number";
  delayInput.min = "1";
  delayInput.max = "60";
  delayInput.step = "1";
  delayInput.value = String(state.tour.delaySeconds);
  delayInput.addEventListener("input", () => {
    state.tour.delaySeconds = Math.max(1, Math.min(60, Number.parseInt(delayInput.value, 10) || 5));
  });
  const delayField = document.createElement("label");
  delayField.className = "operation-field plan-number-field has-tooltip";
  delayField.dataset.tooltip = "Seconds to wait after the selected node is loaded, or after the 10-second load fallback.";
  delayField.title = delayField.dataset.tooltip;
  delayField.append(Object.assign(document.createElement("span"), { textContent: "Delay" }), delayInput);
  timingRow.appendChild(delayField);

  const daysInput = document.createElement("input");
  daysInput.id = "timelineDaysInput";
  daysInput.type = "number";
  daysInput.min = "0";
  daysInput.max = "7";
  daysInput.step = "1";
  daysInput.value = String(state.timelineDays);
  daysInput.addEventListener("input", () => {
    state.timelineDays = Math.max(0, Math.min(7, Number.parseInt(daysInput.value, 10) || 0));
    updateTimelineLabel();
    applyFilter();
  });
  const daysField = document.createElement("label");
  daysField.className = "operation-field plan-number-field has-tooltip";
  daysField.dataset.tooltip = "Recency filter used when generating an auto plan from visible map nodes. 0 means all time.";
  daysField.title = daysField.dataset.tooltip;
  daysField.append(Object.assign(document.createElement("span"), { textContent: "- Days" }), daysInput);
  timingRow.appendChild(daysField);
  modalForm.appendChild(timingRow);

  const controls = document.createElement("div");
  controls.className = "plan-controls";
  const autoLabel = document.createElement("label");
  autoLabel.className = "plan-toggle";
  const autoInput = document.createElement("input");
  autoInput.id = "autoPlanToggle";
  autoInput.type = "checkbox";
  autoInput.checked = state.tour.useAutoList;
  autoInput.addEventListener("change", () => {
    state.tour.useAutoList = autoInput.checked;
    renderAutopilotPlanForm();
  });
  autoLabel.append(autoInput, document.createTextNode("Auto list"));
  controls.appendChild(autoLabel);

  const tabLabel = document.createElement("span");
  tabLabel.className = "plan-tab-label";
  tabLabel.textContent = state.tour.useAutoList ? "Auto generated list" : "Manual plan";
  controls.appendChild(tabLabel);
  modalForm.appendChild(controls);

  if (state.tour.useAutoList) {
    const autoList = document.createElement("div");
    autoList.className = "plan-list plan-list-readonly";
    const autoSlugs = autoPlanSlugs();
    if (!autoSlugs.length) {
      const empty = document.createElement("p");
      empty.className = "operation-empty";
      empty.textContent = "No visible nodes available for the auto list.";
      autoList.appendChild(empty);
    }
    autoSlugs.forEach((slug, index) => {
      const row = document.createElement("div");
      row.className = "plan-row plan-row-readonly";
      const indexLabel = document.createElement("span");
      indexLabel.className = "plan-index";
      indexLabel.textContent = String(index + 1);
      const link = createEntityMarkdownLink(slug, labelForSlug(slug));
      link.className = "relationship-source-link";
      row.append(indexLabel, link);
      autoList.appendChild(row);
    });
    modalForm.appendChild(autoList);
    return;
  }

  const actionRow = document.createElement("div");
  actionRow.className = "plan-action-row";

  const fillButton = document.createElement("button");
  fillButton.id = "fillPlanButton";
  fillButton.className = "ghost-button compact-button has-tooltip";
  fillButton.type = "button";
  fillButton.textContent = "Fill";
  fillButton.dataset.tooltip = "Click to erase current autopilot list and generate a new one based on nodes visible in the map.";
  fillButton.title = fillButton.dataset.tooltip;
  fillButton.addEventListener("click", () => {
    state.tour.fillPlanConfirming = true;
    state.tour.clearPlanConfirming = false;
    renderAutopilotPlanForm();
  });
  actionRow.appendChild(fillButton);

  const addCurrent = document.createElement("button");
  addCurrent.id = "addCurrentPlanNodeButton";
  addCurrent.className = "ghost-button compact-button";
  addCurrent.type = "button";
  addCurrent.textContent = "Add";
  addCurrent.addEventListener("click", () => {
    draft.push("");
    renderAutopilotPlanForm();
  });
  actionRow.appendChild(addCurrent);

  const clearButton = document.createElement("button");
  clearButton.id = "clearPlanButton";
  clearButton.className = "ghost-button compact-button";
  clearButton.type = "button";
  clearButton.textContent = "Clear";
  clearButton.addEventListener("click", () => {
    state.tour.clearPlanConfirming = true;
    state.tour.fillPlanConfirming = false;
    renderAutopilotPlanForm();
  });
  actionRow.appendChild(clearButton);
  modalForm.appendChild(actionRow);

  if (state.tour.fillPlanConfirming || state.tour.clearPlanConfirming) {
    const isClearConfirm = state.tour.clearPlanConfirming;
    const confirmPanel = document.createElement("section");
    confirmPanel.className = "plan-confirm-dialog";
    confirmPanel.setAttribute("role", "alertdialog");
    confirmPanel.setAttribute("aria-labelledby", "planConfirmTitle");
    confirmPanel.setAttribute("aria-describedby", "planConfirmMessage");

    const title = document.createElement("h4");
    title.id = "planConfirmTitle";
    title.textContent = "Warning";
    const message = document.createElement("p");
    message.id = "planConfirmMessage";
    message.textContent = isClearConfirm
      ? "This will fully erase current autopilot plan, are you sure?"
      : "This will fully erase current autopilot plan and generate a new one based on nodes visible in the map, are you sure?";

    const actions = document.createElement("div");
    actions.className = "plan-confirm-actions";
    const cancel = document.createElement("button");
    cancel.type = "button";
    cancel.className = "ghost-button compact-button";
    cancel.textContent = "Cancel";
    cancel.addEventListener("click", () => {
      state.tour.fillPlanConfirming = false;
      state.tour.clearPlanConfirming = false;
      renderAutopilotPlanForm();
    });
    const confirm = document.createElement("button");
    confirm.type = "button";
    confirm.className = "ghost-button compact-button primary";
    confirm.textContent = isClearConfirm ? "Clear" : "Generate";
    confirm.addEventListener("click", () => {
      if (isClearConfirm) {
        draft.splice(0, draft.length);
      } else {
        draft.splice(0, draft.length, ...autoPlanSlugs());
      }
      state.tour.fillPlanConfirming = false;
      state.tour.clearPlanConfirming = false;
      renderAutopilotPlanForm();
    });
    actions.append(cancel, confirm);
    confirmPanel.append(title, message, actions);
    modalForm.appendChild(confirmPanel);
  }

  const list = document.createElement("div");
  list.className = "plan-list";
  list.dataset.planRows = "true";
  if (!draft.length) {
    const empty = document.createElement("p");
    empty.className = "operation-empty";
    empty.textContent = "No planned nodes. Fill or Add.";
    list.appendChild(empty);
  }
  draft.forEach((slug, index) => {
    const row = document.createElement("div");
    row.className = "plan-row";
    if (slug && !state.tour.partialTimeoutSlugs.has(slug) && !isValidPlanSlug(slug)) {
      row.classList.add("is-invalid");
      row.title = "Node invalid, please check!";
    }
    row.draggable = true;
    row.dataset.index = String(index);
    const handle = document.createElement("span");
    handle.className = "plan-drag-handle";
    handle.textContent = "⋮⋮";
    row.appendChild(handle);
    modalForm.appendChild(row);
    const { input } = createSlugSelector({
      id: `planSlug${index}`,
      label: `${index + 1}`,
      value: slug,
      placeholder: "Type two characters; press Return for live search",
      onInput: (value) => {
        const nextSlug = value.trim();
        if (draft[index] && draft[index] !== nextSlug) {
          state.tour.partialTimeoutSlugs.delete(draft[index]);
        }
        draft[index] = nextSlug;
      },
    });
    row.appendChild(input.closest(".operation-field"));
    row.appendChild(document.getElementById(`planSlug${index}Options`));
    const addButton = document.createElement("button");
    addButton.className = "relationship-icon-button plan-insert-button";
    addButton.type = "button";
    addButton.textContent = "+";
    addButton.title = "Insert blank entry below this row";
    addButton.setAttribute("aria-label", "Insert blank plan entry");
    addButton.addEventListener("click", () => {
      draft.splice(index + 1, 0, "");
      renderAutopilotPlanForm();
    });
    const removeButton = document.createElement("button");
    removeButton.className = "relationship-icon-button plan-remove-button";
    removeButton.type = "button";
    removeButton.textContent = "-";
    removeButton.title = "Remove this plan row";
    removeButton.setAttribute("aria-label", "Remove node from plan");
    removeButton.addEventListener("click", () => {
      draft.splice(index, 1);
      renderAutopilotPlanForm();
    });
    row.append(addButton, removeButton);
    row.addEventListener("dragstart", (event) => {
      event.dataTransfer?.setData("text/plain", String(index));
    });
    row.addEventListener("dragover", (event) => event.preventDefault());
    row.addEventListener("drop", (event) => {
      event.preventDefault();
      const from = Number.parseInt(event.dataTransfer?.getData("text/plain") || "-1", 10);
      if (from < 0 || from === index) return;
      const [moved] = draft.splice(from, 1);
      draft.splice(index, 0, moved);
      renderAutopilotPlanForm();
    });
    list.appendChild(row);
  });

  modalForm.appendChild(list);
}

function renderNewNodeForm() {
  modalForm.innerHTML = "";
  const nameInput = document.createElement("input");
  nameInput.id = "operationNodeName";
  nameInput.placeholder = "Node name";
  nameInput.autocomplete = "off";
  appendField(modalForm, "Name", nameInput);

  const descriptionInput = document.createElement("textarea");
  descriptionInput.id = "operationNodeDescription";
  descriptionInput.placeholder = "Short description";
  appendField(modalForm, "Description", descriptionInput);

  const categoryInput = document.createElement("input");
  categoryInput.id = "operationNodeCategory";
  categoryInput.setAttribute("list", "operationNodeCategoryOptions");
  categoryInput.placeholder = "Select or type a category";
  appendField(modalForm, "Category", categoryInput);
  modalForm.appendChild(makeDatalist(
    "operationNodeCategoryOptions",
    [...new Set((state.graph?.nodes || []).map((node) => node.category || node.type).filter(Boolean))].sort(),
    (category) => category,
    (category) => category,
  ));
}

function existingRelationshipOptions(slug) {
  const node = state.nodeMap.get(slug);
  if (!node) return [];
  const options = [];
  (node.links || []).forEach((targetSlug) => {
    const target = state.nodeMap.get(targetSlug);
    const types = relationshipTypes(slug, targetSlug);
    if (types.length) {
      types.forEach((type) => options.push({ targetSlug, type, label: `${target?.label || targetSlug} · ${type}` }));
    } else {
      options.push({ targetSlug, type: "", label: `${target?.label || targetSlug} · all relationship types` });
    }
  });
  return options.sort((left, right) => left.label.localeCompare(right.label));
}

function outgoingRelationshipOptions(slug) {
  const options = [];
  const seen = new Set();
  state.edges.filter((edge) => edge.source.slug === slug && edge.target.slug !== slug).forEach((edge) => {
    const targetSlug = edge.target.slug;
    const target = state.nodeMap.get(targetSlug);
    const types = edge.link_types?.length ? edge.link_types : relationshipTypes(slug, targetSlug);
    (types.length ? types : [""]).forEach((type) => {
      const key = `${targetSlug} | ${type}`;
      if (seen.has(key)) return;
      seen.add(key);
      options.push({ targetSlug, type, label: `${target?.label || targetSlug} · ${type || "all relationship types"}` });
    });
  });
  return options.sort((left, right) => left.label.localeCompare(right.label));
}

function renderRemoveRelationshipForm(slug) {
  modalForm.innerHTML = "";
  const input = document.createElement("input");
  input.id = "operationExistingRelationship";
  input.setAttribute("list", "operationExistingRelationshipOptions");
  input.placeholder = "Search existing relationship";
  appendField(modalForm, "Relationship to remove", input);
  const list = document.createElement("datalist");
  list.id = "operationExistingRelationshipOptions";
  existingRelationshipOptions(slug).forEach((option) => {
    const item = document.createElement("option");
    item.value = `${option.targetSlug} | ${option.type || "all"}`;
    item.label = option.label;
    list.appendChild(item);
  });
  modalForm.appendChild(list);
}

function checkedValues(name) {
  return [...modalForm.querySelectorAll(`input[name="${name}"]:checked`)].map((input) => input.value);
}

function closeModal() {
  operationModal.hidden = true;
  operationModal.classList.remove("compact-modal");
  state.modalAction = null;
  state.yodaLogReturn = null;
  modalConfirmInput.value = "";
  modalConfirmInput.hidden = true;
  modalConfirmInput.dataset.expected = "";
  modalFileInput.value = "";
  modalFileInput.hidden = true;
  modalFileInput.disabled = false;
  modalForm.hidden = true;
  modalForm.innerHTML = "";
  modalEditor.value = "";
  modalEditor.readOnly = false;
  modalEditor.disabled = false;
  modalEditor.hidden = false;
  modalAttach.hidden = true;
  modalAttachDescription.value = "";
  modalAttachDescription.disabled = false;
  modalMarkdown.hidden = true;
  modalMarkdown.innerHTML = "";
  modalMedia.hidden = true;
  modalMedia.innerHTML = "";
  modalChat.hidden = true;
  modalChatLog.innerHTML = "";
  modalChatInput.value = "";
  modalChatInput.disabled = false;
  modalYodaDepthWrap.hidden = true;
  if (modalYodaLogButton) modalYodaLogButton.disabled = false;
  modalPrimaryButton.hidden = false;
  modalPrimaryButton.disabled = false;
  modalCancelButton.hidden = false;
  modalCancelButton.disabled = false;
  modalCancelButton.textContent = "Cancel";
}

async function openNodeModal(action, slug = state.focusSlug) {
  hideContextMenu();
  if (!["new-node", "tour-plan"].includes(action) && !slug) return;
  const node = state.nodeMap.get(slug);
  const label = node?.label || slug;
  state.modalAction = { action, slug, label };
  operationModal.classList.toggle("compact-modal", ["add-link", "remove-link", "tags"].includes(action));
  modalTitle.textContent = label;
  modalConfirmInput.value = "";
  modalConfirmInput.hidden = true;
  modalConfirmInput.dataset.expected = "";
  modalFileInput.value = "";
  modalFileInput.hidden = true;
  modalFileInput.disabled = false;
  modalForm.hidden = true;
  modalForm.innerHTML = "";
  modalEditor.value = "";
  modalEditor.disabled = false;
  modalMessage.textContent = "";
  modalEditor.hidden = false;
  modalAttach.hidden = true;
  modalAttachDescription.value = "";
  modalAttachDescription.disabled = false;
  modalMarkdown.hidden = true;
  modalMarkdown.innerHTML = "";
  modalMedia.hidden = true;
  modalMedia.innerHTML = "";
  modalChat.hidden = true;
  modalChatLog.innerHTML = "";
  modalChatInput.value = "";
  modalChatInput.disabled = false;
  modalYodaDepthWrap.hidden = true;

  if (action === "new-node") {
    state.modalAction = { action, slug: "", label: "New Node" };
    modalTitle.textContent = "New Node";
    modalKicker.textContent = "Create gbrain node";
    modalPrimaryButton.textContent = "Create node";
    modalMessage.textContent = "Create a new gbrain page from a name, description, and category.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderNewNodeForm();
    operationModal.hidden = false;
    modalForm.querySelector("#operationNodeName")?.focus();
    return;
  }

  if (action === "tour-plan") {
    state.modalAction = { action, slug: state.focusSlug || "", label: "Autopilot Plan" };
    state.tour.planDraft = [...state.tour.planSlugs];
    modalTitle.textContent = "Autopilot Plan";
    modalKicker.textContent = "Autopilot";
    modalPrimaryButton.textContent = "Play";
    modalCancelButton.textContent = "Cancel";
    modalMessage.textContent = "";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    operationModal.classList.add("compact-modal");
    renderAutopilotPlanForm();
    operationModal.hidden = false;
    modalForm.querySelector("input")?.focus();
    return;
  }

  modalPrimaryButton.hidden = false;
  modalPrimaryButton.disabled = false;
  modalCancelButton.hidden = false;
  modalCancelButton.textContent = "Cancel";
  modalPrimaryButton.classList.remove("danger");

  if (action === "view" || action === "edit") {
    modalKicker.textContent = action === "view" ? "View" : "Modify gbrain page";
    modalPrimaryButton.textContent = action === "view" ? "Close" : "Save";
    modalEditor.readOnly = action === "view";
    modalCancelButton.hidden = action === "view";
    if (action === "view") {
      renderViewModalMessage(slug);
    } else {
      modalMessage.textContent = "Editing writes this markdown back with `gbrain put`, then refreshes the graph.";
    }
    modalEditor.hidden = action === "view";
    modalMarkdown.hidden = action !== "view";
    operationModal.hidden = false;
    const busyToken = action === "view" ? beginBusyOperation("Loading view") : null;
    try {
      const response = await apiGet(`/api/entity-raw/${encodeURIComponent(slug)}`);
      const content = response.ok ? response.data.content : `Unable to load page: ${response.data?.error || response.status}`;
      if (action === "view") {
        const viewTitle = markdownTitleFromContent(content, label);
        document.title = "Memory Stargraph";
        modalTitle.textContent = viewTitle;
        renderMarkdownView(content);
      } else {
        modalEditor.value = content;
      }
    } finally {
      if (busyToken) endBusyOperation(busyToken);
    }
    return;
  }

  if (action === "media") {
    modalKicker.textContent = "Node media";
    modalPrimaryButton.textContent = "Close";
    modalCancelButton.hidden = true;
    modalEditor.hidden = true;
    modalMedia.hidden = false;
    modalMessage.textContent = "Images, video, audio, and PDFs are detected from this node's gbrain markdown/frontmatter. Hosted or locally served media opens on desktop and mobile.";
    operationModal.hidden = false;
    renderMediaItems([]);
    const busyToken = beginBusyOperation("Loading media");
    try {
      const response = await apiGet(`/api/entity-media/${encodeURIComponent(slug)}`);
      if (!response.ok) {
        modalMessage.textContent = `Unable to load media: ${response.data?.error || response.status}`;
        return;
      }
      rememberNodeMediaStatus(slug, response.data.media || []);
      renderMediaItems(response.data.media || []);
    } finally {
      endBusyOperation(busyToken);
    }
    return;
  }

  if (action === "delete") {
    modalKicker.textContent = "Delete gbrain page";
    modalPrimaryButton.textContent = "Delete";
    modalPrimaryButton.classList.add("danger");
    modalEditor.hidden = true;
    modalConfirmInput.hidden = false;
    modalConfirmInput.dataset.expected = label;
    modalConfirmInput.placeholder = label;
    modalPrimaryButton.disabled = true;
    modalMessage.textContent = `Type the full node name exactly to delete this page from gbrain: ${label}`;
    operationModal.hidden = false;
    modalConfirmInput.focus();
    return;
  }

  if (action === "add-link") {
    modalKicker.textContent = "Add typed relationship";
    modalPrimaryButton.textContent = "Add relationship";
    modalMessage.textContent = "Search/select the target entity and relationship type, or type a new relationship type.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderAddRelationshipForm(slug);
    operationModal.hidden = false;
    modalForm.querySelector("#operationTarget")?.focus();
    return;
  }

  if (action === "ask-yoda") {
    modalKicker.textContent = "Ask Yoda";
    modalPrimaryButton.textContent = "Send";
    modalMessage.textContent = "Chat with an agent using this node as context.";
    modalEditor.hidden = true;
    modalChat.hidden = false;
    modalYodaDepthWrap.hidden = false;
    if (modalYodaLogButton) modalYodaLogButton.disabled = false;
    syncYodaDepthControl();
    modalChatInput.value = "";
    renderAskChat(slug, label, { mode: "yoda" });
    operationModal.hidden = false;
    modalChatInput.focus();
    return;
  }

  if (action === "backlinks") {
    modalKicker.textContent = "Backlinks";
    modalPrimaryButton.textContent = "Close";
    modalCancelButton.hidden = true;
    modalEditor.readOnly = true;
    modalMessage.textContent = "Loading backlinks...";
    modalEditor.hidden = true;
    modalMarkdown.hidden = false;
    renderMarkdownView("Loading backlinks...");
    operationModal.hidden = false;
    state.modalAction = { action: "result", slug, label };
    const busyToken = beginBusyOperation("Loading backlinks");
    try {
      const response = await apiPost(`/api/entity-backlinks/${encodeURIComponent(slug)}`, {});
      if (!response.ok) {
        modalMessage.textContent = `Unable to load backlinks: ${response.data?.error || response.status}`;
        renderMarkdownView(modalMessage.textContent);
        return;
      }
      modalMessage.textContent = "Incoming gbrain links for this node.";
      renderBacklinksView(response.data.output || "(No backlinks)", slug);
    } finally {
      endBusyOperation(busyToken);
    }
    return;
  }

  if (action === "graph-query") {
    modalKicker.textContent = "Query";
    modalPrimaryButton.textContent = "Run graph query";
    modalMessage.textContent = "Choose traversal settings. Leave relationship type blank to include all types.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderGraphQueryForm(slug);
    operationModal.hidden = false;
    modalForm.querySelector("#operationGraphLinkType")?.focus();
    return;
  }

  if (action === "view-relationships") {
    modalKicker.textContent = "Relationships";
    modalPrimaryButton.textContent = "Close";
    modalCancelButton.hidden = true;
    modalEditor.hidden = true;
    modalMarkdown.hidden = false;
    renderRelationshipsMessage(slug);
    operationModal.hidden = false;
    state.modalAction = { action: "result", slug, label };
    renderMarkdownView("Loading outgoing relationships...");
    const busyToken = beginBusyOperation("Loading relationships");
    try {
      const response = await apiPost(`/api/entity-graph-query/${encodeURIComponent(slug)}`, {
        direction: "outgoing",
        depth: "1",
      });
      if (!response.ok) {
        modalMessage.textContent = `Unable to load relationships: ${response.data?.error || response.status}`;
        renderOutgoingRelationshipsView(slug);
        return;
      }
      renderOutgoingRelationshipsView(slug, response.data.output || "");
    } finally {
      endBusyOperation(busyToken);
    }
    return;
  }

  if (action === "history") {
    modalKicker.textContent = "History";
    modalPrimaryButton.textContent = "Close";
    modalCancelButton.hidden = true;
    modalMessage.textContent = "Loading page history for this node.";
    modalEditor.hidden = true;
    modalMarkdown.hidden = false;
    operationModal.hidden = false;
    state.modalAction = { action: "result", slug, label };
    await loadHistoryForSlug(slug);
    return;
  }

  if (action === "timeline-view") {
    modalKicker.textContent = "Timeline";
    modalPrimaryButton.textContent = "Add timeline event";
    modalCancelButton.textContent = "Close";
    modalMessage.textContent = "Read-only gbrain timeline. Add a dated event here when something new should be recorded.";
    modalEditor.hidden = true;
    modalMarkdown.hidden = false;
    operationModal.hidden = false;
    renderMarkdownView("Loading timeline...");
    const busyToken = beginBusyOperation("Loading timeline");
    try {
      const response = await apiGet(`/api/entity-timeline-view/${encodeURIComponent(slug)}`);
      if (!response.ok) {
        modalMessage.textContent = `Unable to load timeline: ${response.data?.error || response.status}`;
        renderMarkdownView("");
        return;
      }
      renderMarkdownView(response.data.output || "(No timeline entries)");
    } finally {
      endBusyOperation(busyToken);
    }
    return;
  }

  if (action === "remove-link") {
    modalKicker.textContent = "Remove relationship";
    modalPrimaryButton.textContent = "Remove relationship";
    modalMessage.textContent = "Only existing relationships for this node can be removed.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderRemoveRelationshipForm(slug);
    operationModal.hidden = false;
    modalForm.querySelector("#operationExistingRelationship")?.focus();
    return;
  }

  if (action === "tags") {
    modalKicker.textContent = "Edit tags";
    modalPrimaryButton.textContent = "Save tags";
    modalMessage.textContent = "Select existing tags to add, enter a new tag, or remove tags already applied to this entity.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderTagOperationForm(slug);
    operationModal.hidden = false;
    modalForm.querySelector("#operationNewTag")?.focus();
    return;
  }

  if (action === "timeline") {
    modalKicker.textContent = "Add timeline event";
    modalPrimaryButton.textContent = "Add event";
    modalMessage.textContent = "Adds a dated timeline entry to this gbrain page.";
    modalEditor.hidden = true;
    modalForm.hidden = false;
    renderTimelineEventForm();
    operationModal.hidden = false;
    modalForm.querySelector("#operationTimelineDate")?.focus();
    return;
  }

  if (action === "attach-file") {
    modalKicker.textContent = "Attach file";
    modalPrimaryButton.textContent = "Attach file";
    modalMessage.textContent = "Choose a file and optionally describe it for the markdown caption or alt text.";
    modalFileInput.hidden = false;
    modalEditor.hidden = true;
    modalAttach.hidden = false;
    modalAttachStatus.textContent = "Choose a file from Finder. Supported media is copied into the web media root, attached to gbrain, and added to markdown using the description above.";
    operationModal.hidden = false;
    modalFileInput.focus();
    return;
  }

  if (action === "embed") {
    modalKicker.textContent = "Refresh embedding";
    modalPrimaryButton.textContent = "Refresh embedding";
    modalMessage.textContent = "Runs `gbrain embed` for this node when the active gbrain backend supports it.";
    modalEditor.hidden = true;
    operationModal.hidden = false;
  }
}

async function copySlug(slug = state.focusSlug) {
  hideContextMenu();
  if (!slug) return;
  try {
    await navigator.clipboard.writeText(slug);
    setHover(slug);
    hoverLabel.textContent = `Copied slug: ${slug}`;
  } catch {
    hoverLabel.textContent = `Slug: ${slug}`;
  }
}

async function hideNode(slug = state.focusSlug) {
  hideContextMenu();
  if (!slug) return;
  const response = await apiPost(`/api/entity-hide/${encodeURIComponent(slug)}`);
  if (!response.ok) {
    hoverLabel.textContent = response.data?.error || `Unable to hide ${slug}`;
    return;
  }
  state.hiddenSlugs = new Set(response.data.hidden || []);
  updateMetrics(state.graph);
  updateCategoryLegend(state.graph);
  updateFilterOptions(state.graph);
  updateHiddenList();
  applyFilter();
  if (state.focusSlug === slug) {
    await focusFallbackNode();
  }
  setHover(null);
}

async function showNode(slug) {
  const response = await apiPost(`/api/entity-show/${encodeURIComponent(slug)}`);
  if (!response.ok) {
    hoverLabel.textContent = response.data?.error || `Unable to show ${slug}`;
    return;
  }
  state.hiddenSlugs = new Set(response.data.hidden || []);
  updateMetrics(state.graph);
  updateCategoryLegend(state.graph);
  updateFilterOptions(state.graph);
  updateHiddenList();
  applyFilter();
  if (!state.focusSlug) {
    await loadEntity(slug);
  }
  setHover(null);
}

function applyGraphPayload(graph, preferredFocus = state.focusSlug) {
  state.graph = graph;
  resizeCanvas();
  buildRuntimeGraph(graph);
  updateUiVersion(graph);
  updateMetrics(graph);
  updateSource(graph.source);
  updateCategoryLegend(graph);
  updateFilterOptions(graph);
  updateHiddenList();
  updateLastRefresh(graph.source);
  const hasPreviousFocus = preferredFocus && graph.nodes.some((node) => node.slug === preferredFocus && !isHidden(node.slug));
  state.focusSlug = hasPreviousFocus
    ? preferredFocus
    : [...graph.nodes].filter((node) => !isHidden(node.slug)).sort((left, right) => (right.degree || 0) - (left.degree || 0))[0]?.slug || null;
  updateAskYodaButtons();
  applyFilter();
  setHover(null);
}

async function ensureExpanded(slug) {
  const node = state.nodeMap.get(slug);
  if (!node || node.expanded || state.expandingSlugs.has(slug)) {
    return;
  }
  state.expandingSlugs.add(slug);
  hoverLabel.textContent = `Loading relationships for ${node.label || slug}...`;
  try {
    const response = await apiPost(`/api/entity-expand/${encodeURIComponent(slug)}`);
    if (!response.ok) {
      hoverLabel.textContent = response.data?.error || `Unable to expand ${slug}`;
      return;
    }
    applyGraphPayload(response.data.graph, slug);
  } finally {
    state.expandingSlugs.delete(slug);
  }
}

async function runModalPrimaryAction() {
  if (!state.modalAction) {
    closeModal();
    return;
  }
  const { action, slug, label } = state.modalAction;
  if (action === "view" || action === "media" || action === "result") {
    closeModal();
    return;
  }
  if (action === "yoda-log") {
    await returnFromYodaLog();
    return;
  }
  if (action === "tour-plan") {
    state.tour.planSlugs = planDraftSlugs().map((slug) => String(slug || "").trim()).filter(Boolean);
    persistPlannedPlayback();
    state.tour.planDraft = null;
    state.tour.slugs = state.tour.useAutoList ? autoPlanSlugs() : plannedPlaybackSlugs();
    state.tour.mode = state.tour.useAutoList ? "auto" : state.tour.slugs.length ? "planned" : "auto";
    state.tour.index = 0;
    updateTourControls();
    closeModal();
    showFloatingPanel(autopilotFlyout, navAutopilotButton);
    await startPlannedPlayback();
    return;
  }
  if (action === "timeline-view") {
    await openNodeModal("timeline", slug);
    return;
  }
  if (action === "delete" && modalConfirmInput.value !== label) {
    modalMessage.textContent = `Type the full node name exactly before deleting: ${label}`;
    modalConfirmInput.focus();
    return;
  }
  modalPrimaryButton.disabled = true;
  modalCancelButton.disabled = true;
  const primaryButtonText = modalPrimaryButton.textContent;
  let pendingAskHistory = null;
  const busyLabels = {
    edit: "Saving page",
    "new-node": "Creating node",
    delete: "Deleting node",
    "add-link": "Saving relationship",
    "remove-link": "Removing relationship",
    tags: "Updating tags",
    timeline: "Updating timeline",
    "graph-query": "Running graph query",
    "attach-file": "Attaching file",
    embed: "Refreshing embedding",
  };
  const busyToken = beginBusyOperation(busyLabels[action] || "Working");
  if (action === "attach-file") {
    modalPrimaryButton.textContent = "Uploading...";
    modalFileInput.disabled = true;
    modalEditor.disabled = true;
    modalAttachDescription.disabled = true;
  }
  try {
    if (action === "edit") {
      const response = await apiPost(`/api/entity-save/${encodeURIComponent(slug)}`, { content: modalEditor.value });
      if (!response.ok) throw new Error(response.data?.error || `Save failed with ${response.status}`);
      closeModal();
      await fetchGraph("/api/graph", { preserveFocus: true, preferredFocus: slug });
      return;
    }
    if (action === "new-node") {
      const name = modalForm.querySelector("#operationNodeName")?.value.trim() || "";
      const description = modalForm.querySelector("#operationNodeDescription")?.value.trim() || "";
      const category = modalForm.querySelector("#operationNodeCategory")?.value.trim() || "";
      if (!name || !category) {
        throw new Error("Name and category are required.");
      }
      const response = await apiPost("/api/entity-create", { name, description, category });
      if (!response.ok) throw new Error(response.data?.error || `Create node failed with ${response.status}`);
      closeModal();
      applyGraphPayload(response.data.graph, response.data.slug);
      await loadEntity(response.data.slug, { source: "system" });
      return;
    }
    if (action === "delete") {
      const response = await apiPost(`/api/entity-delete/${encodeURIComponent(slug)}`, { confirm_label: modalConfirmInput.value });
      if (!response.ok) throw new Error(response.data?.error || `Delete failed with ${response.status}`);
      closeModal();
      await fetchGraph("/api/graph");
      return;
    }
    if (action === "add-link") {
      const target = modalForm.querySelector("#operationTarget")?.value.trim() || "";
      const linkType = modalForm.querySelector("#operationLinkType")?.value.trim() || "";
      const context = modalForm.querySelector("#operationContext")?.value.trim() || "";
      if (!target || !linkType) {
        throw new Error("Choose a target entity and relationship type first.");
      }
      const response = await apiPost(`/api/entity-link/${encodeURIComponent(slug)}`, {
        target,
        link_type: linkType,
        context,
      });
      if (!response.ok) throw new Error(response.data?.error || `Add relationship failed with ${response.status}`);
      closeModal();
      applyGraphPayload(response.data.graph, slug);
      invalidateRelationshipEndpointCache(slug, target);
      await refreshSelectedNodeAfterRelationshipMutation(slug, target, "add-link");
      return;
    }
    if (action === "remove-link") {
      const selected = modalForm.querySelector("#operationExistingRelationship")?.value || "";
      if (!selected) {
        throw new Error("Choose an existing relationship to remove.");
      }
      const [target = "", rawType = ""] = selected.split(" | ");
      const linkType = rawType === "all" ? "" : rawType;
      const isExisting = existingRelationshipOptions(slug).some((option) => option.targetSlug === target && option.type === linkType);
      if (!isExisting) {
        throw new Error("Choose one of the existing relationships from the list.");
      }
      const response = await apiPost(`/api/entity-unlink/${encodeURIComponent(slug)}`, {
        target,
        link_type: linkType,
      });
      if (!response.ok) throw new Error(response.data?.error || `Remove relationship failed with ${response.status}`);
      applyGraphPayload(response.data.graph, slug);
      invalidateRelationshipEndpointCache(slug, target);
      await refreshSelectedNodeAfterRelationshipMutation(slug, target, "remove-link");
      return;
    }
    if (action === "tags") {
      const newTag = modalForm.querySelector("#operationNewTag")?.value.trim() || "";
      const addTags = checkedValues("addTag");
      if (newTag) addTags.push(newTag);
      const response = await apiPost(`/api/entity-tags/${encodeURIComponent(slug)}`, {
        add: addTags,
        remove: checkedValues("removeTag"),
      });
      if (!response.ok) throw new Error(response.data?.error || `Tag update failed with ${response.status}`);
      closeModal();
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
      return;
    }
    if (action === "timeline") {
      const date = modalForm.querySelector("#operationTimelineDate")?.value.trim() || "";
      const summary = modalForm.querySelector("#operationTimelineSummary")?.value.trim() || "";
      const detail = modalForm.querySelector("#operationTimelineDetail")?.value.trim() || "";
      const source = modalForm.querySelector("#operationTimelineSource")?.value.trim() || "";
      if (!date || !summary) {
        throw new Error("Date and summary are required.");
      }
      const response = await apiPost(`/api/entity-timeline/${encodeURIComponent(slug)}`, {
        date,
        summary,
        detail,
        source,
      });
      if (!response.ok) throw new Error(response.data?.error || `Timeline update failed with ${response.status}`);
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
      await openNodeModal("timeline-view", slug);
      return;
    }
    if (action === "ask-yoda") {
      const question = modalChatInput.value.trim();
      if (!question) {
        modalMessage.textContent = "Type a question for Yoda first.";
        modalChatInput.focus();
        return;
      }
      const history = chatHistoryFor(slug, label, { mode: "yoda" });
      pendingAskHistory = history;
      history.push({ role: "user", content: question, timestamp: chatTimestamp() });
      history.push({ role: "assistant", content: "Thinking", pending: true, timestamp: chatTimestamp() });
      renderAskChat(slug, label, { mode: "yoda" });
      modalChatInput.value = "";
      modalChatInput.disabled = true;
      modalMessage.textContent = "Asking Yoda...";
      const historyPayload = history.filter((message) => message.role !== "system" && !message.pending).slice(-8);
      const response = await apiPost(`/api/entity-ask-yoda/${encodeURIComponent(slug)}`, { question, history: historyPayload, depth: state.yodaDepth });
      if (!response.ok) throw new Error(response.data?.error || `Ask Yoda failed with ${response.status}`);
      rememberYodaLog(slug, {
        request_id: response.data.request_id,
        source: response.data.source,
        timings: response.data.timings,
        diagnostics: response.data.diagnostics,
      });
      if (modalYodaLogButton) modalYodaLogButton.disabled = false;
      history[history.length - 1] = { role: "assistant", content: response.data.output || "(No output)", timestamp: chatTimestamp() };
      renderAskChat(slug, label, { mode: "yoda" });
      const timing = response.data.timings?.total_ms ? ` · ${response.data.timings.total_ms}ms` : "";
      modalMessage.textContent = `Ask another question or close the chat.${timing}`;
      modalChatInput.disabled = false;
      modalChatInput.focus();
      return;
    }
    if (action === "backlinks" || action === "history") {
      const endpoint = action === "backlinks" ? "entity-backlinks" : "entity-history";
      const response = await apiPost(`/api/${endpoint}/${encodeURIComponent(slug)}`, {});
      if (!response.ok) throw new Error(response.data?.error || `${action} failed with ${response.status}`);
      state.modalAction = { action: "result", slug, label };
      modalKicker.textContent = action === "backlinks" ? "Backlinks" : "Page history";
      modalPrimaryButton.textContent = "Close";
      modalCancelButton.hidden = true;
      modalEditor.readOnly = true;
      modalEditor.value = response.data.output || "(No output)";
      return;
    }
    if (action === "graph-query") {
      const linkType = modalForm.querySelector("#operationGraphLinkType")?.value.trim() || "";
      const direction = modalForm.querySelector("#operationGraphDirection")?.value || "both";
      const depth = modalForm.querySelector("#operationGraphDepth")?.value || "1";
      if (!["both", "outgoing", "incoming"].includes(direction)) {
        throw new Error("Choose a valid direction.");
      }
      if (!["1", "2", "3"].includes(depth)) {
        throw new Error("Choose a depth from 1 to 3.");
      }
      const response = await apiPost(`/api/entity-graph-query/${encodeURIComponent(slug)}`, {
        link_type: linkType,
        direction,
        depth,
      });
      if (!response.ok) throw new Error(response.data?.error || `Graph query failed with ${response.status}`);
      state.modalAction = { action: "result", slug, label };
      modalKicker.textContent = "Graph query results";
      modalPrimaryButton.textContent = "Close";
      modalCancelButton.hidden = true;
      modalForm.hidden = true;
      modalEditor.hidden = true;
      modalMarkdown.hidden = false;
      modalMessage.textContent = `${label} · ${direction} · ${linkType || "all relationship types"} · depth ${depth}`;
      renderMarkdownView(response.data.output || "(No output)");
      return;
    }
    if (action === "attach-file") {
      const selectedFile = modalFileInput.files?.[0];
      let response;
      if (selectedFile) {
        const formData = new FormData();
        formData.append("file", selectedFile);
        formData.append("description", modalAttachDescription.value.trim());
        response = await apiPostForm(`/api/entity-attach-file/${encodeURIComponent(slug)}`, formData);
      } else {
        throw new Error("Choose a file before attaching.");
      }
      if (!response.ok) throw new Error(response.data?.error || `Attach file failed with ${response.status}`);
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
      if (response.data.local_media?.served_url) {
        state.modalAction = { action: "result", slug, label };
        modalKicker.textContent = "Local media ready";
        modalPrimaryButton.textContent = "Close";
        modalCancelButton.hidden = true;
        modalEditor.readOnly = true;
        modalEditor.value = `Preview URL: ${response.data.local_media.served_url}\nFilesystem path: ${response.data.local_media.path}`;
      } else {
        closeModal();
      }
      return;
    }
    if (action === "embed") {
      const response = await apiPost(`/api/entity-embed/${encodeURIComponent(slug)}`, {});
      if (!response.ok) throw new Error(response.data?.error || `Refresh embedding failed with ${response.status}`);
      closeModal();
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
    }
  } catch (error) {
    if (action === "ask-yoda" && pendingAskHistory && pendingAskHistory.at(-1)?.pending) {
      pendingAskHistory[pendingAskHistory.length - 1] = {
        role: "assistant",
        content: `Ask Yoda failed: ${error.message || String(error)}`,
        timestamp: chatTimestamp(),
      };
      renderAskChat(slug, label, action === "ask-yoda" ? { mode: "yoda" } : {});
    }
    modalMessage.textContent = error.message || String(error);
  } finally {
    endBusyOperation(busyToken);
    modalPrimaryButton.disabled = false;
    modalCancelButton.disabled = false;
    modalFileInput.disabled = false;
    modalEditor.disabled = false;
    modalAttachDescription.disabled = false;
    modalChatInput.disabled = false;
    if (action === "attach-file" && state.modalAction?.action === "attach-file") {
      modalPrimaryButton.textContent = primaryButtonText;
    }
  }
}

modalConfirmInput.addEventListener("input", () => {
  if (state.modalAction?.action !== "delete") return;
  modalPrimaryButton.disabled = modalConfirmInput.value !== state.modalAction.label;
});

async function loadEntity(slug, options = {}) {
  if (isHidden(slug)) return { status: "hidden", slug };
  const busyToken = beginBusyOperation("Loading view");
  let directBusyToken = null;
  if (options.source !== "search" && options.source !== "system") {
    state.selectionVersion += 1;
  }
  try {
    const loadId = (state.entityLoadId || 0) + 1;
    state.entityLoadId = loadId;
    const requestedNode = state.nodeMap.get(slug);
    const shouldExpand = requestedNode && !requestedNode.expanded;
    state.focusSlug = slug;
    updateAskYodaButtons();
    if (requestedNode) {
      const directBusyLabel = `Loading direct neighbors for ${requestedNode.label || slug}`;
      setBusyOperationLabel(busyToken, directBusyLabel);
      if (shouldExpand) {
        directBusyToken = beginBusyOperation(directBusyLabel);
        setBusyOperationLabel(directBusyToken, directBusyLabel);
      }
      detailTitle.textContent = requestedNode.label || slug;
      if (selectionSlugAlways) selectionSlugAlways.textContent = slug || "No selection";
      setTimelineBadge(slug, false);
      detailType.textContent = `${requestedNode.category || requestedNode.type || "entity"} · ${shouldExpand ? "loading direct links" : "loading details"}`;
      detailSummary.textContent = shouldExpand
        ? `Loading direct neighbors for ${requestedNode.label || slug}...`
        : `Loading summary for ${requestedNode.label || slug}...`;
      renderSelectionMediaPreview([], slug);
      detailLinks.innerHTML = "";
      const loading = document.createElement("span");
      loading.textContent = "Loading direct links...";
      detailLinks.appendChild(loading);
      detailSecondRing.innerHTML = "";
      setHover(slug);
    }
    await ensureExpanded(slug);
    if (loadId !== state.entityLoadId) return { status: "stale", slug };
    const response = await apiGet(`/api/entity/${encodeURIComponent(slug)}`);
    if (!response.ok) {
      const requested = requestedNode || state.nodeMap.get(slug);
      state.focusSlug = slug;
      updateAskYodaButtons();
      detailTitle.textContent = requested?.label || slug;
      if (selectionSlugAlways) selectionSlugAlways.textContent = slug || "No selection";
      detailType.textContent = `${requested?.category || requested?.type || "entity"} · partial info`;
      detailSummary.textContent = `Basic graph info is available, but no markdown page was found for ${requested?.label || slug}.`;
      setHover(slug);
      return { status: "partial", slug, httpStatus: response.status };
    }
    if (loadId !== state.entityLoadId) return { status: "stale", slug };
    const payload = response.data;
    const { entity, neighbors, second_ring: secondRing, source } = payload;
    state.focusSlug = entity.slug;
    updateAskYodaButtons();
    if (options.recordHistory !== false) {
      recordSelectionHistory(entity.slug);
    } else {
      updateSelectionHistoryControls();
    }
    detailTitle.textContent = entity.label;
    if (selectionSlugAlways) selectionSlugAlways.textContent = entity.slug;
    setTimelineBadge(entity.slug, false);
    const partText = entity.parts_count ? ` · ${entity.parts_count} collapsed parts` : "";
    const reportText = entity.report_count ? ` · ${entity.report_count} collapsed reports` : "";
    detailType.textContent = `${entity.category || entity.type} · ${entity.type} · ${entity.degree} direct link${entity.degree === 1 ? "" : "s"}${partText}${reportText}`;
    const collapseNote = [
      entity.parts_count ? `Collapsed ${entity.parts_count} document parts into this entity.` : "",
      entity.report_count ? `Collapsed ${entity.report_count} dated usage reports into this entity.` : "",
    ].filter(Boolean).join(" ");
    const summaryText = displaySummary(entity.summary);
    detailSummary.textContent = collapseNote
      ? `${summaryText} ${collapseNote}`
      : summaryText;
    updateSource(source);
    void refreshTimelineBadge(entity.slug, loadId);
    void loadSelectionMediaPreview(entity.slug, loadId);
    state.visibleLabelSlugs = [
      ...new Set([
        ...state.visibleLabelSlugs,
        entity.slug,
        ...neighbors.filter((neighbor) => !isHidden(neighbor.slug)).map((neighbor) => neighbor.slug),
      ]),
    ];

  detailLinks.innerHTML = "";
  neighbors.forEach((neighbor) => {
    if (isHidden(neighbor.slug)) return;
    rememberRelationshipTypes(entity.slug, neighbor.slug, neighbor.link_types || []);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "direct-link-chip";
    const label = document.createElement("span");
    label.className = "direct-link-label";
    label.textContent = `${neighbor.category || neighbor.type} · ${neighbor.label} (${neighbor.degree})`;
    button.appendChild(label);
    if (neighbor.link_types?.length) {
      const relationship = `relationship: ${neighbor.link_types.join(", ")}`;
      button.title = relationship;
      button.dataset.relationship = relationship;
      const relation = document.createElement("span");
      relation.className = "direct-link-relationship";
      relation.textContent = relationship;
      button.appendChild(relation);
    }
    button.addEventListener("mouseenter", () => setHover(neighbor.slug));
    button.addEventListener("focus", () => setHover(neighbor.slug));
    button.addEventListener("mouseleave", () => setHover(entity.slug));
    button.addEventListener("blur", () => setHover(entity.slug));
    button.addEventListener("click", () => {
      void loadEntity(neighbor.slug);
    });
    detailLinks.appendChild(button);
  });
  if (![...detailLinks.children].length) {
    const empty = document.createElement("span");
    empty.textContent = "No direct links";
    detailLinks.appendChild(empty);
  }

  detailSecondRing.innerHTML = "";
  secondRing.forEach((neighbor) => {
    if (isHidden(neighbor.slug)) return;
    const tag = document.createElement("span");
    tag.textContent = `${neighbor.category || neighbor.type} · ${neighbor.label} (${neighbor.degree})`;
    detailSecondRing.appendChild(tag);
  });
  if (![...detailSecondRing.children].length) {
    const empty = document.createElement("span");
    empty.textContent = "No second-ring entities";
    detailSecondRing.appendChild(empty);
  }
    setHover(slug);
    return { status: "loaded", slug: entity.slug };
  } finally {
    endBusyOperation(directBusyToken);
    endBusyOperation(busyToken);
  }
}

async function refreshTimelineBadge(slug, loadId = state.entityLoadId) {
  try {
    const response = await apiGet(`/api/entity-timeline-view/${encodeURIComponent(slug)}`);
    if (loadId !== state.entityLoadId || state.focusSlug !== slug) return;
    setTimelineBadge(slug, response.ok && timelineOutputHasEntries(response.data?.output));
  } catch (_error) {
    if (loadId === state.entityLoadId && state.focusSlug === slug) {
      setTimelineBadge(slug, false);
    }
  }
}

async function focusFallbackNode() {
  const fallback = visibleGraphNodes().sort((left, right) => (right.degree || 0) - (left.degree || 0))[0];
  if (fallback) {
    await loadEntity(fallback.slug);
    return;
  }
  state.focusSlug = null;
  updateAskYodaButtons();
  detailTitle.textContent = "No visible node";
  setTimelineBadge("", false);
  detailType.textContent = "";
  detailSummary.textContent = "Use the Hidden List to show nodes again.";
  renderSelectionMediaPreview([]);
  detailLinks.innerHTML = "";
  detailSecondRing.innerHTML = "";
}

function pickNode(clientX, clientY) {
  const rect = canvas.getBoundingClientRect();
  const x = clientX - rect.left;
  const y = clientY - rect.top;
  let winner = null;
  let winnerDistance = Infinity;
  for (const node of state.nodes) {
    if (!state.filteredSlugs.has(node.slug)) continue;
    const radius = Math.max(4, node.size * (node.depthScale || 1));
    const distance = Math.hypot(node.screenX - x, node.screenY - y);
    if (distance <= radius + 10 && distance < winnerDistance) {
      winner = node;
      winnerDistance = distance;
    }
  }
  return winner;
}

function startCanvasDrag(clientX, clientY, pointerId = null) {
  state.drag.active = true;
  state.drag.moved = false;
  state.drag.lastX = clientX;
  state.drag.lastY = clientY;
  state.drag.pointerId = pointerId;
  state.rotation.vx = 0;
  state.rotation.vy = 0;
  hideGraphTooltip();
  canvas.style.cursor = "grabbing";
  requestRender();
}

function moveCanvasDrag(clientX, clientY) {
  hideGraphTooltip();
  const dx = clientX - state.drag.lastX;
  const dy = clientY - state.drag.lastY;
  if (Math.abs(dx) + Math.abs(dy) > 3) {
    state.drag.moved = true;
  }
  state.rotation.y += dx * 0.006;
  state.rotation.x = Math.max(-1.15, Math.min(1.15, state.rotation.x + dy * 0.006));
  state.rotation.vy = dx * 0.0007;
  state.rotation.vx = dy * 0.0007;
  state.drag.lastX = clientX;
  state.drag.lastY = clientY;
  requestRender();
}

function finishCanvasDrag(clientX, clientY, options = {}) {
  if (!state.drag.active) return;
  state.drag.active = false;
  state.drag.pointerId = null;
  const node = pickNode(clientX, clientY);
  if (!state.drag.moved && node && options.selectOnTap !== false) {
    void loadEntity(node.slug);
  }
  canvas.style.cursor = node ? "pointer" : "default";
  requestRender();
}

function cancelCanvasDrag() {
  state.drag.active = false;
  state.drag.pointerId = null;
  canvas.style.cursor = "default";
  requestRender();
}

function firstTouch(event) {
  return event.changedTouches?.[0] || event.touches?.[0] || null;
}

function showMobileNodeHint(node, clientX, clientY) {
  if (!node) return;
  window.clearTimeout(state.mobileTooltipTimer);
  setHover(node.slug);
  showGraphTooltip(node, clientX, clientY);
  state.mobileTooltipTimer = window.setTimeout(() => {
    hideGraphTooltip();
  }, 3200);
}

function bindEvents() {
  navSearchButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleFloatingPanel(searchFlyout, navSearchButton);
    if (searchFlyout && !searchFlyout.hidden) {
      window.setTimeout(() => searchInput?.focus(), 0);
    }
  });

  navAutopilotButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    if (state.tour.active || state.tour.toolbarPinned) {
      stopTour();
      setFlyoutOpen(autopilotFlyout, navAutopilotButton, false);
      return;
    }
    showFloatingPanel(autopilotFlyout, navAutopilotButton);
  });

  navSettingsButton?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleFloatingPanel(settingsFlyout, navSettingsButton);
  });

  navSearchButton?.addEventListener("mouseenter", () => {
    showFloatingPanel(searchFlyout, navSearchButton);
    window.setTimeout(() => searchInput?.focus(), 0);
  });

  navAutopilotButton?.addEventListener("mouseenter", () => {
    showFloatingPanel(autopilotFlyout, navAutopilotButton);
  });

  navSettingsButton?.addEventListener("mouseenter", () => {
    showFloatingPanel(settingsFlyout, navSettingsButton);
  });

  settingsFlyout?.addEventListener("mouseleave", () => {
    setFlyoutOpen(settingsFlyout, navSettingsButton, false);
  });

  settingsOkButton?.addEventListener("click", applySettingsFromControls);
  settingsCancelButton?.addEventListener("click", cancelSettingsChanges);
  flushCacheButton?.addEventListener("click", flushNodeCache);
  yodaDepthInput?.addEventListener("input", (event) => {
    setYodaDepth(event.target.value);
  });
  modalYodaDepth?.addEventListener("input", (event) => {
    setYodaDepth(event.target.value);
  });
  modalYodaLogButton?.addEventListener("click", () => {
    openYodaLogWindow(yodaLogSlug());
  });
  settingsYodaLogButton?.addEventListener("click", () => {
    openYodaLogWindow(yodaLogSlug());
  });
  selectionAskYodaButton?.addEventListener("click", () => {
    if (state.focusSlug) void openNodeModal("ask-yoda", state.focusSlug);
  });
  selectionViewButton?.addEventListener("click", () => {
    if (state.focusSlug) void openNodeModal("view", state.focusSlug);
  });
  mapAskYodaButton?.addEventListener("click", () => {
    if (state.focusSlug) void openNodeModal("ask-yoda", state.focusSlug);
  });
  mapViewButton?.addEventListener("click", () => {
    if (state.focusSlug) void openNodeModal("view", state.focusSlug);
  });
  detailTitle?.addEventListener("dblclick", () => {
    if (state.focusSlug) void openNodeModal("view", state.focusSlug);
  });
  mapFilterToggleButton?.addEventListener("click", () => {
    state.mapFiltersVisible = !state.mapFiltersVisible;
    mapFilterPanel?.classList.toggle("is-hidden", !state.mapFiltersVisible);
    updateMapFilterPanel();
  });
  filterDrawerHandle?.addEventListener("pointerenter", showFilterSidebar);
  filterDrawerHandle?.addEventListener("pointerleave", (event) => {
    if (!pointerStayedInsideFilterSidebar(event.relatedTarget)) hideFilterSidebar();
  });
  filterDrawerHandle?.addEventListener("focus", showFilterSidebar);
  mapFilterPanel?.addEventListener("pointerenter", showFilterSidebar);
  mapFilterPanel?.addEventListener("click", showFilterSidebar);
  mapFilterPanel?.addEventListener("pointerleave", (event) => {
    if (!pointerStayedInsideFilterSidebar(event.relatedTarget)) hideFilterSidebar();
  });
  mapFilterPanel?.addEventListener("blur", (event) => {
    if (!pointerStayedInsideFilterSidebar(event.relatedTarget)) hideFilterSidebar();
  }, true);

  searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    applyFilter();
  });

  searchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    hideFloatingPanels();
    void submitSearch();
  });

  searchButton.addEventListener("click", () => {
    hideFloatingPanels();
    void submitSearch();
  });

  modalChatInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      void runModalPrimaryAction();
    }
  });

  modalMarkdown.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-entity-query]");
    if (!link) return;
    event.preventDefault();
    void searchEntityLink(link.dataset.entityQuery);
  });

  modalChat.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-entity-query]");
    if (!link) return;
    event.preventDefault();
    closeModal();
    void searchEntityLink(link.dataset.entityQuery);
  });

  matchesOnlyToggle.addEventListener("change", (event) => {
    state.matchesOnly = event.target.checked;
    applyFilter();
  });

  minDegreeFilter.addEventListener("input", (event) => {
    state.filters.minDegree = Math.max(0, Number.parseInt(event.target.value, 10) || 0);
    applyFilter();
  });

  const setCloudMode = (enabled) => {
    state.cloudMode = enabled;
    updateCloudModeControl();
    if (state.graph) {
      buildRuntimeGraph(state.graph);
      applyFilter();
    }
  };

  cloudModeToggle?.addEventListener("change", (event) => {
    setCloudMode(event.target.checked);
  });

  cloudModeButton?.addEventListener("click", () => {
    setCloudMode(!state.cloudMode);
  });

  categoryLimitInput?.addEventListener("input", (event) => {
    state.categoryLimit = Math.max(1, Math.min(50, Number.parseInt(event.target.value, 10) || 5));
    updateCategoryLegend(state.graph);
  });

  clusterLimitInput?.addEventListener("input", (event) => {
    state.clusterLimit = Math.max(1, Math.min(50, Number.parseInt(event.target.value, 10) || 5));
    updateHubClusterLegend();
  });

  timelineDaysInput?.addEventListener("input", (event) => {
    state.timelineDays = Math.max(0, Math.min(7, Number.parseInt(event.target.value, 10) || 0));
    updateTimelineLabel();
    applyFilter();
  });

  tourPlanButton?.addEventListener("click", () => {
    state.tour.toolbarPinned = true;
    showFloatingPanel(autopilotFlyout, navAutopilotButton);
    void openNodeModal("tour-plan", state.focusSlug || "");
  });
  tourButton?.addEventListener("click", () => {
    toggleTour();
  });
  tourPrevButton?.addEventListener("click", () => moveTour(-1));
  tourNextButton?.addEventListener("click", () => moveTour(1));
  tourStopButton?.addEventListener("click", () => {
    stopTour();
    hideFloatingPanels();
  });

  refreshButton?.addEventListener("click", async () => {
    await fetchGraph("/api/refresh", { preserveFocus: true });
  });

  zoomOutButton.addEventListener("click", () => {
    zoomBy(-1);
  });

  zoomInButton.addEventListener("click", () => {
    zoomBy(1);
  });

  historyBackButton?.addEventListener("click", () => {
    void navigateSelectionHistory(-1);
  });

  historyForwardButton?.addEventListener("click", () => {
    void navigateSelectionHistory(1);
  });

  floatingHistoryBackButton?.addEventListener("click", () => {
    void navigateSelectionHistory(-1);
  });

  floatingHistoryForwardButton?.addEventListener("click", () => {
    void navigateSelectionHistory(1);
  });

  newNodeButton.addEventListener("click", () => {
    void openNodeModal("new-node", "");
  });

  nodeMenuButton.addEventListener("click", (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    showContextMenu(state.focusSlug, rect.left, rect.bottom + 6);
  });

  timelineBadge?.addEventListener("click", () => {
    const slug = timelineBadge.dataset.slug || state.focusSlug;
    void openNodeModal("timeline-view", slug);
  });

  contextMenu.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const action = button.dataset.action;
    const slug = state.menuSlug || state.focusSlug;
    if (action === "hide") {
      void hideNode(slug);
      return;
    }
    void openNodeModal(action, slug);
  });

  modalCloseButton.addEventListener("click", closeModalFromControl);
  modalCancelButton.addEventListener("click", () => {
    if (state.modalAction?.action === "yoda-log" && state.yodaLogReturn) {
      void returnFromYodaLog();
      return;
    }
    if (state.modalAction?.action === "tour-plan") {
      state.tour.planDraft = null;
      closeModal();
      showFloatingPanel(autopilotFlyout, navAutopilotButton);
      return;
    }
    if (state.modalAction?.action === "remove-link") {
      void reopenRelationshipsView(state.modalAction.slug);
      return;
    }
    closeModal();
  });
  modalPrimaryButton.addEventListener("click", () => {
    void runModalPrimaryAction();
  });

  window.addEventListener("click", (event) => {
    if (!contextMenu.hidden && !contextMenu.contains(event.target) && event.target !== nodeMenuButton) {
      hideContextMenu();
    }
    if (!targetIsInsideFloatingPanel(event.target)) {
      hideFloatingPanels();
    }
  });

  const usePointerEvents = Boolean(window.PointerEvent);
  let longPressTimer = null;
  let suppressContextMenuUntil = 0;
  const activeTouchPointers = new Map();
  const pinchGesture = { active: false, initialDistance: 0, initialZoom: 1 };

  const clearLongPress = () => {
    window.clearTimeout(longPressTimer);
    longPressTimer = null;
  };

  const safeSetPointerCapture = (pointerId) => {
    try {
      canvas.setPointerCapture?.(pointerId);
    } catch {
      // Some mobile/synthetic pointer paths do not expose a capturable pointer.
    }
  };

  const safeReleasePointerCapture = (pointerId) => {
    try {
      canvas.releasePointerCapture?.(pointerId);
    } catch {
      // Capture may not have been established on all touch browsers.
    }
  };

  const handleHoverMove = (clientX, clientY) => {
    const node = pickNode(clientX, clientY);
    setHover(node ? node.slug : null);
    showGraphTooltip(node, clientX, clientY);
    canvas.style.cursor = node ? "pointer" : "default";
  };

  const touchDistance = (points) => {
    if (points.length < 2) return 0;
    return Math.hypot(points[0].clientX - points[1].clientX, points[0].clientY - points[1].clientY);
  };

  const beginPinchZoom = (points) => {
    const distance = touchDistance(points);
    if (!distance) return;
    clearLongPress();
    cancelCanvasDrag();
    hideGraphTooltip();
    pinchGesture.active = true;
    pinchGesture.initialDistance = distance;
    pinchGesture.initialZoom = state.zoom;
  };

  const updatePinchZoom = (points) => {
    if (!pinchGesture.active) return;
    const distance = touchDistance(points);
    if (!distance || !pinchGesture.initialDistance) return;
    setZoom(pinchGesture.initialZoom * (distance / pinchGesture.initialDistance));
  };

  const endPinchZoom = () => {
    pinchGesture.active = false;
    pinchGesture.initialDistance = 0;
    pinchGesture.initialZoom = state.zoom;
  };

  const selectMobileNode = (node) => {
    if (!node) return;
    state.focusSlug = node.slug;
    setHover(node.slug);
    hideGraphTooltip();
    void loadEntity(node.slug);
  };

  const beginTouchLikeDrag = (clientX, clientY, pointerId = null) => {
    startCanvasDrag(clientX, clientY, pointerId);
    clearLongPress();
    longPressTimer = window.setTimeout(() => {
      const node = pickNode(state.drag.lastX, state.drag.lastY);
      if (!node || state.drag.moved) return;
      state.drag.moved = true;
      suppressContextMenuUntil = Date.now() + 1200;
      selectMobileNode(node);
    }, 580);
  };

  if (usePointerEvents) {
    canvas.addEventListener("pointerdown", (event) => {
      if (event.button !== 0 && event.pointerType !== "touch") return;
      event.preventDefault();
      safeSetPointerCapture(event.pointerId);
      if (event.pointerType === "touch" || event.pointerType === "pen") {
        activeTouchPointers.set(event.pointerId, { clientX: event.clientX, clientY: event.clientY });
        if (activeTouchPointers.size >= 2) {
          beginPinchZoom([...activeTouchPointers.values()]);
          return;
        }
        beginTouchLikeDrag(event.clientX, event.clientY, event.pointerId);
      } else {
        startCanvasDrag(event.clientX, event.clientY, event.pointerId);
      }
    });

    canvas.addEventListener("pointermove", (event) => {
      if (activeTouchPointers.has(event.pointerId)) {
        activeTouchPointers.set(event.pointerId, { clientX: event.clientX, clientY: event.clientY });
      }
      if (pinchGesture.active && activeTouchPointers.size >= 2) {
        event.preventDefault();
        updatePinchZoom([...activeTouchPointers.values()]);
        return;
      }
      if (state.drag.active && state.drag.pointerId === event.pointerId) {
        event.preventDefault();
        moveCanvasDrag(event.clientX, event.clientY);
        if (state.drag.moved) clearLongPress();
        return;
      }
      if (event.pointerType !== "touch") {
        handleHoverMove(event.clientX, event.clientY);
      }
    });

    window.addEventListener("pointerup", (event) => {
      const wasTouchPointer = activeTouchPointers.has(event.pointerId);
      if (wasTouchPointer) {
        activeTouchPointers.delete(event.pointerId);
        if (pinchGesture.active) {
          event.preventDefault();
          if (activeTouchPointers.size < 2) endPinchZoom();
          return;
        }
      }
      if (!state.drag.active || state.drag.pointerId !== event.pointerId) return;
      event.preventDefault();
      clearLongPress();
      const wasTap = !state.drag.moved;
      const node = pickNode(event.clientX, event.clientY);
      safeReleasePointerCapture(event.pointerId);
      const isTouchLike = event.pointerType === "touch" || event.pointerType === "pen" || wasTouchPointer;
      finishCanvasDrag(event.clientX, event.clientY, { selectOnTap: !isTouchLike });
      if (wasTap && node && (event.pointerType === "touch" || event.pointerType === "pen")) {
        showMobileNodeHint(node, event.clientX, event.clientY);
      }
    });

    window.addEventListener("pointercancel", (event) => {
      activeTouchPointers.delete(event.pointerId);
      if (pinchGesture.active && activeTouchPointers.size < 2) endPinchZoom();
      if (state.drag.pointerId === event.pointerId) {
        clearLongPress();
        cancelCanvasDrag();
      }
    });
  } else {
    canvas.addEventListener("mousedown", (event) => {
      startCanvasDrag(event.clientX, event.clientY);
    });

    canvas.addEventListener("mousemove", (event) => {
      if (state.drag.active) {
        moveCanvasDrag(event.clientX, event.clientY);
        return;
      }
      handleHoverMove(event.clientX, event.clientY);
    });

    window.addEventListener("mouseup", (event) => {
      finishCanvasDrag(event.clientX, event.clientY);
    });
  }

  canvas.addEventListener("touchstart", (event) => {
    if (usePointerEvents) return;
    if (event.touches.length >= 2) {
      event.preventDefault();
      beginPinchZoom([...event.touches]);
      return;
    }
    const touch = firstTouch(event);
    if (!touch) return;
    event.preventDefault();
    beginTouchLikeDrag(touch.clientX, touch.clientY);
  }, { passive: false });

  canvas.addEventListener("touchmove", (event) => {
    if (usePointerEvents) return;
    if (pinchGesture.active && event.touches.length >= 2) {
      event.preventDefault();
      updatePinchZoom([...event.touches]);
      return;
    }
    if (!state.drag.active) return;
    const touch = firstTouch(event);
    if (!touch) return;
    event.preventDefault();
    moveCanvasDrag(touch.clientX, touch.clientY);
    if (state.drag.moved) clearLongPress();
  }, { passive: false });

  canvas.addEventListener("touchend", (event) => {
    if (usePointerEvents) return;
    if (pinchGesture.active) {
      event.preventDefault();
      if (event.touches.length >= 2) {
        beginPinchZoom([...event.touches]);
      } else {
        endPinchZoom();
      }
      return;
    }
    if (!state.drag.active) return;
    const touch = firstTouch(event);
    clearLongPress();
    if (!touch) {
      cancelCanvasDrag();
      return;
    }
    event.preventDefault();
    const wasTap = !state.drag.moved;
    const node = pickNode(touch.clientX, touch.clientY);
    finishCanvasDrag(touch.clientX, touch.clientY, { selectOnTap: false });
    if (wasTap && node) {
      showMobileNodeHint(node, touch.clientX, touch.clientY);
    }
  }, { passive: false });

  canvas.addEventListener("touchcancel", () => {
    if (!usePointerEvents) {
      clearLongPress();
      endPinchZoom();
      cancelCanvasDrag();
    }
  }, { passive: false });

  canvas.addEventListener("contextmenu", (event) => {
    if (Date.now() < suppressContextMenuUntil) {
      event.preventDefault();
      return;
    }
    const node = pickNode(event.clientX, event.clientY);
    if (!node) return;
    event.preventDefault();
    state.focusSlug = node.slug;
    void loadEntity(node.slug);
    showContextMenu(node.slug, event.clientX, event.clientY);
  });

  canvas.addEventListener("dblclick", (event) => {
    const node = pickNode(event.clientX, event.clientY);
    if (!node) return;
    event.preventDefault();
    state.focusSlug = node.slug;
    void loadEntity(node.slug);
    void openNodeModal("view", node.slug);
  });

  canvas.addEventListener("wheel", (event) => {
    if (!event.metaKey) return;
    event.preventDefault();
    zoomBy(event.deltaY < 0 ? 1 : -1);
  }, { passive: false });

  canvas.addEventListener("mouseleave", () => {
    if (state.drag.active) return;
    setHover(null);
    hideGraphTooltip();
    canvas.style.cursor = "default";
  });

  window.addEventListener("resize", () => {
    updateResponsiveSelectionPlacement();
    resizeCanvas();
    if (state.graph) {
      buildRuntimeGraph(state.graph);
    }
  });

  if (typeof compactSelectionQuery.addEventListener === "function") {
    compactSelectionQuery.addEventListener("change", updateResponsiveSelectionPlacement);
  } else if (typeof compactSelectionQuery.addListener === "function") {
    compactSelectionQuery.addListener(updateResponsiveSelectionPlacement);
  }
}

async function fetchGraph(endpoint = "/api/graph", options = {}) {
  if (state.isRefreshing) {
    return state.graph;
  }
  const isRefresh = endpoint.includes("refresh");
  if (isRefresh) setRefreshing(true);
  try {
    const previousFocus = options.preferredFocus || (options.preserveFocus ? state.focusSlug : null);
    const response = await apiGet(endpoint);
    const graph = response.data;
    if (!response.ok) {
      throw new Error(graph?.error || `Graph request failed with ${response.status}`);
    }
    applyGraphPayload(graph, previousFocus);
    requestRender();
    if (state.focusSlug) {
      await loadEntity(state.focusSlug, { source: "system", recordHistory: false });
    }
    return graph;
  } finally {
    if (isRefresh) setRefreshing(false);
  }
}

async function fetchHidden() {
  const response = await apiGet("/api/hidden");
  if (!response.ok) return;
  state.hiddenSlugs = new Set(response.data.slugs || []);
  updateHiddenList();
}

async function init() {
  bindEvents();
  updateResponsiveSelectionPlacement();
  uiVersion.textContent = UI_VERSION;
  if (cloudModeToggle) cloudModeToggle.checked = state.cloudMode;
  if (flowingEdgesToggle) flowingEdgesToggle.checked = state.flowingEdges;
  if (yodaDepthInput) yodaDepthInput.value = String(state.yodaDepth);
  updateCloudModeControl();
  updateMapFilterPanel();
  updateTimelineLabel();
  updateSelectionHistoryControls();
  updateNavModeState();
  updateCacheSettingsView();
  setZoom(state.zoom);
  await fetchHidden();
  await fetchGraph();
  if (!state.animationHandle) {
    requestRender();
  }
}

void init();

window.__MEMORY_STARGRAPH__ = {
  getState: () => state,
  loadEntity,
  hideNode,
  showNode,
  ensureExpanded,
  setZoom,
  navigateSelectionHistory,
  labelForNode,
  relationshipTypes,
  submitSearch,
  setHover,
  renderMarkdownView,
  searchEntityLink,
};
window.__TGKS__ = window.__MEMORY_STARGRAPH__;
