/* dir-forensics viewer — fetches artifacts and renders interactive dashboard */

const CASE = window.CASE || "";
const BASE = window.DEMO_BASE || "";

// ── state ──
let _cache = {};

async function fetchJSON(artifact) {
  const url = `${BASE}/${CASE}-${artifact}.json`;
  if (_cache[url]) return _cache[url];
  try {
    const r = await fetch(url, { headers: { Accept: "application/json" } });
    if (!r.ok) return null;
    const data = await r.json();
    _cache[url] = data;
    return data;
  } catch { return null; }
}

// ── tabs ──
document.querySelectorAll(".tab").forEach(tab => {
  tab.addEventListener("click", () => {
    document.querySelectorAll(".tab").forEach(t => t.classList.remove("active"));
    document.querySelectorAll(".tab-panel").forEach(p => p.classList.remove("active"));
    tab.classList.add("active");
    document.getElementById(`tab-${tab.dataset.tab}`).classList.add("active");
    const renderer = renderers[tab.dataset.tab];
    if (renderer) renderer();
  });
});

// ── utils ──
function fmtBytes(b) {
  if (!b || b < 1024) return `${b || 0} B`;
  if (b < 1e6) return `${(b / 1024).toFixed(1)} KB`;
  if (b < 1e9) return `${(b / 1e6).toFixed(1)} MB`;
  if (b < 1e12) return `${(b / 1e9).toFixed(1)} GB`;
  return `${(b / 1e12).toFixed(2)} TB`;
}
function fmtNum(n) { return (n || 0).toLocaleString(); }
function el(tag, cls, html) { const e = document.createElement(tag); if (cls) e.className = cls; if (html !== undefined) e.innerHTML = html; return e; }
function escapeHtml(s) { const d = document.createElement("div"); d.textContent = s; return d.innerHTML; }

// ── renderers ──
const renderers = {
  overview: renderOverview,
  tree: renderTree,
  flags: renderFlags,
  ext: renderExtensions,
  depth: renderDepth,
  dupes: renderDupes,
};

// OVERVIEW
async function renderOverview() {
  const stats = await fetchJSON("stats");
  const tier0 = await fetchJSON("tier0");
  if (!stats) { document.getElementById("overview-cards").innerHTML = '<p class="empty">No stats artifact found.</p>'; return; }

  const s = stats.stats || stats;
  const cards = [
    { label: "Directories", value: fmtNum(s.dirs) },
    { label: "Files", value: fmtNum(s.files) },
    { label: "Total Size", value: fmtBytes(s.bytes) },
    { label: "Avg File Size", value: s.files ? fmtBytes(Math.round(s.bytes / s.files)) : "—" },
  ];
  document.getElementById("overview-cards").innerHTML = "";
  cards.forEach(c => {
    const card = el("div", "card");
    card.appendChild(el("div", "label", c.label));
    card.appendChild(el("div", "value", c.value));
    document.getElementById("overview-cards").appendChild(card);
  });

  if (tier0) {
    const panel = document.getElementById("tier0-panel");
    const t = tier0.stats || tier0;
    panel.innerHTML = `
      <div class="card">
        <h3>Tier 0 Deduplication</h3>
        <div class="tier0-stat"><span>Raw files</span><span>${fmtNum(t.raw_files || t.files)}</span></div>
        <div class="tier0-stat"><span>Exact duplicates dropped</span><span>${fmtNum(t.exact_dupe_files_dropped || t.exact_dupes_dropped || "—")}</span></div>
        <div class="tier0-stat"><span>Near duplicates dropped</span><span>${fmtNum(t.near_dupe_files_dropped || t.near_dupes_dropped || "—")}</span></div>
        <div class="tier0-stat"><span>Logical files (after dedup)</span><span>${fmtNum(t.logical_files || "—")}</span></div>
        <div class="tier0-stat"><span>Reduction</span><span>${t.reduction_pct ? t.reduction_pct.toFixed(1) + "%" : "—"}</span></div>
        <div class="tier0-stat"><span>Wasted bytes</span><span>${fmtBytes(t.exact_dupe_bytes_wasted || t.exact_dupe_bytes || t.wasted_bytes || 0)}</span></div>
      </div>`;
  }
}

// TREE
async function renderTree() {
  const tree = await fetchJSON("tree");
  if (!tree) { document.getElementById("tree-container").innerHTML = '<p class="empty">No tree artifact found.</p>'; return; }

  // tree is either [name, count, bytes, children[]] or {label, source, tree:[...]}
  let root = tree.tree || tree;
  const container = document.getElementById("tree-container");
  container.innerHTML = "";
  renderTreeNode(root, container, 0);

  document.getElementById("tree-filter").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    container.querySelectorAll(".tree-node").forEach(n => {
      const match = !q || n.textContent.toLowerCase().includes(q);
      n.style.display = match ? "" : "none";
    });
  });
}

function renderTreeNode(node, parent, depth) {
  // node = [name, fileCount, bytes, children[]]
  const [name, fileCount, bytes, children] = Array.isArray(node) ? node :
    [node.name, node.files || node.file_count, node.bytes || node.total_bytes, node.children];

  const wrapper = el("div", "tree-node-wrapper");
  const row = el("div", "tree-node");
  const hasChildren = children && children.length > 0;
  if (hasChildren) {
    const toggle = el("span", "tree-toggle", "▶");
    row.appendChild(toggle);
  } else {
    row.appendChild(el("span", "tree-toggle"));
  }
  row.appendChild(el("span", "tree-label", escapeHtml(name)));
  row.appendChild(el("span", "tree-count", `${fmtNum(fileCount)} files · ${fmtBytes(bytes)}`));
  wrapper.appendChild(row);

  if (hasChildren) {
    const childWrap = el("div", "tree-children");
    childWrap.style.display = "none";
    children.forEach(c => renderTreeNode(c, childWrap, depth + 1));
    wrapper.appendChild(childWrap);

    row.onclick = () => {
      const isHidden = childWrap.style.display === "none";
      childWrap.style.display = isHidden ? "" : "none";
      row.querySelector(".tree-toggle").textContent = isHidden ? "▼" : "▶";
    };
  }
  parent.appendChild(wrapper);
}

// FLAGS
async function renderFlags() {
  const flags = await fetchJSON("flags");
  if (!flags) { document.getElementById("flags-chart").innerHTML = '<p class="empty">No flags artifact found.</p>'; return; }

  const cats = flags.categories || {};
  const total = flags.total || Object.values(cats).reduce((s, c) => s + (c.count || (Array.isArray(c) ? c.length : 0)), 0);
  const entries = Object.entries(cats).map(([name, c]) => ({
    name, count: c.count !== undefined ? c.count : (Array.isArray(c) ? c.length : 0),
    severity: c.severity, color: c.color
  })).sort((a, b) => b.count - a.count);

  // chart
  const maxCount = Math.max(...entries.map(e => e.count), 1);
  const chart = document.getElementById("flags-chart");
  chart.innerHTML = `<div style="margin-bottom:0.5rem;font-weight:600">${fmtNum(total)} flagged files · ${entries.length} categories</div>`;
  entries.forEach(e => {
    const row = el("div", "flag-row");
    row.appendChild(el("span", "flag-cat", escapeHtml(e.name)));
    const track = el("div", "bar-track");
    const fill = el("span", "bar-fill");
    fill.style.width = `${(e.count / maxCount) * 100}%`;
    if (e.color) fill.style.background = e.color;
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "flag-count", fmtNum(e.count)));
    chart.appendChild(row);
  });

  // table
  const table = document.getElementById("flags-table");
  if (flags.files && flags.files.length > 0) {
    table.innerHTML = `<table class="flag-table"><thead><tr><th>Flag</th><th>Severity</th><th>Path</th></tr></thead><tbody>${
      flags.files.slice(0, 500).map(f => `<tr><td><strong>${escapeHtml(f.flag || "")}</strong></td><td><span class="severity severity-${(f.severity || "").toLowerCase()}">${escapeHtml(f.severity || "")}</span></td><td style="font-family:monospace;font-size:0.8rem">${escapeHtml(f.path || "")}</td></tr>`).join("")
    }</tbody></table>`;
    if (flags.files.length > 500) table.innerHTML += `<p class="empty">Showing 500 of ${fmtNum(flags.files.length)} flagged files.</p>`;
  }
}

// EXTENSIONS
async function renderExtensions() {
  const ext = await fetchJSON("extensions");
  if (!ext) { document.getElementById("ext-chart").innerHTML = '<p class="empty">No extensions artifact found.</p>'; return; }

  let extensions = ext.extensions || ext;
  const total = ext.total_extensions || extensions.length;

  // chart: top 25 by file count
  const sorted = [...extensions].sort((a, b) => (b.files || b.count) - (a.files || a.count)).slice(0, 25);
  const maxCount = Math.max(...sorted.map(e => e.files || e.count), 1);
  const chart = document.getElementById("ext-chart");
  chart.innerHTML = `<div style="margin-bottom:0.5rem;font-weight:600">${total} extensions · top 25 by file count</div>`;
  sorted.forEach(e => {
    const count = e.files || e.count;
    const bytes = e.bytes || e.total_bytes || 0;
    const row = el("div", "bar-row");
    row.appendChild(el("span", "bar-label", `.${e.ext || e.extension}`));
    const track = el("div", "bar-track");
    const fill = el("span", "bar-fill");
    fill.style.width = `${(count / maxCount) * 100}%`;
    fill.style.background = "var(--accent-2)";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "bar-value", `${fmtNum(count)} files · ${fmtBytes(bytes)}`));
    chart.appendChild(row);
  });

  // table
  const table = document.getElementById("ext-table");
  table.innerHTML = `<table><thead><tr><th>Extension</th><th>Files</th><th>Bytes</th></tr></thead><tbody>${
    sorted.map(e => `<tr><td><code>.${e.ext || e.extension}</code></td><td>${fmtNum(e.files || e.count)}</td><td>${fmtBytes(e.bytes || e.total_bytes || 0)}</td></tr>`).join("")
  }</tbody></table>`;

  document.getElementById("ext-filter").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    table.querySelectorAll("tbody tr").forEach(tr => {
      tr.style.display = tr.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
}

// DEPTH
async function renderDepth() {
  const depth = await fetchJSON("depth");
  if (!depth) { document.getElementById("depth-chart").innerHTML = '<p class="empty">No depth artifact found.</p>'; return; }

  const levels = depth.levels || [];
  const maxFiles = Math.max(...levels.map(l => l.files), 1);
  const chart = document.getElementById("depth-chart");
  chart.innerHTML = `<div style="margin-bottom:0.5rem;font-weight:600">${depth.max_depth || levels.length} levels</div>`;
  levels.forEach(l => {
    const row = el("div", "bar-row");
    row.appendChild(el("span", "bar-label", `L${l.depth}`));
    const track = el("div", "bar-track");
    const fill = el("span", "bar-fill");
    fill.style.width = `${(l.files / maxFiles) * 100}%`;
    fill.style.background = "var(--green)";
    track.appendChild(fill);
    row.appendChild(track);
    row.appendChild(el("span", "bar-value", `${fmtNum(l.files)} files · ${fmtBytes(l.bytes)}`));
    chart.appendChild(row);
  });

  const table = document.getElementById("depth-table");
  table.innerHTML = `<table><thead><tr><th>Level</th><th>Directories</th><th>Files</th><th>Bytes</th></tr></thead><tbody>${
    levels.map(l => `<tr><td>L${l.depth}</td><td>${fmtNum(l.dirs)}</td><td>${fmtNum(l.files)}</td><td>${fmtBytes(l.bytes)}</td></tr>`).join("")
  }</tbody></table>`;
}

// DUPLICATES
async function renderDupes() {
  const dupes = await fetchJSON("duplicates");
  if (!dupes) { document.getElementById("dupes-summary").innerHTML = '<p class="empty">No duplicates artifact found.</p>'; return; }

  const groups = dupes.groups || [];
  document.getElementById("dupes-summary").innerHTML = `
    <div class="grid" style="margin-bottom:1rem">
      <div class="card"><div class="label">Duplicate Groups</div><div class="value">${fmtNum(dupes.total_dupe_keys || groups.length)}</div></div>
      <div class="card"><div class="label">Duplicate Files</div><div class="value">${fmtNum(dupes.total_dupe_files || groups.reduce((s,g)=>s+(g.count||0),0))}</div></div>
      <div class="card"><div class="label">Wasted Bytes</div><div class="value">${fmtBytes(dupes.wasted_bytes_estimate || 0)}</div></div>
    </div>`;

  const list = document.getElementById("dupes-list");
  const sorted = [...groups].sort((a, b) => (b.count || 0) - (a.count || 0)).slice(0, 200);
  list.innerHTML = sorted.map(g => {
    const paths = (g.paths || []).slice(0, 3);
    const more = (g.paths || []).length > 3 ? ` +${g.paths.length - 3} more` : "";
    return `<div class="dupe-group"><span class="name">${escapeHtml(g.name)}</span><span class="count">${g.count || paths.length} copies</span>${
      paths.map(p => `<div class="path">${escapeHtml(p)}</div>`).join("")}${more}</div>`;
  }).join("");

  if (groups.length > 200) list.innerHTML += `<p class="empty">Showing top 200 of ${fmtNum(groups.length)} duplicate groups.</p>`;

  document.getElementById("dupes-filter").addEventListener("input", (e) => {
    const q = e.target.value.toLowerCase();
    list.querySelectorAll(".dupe-group").forEach(dg => {
      dg.style.display = dg.textContent.toLowerCase().includes(q) ? "" : "none";
    });
  });
}

// ── init ──
renderOverview();
