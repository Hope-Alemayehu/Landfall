/* Landfall website: reads the circuit, calls /api/analyze and draws the report. No framework, no build step. */
(() => {
  "use strict";

  // Paste the Qollab project URL here; every "Run it on Qollab" link uses it.
  const QOLLAB_URL = "#";

  const STRATEGIES = ["qiskit_o1", "qiskit_o3", "zx_teleport", "zx_full"];
  const COLORS = { qiskit_o1: "#2a78d6", qiskit_o3: "#eb6834", zx_teleport: "#1baf7a", zx_full: "#eda100" };
  const LABELS = { qiskit_o1: "Qiskit O1", qiskit_o3: "Qiskit O3", zx_teleport: "ZX teleport", zx_full: "ZX full" };
  const BASELINE = "qiskit_o3";
  const DEVICES = [
    { key: "fake_kolkata", api: "kolkata", label: "IBM Kolkata", short: "Kolkata", abbr: "Kolk.", family: "Falcon r5", native: "CX", topology: "heavy-hex", icon: "hex" },
    { key: "fake_sherbrooke", api: "sherbrooke", label: "IBM Sherbrooke", short: "Sherbrooke", abbr: "Sherb.", family: "Eagle r3", native: "ECR", topology: "heavy-hex", icon: "hex" },
    { key: "fake_fez", api: "fez", label: "IBM Fez", short: "Fez", abbr: "Fez", family: "Heron r2", native: "CZ", topology: "heavy-hex", icon: "hex" },
    { key: "fake_miami", api: "miami", label: "IBM Miami", short: "Miami", abbr: "Miami", family: "Nighthawk r1", native: "CZ", topology: "square lattice", icon: "square" },
    { key: "ionq_forte", api: "ionq", label: "IonQ Forte", short: "IonQ Forte", abbr: "IonQ", family: "Trapped ion", native: "ZZ", topology: "all-to-all", icon: "ring" },
  ];
  const DEVICE = Object.fromEntries(DEVICES.map((d) => [d.key, d]));
  const FALLBACK_PRESETS = ["qft5", "toffoli", "adder", "grover3", "random_ct"].map((name) => ({ name, description: "" }));
  const QISKIT_EXAMPLE = [
    "from qiskit import QuantumCircuit",
    "from math import pi",
    "",
    "# GHZ state, then a phase on every qubit",
    "qc = QuantumCircuit(5)",
    "qc.h(0)",
    "for i in range(4):",
    "    qc.cx(i, i + 1)",
    "for i in range(5):",
    "    qc.rz(pi / 2 ** (i + 1), i)",
    "qc.ccx(0, 2, 4)",
    "qc.measure_all()",
  ].join("\n");
  const MAX_FILE_BYTES = 200 * 1024;
  const U = 40; // chip-view pixels per grid unit
  const reducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

  const state = {
    source: "preset", // "preset" | "qasm" | "qiskit"
    preset: "adder",
    devices: new Set(DEVICES.map((d) => d.key)),
    result: null,
    sel: null, // { device, strategy }
    opt: BASELINE,
    wholeChip: false,
    busy: false,
  };

  const $ = (id) => document.getElementById(id);

  // DOM helpers: text always goes in through textContent ---------------------------------------
  function h(tag, attrs, ...children) {
    const node = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null) continue;
      if (k.startsWith("aria-")) { node.setAttribute(k, String(v)); continue; } // aria-pressed="false" matters
      if (v === false) continue;
      if (k === "class") node.className = v;
      else if (k === "text") node.textContent = v;
      else if (k.startsWith("on")) node.addEventListener(k.slice(2), v);
      else if (k === "vars") for (const [name, val] of Object.entries(v)) node.style.setProperty(name, val);
      else node.setAttribute(k, v === true ? "" : String(v));
    }
    for (const c of children.flat()) {
      if (c == null || c === false) continue;
      node.append(c instanceof Node ? c : document.createTextNode(String(c)));
    }
    return node;
  }
  const SVGNS = "http://www.w3.org/2000/svg";
  function svg(tag, attrs) {
    const node = document.createElementNS(SVGNS, tag);
    for (const [k, v] of Object.entries(attrs || {})) if (v != null) node.setAttribute(k, String(v));
    return node;
  }

  // formatting --------------------------------------------------------------------------------
  function pts(v) {
    const r = Math.round(v * 10) / 10;
    return r === 0 ? "0.0" : (r > 0 ? "+" : "") + r.toFixed(1);
  }
  const fmt3 = (v) => v.toFixed(3);
  const plural = (n, word) => `${n.toLocaleString()} ${word}${n === 1 ? "" : "s"}`;

  function mix(a, b, t) {
    const pa = a.match(/\w\w/g).map((x) => parseInt(x, 16));
    const pb = b.match(/\w\w/g).map((x) => parseInt(x, 16));
    return "#" + pa.map((x, i) => Math.round(x + (pb[i] - x) * t).toString(16).padStart(2, "0")).join("");
  }
  function diverging(v, lim) {
    const t = Math.min(1, Math.abs(v) / lim);
    return mix("#f0efec", v < 0 ? "#e34948" : "#2a78d6", t);
  }

  // data access -------------------------------------------------------------------------------
  function rowFor(device, strategy) {
    return state.result && state.result.rows.find((r) => r.device === device && r.strategy === strategy);
  }
  function strategiesIn(result) {
    return STRATEGIES.filter((s) => result.rows.some((r) => r.strategy === s));
  }
  function label(s) {
    return (state.result && state.result.strategies && state.result.strategies[s] && state.result.strategies[s].label) || LABELS[s];
  }
  function deltaPts(device, strategy) {
    const row = rowFor(device, strategy), base = rowFor(device, BASELINE);
    return row && base ? 100 * (row.success - base.success) : null;
  }

  // tooltip -----------------------------------------------------------------------------------
  const tip = $("tooltip");
  function showTip(target, content, point) {
    tip.replaceChildren(content);
    tip.hidden = false;
    const r = target.getBoundingClientRect();
    const tw = tip.offsetWidth, th = tip.offsetHeight;
    let x = point ? point.x + 14 : r.left + r.width / 2 - tw / 2;
    let y = point ? point.y + 16 : r.top - th - 10;
    if (!point && y < 8) y = r.bottom + 10;
    if (point && y + th > window.innerHeight - 8) y = point.y - th - 12;
    x = Math.max(8, Math.min(x, window.innerWidth - tw - 8));
    tip.style.left = `${x}px`;
    tip.style.top = `${Math.max(8, y)}px`;
  }
  let tipFocus = null; // { node, build } while a tooltip is open because of keyboard focus
  function hideTip() { tip.hidden = true; }
  function bindTip(node, build, follow) {
    node.addEventListener("pointerenter", (e) => showTip(node, build(), follow ? { x: e.clientX, y: e.clientY } : null));
    if (follow) node.addEventListener("pointermove", (e) => showTip(node, build(), { x: e.clientX, y: e.clientY }));
    node.addEventListener("pointerleave", hideTip);
    node.addEventListener("focus", () => { tipFocus = { node, build }; showTip(node, build()); });
    node.addEventListener("blur", () => { tipFocus = null; hideTip(); });
  }
  function rowTip(row, valueText) {
    return h("div", null,
      h("span", { class: "tt-value", text: valueText }),
      h("span", { class: "tt-title" }, h("i", { class: "tt-line", vars: { "--c": COLORS[row.strategy] } }),
        `${row.device_label}, ${label(row.strategy)}`),
      h("span", { class: "tt-rows" },
        "2Q gates", h("b", { text: row.two_q }),
        "routing", h("b", { text: row.routing_2q }),
        "depth", h("b", { text: row.depth }),
        "est. success", h("b", { text: fmt3(row.success) })));
  }
  window.addEventListener("scroll", () => {
    // focusing an off-screen cell scrolls the page: keep that tooltip, just move it along
    if (tipFocus && document.activeElement === tipFocus.node) showTip(tipFocus.node, tipFocus.build());
    else hideTip();
  }, { passive: true });

  // input -------------------------------------------------------------------------------------
  function topoIcon(kind) {
    const s = svg("svg", { class: "topo", viewBox: "0 0 30 30", "aria-hidden": "true" });
    if (kind === "hex") {
      const pts6 = [0, 1, 2, 3, 4, 5].map((i) => [15 + 10 * Math.cos(Math.PI / 3 * i + Math.PI / 6), 15 + 10 * Math.sin(Math.PI / 3 * i + Math.PI / 6)]);
      s.append(svg("polygon", { class: "e", points: pts6.map((p) => p.join(",")).join(" ") }));
      pts6.forEach(([x, y]) => s.append(svg("circle", { class: "n", cx: x, cy: y, r: 2.6 })));
    } else if (kind === "square") {
      for (const v of [6, 15, 24]) {
        s.append(svg("line", { class: "e", x1: 6, y1: v, x2: 24, y2: v }));
        s.append(svg("line", { class: "e", x1: v, y1: 6, x2: v, y2: 24 }));
      }
      for (const x of [6, 15, 24]) for (const y of [6, 15, 24]) s.append(svg("circle", { class: "n", cx: x, cy: y, r: 2.4 }));
    } else {
      const ring = [0, 1, 2, 3, 4, 5, 6, 7].map((i) => [15 + 11 * Math.cos(Math.PI / 4 * i), 15 + 11 * Math.sin(Math.PI / 4 * i)]);
      [[0, 3], [1, 5], [2, 6], [4, 7]].forEach(([a, b]) => s.append(svg("line", { class: "e", x1: ring[a][0], y1: ring[a][1], x2: ring[b][0], y2: ring[b][1] })));
      ring.forEach(([x, y]) => s.append(svg("circle", { class: "n", cx: x, cy: y, r: 2.4 })));
    }
    return s;
  }

  function renderDeviceToggles() {
    $("devices").replaceChildren(...DEVICES.map((d) => {
      const btn = h("button", {
        type: "button", class: "device-toggle", "aria-pressed": state.devices.has(d.key),
        "aria-label": `${d.label}, ${d.family}, native ${d.native}, ${d.topology}`,
        onclick: () => {
          if (state.devices.has(d.key) && state.devices.size === 1) return setStatus("Keep at least one device selected.");
          state.devices.has(d.key) ? state.devices.delete(d.key) : state.devices.add(d.key);
          btn.setAttribute("aria-pressed", state.devices.has(d.key));
        },
      }, topoIcon(d.icon), h("span", null, h("span", { class: "name", text: d.label }), h("span", { class: "sub", text: `${d.native}, ${d.topology}` })));
      return btn;
    }));
  }

  async function loadPresets() {
    let presets = FALLBACK_PRESETS;
    try {
      const res = await fetch("/api/presets");
      if (res.ok) presets = await res.json();
    } catch (_) { /* the fallback list still works */ }
    $("presets").replaceChildren(...presets.map((p) => h("button", {
      type: "button", class: "pill", "data-preset": p.name, title: p.description || null,
      "aria-pressed": state.source === "preset" && state.preset === p.name,
      onclick: () => { state.source = "preset"; state.preset = p.name; syncSource(); analyze(); },
    }, p.name)));
  }

  function syncSource() {
    for (const chip of document.querySelectorAll(".pill")) {
      chip.setAttribute("aria-pressed", state.source === "preset" && chip.dataset.preset === state.preset);
    }
    const what = state.source === "preset" ? state.preset : state.source === "qasm" ? "QASM" : "Qiskit code";
    $("analyze").textContent = `Analyze ${what}`;
  }

  function selectTab(name, focus) {
    for (const t of ["qasm", "qiskit"]) {
      const tab = $(`tab-${t}`), on = t === name;
      tab.setAttribute("aria-selected", on);
      tab.tabIndex = on ? 0 : -1;
      $(`panel-${t}`).hidden = !on;
      if (on && focus) tab.focus();
    }
    state.source = name;
    syncSource();
  }

  function initInput() {
    $("qiskit").value = QISKIT_EXAMPLE;
    for (const t of ["qasm", "qiskit"]) {
      $(`tab-${t}`).addEventListener("click", () => selectTab(t));
      $(t).addEventListener("input", () => { state.source = t; syncSource(); });
    }
    $("tab-qasm").parentElement.addEventListener("keydown", (e) => {
      if (e.key === "ArrowRight" || e.key === "ArrowLeft") {
        selectTab($("tab-qasm").getAttribute("aria-selected") === "true" ? "qiskit" : "qasm", true);
        e.preventDefault();
      }
    });

    const zone = $("dropzone");
    zone.addEventListener("dragover", (e) => { e.preventDefault(); zone.classList.add("is-over"); });
    zone.addEventListener("dragleave", () => zone.classList.remove("is-over"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      zone.classList.remove("is-over");
      if (e.dataTransfer.files.length) readFile(e.dataTransfer.files[0]);
    });
    $("qasm-file").addEventListener("change", (e) => { if (e.target.files.length) readFile(e.target.files[0]); e.target.value = ""; });

    $("analyze").addEventListener("click", analyze);
    document.addEventListener("keydown", (e) => {
      if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); analyze(); }
    });
    $("whole-chip").addEventListener("change", (e) => { state.wholeChip = e.target.checked; renderChip(true); });
    for (const link of document.querySelectorAll(".qollab-link")) link.href = QOLLAB_URL;
  }

  function readFile(file) {
    if (file.size > MAX_FILE_BYTES) return showError(`${file.name} is larger than 200 KB.`);
    const reader = new FileReader();
    reader.onload = () => { $("qasm").value = reader.result; selectTab("qasm"); setStatus(`Loaded ${file.name}.`); };
    reader.onerror = () => showError(`Could not read ${file.name}.`);
    reader.readAsText(file);
  }

  // analysis request --------------------------------------------------------------------------
  function setStatus(text, busy) {
    const el = $("status");
    el.textContent = text;
    el.classList.toggle("is-busy", !!busy);
  }
  function showError(message) {
    const el = $("error");
    el.replaceChildren(h("strong", { text: "Could not analyze. " }), message);
    el.hidden = false;
  }

  async function analyze() {
    if (state.busy) return;
    const body = { devices: DEVICES.filter((d) => state.devices.has(d.key)).map((d) => d.api) };
    if (state.source === "preset") body.preset = state.preset;
    else {
      const text = $(state.source).value.trim();
      if (!text) return showError(state.source === "qasm" ? "Paste OpenQASM, drop a .qasm file or pick a preset." : "Paste Qiskit code or pick a preset.");
      body[state.source] = text;
    }
    state.busy = true;
    $("analyze").disabled = true;
    $("error").hidden = true;
    $("results").classList.add("is-stale");
    const what = body.preset || (state.source === "qasm" ? "your QASM" : "your Qiskit code");
    setStatus(`Analyzing ${what} on ${plural(body.devices.length, "device")}. The first request after a quiet spell takes a few extra seconds while the server starts.`, true);
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), 120000);
    const t0 = performance.now();
    try {
      const res = await fetch("/api/analyze", {
        method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal: controller.signal,
      });
      let data = null;
      try { data = await res.json(); } catch (_) { /* a platform error page, not JSON */ }
      if (!res.ok || !data) {
        const detail = data && data.detail ? data.detail
          : res.status === 504 ? "The analysis took too long. Try fewer devices or a smaller circuit."
          : `The server returned an error (HTTP ${res.status}).`;
        throw new Error(detail);
      }
      state.result = data;
      render(data);
      $("example-note").hidden = true;
      setStatus(`Analyzed in ${((performance.now() - t0) / 1000).toFixed(1)} s.`);
    } catch (err) {
      setStatus("");
      showError(err.name === "AbortError" ? "The request timed out." : err.message || "The request failed. Check your connection and try again.");
    } finally {
      clearTimeout(timer);
      state.busy = false;
      $("analyze").disabled = false;
      $("results").classList.remove("is-stale");
    }
  }

  // render ------------------------------------------------------------------------------------
  function defaultSelection(r) {
    // the device where the strategies differ most, at its best strategy
    let pick = null, spread = -1;
    for (const d of r.devices) {
      const ok = r.rows.filter((x) => x.device === d).map((x) => x.success);
      if (ok.length && Math.max(...ok) - Math.min(...ok) > spread) { spread = Math.max(...ok) - Math.min(...ok); pick = d; }
    }
    return pick ? { device: pick, strategy: r.best[pick] || BASELINE } : null;
  }

  function render(r) {
    $("results").hidden = false;
    const keep = state.sel && rowFor(state.sel.device, state.sel.strategy);
    state.sel = keep ? state.sel : defaultSelection(r);
    if (!r.optimized_qasm[state.opt]) state.opt = Object.keys(r.optimized_qasm)[0];
    renderVerdict(r);
    renderGrid(r);
    renderChip(false);
    renderBars(r);
    renderCards(r);
    renderOutputs(r);
    renderTable(r);
  }

  function renderVerdict(r) {
    const name = r.circuit === "custom" ? "Your circuit" : r.circuit;
    $("circuit-meta").textContent = `${name}, ${plural(r.num_qubits, "qubit")}, ${plural(r.input.gates, "gate")}, ${plural(r.devices.length, "device")}`;
    const [headline, ...rest] = r.verdict;
    $("headline").textContent = headline || "";
    const deviceLabels = DEVICES.map((d) => d.label);
    const isDevice = (line) => deviceLabels.some((l) => line.startsWith(`${l}:`));
    $("findings").replaceChildren(...rest.filter((l) => !isDevice(l)).map((l) => h("li", { text: l })));
    $("device-verdicts").replaceChildren(...rest.filter(isDevice).map((l) => {
      const i = l.indexOf(":");
      return h("li", null, h("strong", { text: l.slice(0, i + 1) }), l.slice(i + 1));
    }));
  }

  function renderGrid(r) {
    const grid = $("grid");
    const strategies = strategiesIn(r);
    grid.style.setProperty("--cols", r.devices.length);
    const deltas = [];
    for (const d of r.devices) for (const s of strategies) if (s !== BASELINE) { const v = deltaPts(d, s); if (v != null) deltas.push(Math.abs(v)); }
    const lim = Math.max(1, ...deltas);
    const cells = [h("div", { class: "g-corner" })];
    for (const d of r.devices) {
      cells.push(h("div", { class: "g-head" }, h("span", { class: "long", text: DEVICE[d].short }),
        h("span", { class: "abbr", text: DEVICE[d].abbr }), h("span", { class: "sub", text: DEVICE[d].native })));
    }
    for (const s of strategies) {
      cells.push(h("div", { class: "g-row" }, h("i", { class: "key", vars: { "--c": COLORS[s] } }), label(s)));
      for (const d of r.devices) {
        const row = rowFor(d, s);
        if (!row) { cells.push(h("div", { class: "g-empty", "aria-label": `${label(s)} on ${DEVICE[d].label}: not available` })); continue; }
        const v = deltaPts(d, s), isBase = s === BASELINE, isBest = r.best[d] === s;
        const value = isBase ? "baseline" : v == null ? "n/a" : pts(v);
        const dark = !isBase && v != null && Math.abs(v) > 0.6 * lim;
        const cell = h("button", {
          type: "button", class: "g-cell", "data-device": d, "data-strategy": s,
          "aria-pressed": isSelected(d, s),
          "aria-label": `${row.device_label}, ${label(s)}: ${isBase ? "Qiskit O3 baseline" : `${value} points vs Qiskit O3`}${isBest ? ", best on this device" : ""}. ` +
            `${row.two_q} two-qubit gates, ${row.routing_2q} from routing, depth ${row.depth}, estimated success ${fmt3(row.success)}.`,
          onclick: () => select(d, s),
        }, isBase ? h("span", { class: "g-base" }, h("span", { class: "long", text: "baseline" }), h("span", { class: "abbr", text: "ref" }))
          : h("span", { class: "g-val", text: value }), isBest ? h("span", { class: "g-best", text: "best" }) : null);
        cell.style.background = isBase || v == null ? "#f0efec" : diverging(v, lim);
        cell.style.color = dark ? "#ffffff" : "#1f1b16";
        bindTip(cell, () => rowTip(row, isBase ? "Qiskit O3 baseline" : `${value} pts vs Qiskit O3`));
        cells.push(cell);
      }
    }
    grid.replaceChildren(...cells);
    $("scale").replaceChildren(h("span", { text: `${pts(-lim)} worse` }), h("span", { class: "bar" }), h("span", { text: `${pts(lim)} better` }));
  }

  function isSelected(d, s) { return !!state.sel && state.sel.device === d && state.sel.strategy === s; }

  function select(device, strategy) {
    const sameDevice = state.sel && state.sel.device === device;
    state.sel = { device, strategy };
    for (const el of document.querySelectorAll(".g-cell, .bar-row")) {
      el.setAttribute("aria-pressed", isSelected(el.dataset.device, el.dataset.strategy));
    }
    renderChip(sameDevice);
    renderCompiled(state.result);
  }

  // chip view ---------------------------------------------------------------------------------
  const geometryCache = new Map();
  function geometry(key) {
    if (!geometryCache.has(key)) {
      geometryCache.set(key, fetch(`devices/${key}.json`).then((res) => {
        if (!res.ok) throw new Error(`no geometry for ${key}`);
        return res.json();
      }));
    }
    return geometryCache.get(key);
  }

  const chip = { device: null, qubits: [], labels: [], used: null, hits: null, view: null, raf: 0, token: 0 };

  function buildChipBase(geo) {
    const root = $("chip");
    root.replaceChildren();
    const P = geo.coords.map(([x, y]) => [x * U, y * U]);
    const edges = svg("g");
    const center = [P.reduce((a, p) => a + p[0], 0) / P.length, P.reduce((a, p) => a + p[1], 0) / P.length];
    if (geo.all_to_all) {
      edges.append(svg("circle", { class: "ring-guide", cx: center[0], cy: center[1], r: Math.hypot(P[0][0] - center[0], P[0][1] - center[1]) }));
    }
    for (const [a, b] of geo.edges) edges.append(svg("line", { class: "edge", x1: P[a][0], y1: P[a][1], x2: P[b][0], y2: P[b][1] }));
    const used = svg("g"), qubits = svg("g"), labels = svg("g"), hits = svg("g");
    chip.qubits = P.map(([x, y]) => { const c = svg("circle", { class: "q", cx: x, cy: y, r: 6 }); qubits.append(c); return c; });
    chip.labels = P.map(([x, y], i) => {
      const t = svg("text", { class: i >= 100 ? "ql ql3" : "ql", x, y });
      t.textContent = i;
      labels.append(t);
      return t;
    });
    root.append(edges, used, qubits, labels, hits);
    Object.assign(chip, { device: geo.key, points: P, center, used, hits, geo });
  }

  function viewFor(points, pad, minW, minH) {
    const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
    let x0 = Math.min(...xs) - pad, x1 = Math.max(...xs) + pad, y0 = Math.min(...ys) - pad, y1 = Math.max(...ys) + pad;
    const grow = (lo, hi, min) => { const extra = Math.max(0, min - (hi - lo)) / 2; return [lo - extra, hi + extra]; };
    [x0, x1] = grow(x0, x1, minW);
    [y0, y1] = grow(y0, y1, minH);
    // match the box's aspect ratio so the figure never letterboxes or jumps in height
    const box = $("chip").getBoundingClientRect();
    const ratio = box.width > 0 && box.height > 0 ? box.width / box.height : 16 / 9;
    if ((x1 - x0) / (y1 - y0) < ratio) [x0, x1] = grow(x0, x1, (y1 - y0) * ratio);
    else [y0, y1] = grow(y0, y1, (x1 - x0) / ratio);
    return [x0, y0, x1 - x0, y1 - y0];
  }

  function keepOnChip(view, points, pad) {
    // slide a zoomed window so it shows chip rather than empty space past the chip's edge
    const xs = points.map((p) => p[0]), ys = points.map((p) => p[1]);
    const [x0, x1, y0, y1] = [Math.min(...xs) - pad, Math.max(...xs) + pad, Math.min(...ys) - pad, Math.max(...ys) + pad];
    let [x, y, w, hgt] = view;
    x = w <= x1 - x0 ? Math.min(Math.max(x, x0), x1 - w) : (x0 + x1 - w) / 2;
    y = hgt <= y1 - y0 ? Math.min(Math.max(y, y0), y1 - hgt) : (y0 + y1 - hgt) / 2;
    return [x, y, w, hgt];
  }

  function setView(target, animate) {
    const root = $("chip");
    cancelAnimationFrame(chip.raf);
    const from = chip.view;
    const apply = (v) => { chip.view = v; root.setAttribute("viewBox", v.map((n) => n.toFixed(2)).join(" ")); };
    if (!animate || !from || reducedMotion) return apply(target);
    const t0 = performance.now(), dur = 420;
    const step = (now) => {
      const k = Math.min(1, (now - t0) / dur), e = k < 0.5 ? 2 * k * k : 1 - Math.pow(-2 * k + 2, 2) / 2;
      apply(from.map((f, i) => f + (target[i] - f) * e));
      if (k < 1) chip.raf = requestAnimationFrame(step);
    };
    chip.raf = requestAnimationFrame(step);
  }

  async function renderChip(animate) {
    renderChipSwitcher();
    const sel = state.sel;
    if (!sel) return;
    const token = ++chip.token;
    let geo;
    try { geo = await geometry(sel.device); } catch (_) {
      $("chip").replaceChildren();
      $("chip-caption").textContent = "The chip map for this device is not available.";
      return;
    }
    if (token !== chip.token) return;
    const row = rowFor(sel.device, sel.strategy);
    if (!row) return;
    const newDevice = chip.device !== geo.key;
    if (newDevice) { buildChipBase(geo); chip.view = null; }

    const usedSet = new Set(row.qubits_used);
    chip.qubits.forEach((c, i) => {
      const on = usedSet.has(i);
      c.classList.toggle("used", on);
      c.setAttribute("r", on ? 12 : 6); // the CSS r property animates it where supported
    });
    chip.labels.forEach((t, i) => t.classList.toggle("shown", usedSet.has(i)));

    const P = chip.points;
    const usage = Object.entries(row.edge_usage).map(([k, n]) => [k.split("-").map(Number), n]).sort((a, b) => a[1] - b[1]);
    const max = Math.max(1, ...usage.map((u) => u[1]));
    const lines = [], hits = [];
    const ring = !!geo.all_to_all;
    const apexes = []; // where the bowed couplings peak, so the zoom keeps them in frame
    const link = (cls, a, b) => {
      if (!ring) return svg("line", { class: cls, x1: P[a][0], y1: P[a][1], x2: P[b][0], y2: P[b][1] });
      // all-to-all: bow each coupling toward the ring's center, like a chord diagram
      const [cx, cy] = chip.center, mx = (P[a][0] + P[b][0]) / 2, my = (P[a][1] + P[b][1]) / 2;
      const qx = cx + 0.3 * (mx - cx), qy = cy + 0.3 * (my - cy);
      if (cls === "used-edge") apexes.push([(mx + qx) / 2, (my + qy) / 2]);
      return svg("path", { class: cls, d: `M${P[a][0]} ${P[a][1]} Q${qx} ${qy} ${P[b][0]} ${P[b][1]}` });
    };
    for (const [[a, b], n] of usage) {
      const t = n / max;
      const line = link("used-edge", a, b);
      line.style.stroke = mix("#d6b494", "#4a2812", t);
      line.style.strokeWidth = String(ring ? 2 + 4 * t : 3 + 7 * t);
      lines.push(line);
      const hit = link("hit hit-line", a, b);
      hit.setAttribute("stroke-width", 18);
      bindTip(hit, () => h("div", null, h("span", { class: "tt-value", text: plural(n, "two-qubit gate") }),
        h("span", { class: "tt-title", text: `Coupler ${a}-${b}` })), true);
      hits.push(hit);
    }
    for (const q of row.qubits_used) {
      const hit = svg("circle", { class: "hit", cx: P[q][0], cy: P[q][1], r: 16 });
      const gates = usage.filter(([[a, b]]) => a === q || b === q).reduce((s, u) => s + u[1], 0);
      bindTip(hit, () => h("div", null, h("span", { class: "tt-value", text: `Qubit ${q}` }),
        h("span", { class: "tt-title", text: `${plural(gates, "two-qubit gate")} touch it` })), true);
      hits.push(hit);
    }
    chip.used.replaceChildren(...lines);
    chip.hits.replaceChildren(...hits);

    const usedPoints = row.qubits_used.map((q) => P[q]);
    const zoom = !state.wholeChip && usedPoints.length > 0;
    const target = zoom ? keepOnChip(viewFor(usedPoints.concat(apexes), U * 1.3, U * 7, U * 4), P, U * 0.9) : viewFor(P, U * 0.9, 0, 0);
    setView(target, animate && !newDevice);

    const d = DEVICE[row.device] || { label: row.device_label, family: row.family, native: row.native_2q, topology: row.topology };
    const busiest = usage.length ? usage[usage.length - 1] : null;
    $("chip-caption").replaceChildren(
      h("strong", { text: `${d.label}, ${label(row.strategy)}. ` }),
      `${d.family}, native ${d.native} gate, ${d.topology}. ${plural(row.two_q, "two-qubit gate")}, ` +
      `${row.routing_2q} of them routing overhead; ${row.qubits_used.length} of ${geo.num_qubits} qubits used` +
      (busiest ? `; busiest coupler ${busiest[0][0]}-${busiest[0][1]} with ${plural(busiest[1], "gate")}.` : "."));
  }

  function renderChipSwitcher() {
    const r = state.result;
    if (!r || !state.sel) return;
    $("chip-strategies").replaceChildren(...strategiesIn(r).map((s) => h("button", {
      type: "button", "aria-pressed": state.sel.strategy === s, disabled: !rowFor(state.sel.device, s),
      onclick: () => select(state.sel.device, s),
    }, h("i", { class: "key", vars: { "--c": COLORS[s] } }), label(s))));
  }

  // gate-cost bars ----------------------------------------------------------------------------
  function renderBars(r) {
    const strategies = strategiesIn(r);
    $("bars-legend").replaceChildren(
      ...strategies.map((s) => h("span", null, h("i", { class: "key", vars: { "--c": COLORS[s] } }), label(s))),
      h("span", null, h("i", { class: "swatch-solid" }), "circuit's own 2Q gates"),
      h("span", null, h("i", { class: "swatch-hatch" }), "routing (SWAP) overhead"));
    const max = Math.max(1, ...r.rows.map((x) => x.two_q));
    $("bars").replaceChildren(...r.devices.map((d) => h("div", { class: "bar-group" },
      h("h3", { text: DEVICE[d] ? DEVICE[d].label : d }),
      h("p", { class: "sub", text: DEVICE[d] ? `${DEVICE[d].native}, ${DEVICE[d].topology}` : "" }),
      ...strategies.map((s) => {
        const row = rowFor(d, s);
        if (!row) return null;
        const own = row.two_q - row.routing_2q;
        const btn = h("button", {
          type: "button", class: "bar-row", "data-device": d, "data-strategy": s, "aria-pressed": isSelected(d, s),
          "aria-label": `${row.device_label}, ${label(s)}: ${row.two_q} two-qubit gates, ${own} from the circuit and ${row.routing_2q} from routing.`,
          onclick: () => select(d, s),
        },
        h("span", { class: "bar-label" }, h("i", { class: "key", vars: { "--c": COLORS[s] } }), label(s)),
        h("span", { class: "bar-area" },
          h("span", { class: "seg-own", style: `width:${(100 * own / max).toFixed(2)}%`, vars: { "--c": COLORS[s] } }),
          row.routing_2q ? h("span", { class: "seg-route", style: `width:${(100 * row.routing_2q / max).toFixed(2)}%`, vars: { "--c": COLORS[s] } }) : null,
          h("span", { class: "bar-val", text: row.two_q })));
        bindTip(btn, () => rowTip(row, `${plural(row.two_q, "two-qubit gate")}`));
        return btn;
      }))));
  }

  // metric cards ------------------------------------------------------------------------------
  function renderCards(r) {
    const metric = (name, before, after) => {
      const d = after - before;
      return [h("dt", { text: name }), h("dd", null, `${before} → ${after}`, h("span", { class: "delta", text: d === 0 ? "" : d > 0 ? `+${d}` : `${d}` }))];
    };
    $("cards").replaceChildren(...strategiesIn(r).filter((s) => r.logical[s]).map((s) => {
      const m = r.logical[s], check = r.equivalent[s] || {};
      const method = check.method === "exact" ? "exact check" : `${check.method || "unknown"} check`;
      return h("article", { class: "card" },
        h("div", { class: "card-head" }, h("i", { class: "key", vars: { "--c": COLORS[s] } }), h("h3", { text: label(s) })),
        h("p", { class: "card-desc", text: (r.strategies[s] && r.strategies[s].description) || "" }),
        h("dl", null, metric("2Q gates", r.input.two_q, m.two_q), metric("T / non-Clifford", r.input.t, m.t), metric("Depth", r.input.depth, m.depth)),
        check.ok
          ? h("p", { class: "verified ok" }, h("span", { class: "mark", text: "✓ Verified" }), `equivalent (${method})`)
          : h("p", { class: "verified bad" }, h("span", { class: "mark", text: "✕ Not equivalent" }), `(${method})`));
    }));
  }

  // outputs -----------------------------------------------------------------------------------
  function download(name, text, type) {
    const url = URL.createObjectURL(new Blob([text], { type: type || "text/plain" }));
    const a = h("a", { href: url, download: name });
    document.body.append(a);
    a.click();
    a.remove();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
  }
  async function copy(button, text) {
    try {
      await navigator.clipboard.writeText(text);
    } catch (_) {
      const area = h("textarea", { style: "position:fixed;opacity:0" });
      area.value = text;
      document.body.append(area);
      area.select();
      document.execCommand("copy");
      area.remove();
    }
    const old = button.textContent;
    button.textContent = "Copied";
    setTimeout(() => { button.textContent = old; }, 1400);
  }

  function renderOutputs(r) {
    $("opt-strategies").replaceChildren(...Object.keys(r.optimized_qasm).map((s) => h("button", {
      type: "button", "aria-pressed": state.opt === s,
      onclick: () => { state.opt = s; renderOutputs(state.result); },
    }, h("i", { class: "key", vars: { "--c": COLORS[s] } }), label(s))));
    $("opt-code").textContent = r.optimized_qasm[state.opt] || "";
    renderCompiled(r);
  }

  function renderCompiled(r) {
    if (!r || !state.sel) return;
    const row = rowFor(state.sel.device, state.sel.strategy);
    $("compiled-for").textContent = row ? `for ${row.device_label}, ${label(row.strategy)}` : "";
    const omitted = r.compiled_qasm_omitted || !row || row.compiled_qasm == null;
    $("compiled-code").hidden = omitted;
    $("compiled-omitted").hidden = !omitted;
    $("compiled-actions").hidden = omitted;
    $("compiled-code").textContent = omitted ? "" : row.compiled_qasm;
  }

  function fileStem() { return state.result.circuit.replace(/[^\w-]+/g, "_"); }

  function qollabReport(r) {
    // the same shape as Qollab's landfall_<circuit>.json
    return {
      circuit: r.circuit, num_qubits: r.num_qubits, input: r.input, logical: r.logical, equivalent: r.equivalent,
      rows: r.rows.map(({ compiled_qasm, ...rest }) => rest), devices: r.devices, elapsed_s: r.elapsed_s,
      verdict: r.verdict, hardware_check: null,
    };
  }

  function initOutputs() {
    $("opt-copy").addEventListener("click", (e) => copy(e.currentTarget, $("opt-code").textContent));
    $("opt-download").addEventListener("click", () => download(`${fileStem()}_${state.opt}.qasm`, $("opt-code").textContent));
    $("compiled-copy").addEventListener("click", (e) => copy(e.currentTarget, $("compiled-code").textContent));
    $("compiled-download").addEventListener("click", () => {
      const row = rowFor(state.sel.device, state.sel.strategy);
      download(`${fileStem()}_${row.strategy}_${row.device.replace("fake_", "")}.qasm`, row.compiled_qasm);
    });
    $("download-json").addEventListener("click", () => {
      download(`landfall_${fileStem()}.json`, JSON.stringify(qollabReport(state.result), null, 2), "application/json");
    });
  }

  function renderTable(r) {
    const head = ["Device", "Strategy", "2Q gates", "Routing", "Depth", "2Q depth", "Est. success", "vs Qiskit O3"];
    const body = [];
    for (const d of r.devices) {
      for (const s of strategiesIn(r)) {
        const row = rowFor(d, s);
        if (!row) continue;
        const v = deltaPts(d, s);
        body.push(h("tr", null,
          h("td", { text: row.device_label }),
          h("td", { text: label(s) + (r.best[d] === s ? " (best)" : "") }),
          h("td", { text: row.two_q }), h("td", { text: row.routing_2q }), h("td", { text: row.depth }),
          h("td", { text: row.two_q_depth }), h("td", { text: fmt3(row.success) }),
          h("td", { text: s === BASELINE ? "baseline" : v == null ? "n/a" : `${pts(v)} pts` })));
      }
    }
    $("table").replaceChildren(h("thead", null, h("tr", null, head.map((t) => h("th", { scope: "col", text: t })))), h("tbody", null, body));
  }

  // start ---------------------------------------------------------------------------------------
  window.addEventListener("resize", () => { if (state.result && state.sel) renderChip(false); });
  renderDeviceToggles();
  initInput();
  initOutputs();
  syncSource();
  loadPresets();
  loadExample();

  async function loadExample() {
    // the adder preset, precomputed by scripts/export_example.py: instant first paint, no cold start
    try {
      const res = await fetch("data/adder.json");
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const data = await res.json();
      if (state.result) return; // a live analysis finished first
      state.result = data;
      render(data);
      $("example-note").hidden = false;
    } catch (_) {
      analyze();
    }
  }
})();
