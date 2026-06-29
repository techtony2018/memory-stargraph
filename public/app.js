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
  filters: { category: "", type: "", minDegree: 0 },
  nodes: [],
  edges: [],
  edgeTypeMap: new Map(),
  nodeMap: new Map(),
  visibleLabelSlugs: [],
  animationHandle: null,
  isRefreshing: false,
  lastRefreshAt: null,
  autoRefresh: { enabled: false, intervalMinutes: 10, timer: null },
  lazySearch: { timer: null, query: "", loading: false },
  menuSlug: null,
  modalAction: null,
  askChats: new Map(),
  entityLoadId: 0,
  selectionVersion: 0,
  zoom: 1,
  rotation: { x: -0.34, y: 0.58, vx: 0.0012, vy: 0.0022 },
  drag: { active: false, moved: false, lastX: 0, lastY: 0, pointerId: null },
  mobileTooltipTimer: null,
  viewport: { width: 1200, height: 760, dpr: Math.max(1, window.devicePixelRatio || 1) },
};

const UI_VERSION = "V1.0.34";
const canvas = document.getElementById("graphCanvas");
const ctx = canvas.getContext("2d");
const hoverLabel = document.getElementById("hoverLabel");
const graphTooltip = document.getElementById("graphTooltip");
const searchInput = document.getElementById("searchInput");
const searchButton = document.getElementById("searchButton");
const matchesOnlyToggle = document.getElementById("matchesOnlyToggle");
const refreshButton = document.getElementById("refreshButton");
const autoRefreshToggle = document.getElementById("autoRefreshToggle");
const autoRefreshInterval = document.getElementById("autoRefreshInterval");
const lastRefresh = document.getElementById("lastRefresh");
const categoryFilter = document.getElementById("categoryFilter");
const typeFilter = document.getElementById("typeFilter");
const minDegreeFilter = document.getElementById("minDegreeFilter");
const clearFiltersButton = document.getElementById("clearFiltersButton");
const zoomOutButton = document.getElementById("zoomOutButton");
const zoomInButton = document.getElementById("zoomInButton");
const zoomLevel = document.getElementById("zoomLevel");

const detailTitle = document.getElementById("detailTitle");
const detailType = document.getElementById("detailType");
const detailSummary = document.getElementById("detailSummary");
const detailLinks = document.getElementById("detailLinks");
const detailSecondRing = document.getElementById("detailSecondRing");
const sourceBadge = document.getElementById("sourceBadge");
const sourceMessage = document.getElementById("sourceMessage");
const sourceWarnings = document.getElementById("sourceWarnings");
const categoryLegend = document.getElementById("categoryLegend");
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
const modalCloseButton = document.getElementById("modalCloseButton");
const modalCancelButton = document.getElementById("modalCancelButton");
const modalPrimaryButton = document.getElementById("modalPrimaryButton");

const metricNodes = document.getElementById("metricNodes");
const metricEdges = document.getElementById("metricEdges");
const metricDegree = document.getElementById("metricDegree");
const metricCollapsed = document.getElementById("metricCollapsed");

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
}

function apiGet(url) {
  if (typeof window.fetch === "function") {
    return window.fetch(url).then(async (response) => ({
      ok: response.ok,
      status: response.status,
      data: await response.json(),
    }));
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
          resolve({
            ok: true,
            status: request.status,
            data: JSON.parse(request.responseText),
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
  refreshButton.disabled = active;
  refreshButton.textContent = active ? "Refreshing..." : "Refresh Graph";
}

function updateLastRefresh(source) {
  state.lastRefreshAt = source?.updated_at || new Date().toISOString();
  lastRefresh.textContent = formatRefreshTime(state.lastRefreshAt);
}

function scheduleAutoRefresh() {
  if (state.autoRefresh.timer) {
    window.clearInterval(state.autoRefresh.timer);
    state.autoRefresh.timer = null;
  }
  if (!state.autoRefresh.enabled) return;
  const minutes = Math.max(1, Math.min(120, Number.parseInt(autoRefreshInterval.value, 10) || 10));
  state.autoRefresh.intervalMinutes = minutes;
  state.autoRefresh.timer = window.setInterval(() => {
    void fetchGraph("/api/refresh", { preserveFocus: true });
  }, minutes * 60 * 1000);
}

function clampZoom(value) {
  return Math.max(0.45, Math.min(2.4, value));
}

function setZoom(value) {
  state.zoom = clampZoom(value);
  zoomLevel.textContent = `${Math.round(state.zoom * 100)}%`;
  projectAll();
}

function zoomBy(direction) {
  const factor = direction > 0 ? 1.14 : 1 / 1.14;
  setZoom(state.zoom * factor);
}

function setSearchLoading(active) {
  state.lazySearch.loading = active;
  searchInput.disabled = active;
  searchButton.disabled = active;
  searchButton.textContent = active ? "Searching..." : "Search";
}

async function runLazySearch(query) {
  if (state.lazySearch.loading) return;
  const submittedQuery = String(query || "").trim();
  if (submittedQuery.length < 3) return;
  setSearchLoading(true);
  const selectionVersion = state.selectionVersion;
  try {
    const response = await apiGet(`/api/search?q=${encodeURIComponent(submittedQuery)}`);
    if (!response.ok) return;
    const preferredFocus = pickSearchFocus(response.data.graph, submittedQuery) || state.focusSlug;
    const focusSlug = selectionVersion === state.selectionVersion ? preferredFocus : state.focusSlug;
    applyGraphPayload(response.data.graph, focusSlug);
    if (selectionVersion === state.selectionVersion && preferredFocus && state.focusSlug === preferredFocus) {
      await loadEntity(preferredFocus, { source: "search" });
    }
  } finally {
    setSearchLoading(false);
    searchInput.focus();
  }
}

async function submitSearch() {
  const query = state.query.trim();
  if (!query || query.length < 3 || state.lazySearch.loading) return;
  await runLazySearch(query);
}

async function searchEntityLink(query) {
  const value = String(query || "").trim();
  if (value.length < 3 || state.lazySearch.loading) return;
  closeModal();
  state.query = value;
  searchInput.value = value;
  matchesOnlyToggle.checked = false;
  state.matchesOnly = false;
  await runLazySearch(value);
}

function isHidden(slug) {
  return state.hiddenSlugs.has(slug);
}

function visibleGraphNodes() {
  return state.nodes.filter((node) => !isHidden(node.slug));
}

function normalizeSearchText(value) {
  return String(value || "").toLowerCase().replace(/[^a-z0-9]+/g, " ").trim();
}

function pickSearchFocus(graph, query) {
  const normalizedQuery = normalizeSearchText(query);
  if (!normalizedQuery) return null;
  const queryTerms = normalizedQuery.split(/\s+/).filter(Boolean);
  const candidates = (graph.nodes || [])
    .filter((node) => !isHidden(node.slug) && matchesQuery(node, normalizedQuery))
    .map((node) => {
      const label = normalizeSearchText(node.label);
      const slug = normalizeSearchText(node.slug);
      const categoryBoost = (node.category || node.type || "").toLowerCase() === "people" ? 25 : 0;
      const exactBoost = label === normalizedQuery || slug === normalizedQuery ? 100 : 0;
      const phraseBoost = label.includes(normalizedQuery) || slug.includes(normalizedQuery) ? 50 : 0;
      const termBoost = queryTerms.every((term) => label.includes(term) || slug.includes(term)) ? 20 : 0;
      return { node, score: exactBoost + phraseBoost + termBoost + categoryBoost + (node.degree || 0) };
    })
    .sort((left, right) => right.score - left.score || (right.node.degree || 0) - (left.node.degree || 0));
  return candidates[0]?.node.slug || null;
}

function updateUiVersion(graph) {
  uiVersion.textContent = graph?.ui_version || UI_VERSION;
}

function buildRuntimeGraph(graph) {
  const width = state.viewport.width || 1200;
  const height = state.viewport.height || 760;
  const categories = [...new Set(graph.nodes.map((node) => node.category || node.type || "entity"))];
  const categoryIndex = new Map(categories.map((category, index) => [category, index]));
  const visibleSpan = Math.min(width, height);
  const cloudRadius = Math.max(170, visibleSpan * 0.28);
  const maxDegree = Math.max(1, graph.stats?.max_degree || 1);
  const nodes = graph.nodes.map((node, index) => {
    const category = node.category || node.type || "entity";
    const bandIndex = categoryIndex.get(category) || 0;
    const bandAngle = (Math.PI * 2 * bandIndex) / Math.max(categories.length, 1);
    const localAngle = index * 2.399963229728653;
    const degreeRatio = (node.degree || 0) / maxDegree;
    const hierarchyDepth = Math.min(3, Math.max(0, (node.slug.match(/\//g) || []).length));
    const radius = cloudRadius * (0.46 + hierarchyDepth * 0.18 + (1 - degreeRatio) * 0.22);
    const categoryPull = cloudRadius * 0.44;
    const x3 = Math.cos(bandAngle) * categoryPull + Math.cos(localAngle) * radius;
    const y3 = Math.sin(localAngle * 0.73) * radius * 0.72;
    const z3 = Math.sin(bandAngle) * categoryPull + Math.sin(localAngle) * radius;
    return {
      ...node,
      category,
      x3,
      y3,
      z3,
      screenX: width / 2,
      screenY: height / 2,
      depth: 0,
      depthScale: 1,
      pulseOffset: Math.random() * Math.PI * 2,
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
  const visibleSlugs = new Set(graph.nodes.filter((node) => !isHidden(node.slug)).map((node) => node.slug));
  const visibleNodes = graph.nodes.filter((node) => visibleSlugs.has(node.slug));
  const visibleEdges = graph.edges.filter((edge) => visibleSlugs.has(edge.source) && visibleSlugs.has(edge.target));
  metricNodes.textContent = visibleNodes.length;
  metricEdges.textContent = visibleEdges.length;
  metricDegree.textContent = Math.max(0, ...visibleNodes.map((node) => node.degree || 0));
  metricCollapsed.textContent = visibleNodes.reduce((sum, node) => sum + (node.parts_count || 0), 0);
}

function updateSource(source) {
  const mode = source.mode || "unknown";
  const status = source.status || "unknown";
  sourceBadge.textContent = `${mode} · ${status}`;
  const coverage = source.coverage || {};
  const expanded = coverage.expanded_slugs?.length || 0;
  const lazyText = source.lazy ? ` ${expanded} node${expanded === 1 ? "" : "s"} expanded lazily.` : "";
  sourceMessage.textContent = `${source.message || "No source note provided."}${lazyText}`;
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
  let hash = 0;
  for (let index = 0; index < value.length; index += 1) {
    hash = (hash * 31 + value.charCodeAt(index)) >>> 0;
  }
  return CATEGORY_PALETTE[hash % CATEGORY_PALETTE.length];
}

function updateCategoryLegend(graph) {
  categoryLegend.innerHTML = "";
  const counts = new Map();
  graph.nodes.forEach((node) => {
    if (isHidden(node.slug)) return;
    const category = node.category || node.type || "entity";
    counts.set(category, (counts.get(category) || 0) + 1);
  });
  [...counts.entries()]
    .sort((left, right) => right[1] - left[1] || left[0].localeCompare(right[0]))
    .forEach(([category, count]) => {
      const item = document.createElement("span");
      const swatch = document.createElement("i");
      swatch.style.backgroundColor = getCategoryColor(category);
      item.appendChild(swatch);
      item.append(`${category} (${count})`);
      categoryLegend.appendChild(item);
    });
}

function setSelectOptions(select, values, currentValue) {
  const nextValues = ["", ...values];
  select.innerHTML = "";
  nextValues.forEach((value) => {
    const option = document.createElement("option");
    option.value = value;
    option.textContent = value || "All";
    select.appendChild(option);
  });
  select.value = nextValues.includes(currentValue) ? currentValue : "";
}

function updateFilterOptions(graph) {
  const categories = new Set();
  const types = new Set();
  graph.nodes.forEach((node) => {
    if (isHidden(node.slug)) return;
    categories.add(node.category || node.type || "entity");
    types.add(node.type || "entity");
  });
  setSelectOptions(categoryFilter, [...categories].sort(), state.filters.category);
  setSelectOptions(typeFilter, [...types].sort(), state.filters.type);
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
  const haystack = [node.slug, node.label, node.type, node.category, node.summary, ...(node.tags || []), ...(node.collapsed_children || []), ...(node.collapsed_aliases || [])]
    .join(" ")
    .toLowerCase();
  const looseHaystack = haystack.replace(/[^a-z0-9]+/g, " ");
  const looseQuery = query.replace(/[^a-z0-9]+/g, " ");
  const queryTerms = looseQuery.split(/\s+/).filter(Boolean);
  const contentTerms = queryTerms.filter((term) => term !== "part" && !/^\d{1,3}$/.test(term));
  return haystack.includes(query)
    || looseHaystack.includes(looseQuery)
    || queryTerms.every((term) => looseHaystack.includes(term))
    || (contentTerms.length > 0 && contentTerms.every((term) => looseHaystack.includes(term)));
}

function applyFilter() {
  const query = state.query.trim().toLowerCase();
  const { category, type, minDegree } = state.filters;
  const matchSlugs = new Set();
  const filteredSlugs = new Set();

  state.nodes.forEach((node) => {
    if (isHidden(node.slug)) return;
    const isMatch = matchesQuery(node, query);
    const passesCategory = !category || (node.category || node.type || "entity") === category;
    const passesType = !type || (node.type || "entity") === type;
    const passesDegree = (node.degree || 0) >= minDegree;
    const passesFilters = passesCategory && passesType && passesDegree;
    if (isMatch) {
      matchSlugs.add(node.slug);
    }
    if (passesFilters && (!state.matchesOnly || isMatch)) {
      filteredSlugs.add(node.slug);
    }
  });

  if (!query) {
    state.nodes.forEach((node) => {
      if (isHidden(node.slug)) return;
      const passesCategory = !category || (node.category || node.type || "entity") === category;
      const passesType = !type || (node.type || "entity") === type;
      const passesDegree = (node.degree || 0) >= minDegree;
      if (passesCategory && passesType && passesDegree) filteredSlugs.add(node.slug);
    });
  }

  state.matchSlugs = matchSlugs;
  state.filteredSlugs = filteredSlugs;

  if (state.focusSlug && !filteredSlugs.has(state.focusSlug)) {
    state.focusSlug = null;
  }
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
  if (isHidden(edge.source.slug) || isHidden(edge.target.slug)) return 0;
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

  const glow = ctx.createRadialGradient(width * 0.5, height * 0.48, 10, width * 0.5, height * 0.48, width * 0.42);
  glow.addColorStop(0, "rgba(143, 124, 255, 0.14)");
  glow.addColorStop(0.5, "rgba(136, 246, 255, 0.05)");
  glow.addColorStop(1, "rgba(4, 8, 18, 0)");
  ctx.fillStyle = glow;
  ctx.fillRect(0, 0, width, height);

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

function drawEdges() {
  state.edges.forEach((edge) => {
    const alpha = edgeAlpha(edge);
    if (alpha <= 0) return;
    const isHoveredFocusEdge = state.focusSlug
      && state.hoverSlug
      && edge.source.slug !== edge.target.slug
      && ((edge.source.slug === state.focusSlug && edge.target.slug === state.hoverSlug)
        || (edge.target.slug === state.focusSlug && edge.source.slug === state.hoverSlug));
    const depthAlpha = Math.max(0.35, Math.min(1.15, (edge.source.depthScale + edge.target.depthScale) / 2));
    ctx.strokeStyle = `rgba(143, 168, 255, ${alpha * depthAlpha})`;
    ctx.lineWidth = isHoveredFocusEdge
      ? 3
      : edge.source.slug === state.focusSlug || edge.target.slug === state.focusSlug || edge.source.slug === state.hoverSlug || edge.target.slug === state.hoverSlug ? 1.8 : 1;
    ctx.beginPath();
    ctx.moveTo(edge.source.screenX, edge.source.screenY);
    ctx.lineTo(edge.target.screenX, edge.target.screenY);
    ctx.stroke();

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
      ctx.font = "700 12px Inter, sans-serif";
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
  if (!text || text === "No summary available.") {
    return "No summary available.";
  }
  return shortLabel(text, 150);
}

function visibleSearchMatches() {
  return state.nodes
    .filter((node) => !isHidden(node.slug) && state.matchSlugs.has(node.slug))
    .sort((left, right) => (right.degree || 0) - (left.degree || 0))
    .slice(0, 5)
    .map((node) => node.slug);
}

function shouldShowLabel(node, topMatches) {
  if (node.slug === state.focusSlug || node.slug === state.hoverSlug) return true;
  if (isLinkedToFocus(node)) return true;
  if (state.query && topMatches.has(node.slug)) return true;
  const threshold = Math.max(8, (state.graph?.stats?.max_degree || 1) * 0.35);
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
  return `${node.category || node.type} · ${node.degree || 0}`;
}

function drawNodes() {
  const now = performance.now();
  const topMatches = new Set(visibleSearchMatches());
  const ordered = [...state.nodes].sort((left, right) => left.depth - right.depth);
  const visibleLabelSlugs = [];
  ordered.forEach((node) => {
    if (isHidden(node.slug)) return;
    const alpha = nodeAlpha(node);
    if (alpha <= 0) return;
    const pulse = 1 + Math.sin(now / 700 + node.pulseOffset) * 0.06;
    const radius = Math.max(3.5, node.size * pulse * node.depthScale);
    const color = getNodeColor(node);

    ctx.save();
    ctx.globalAlpha = alpha;

    const glow = ctx.createRadialGradient(node.screenX, node.screenY, 0, node.screenX, node.screenY, radius * 3.2);
    glow.addColorStop(0, hexToRgba(color, 0.36));
    glow.addColorStop(1, "rgba(0, 0, 0, 0)");
    ctx.fillStyle = glow;
    ctx.beginPath();
    ctx.arc(node.screenX, node.screenY, radius * 3.2, 0, Math.PI * 2);
    ctx.fill();

    ctx.fillStyle = color;
    ctx.beginPath();
    ctx.arc(node.screenX, node.screenY, radius, 0, Math.PI * 2);
    ctx.fill();

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

    if (shouldShowLabel(node, topMatches)) {
      visibleLabelSlugs.push(node.slug);
      const labelX = node.screenX + radius + 8;
      const labelY = node.screenY - radius - 6;
      ctx.fillStyle = "rgba(238, 244, 255, 0.92)";
      ctx.font = "600 12px Inter, sans-serif";
      ctx.fillText(labelForNode(node), labelX, labelY);
    }

    ctx.restore();
  });
  state.visibleLabelSlugs = visibleLabelSlugs;
}

function render() {
  drawBackground();
  tick();
  drawEdges();
  drawNodes();
  state.animationHandle = requestAnimationFrame(render);
}

function setHover(slug) {
  state.hoverSlug = slug;
  const node = slug ? state.nodeMap.get(slug) : null;
  const partText = node?.parts_count ? ` · ${node.parts_count} collapsed parts` : "";
  const reportText = node?.report_count ? ` · ${node.report_count} collapsed reports` : "";
  const linkTypes = node && state.focusSlug && node.slug !== state.focusSlug && isLinkedToFocus(node)
    ? relationshipTypes(state.focusSlug, node.slug)
    : [];
  const relationshipText = linkTypes.length ? ` · relationship: ${linkTypes.join(", ")}` : "";
  hoverLabel.textContent = node
    ? `${node.label} · ${node.category || node.type} · ${node.degree} direct link${node.degree === 1 ? "" : "s"}${partText}${reportText}${relationshipText}`
    : state.focusSlug
      ? "Drag to rotate. Hover or tap for full names. Long-press a node to select."
      : "Search the sky, drag to rotate, tap for details, or long-press a node to select.";
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
  const value = String(url || "").trim();
  if (!value) return "";
  if (/^https?:\/\//i.test(value)) return value;
  if (value.startsWith("/")) return encodeURI(value);
  return `/media/${value.replace(/^\/+/, "").split("/").map(encodeURIComponent).join("/")}`;
}

function cleanMarkdownDestination(value) {
  const text = String(value || "").trim();
  const title = text.match(/^(.+?)\s+"[^"]*"\s*$/);
  return (title ? title[1] : text).trim();
}

function appendTextWithBreaks(parent, text) {
  String(text || "").split(/ {2,}\n|\n/).forEach((part, index) => {
    if (index) parent.appendChild(document.createElement("br"));
    if (part) parent.appendChild(document.createTextNode(part));
  });
}

function appendInlineMarkdown(parent, text) {
  const pattern = /(!?)\[([^\]]+)\]\(([^)]+)\)|\[\[([^\]|]+)(?:\|([^\]]+))?\]\]|`([^`]+)`|\*\*\*([^*]+?)\*\*\*|\*\*([^*]+?)\*\*\*?|\*([^*]+?)\*|__([^_]+?)__|_([^_]+?)_|~~([^~]+?)~~/g;
  let cursor = 0;
  String(text || "").replace(pattern, (match, bang, label, url, wikiTarget, wikiLabel, code, boldItalic, bold, italicStar, boldUnderscore, italicUnderscore, strike, offset) => {
    if (offset > cursor) appendTextWithBreaks(parent, text.slice(cursor, offset));
    if (code !== undefined) {
      const codeNode = document.createElement("code");
      codeNode.textContent = code;
      parent.appendChild(codeNode);
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
      const link = document.createElement("a");
      link.href = `#entity:${encodeURIComponent(wikiTarget.trim())}`;
      link.dataset.entityQuery = wikiTarget.trim();
      link.textContent = (wikiLabel || wikiTarget).trim();
      parent.appendChild(link);
    } else if (bang) {
      const image = document.createElement("img");
      image.src = mediaDisplayUrl(cleanMarkdownDestination(url));
      image.alt = label || "Markdown image";
      image.loading = "lazy";
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
      appendInlineMarkdown(item, bullet[1]);
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
      appendInlineMarkdown(item, ordered[1]);
      list.appendChild(item);
      return;
    }
    closeList();
    const paragraph = document.createElement("p");
    appendInlineMarkdown(paragraph, line);
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
  modalMessage.appendChild(document.createTextNode("Rendered from gbrain markdown. Use "));
  const editButton = document.createElement("button");
  editButton.type = "button";
  editButton.className = "inline-link-button";
  editButton.textContent = "Modify markdown";
  editButton.addEventListener("click", () => {
    void openNodeModal("edit", slug);
  });
  modalMessage.appendChild(editButton);
  modalMessage.appendChild(document.createTextNode(" if you want to edit this page."));
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
    const displayUrl = item.served_url || item.url;
    const canEmbed = Boolean(item.embeddable || item.served_available);
    const card = document.createElement("div");
    card.className = "media-card";
    const label = document.createElement("span");
    label.textContent = `${item.kind || "media"} · ${item.label || item.url}`;
    card.appendChild(label);

    if (canEmbed && item.kind === "image") {
      const image = document.createElement("img");
      image.src = displayUrl;
      image.alt = item.label || "Node media";
      image.loading = "lazy";
      card.appendChild(image);
    } else if (canEmbed && item.kind === "video") {
      const video = document.createElement("video");
      video.src = displayUrl;
      video.controls = true;
      video.playsInline = true;
      card.appendChild(video);
    } else if (canEmbed && item.kind === "audio") {
      const audio = document.createElement("audio");
      audio.src = displayUrl;
      audio.controls = true;
      card.appendChild(audio);
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

function chatHistoryFor(slug, label) {
  if (!state.askChats.has(slug)) {
    state.askChats.set(slug, [
      {
        role: "system",
        content: `Ask GBrain about ${label}. Each question runs against the current node context.`,
      },
    ]);
  }
  return state.askChats.get(slug);
}

function renderAskChat(slug, label) {
  const history = chatHistoryFor(slug, label);
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
    speaker.textContent = message.role === "user" ? "You" : message.role === "assistant" ? "GBrain" : "Context";
    row.appendChild(speaker);

    const bubble = document.createElement("div");
    bubble.className = "chat-bubble";
    bubble.textContent = message.content;
    row.appendChild(bubble);

    modalChatLog.appendChild(row);
  });
  modalChatLog.scrollTop = modalChatLog.scrollHeight;
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
  const targetInput = document.createElement("input");
  targetInput.id = "operationTarget";
  targetInput.setAttribute("list", "operationTargetOptions");
  targetInput.placeholder = "Search by node name or slug";
  appendField(modalForm, "Target entity", targetInput);
  modalForm.appendChild(makeDatalist(
    "operationTargetOptions",
    nodeOptionsExcept(slug),
    (node) => node.slug,
    (node) => `${node.label || node.slug} · ${node.category || node.type || "entity"}`,
  ));

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
  modalPrimaryButton.hidden = false;
  modalPrimaryButton.disabled = false;
  modalCancelButton.hidden = false;
  modalCancelButton.disabled = false;
}

async function openNodeModal(action, slug = state.focusSlug) {
  hideContextMenu();
  if (!slug) return;
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
  modalPrimaryButton.hidden = false;
  modalPrimaryButton.disabled = false;
  modalCancelButton.hidden = false;
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
    const response = await apiGet(`/api/entity-raw/${encodeURIComponent(slug)}`);
    const content = response.ok ? response.data.content : `Unable to load page: ${response.data?.error || response.status}`;
    if (action === "view") {
      renderMarkdownView(content);
    } else {
      modalEditor.value = content;
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
    const response = await apiGet(`/api/entity-media/${encodeURIComponent(slug)}`);
    if (!response.ok) {
      modalMessage.textContent = `Unable to load media: ${response.data?.error || response.status}`;
      return;
    }
    renderMediaItems(response.data.media || []);
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

  if (action === "ask") {
    modalKicker.textContent = "Ask GBrain";
    modalPrimaryButton.textContent = "Send";
    modalMessage.textContent = "Chat with GBrain using this node as context.";
    modalEditor.hidden = true;
    modalChat.hidden = false;
    modalChatInput.value = "";
    renderAskChat(slug, label);
    operationModal.hidden = false;
    modalChatInput.focus();
    return;
  }

  if (action === "backlinks") {
    modalKicker.textContent = "Show backlinks";
    modalPrimaryButton.textContent = "Load backlinks";
    modalMessage.textContent = "Loads incoming gbrain links for this node.";
    modalEditor.value = `slug: ${slug}`;
    modalEditor.readOnly = true;
    operationModal.hidden = false;
    return;
  }

  if (action === "graph-query") {
    modalKicker.textContent = "Graph query from here";
    modalPrimaryButton.textContent = "Run graph query";
    modalMessage.textContent = "Filters typed graph traversal by relationship type, direction, and depth.";
    modalEditor.value = "link_type: \ndirection: both\ndepth: 1";
    operationModal.hidden = false;
    modalEditor.focus();
    return;
  }

  if (action === "history") {
    modalKicker.textContent = "View history";
    modalPrimaryButton.textContent = "Load history";
    modalMessage.textContent = "Loads gbrain page version history for this node.";
    modalEditor.value = `slug: ${slug}`;
    modalEditor.readOnly = true;
    operationModal.hidden = false;
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
    modalEditor.value = "date: YYYY-MM-DD\nsummary: \ndetail: \nsource: ";
    operationModal.hidden = false;
    modalEditor.focus();
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
  if (action === "delete" && modalConfirmInput.value !== label) {
    modalMessage.textContent = `Type the full node name exactly before deleting: ${label}`;
    modalConfirmInput.focus();
    return;
  }
  modalPrimaryButton.disabled = true;
  modalCancelButton.disabled = true;
  const primaryButtonText = modalPrimaryButton.textContent;
  let pendingAskHistory = null;
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
      await loadEntity(slug, { source: "system" });
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
      closeModal();
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
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
      const fields = parseOperationFields(modalEditor.value);
      const response = await apiPost(`/api/entity-timeline/${encodeURIComponent(slug)}`, {
        date: fields.date,
        summary: fields.summary,
        detail: fields.detail,
        source: fields.source,
      });
      if (!response.ok) throw new Error(response.data?.error || `Timeline update failed with ${response.status}`);
      closeModal();
      applyGraphPayload(response.data.graph, slug);
      await loadEntity(slug, { source: "system" });
      return;
    }
    if (action === "ask") {
      const question = modalChatInput.value.trim();
      if (!question) {
        modalMessage.textContent = "Type a question for GBrain first.";
        modalChatInput.focus();
        return;
      }
      const history = chatHistoryFor(slug, label);
      pendingAskHistory = history;
      history.push({ role: "user", content: question });
      history.push({ role: "assistant", content: "Thinking..." });
      renderAskChat(slug, label);
      modalChatInput.value = "";
      modalChatInput.disabled = true;
      modalMessage.textContent = "Asking GBrain...";
      const response = await apiPost(`/api/entity-ask/${encodeURIComponent(slug)}`, {
        question,
      });
      if (!response.ok) throw new Error(response.data?.error || `Ask GBrain failed with ${response.status}`);
      history[history.length - 1] = { role: "assistant", content: response.data.output || "(No output)" };
      renderAskChat(slug, label);
      modalMessage.textContent = "Ask another question or close the chat.";
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
      const fields = parseOperationFields(modalEditor.value);
      const response = await apiPost(`/api/entity-graph-query/${encodeURIComponent(slug)}`, {
        link_type: fields.link_type,
        direction: fields.direction,
        depth: fields.depth,
      });
      if (!response.ok) throw new Error(response.data?.error || `Graph query failed with ${response.status}`);
      state.modalAction = { action: "result", slug, label };
      modalKicker.textContent = "Graph query results";
      modalPrimaryButton.textContent = "Close";
      modalCancelButton.hidden = true;
      modalEditor.readOnly = true;
      modalEditor.value = response.data.output || "(No output)";
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
    if (action === "ask" && pendingAskHistory && pendingAskHistory.at(-1)?.content === "Thinking...") {
      pendingAskHistory[pendingAskHistory.length - 1] = {
        role: "assistant",
        content: `Ask GBrain failed: ${error.message || String(error)}`,
      };
      renderAskChat(slug, label);
    }
    modalMessage.textContent = error.message || String(error);
  } finally {
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
  if (isHidden(slug)) return;
  if (options.source !== "search" && options.source !== "system") {
    state.selectionVersion += 1;
  }
  const loadId = (state.entityLoadId || 0) + 1;
  state.entityLoadId = loadId;
  const requestedNode = state.nodeMap.get(slug);
  const shouldExpand = requestedNode && !requestedNode.expanded;
  state.focusSlug = slug;
  if (requestedNode) {
    detailTitle.textContent = requestedNode.label || slug;
    detailType.textContent = `${requestedNode.category || requestedNode.type || "entity"} · ${shouldExpand ? "loading direct links" : "loading details"}`;
    detailSummary.textContent = shouldExpand
      ? `Loading direct neighbors for ${requestedNode.label || slug}...`
      : `Loading summary for ${requestedNode.label || slug}...`;
    detailLinks.innerHTML = "";
    const loading = document.createElement("span");
    loading.textContent = "Loading direct links...";
    detailLinks.appendChild(loading);
    detailSecondRing.innerHTML = "";
    setHover(slug);
  }
  await ensureExpanded(slug);
  if (loadId !== state.entityLoadId) return;
  const response = await apiGet(`/api/entity/${encodeURIComponent(slug)}`);
  if (!response.ok) return;
  if (loadId !== state.entityLoadId) return;
  const payload = response.data;
  const { entity, neighbors, second_ring: secondRing, source } = payload;
  state.focusSlug = entity.slug;
  detailTitle.textContent = entity.label;
  const partText = entity.parts_count ? ` · ${entity.parts_count} collapsed parts` : "";
  const reportText = entity.report_count ? ` · ${entity.report_count} collapsed reports` : "";
  detailType.textContent = `${entity.category || entity.type} · ${entity.type} · ${entity.degree} direct link${entity.degree === 1 ? "" : "s"}${partText}${reportText}`;
  const collapseNote = [
    entity.parts_count ? `Collapsed ${entity.parts_count} document parts into this entity.` : "",
    entity.report_count ? `Collapsed ${entity.report_count} dated usage reports into this entity.` : "",
  ].filter(Boolean).join(" ");
  detailSummary.textContent = collapseNote
    ? `${entity.summary || "No summary available."} ${collapseNote}`
    : entity.summary || "No summary available.";
  updateSource(source);

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
}

async function focusFallbackNode() {
  const fallback = visibleGraphNodes().sort((left, right) => (right.degree || 0) - (left.degree || 0))[0];
  if (fallback) {
    await loadEntity(fallback.slug);
    return;
  }
  state.focusSlug = null;
  detailTitle.textContent = "No visible node";
  detailType.textContent = "";
  detailSummary.textContent = "Use the Hidden List to show nodes again.";
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
}

function cancelCanvasDrag() {
  state.drag.active = false;
  state.drag.pointerId = null;
  canvas.style.cursor = "default";
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
  searchInput.addEventListener("input", (event) => {
    state.query = event.target.value;
    applyFilter();
  });

  searchInput.addEventListener("keydown", (event) => {
    if (event.key !== "Enter") return;
    event.preventDefault();
    void submitSearch();
  });

  searchButton.addEventListener("click", () => {
    void submitSearch();
  });

  modalMarkdown.addEventListener("click", (event) => {
    const link = event.target.closest("a[data-entity-query]");
    if (!link) return;
    event.preventDefault();
    void searchEntityLink(link.dataset.entityQuery);
  });

  matchesOnlyToggle.addEventListener("change", (event) => {
    state.matchesOnly = event.target.checked;
    applyFilter();
  });

  categoryFilter.addEventListener("change", (event) => {
    state.filters.category = event.target.value;
    applyFilter();
  });

  typeFilter.addEventListener("change", (event) => {
    state.filters.type = event.target.value;
    applyFilter();
  });

  minDegreeFilter.addEventListener("input", (event) => {
    state.filters.minDegree = Math.max(0, Number.parseInt(event.target.value, 10) || 0);
    applyFilter();
  });

  clearFiltersButton.addEventListener("click", () => {
    state.filters = { category: "", type: "", minDegree: 0 };
    categoryFilter.value = "";
    typeFilter.value = "";
    minDegreeFilter.value = "0";
    applyFilter();
  });

  refreshButton.addEventListener("click", async () => {
    await fetchGraph("/api/refresh", { preserveFocus: true });
  });

  autoRefreshToggle.addEventListener("change", (event) => {
    state.autoRefresh.enabled = event.target.checked;
    scheduleAutoRefresh();
  });

  autoRefreshInterval.addEventListener("change", () => {
    scheduleAutoRefresh();
  });

  zoomOutButton.addEventListener("click", () => {
    zoomBy(-1);
  });

  zoomInButton.addEventListener("click", () => {
    zoomBy(1);
  });

  nodeMenuButton.addEventListener("click", (event) => {
    const rect = event.currentTarget.getBoundingClientRect();
    showContextMenu(state.focusSlug, rect.left, rect.bottom + 6);
  });

  contextMenu.addEventListener("click", (event) => {
    const button = event.target.closest("button");
    if (!button) return;
    const action = button.dataset.action;
    const slug = state.menuSlug || state.focusSlug;
    if (action === "copy") {
      void copySlug(slug);
      return;
    }
    if (action === "hide") {
      void hideNode(slug);
      return;
    }
    void openNodeModal(action, slug);
  });

  modalCloseButton.addEventListener("click", closeModal);
  modalCancelButton.addEventListener("click", closeModal);
  modalPrimaryButton.addEventListener("click", () => {
    void runModalPrimaryAction();
  });

  window.addEventListener("click", (event) => {
    if (!contextMenu.hidden && !contextMenu.contains(event.target) && event.target !== nodeMenuButton) {
      hideContextMenu();
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
    resizeCanvas();
    if (state.graph) {
      buildRuntimeGraph(state.graph);
    }
  });
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
    if (state.focusSlug) {
      await loadEntity(state.focusSlug, { source: "system" });
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
  uiVersion.textContent = UI_VERSION;
  setZoom(state.zoom);
  await fetchHidden();
  await fetchGraph();
  if (!state.animationHandle) {
    render();
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
  labelForNode,
  relationshipTypes,
  submitSearch,
  setHover,
  renderMarkdownView,
  searchEntityLink,
};
window.__TGKS__ = window.__MEMORY_STARGRAPH__;
