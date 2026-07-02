"use strict";

// ---- constants ------------------------------------------------------------
const TYPE_COLORS = {
  Commit: "#a371f7",
  File: "#3fb950",
  PullRequest: "#2f81f7",
  Issue: "#db6d28",
  Person: "#f778ba",
  Message: "#56d364",
  Module: "#7d8590",
  Decision: "#e3b341",
};
const colorFor = (t) => TYPE_COLORS[t] || "#7d8590";

let API_KEY = localStorage.getItem("repomind_key") || "";
let askGraph = null;
let fullGraph = null;

// ---- helpers --------------------------------------------------------------
const $ = (id) => document.getElementById(id);

function toast(msg, kind = "") {
  const el = $("toast");
  el.textContent = msg;
  el.className = "toast " + kind;
  setTimeout(() => el.classList.add("hidden"), 3200);
}

async function api(path, { method = "GET", body } = {}) {
  const headers = { "X-API-Key": API_KEY };
  if (body) headers["Content-Type"] = "application/json";
  const res = await fetch(path, { method, headers, body: body ? JSON.stringify(body) : undefined });
  if (res.status === 401) throw new ApiError("Invalid or missing API key", res.status);
  if (res.status === 403) throw new ApiError("Your key lacks the required scope for this action", res.status);
  if (res.status === 429) throw new ApiError("Rate limit exceeded - slow down", res.status);
  if (res.status === 503) throw new ApiError("Server has no API keys configured", res.status);
  if (!res.ok) throw new ApiError("Request failed (" + res.status + ")", res.status);
  return res.json();
}
class ApiError extends Error {
  constructor(message, status) { super(message); this.status = status; }
}

function setStatus(ok, text) {
  $("statusDot").className = "dot " + (ok === null ? "dot-idle" : ok ? "dot-ok" : "dot-err");
  $("statusText").textContent = text;
}

function renderCounts(counts) {
  if (!counts) { $("countsBar").textContent = ""; return; }
  const by = counts.by_type || {};
  const parts = Object.entries(by).map(([k, v]) => `${k}: <b>${v}</b>`);
  parts.push(`edges: <b>${counts.edges}</b>`);
  if (counts.tombstoned) parts.push(`tombstoned: <b>${counts.tombstoned}</b>`);
  $("countsBar").innerHTML = parts.join(" &nbsp;|&nbsp; ");
}

// ---- connection -----------------------------------------------------------
async function connect() {
  API_KEY = $("apiKey").value.trim();
  if (!API_KEY) { toast("Enter an API key first", "err"); return; }
  localStorage.setItem("repomind_key", API_KEY);
  try {
    const h = await api("/health");
    setStatus(true, "Connected");
    renderCounts(h.counts);
    toast("Connected", "ok");
  } catch (e) {
    setStatus(false, e.message);
    toast(e.message, "err");
  }
}

function clearKey() {
  API_KEY = "";
  localStorage.removeItem("repomind_key");
  $("apiKey").value = "";
  setStatus(null, "Not connected");
  renderCounts(null);
  toast("Key forgotten");
}

// ---- tabs -----------------------------------------------------------------
function initTabs() {
  document.querySelectorAll(".tab").forEach((tab) => {
    tab.addEventListener("click", () => {
      document.querySelectorAll(".tab").forEach((t) => t.classList.remove("tab-active"));
      document.querySelectorAll(".panel").forEach((p) => p.classList.add("hidden"));
      tab.classList.add("tab-active");
      $("tab-" + tab.dataset.tab).classList.remove("hidden");
      if (tab.dataset.tab === "graph" && fullGraph) fullGraph.zoomToFit(400, 40);
    });
  });
}

// ---- graph rendering ------------------------------------------------------
function buildGraph(container, data) {
  const nodes = data.nodes.map((n) => ({ ...n }));
  const ids = new Set(nodes.map((n) => n.id));
  const links = data.edges
    .filter((e) => ids.has(e.src) && ids.has(e.dst))
    .map((e) => ({ source: e.src, target: e.dst, type: e.type }));

  const g = ForceGraph()(container)
    .backgroundColor("rgba(0,0,0,0)")
    .graphData({ nodes, links })
    .nodeRelSize(5)
    .nodeVal((n) => (n.status === "deleted" ? 3 : 6))
    .linkColor(() => "rgba(125,133,144,0.45)")
    .linkDirectionalArrowLength(4)
    .linkDirectionalArrowRelPos(1)
    .linkCurvature(0.06)
    .linkLabel((l) => l.type)
    .nodeCanvasObject((node, ctx, scale) => {
      const r = (node.status === "deleted" ? 4 : 6);
      ctx.beginPath();
      ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
      ctx.fillStyle = colorFor(node.type);
      ctx.globalAlpha = node.status === "deleted" ? 0.4 : 1;
      ctx.fill();
      ctx.globalAlpha = 1;
      if (node.status === "deleted") {
        ctx.strokeStyle = "#f85149";
        ctx.setLineDash([2, 2]);
        ctx.stroke();
        ctx.setLineDash([]);
      }
      if (scale > 1.3) {
        const label = (node.title || node.id).slice(0, 28);
        ctx.font = `${11 / scale}px ui-monospace, monospace`;
        ctx.fillStyle = "#c9d1d9";
        ctx.textAlign = "center";
        ctx.fillText(label, node.x, node.y + r + 9 / scale);
      }
    })
    .onNodeHover((n) => { container.style.cursor = n ? "pointer" : ""; })
    .onNodeClick((n) => toast(`${n.type}: ${n.title}`));
  setTimeout(() => g.zoomToFit(400, 40), 300);
  return g;
}

function legend(el, types) {
  el.innerHTML = types
    .map((t) => `<span><span class="dot" style="background:${colorFor(t)}"></span>${t}</span>`)
    .join("");
}

// ---- ask ------------------------------------------------------------------
async function ask() {
  const q = $("question").value.trim();
  if (!q) { toast("Type a question", "err"); return; }
  try {
    const r = await api("/ask", { method: "POST", body: { question: q } });
    $("question").value = "";  // clear the box after a successful ask
    $("askResult").classList.remove("hidden");
    $("answerQuestion").textContent = r.question;
    $("answerText").innerHTML = formatAnswer(r.answer || "");
    renderSeeds(r.seeds || []);
    const facts = r.facts || [];
    $("factsHead").innerHTML = facts.length
      ? `<span class="facts-title">Traversal &mdash; ${facts.length} hop${facts.length > 1 ? "s" : ""}</span>`
      : "";
    $("answerFacts").innerHTML = facts
      .map((f, i) => `<div class="fact"><span class="fact-num">${i + 1}</span><span class="fact-text">${formatAnswer(f)}</span></div>`)
      .join("");
    const sg = r.subgraph || { nodes: [], edges: [] };
    $("subgraphMeta").textContent = `${sg.nodes.length} nodes / ${sg.edges.length} edges`;
    const cont = $("subgraph");
    cont.innerHTML = "";
    if (sg.nodes.length) {
      askGraph = buildGraph(cont, sg);
      askGraph.width(cont.clientWidth).height(cont.clientHeight);
      legend($("legendAsk"), [...new Set(sg.nodes.map((n) => n.type))]);
    }
  } catch (e) {
    handleErr(e);
  }
}

// ---- graph explorer -------------------------------------------------------
async function loadGraph() {
  try {
    const data = await api("/graph");
    renderCounts(data.counts);
    const showDel = $("showDeleted").checked;
    const filtered = {
      nodes: data.nodes.filter((n) => showDel || n.status !== "deleted"),
      edges: data.edges,
    };
    $("graphMeta").textContent = `${filtered.nodes.length} nodes / ${filtered.edges.length} edges`;
    const cont = $("fullGraph");
    cont.innerHTML = "";
    fullGraph = buildGraph(cont, filtered);
    fullGraph.width(cont.clientWidth).height(cont.clientHeight);
    legend($("legendFull"), [...new Set(filtered.nodes.map((n) => n.type))]);
  } catch (e) {
    handleErr(e);
  }
}

// ---- ingest ---------------------------------------------------------------
async function ingest() {
  const body = {
    id: $("msgId").value.trim(),
    author: $("msgAuthor").value.trim(),
    channel: $("msgChannel").value.trim(),
    content: $("msgText").value.trim(),
  };
  if (!body.id) { toast("Message ID is required", "err"); return; }
  try {
    const r = await api("/ingest/message", { method: "POST", body });
    toast(r.status === "ok" ? `Ingested (${r.node_id})` : "Error: " + r.reason, r.status === "ok" ? "ok" : "err");
  } catch (e) { handleErr(e); }
}

// ---- admin ----------------------------------------------------------------
async function doSync() {
  try {
    const r = await api("/sync", {
      method: "POST",
      body: { scope: $("syncScope").value, mode: $("syncFull").checked ? "full" : "incremental" },
    });
    showAdmin(r);
    toast("Sync complete", "ok");
  } catch (e) { handleErr(e); }
}
async function doVerify() {
  try {
    const r = await api("/verify", { method: "POST", body: { scope: $("syncScope").value } });
    showAdmin(r);
    toast(r.consistent ? "Graph consistent" : "Discrepancies found", r.consistent ? "ok" : "err");
  } catch (e) { handleErr(e); }
}
async function doForget() {
  const target = $("forgetTarget").value.trim();
  if (!target) { toast("Enter a node id", "err"); return; }
  try {
    const r = await api("/forget", { method: "POST", body: { target } });
    showAdmin(r);
    toast(r.forgotten ? "Forgotten" : "Node not found", r.forgotten ? "ok" : "err");
  } catch (e) { handleErr(e); }
}
function showAdmin(obj) {
  const el = $("adminOut");
  el.classList.remove("hidden");
  el.textContent = JSON.stringify(obj, null, 2);
}

// ---- misc -----------------------------------------------------------------
function handleErr(e) {
  if (e.status === 401 || e.status === 503) setStatus(false, e.message);
  toast(e.message, "err");
}
function escapeHtml(s) {
  return s.replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
}

// Highlight node-type keywords and 'quoted titles' in answer/fact text so the
// report reads as structured entities rather than a wall of prose.
function formatAnswer(text) {
  let s = escapeHtml(text || "");
  s = s.replace(/'([^']+)'/g, '<span class="ent-title">$1</span>');
  const types = Object.keys(TYPE_COLORS).sort((a, b) => b.length - a.length);
  const re = new RegExp("\\b(" + types.join("|") + ")\\b", "g");
  s = s.replace(re, (m) => `<span class="ent" style="--ent:${colorFor(m)}">${m}</span>`);
  return s;
}

// Render the seed nodes the answer is grounded on as colored chips.
function renderSeeds(seeds) {
  const el = $("answerSeeds");
  if (!seeds.length) { el.innerHTML = ""; return; }
  el.innerHTML =
    '<span class="seeds-label">Grounded on</span>' +
    seeds
      .slice(0, 8)
      .map((s) => {
        const title = (s.title || s.id || "").slice(0, 42);
        return `<span class="seed-chip" title="${escapeHtml(s.id || "")}"><span class="dot" style="background:${colorFor(s.type)}"></span>${escapeHtml(title)}</span>`;
      })
      .join("");
}

// ---- graph controls (zoom / fit / fullscreen) -----------------------------
const graphByName = (name) => (name === "ask" ? askGraph : fullGraph);
const wrapByName = (name) => (name === "ask" ? $("subgraphWrap") : $("fullGraphWrap"));
const canvasByName = (name) => (name === "ask" ? $("subgraph") : $("fullGraph"));

function graphAction(name, act) {
  const g = graphByName(name);
  if (!g) { toast("Load a graph first", "err"); return; }
  if (act === "in") g.zoom(g.zoom() * 1.4, 250);
  else if (act === "out") g.zoom(g.zoom() / 1.4, 250);
  else if (act === "fit") g.zoomToFit(400, 40);
  else if (act === "full") toggleFullscreen(name);
}

function toggleFullscreen(name) {
  const wrap = wrapByName(name);
  if (!document.fullscreenElement) {
    (wrap.requestFullscreen || wrap.webkitRequestFullscreen)?.call(wrap);
  } else {
    (document.exitFullscreen || document.webkitExitFullscreen)?.call(document);
  }
}

// Keep the active graph sized to its container on fullscreen enter/exit + resize.
function resizeActiveGraphs() {
  ["ask", "full"].forEach((name) => {
    const g = graphByName(name);
    const cont = canvasByName(name);
    if (g && cont && cont.clientWidth) {
      g.width(cont.clientWidth).height(cont.clientHeight);
      setTimeout(() => g.zoomToFit(400, 40), 60);
    }
  });
}

// ---- wire up --------------------------------------------------------------
window.addEventListener("DOMContentLoaded", () => {
  initTabs();
  if (API_KEY) { $("apiKey").value = API_KEY; connect(); }

  $("connectBtn").onclick = connect;
  $("clearKeyBtn").onclick = clearKey;
  $("apiKey").addEventListener("keydown", (e) => e.key === "Enter" && connect());

  $("askBtn").onclick = ask;
  $("question").addEventListener("keydown", (e) => e.key === "Enter" && ask());
  document.querySelectorAll(".chip").forEach((c) =>
    c.addEventListener("click", () => { $("question").value = c.dataset.q; ask(); })
  );

  $("loadGraphBtn").onclick = loadGraph;
  $("showDeleted").addEventListener("change", loadGraph);
  $("ingestBtn").onclick = ingest;
  $("syncBtn").onclick = doSync;
  $("verifyBtn").onclick = doVerify;
  $("forgetBtn").onclick = doForget;

  // Graph zoom / fit / fullscreen controls (delegated).
  document.querySelectorAll(".gbtn").forEach((b) =>
    b.addEventListener("click", () => graphAction(b.dataset.g, b.dataset.act))
  );
  document.addEventListener("fullscreenchange", resizeActiveGraphs);
  document.addEventListener("webkitfullscreenchange", resizeActiveGraphs);
  window.addEventListener("resize", resizeActiveGraphs);
});
