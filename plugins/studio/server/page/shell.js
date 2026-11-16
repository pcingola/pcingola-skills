/*
 * Studio shell: the left column, the Claude column, the version detail view with marking,
 * the theme and the connection to the studio server. Shared by every workspace skill.
 *
 * The left column lists the kinds of project of /api/config; a kind's workspace is the module of its `skill`, so
 * one module serves several kinds. A workspace module registers once and draws the centre column:
 *
 *   Studio.register({
 *     id: "images",                 // workspace skill, the `skill` of the kinds of /api/config it serves
 *     tag(kind),                    // label next to the project title for a kind id; "<tag> projects" in the left column
 *     open(el, project, kind),      // draw the workspace of the kind id `kind` into el: a project, or null for a blank
 *                                   //   workspace whose first `generate` (project null) creates the project
 *     update(project),              // the open project's files changed, or the blank workspace became a project:
 *                                   //   redraw what depends on them and keep what the user is editing
 *     askPlaceholder: "...",        // optional: placeholder of the Claude input box
 *     versionNoun: "film",          // optional: what `versions` of /api/projects counts; "version" by default
 *     onEvent(event),               // optional: every server event, after the shell handled it, and three of the
 *                                   //   shell: {kind: "pending"} when its request bookkeeping changed (a request
 *                                   //   sent, the session reset before a replay), {kind: "reconnected"} after a
 *                                   //   reconnect, {kind: "autonomy"} when the user switched the mode
 *     describe(request),            // optional: {text, images} of a request for the Claude column
 *     versionInfo(version),         // rows [[label, text or node, long?], ...] of the detail view
 *     detailActions(version),       // buttons [{label, run(version), disabled?, title?}, ...] after "Send"
 *     changeFields(version),        // optional: fields added to the `change`, `variations` and `other-styles`
 *                                   //   requests and the /api/marked body
 *     detailTitle(version),         // optional: title of the detail view; "<project name> · v<N>" by default
 *   });
 *
 * In open(), a module that has one main action puts it in the bar at the bottom of the centre column with
 * Studio.actionBar({label, run, more}); it answers {summary(text), error(text), enable(on)}. `more`, optional, is a
 * second {label, run} shown as a secondary button after the main one. The buttons are disabled while a run() runs
 * and while enable(false) holds; a second call replaces the bar.
 *
 * Helpers shared by the modules, besides the small ones (h, seg, plural, when, api, fileUrl, ...):
 *   models() the answer of /api/models (each config task's model id, each image-gen tier), withModel(label, id)
 *   stylePicker({cards, value, onPick}) the style picker on the catalogue; brandSelect(value, onPick); nice(name)
 *   dropZone(text, accept, onFiles), upload(endpoint, files), copyToRefs(path), refThumb(path, onRemove),
 *   readDataUrl(file), IMAGE_TYPES the picture types accepted from the user
 *   versionRows(version, shapeLabel), editActions(version, useAsReference), describeEdit(request, on)
 *   openDetail(version, {into}) over the page or inline in an element; refreshDetail(); closeDetail(); releaseDetail()
 *   request(fields), pending(dir), progress(id) the latest note on the current request, autonomy(), startProject()
 *   runStatus(id) the short status of a pending request's card: "Running <elapsed>", "Waiting" or "Stopping…". The
 *     shell keeps it current, so a module draws it once per card; what runs and Stop are in the Claude column
 *   started(id) when the current request started (ms since the epoch), else null; stopped(id) whether the user
 *     stopped it; stopRequest(id) Stop, after a confirmation
 *
 * `project` is the answer of /api/project. Every request the shell sends carries the current `kind` and its `skill`.
 */
"use strict";

const Studio = (() => {
  const $ = id => document.getElementById(id);
  const modules = {};
  const S = {
    config: null, kind: null, projects: [], dir: null, project: null,
    busy: false, current: null, queued: [], started: null, requests: {}, unseen: new Set(), named: new Set(), stopped: new Set(),
    blankAutonomy: "step", creating: false, connected: false, opened: false, replaying: false,
  };
  /** Line icons on a 24-unit grid, drawn in the text colour: name -> SVG elements. */
  const ICONS = {
    "short-video": '<rect x="3" y="6" width="13" height="12" rx="2"/><path d="M16 10.5 21 7.5v9l-5-3"/>',
    slide: '<rect x="3" y="4" width="18" height="12" rx="1.5"/><path d="M12 16v4M8 20h8M7 12l3-3 2 2 4-4"/>',
    image: '<rect x="3" y="4" width="18" height="16" rx="2"/><circle cx="8.5" cy="9.5" r="1.5"/><path d="m21 15-5-5L6 20"/>',
    infographic: '<path d="M3 20h18"/><rect x="5" y="11" width="3" height="6" rx=".5"/><rect x="10.5" y="5" width="3" height="12" rx=".5"/><rect x="16" y="8" width="3" height="9" rx=".5"/>',
    settings: '<path d="M4 6h9M17 6h3M4 12h3M11 12h9M4 18h11M19 18h1"/><circle cx="15" cy="6" r="2"/><circle cx="9" cy="12" r="2"/><circle cx="17" cy="18" r="2"/>',
    auto: '<path d="M11 3.5 12.6 8l4.4 1.6-4.4 1.6L11 15.5l-1.6-4.3L5 9.6 9.4 8z"/><path d="m18 14 .8 2.2 2.2.8-2.2.8L18 20l-.8-2.2-2.2-.8 2.2-.8z"/>',
    invent: '<path d="M9 3h6M10 3v6.5L5.2 18A2 2 0 0 0 7 21h10a2 2 0 0 0 1.8-3L14 9.5V3M7.6 15h8.8"/>',
    draw: '<path d="M4 20h4L19.5 8.5a2.1 2.1 0 0 0-4-4L4 16z"/><path d="m14 6 4 4M13 20h7"/>',
    file: '<path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z"/><path d="M14 3v5h5M9 13h6M9 17h6"/>',
    view: '<path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z"/><circle cx="12" cy="12" r="3"/>',
    box: '<rect x="4" y="6" width="16" height="12" rx="1"/>',
    point: '<circle cx="12" cy="12" r="4" fill="currentColor"/>',
    loop: '<path d="M6.5 17C4.3 15.6 4 13.2 4 12c0-4 3.6-7 8-7s8 3 8 7-3.6 7-8 7c-1.4 0-2.7-.3-3.8-.8"/>',
  };
  /** The icon `name` of ICONS as an inline SVG element, or null for an unknown name. */
  function icon(name) {
    if (!ICONS[name]) return null;
    const t = document.createElement("template");
    t.innerHTML = `<svg class="ico" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7"
      stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
    return t.content.firstChild;
  }
  const isMac = /Mac|iPhone|iPad/.test(navigator.platform);

  /* ---------- small helpers ---------- */

  /** Builds an element: attributes (on* are listeners, value/checked are properties), then children. */
  function h(tag, attrs, ...kids) {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs || {})) {
      if (v == null || v === false) continue;
      if (k.startsWith("on")) el.addEventListener(k.slice(2), v);
      else if (k === "value" || k === "checked") el[k] = v;
      else el.setAttribute(k, v === true ? "" : v);
    }
    for (const c of kids.flat(Infinity)) if (c != null && c !== false) el.append(c);
    return el;
  }

  const plural = (n, word) => `${n} ${word}${n === 1 ? "" : "s"}`;
  const baseName = path => path.split(/[\\/]/).pop();

  /** Marks as text lines "1. comment". */
  const markLines = marks => (marks || []).map(m => `${m.n}. ${m.comment || "(no comment)"}`);

  /** A segmented control: options [[value, label, title?]]; calls onPick(value). */
  function seg(options, value, onPick) {
    const el = h("div", { class: "seg" });
    const mark = v => el.querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === String(v)));
    for (const [v, label, title] of options) {
      el.append(h("button", { type: "button", "data-v": v, title, onclick: () => { mark(v); onPick(v); } }, label));
    }
    mark(value);
    el.set = mark;
    return el;
  }

  const startOfDay = d => new Date(d.getFullYear(), d.getMonth(), d.getDate());

  /** Time of an ISO timestamp: "09:12" today, "Thu 16:40" this week, "3 Mar" or "3 Mar 2025" before. */
  function when(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return "";
    const now = new Date(), today = startOfDay(now);
    const hm = d.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" });
    if (d >= today) return hm;
    if (today - d < 6 * 864e5) return `${d.toLocaleDateString([], { weekday: "short" })} ${hm}`;
    return d.toLocaleDateString([], { day: "numeric", month: "short", year: d.getFullYear() === now.getFullYear() ? undefined : "numeric" });
  }

  /** Day of an ISO timestamp: "today", "yesterday", or as when(). */
  function day(iso) {
    const d = new Date(iso);
    if (!iso || isNaN(d)) return "";
    const days = Math.round((startOfDay(new Date()) - startOfDay(d)) / 864e5);
    return days <= 0 ? "today" : days === 1 ? "yesterday" : when(iso);
  }

  /* ---------- server API ---------- */

  async function call(method, path, body) {
    const init = method === "GET" ? {} : { method, headers: { "content-type": "application/json" }, body: JSON.stringify(body) };
    const r = await fetch(path, init);
    const text = await r.text();
    let data = null;
    try { data = text ? JSON.parse(text) : null; } catch { data = text; }
    if (!r.ok) {
      const msg = typeof data === "string" ? data : data && (data.error || data.message);
      throw Object.assign(new Error(msg || `${r.status} ${r.statusText}`), { status: r.status, data });
    }
    return data;
  }
  const qs = params => "?" + new URLSearchParams(params);
  const api = {
    get: (path, params) => call("GET", params ? path + qs(params) : path),
    post: (path, body) => call("POST", path, body),
  };
  const fileUrl = (path, download) => "/file" + qs(download ? { path, download: 1 } : { path });

  /* ---------- style catalogue, brands, style picker ---------- */

  let catalogue = { styles: [], brands: [] };  // answer of /api/catalogue; empty lists while the server loads it
  /** Parts of the page drawn from the catalogue: [element, render], redrawn when it loads, dropped once detached. */
  const live = new Set();
  function onCatalogue(el, render) {
    live.add([el, render]);
    render();
  }

  async function loadCatalogue() {
    try { catalogue = { styles: [], brands: [], ...(await api.get("/api/catalogue")) }; }
    catch (e) { catalogue = { styles: [], brands: [], error: e.message }; }
    for (const entry of live) if (entry[0].isConnected) entry[1](); else live.delete(entry);
  }

  /* ---------- models of config.yaml ---------- */

  let models = { tasks: {}, tiers: [] };  // answer of /api/models: each task's model id, each image-gen tier
  async function loadModels() {
    try { models = await api.get("/api/models"); } catch (e) { models = { tasks: {}, tiers: [], error: e.message }; }
  }
  /** `label (model id)`, or `label (no model)` when the config names none. */
  const withModel = (label, model) => `${label} (${model || "no model"})`;

  /** A style's display name: its catalogue `title`, else the name with a capital and spaces for hyphens. */
  function nice(name) {
    const s = name && catalogue.styles.find(x => x.name === name);
    if (s && s.title) return s.title;
    return name ? name.charAt(0).toUpperCase() + name.slice(1).replace(/-/g, " ") : "";
  }
  /** Shown style name of a version: the invented style's name, else the catalogue name. */
  const versionStyle = v => (v.invented ? v.invented.name : nice(v.style));

  /** The brand pull-down ("None" and the catalogue's brands); calls onPick(name or null). */
  function brandSelect(value, onPick) {
    const el = h("select", { onchange: e => { value = e.target.value || null; onPick(value); } });
    const render = () => {
      const names = [...catalogue.brands];
      if (value && !names.includes(value)) names.push(value);
      el.replaceChildren(h("option", { value: "" }, "None"), ...names.map(b => h("option", { value: b }, b)));
      el.value = value || "";
    };
    el.set = v => { value = v; render(); };
    onCatalogue(el, render);
    return el;
  }

  /** "More information: Project · Site" for a style with `links`, each opening in a new tab without picking the style. */
  function styleLinks(s) {
    const links = Object.entries(s.links || {});
    if (!links.length) return null;
    return h("span", { class: "links" }, "More information: ", ...links.flatMap(([label, url], i) => [i ? " · " : "",
      h("a", { href: url, target: "_blank", rel: "noopener", onclick: e => e.stopPropagation() }, label)]));
  }

  /**
   * The style picker of every workspace: tag chips, the cards that leave the style to the agent (`cards`,
   * {value: {icon, title, line}}), then every catalogue style. Calls onPick(value). Answers {el, count}: the picker and a
   * hint element with the number of styles shown, for the step's title; el.set(value) marks another value.
   */
  function stylePicker({ cards = {}, value = null, onPick }) {
    let filter = "all";
    const count = h("span", { class: "hint" }), chips = h("div", { class: "chips" }), grid = h("div");
    const el = h("div", {}, chips, grid);
    const styles = () => catalogue.styles;
    /** Tags of the listed styles, the most used first. */
    const tags = () => {
      const n = {};
      for (const s of styles()) for (const t of s.tags || []) n[t] = (n[t] || 0) + 1;
      return Object.keys(n).sort((a, b) => n[b] - n[a] || a.localeCompare(b));
    };
    const render = () => {
      const all = styles(), list = all.filter(s => filter === "all" || (s.tags || []).includes(filter));
      count.textContent = all.length ? `${list.length} of ${all.length} shown · from the shared style catalogue` : "";
      chips.replaceChildren(...(catalogue.error ? [h("div", { class: "err" }, `The style catalogue could not be read: ${catalogue.error}`)] : []),
        ...(all.length ? ["all", ...tags()] : []).map(t =>
          h("button", { class: "chip" + (t === filter ? " on" : ""), onclick: () => { filter = t; render(); } }, t)));
      const pick = name => () => { value = name; render(); onPick(name); };
      grid.replaceChildren(h("div", { class: "styles" },
        Object.entries(cards).map(([id, c]) => h("div", { class: "style auto" + (value === id ? " on" : ""), onclick: pick(id) },
          icon(c.icon), c.title, h("span", {}, c.line))),
        list.map(s => h("div", { class: "style" + (s.name === value ? " on" : ""), onclick: pick(s.name),
          title: [(s.tags || []).join(", "), s.suits && s.suits.length ? `suits: ${s.suits.join(", ")}` : ""].filter(Boolean).join("\n") },
          s.sample ? h("img", { src: fileUrl(s.sample), alt: "", loading: "lazy" }) : h("div", { class: "nosample" }, "No sample yet"),
          h("div", { class: "t" }, h("b", {}, nice(s.name)), h("span", {}, s.description), styleLinks(s))))));
    };
    el.set = v => { value = v; render(); };
    onCatalogue(el, render);
    return { el, count };
  }

  /* ---------- files from the user ---------- */

  const readDataUrl = file => new Promise((resolve, reject) => {
    const r = new FileReader();
    r.onload = () => resolve(r.result);
    r.onerror = () => reject(r.error);
    r.readAsDataURL(file);
  });

  /** A drop zone with `text` that also opens the file chooser (`accept`: MIME types or suffixes); calls onFiles(files). */
  function dropZone(text, accept, onFiles) {
    const input = h("input", { type: "file", accept, multiple: true, hidden: true,
      onchange: e => { onFiles([...e.target.files]); e.target.value = ""; } });
    const drop = h("div", { class: "drop", onclick: e => { if (e.target !== input) input.click(); } }, text, input);
    drop.addEventListener("dragover", e => { e.preventDefault(); drop.classList.add("over"); });
    drop.addEventListener("dragleave", () => drop.classList.remove("over"));
    drop.addEventListener("drop", e => { e.preventDefault(); drop.classList.remove("over"); onFiles([...e.dataTransfer.files]); });
    return drop;
  }

  /**
   * Uploads files to `endpoint` (`/api/refs`, `/api/sources`) of the open project, first creating an untitled
   * project in a blank workspace; answers the written paths, after showing an error for each file that failed.
   */
  async function upload(endpoint, files) {
    if (!files.length) return [];
    const dir = await startProject();
    if (!dir) return [];
    const paths = [];
    for (const file of files) {
      try { paths.push((await api.post(endpoint, { project: dir, name: file.name, data: await readDataUrl(file) })).path); }
      catch (e) { error(`Could not add ${file.name}: ${e.message}`); }
    }
    return paths;
  }

  /** The picture types the page accepts from the user: references, a scene's own picture. */
  const IMAGE_TYPES = ["image/png", "image/jpeg", "image/webp"];

  /** Copies a file of the server (a version's picture) into the open project's refs/; answers its path, or null. */
  async function copyToRefs(path) {
    try {
      const blob = await (await fetch(fileUrl(path))).blob();
      const [ref] = await upload("/api/refs", [new File([blob], baseName(path), { type: blob.type || "image/png" })]);
      return ref || null;
    } catch (e) { error(`Could not use ${baseName(path)} as a reference: ${e.message}`); return null; }
  }

  /** The thumbnail of a reference picture with a remove button. */
  const refThumb = (path, onRemove) => h("div", { class: "ref", title: baseName(path) },
    h("img", { src: fileUrl(path), alt: "" }),
    h("button", { type: "button", title: "Remove", onclick: onRemove }, "×"));

  /* ---------- versions: detail rows, actions, request texts ---------- */

  /** Rows of the detail view for an image version; `shapeLabel` names a ratio. */
  function versionRows(v, shapeLabel) {
    const style = v.invented
      ? h("div", {}, v.invented.name, " ", h("span", { class: "tag" }, "new"),
        v.invented.description ? h("div", { class: "hint" }, v.invented.description) : null)
      : nice(v.style) || "none";
    const rows = [["Style", style], ["Shape", shapeLabel(v.shape)], ["Brand", v.brand || "None"],
      ["Model", v.model_id ? withModel(v.model, v.model_id) : v.model], ["Made", when(v.created)]];
    if (v.action === "own-picture") rows.push(["From", `your picture ${v.original || ""}`.trim()]);
    if (v.source != null) rows.push(["From", `v${v.source} (${v.action})`]);
    if (v.change) {
      const lines = markLines(v.change.marks);
      if (v.change.note) lines.push(v.change.note);
      if (lines.length) rows.push(["Change", lines.join("\n")]);
    }
    if (v.scene && typeof v.scene === "string") rows.push(["Scene", v.scene]);
    if (v.refs && v.refs.length) rows.push(["References", h("div", { class: "drefs" },
      v.refs.map(path => h("img", { src: fileUrl(path), alt: "", title: baseName(path) })))]);
    if (v.prompt) rows.push(["Prompt", v.prompt, true]);
    return rows.filter(r => r[1]);
  }

  /**
   * The detail actions every image version has: 3 variations, other styles (both carrying the module's
   * changeFields), "Use as reference" (calls useAsReference(v)) and Download.
   */
  function editActions(v, useAsReference) {
    const send = fields => async () => { if (await request({ ...fields, ...(mod().changeFields?.(v) || {}), version: v.n })) closeDetail(); };
    return [
      { label: "3 variations", run: send({ action: "variations", count: 3 }) },
      { label: "Try other styles", run: send({ action: "other-styles", styles: [] }) },
      { label: "Use as reference", run: () => { useAsReference(v); closeDetail(); } },
      { label: "Download", run: () => download(v.image) },
    ];
  }

  /** Text in the Claude column of a change, variations or other-styles request; `on` names the version's place. */
  function describeEdit(req, on = "") {
    switch (req.action) {
      case "change": {
        const lines = markLines(req.marks);
        if (req.note) lines.push(req.marks && req.marks.length ? `Also: ${req.note}` : req.note);
        return { text: `Change ${on}v${req.version}:\n${lines.join("\n")}`, images: req.marked ? [req.marked] : [] };
      }
      case "variations": return { text: `${req.count || 3} variations of ${on}v${req.version}` };
      case "other-styles": return { text: `Other styles for ${on}v${req.version}${req.styles && req.styles.length ? ": " + req.styles.map(nice).join(", ") : ""}` };
      default: return null;
    }
  }

  /**
   * Sends a request of the current kind and project; returns its id, or null after showing the error.
   * A request other than a message from the blank workspace creates a project: it carries the workspace's
   * autonomy choice, only one is in flight at a time, and the page switches to the project when the 202 names it.
   */
  async function request(fields) {
    const body = { kind: S.kind, skill: kindOf().skill, project: S.dir, ...fields };
    const creates = body.project === null && body.action !== "message";
    if (creates) {
      if (S.creating) return null;
      S.creating = true;
      body.autonomy = S.blankAutonomy;
    }
    try {
      const { id, project } = await api.post("/api/request", body);
      remember({ ...body, id, project: project !== undefined ? project : body.project });
      if (!S.named.has(id)) S.unseen.add(id);
      if (body.project === null && project && !S.dir && body.kind === S.kind) await adopt(project);
      onChange();
      return id;
    } catch (e) {
      error(`The request was not sent: ${e.message}`);
      return null;
    } finally {
      if (creates) S.creating = false;
    }
  }

  /** Records a request; the server's copy (from the `request` event, with `project` and `time`) wins. */
  function remember(req, fromServer) {
    if (fromServer || !S.requests[req.id]) S.requests[req.id] = req;
  }

  /**
   * Requests of a project that Claude works on or has not started: [{request, current}], the current one first.
   * A request just sent counts as waiting until the first `state` that names it. Requests sent before the page
   * loaded come from the server's replay on connect.
   */
  function pending(dir = S.dir) {
    const ids = [S.current, ...S.queued, ...S.unseen].filter((id, i, all) => id && all.indexOf(id) === i && !S.stopped.has(id));
    return ids.map(id => S.requests[id]).filter(r => r && r.project === dir)
      .map(request => ({ request, current: request.id === S.current }));
  }

  /* ---------- theme ---------- */

  const THEME_KEY = "studio-theme";
  const dark = matchMedia("(prefers-color-scheme: dark)");
  const themeChoice = () => localStorage.getItem(THEME_KEY) || "system";
  function applyTheme(choice) {
    const isDark = choice === "dark" || (choice === "system" && dark.matches);
    document.documentElement.dataset.theme = isDark ? "dark" : "light";
  }
  applyTheme(themeChoice());
  dark.addEventListener("change", () => applyTheme(themeChoice()));

  /* ---------- side columns: width and fold ---------- */

  /**
   * Each side column is resized by the handle on its inner edge (within its limits; a double click gives back the
   * base width) and folds to a rail of RAIL pixels by its fold button. Widths and folds are kept in localStorage;
   * below NARROW pixels of window width the left column starts folded. The left rail keeps the kinds and "New
   * project", the right rail the busy dot, a mark for an answer that came while folded and one for an approval
   * waiting; a click on the right rail unfolds it.
   */
  const COLS_KEY = "studio-columns", RAIL = 40, NARROW = 1100, CENTRE_MIN = 420;
  const WIDTHS = { left: { min: 180, max: 420, base: 232 }, right: { min: 280, max: 640, base: 360 } };
  const cols = (() => {
    let saved = {};
    try { saved = JSON.parse(localStorage.getItem(COLS_KEY)) || {}; } catch { /* a bad value counts as none */ }
    const width = (side, v) => (typeof v === "number" ? Math.min(WIDTHS[side].max, Math.max(WIDTHS[side].min, v)) : WIDTHS[side].base);
    // `leftChosen` is the user's fold of the left column, the one saved; `left` also folds it in a narrow window.
    return { leftW: width("left", saved.leftW), rightW: width("right", saved.rightW), leftChosen: !!saved.left,
      left: !!saved.left || innerWidth < NARROW, right: !!saved.right };
  })();
  /** An answer came while the right column was folded. */
  let unread = false;

  /** Applies the widths and folds; an unfolded column gives up width, down to its minimum, so the centre keeps
   *  CENTRE_MIN pixels. */
  function applyCols(save = true) {
    const app = document.querySelector(".app");
    let left = cols.left ? RAIL : cols.leftW, right = cols.right ? RAIL : cols.rightW;
    let over = left + right + CENTRE_MIN - innerWidth;
    if (over > 0 && !cols.right) { const cut = Math.min(over, right - WIDTHS.right.min); right -= cut; over -= cut; }
    if (over > 0 && !cols.left) left -= Math.min(over, left - WIDTHS.left.min);
    app.style.setProperty("--left-w", `${left}px`);
    app.style.setProperty("--right-w", `${right}px`);
    app.classList.toggle("left-folded", cols.left);
    app.classList.toggle("right-folded", cols.right);
    $("left-fold").textContent = cols.left ? "»" : "«";
    $("left-fold").title = cols.left ? "Unfold this column" : "Fold this column";
    if (!cols.right) unread = false;
    renderRail();
    if (save) localStorage.setItem(COLS_KEY, JSON.stringify({ leftW: cols.leftW, rightW: cols.rightW, left: cols.leftChosen, right: cols.right }));
    if (D.version) redraw();
  }

  function renderRail() {
    $("rail-unread").hidden = !unread;
    $("rail-ask").hidden = $("asking").hidden;
  }

  const fold = (side, on = !cols[side]) => {
    cols[side] = on;
    if (side === "left") cols.leftChosen = on;
    applyCols();
  };

  /** Dragging the handle of `side`: the column follows the pointer within its limits; saved on release. */
  function wireResize(side) {
    const handle = $(`${side}-resize`), w = WIDTHS[side];
    handle.addEventListener("pointerdown", e => {
      e.preventDefault();
      try { handle.setPointerCapture(e.pointerId); } catch { /* synthetic events have no capture */ }
      document.body.classList.add("resizing");
      const move = ev => {
        const x = side === "left" ? ev.clientX : innerWidth - ev.clientX;
        cols[`${side}W`] = Math.round(Math.min(w.max, Math.max(w.min, x)));
        applyCols(false);
      };
      const up = () => {
        handle.removeEventListener("pointermove", move);
        document.body.classList.remove("resizing");
        applyCols();
      };
      handle.addEventListener("pointermove", move);
      handle.addEventListener("pointerup", up, { once: true });
      handle.addEventListener("pointercancel", up, { once: true });
    });
    handle.addEventListener("dblclick", () => { cols[`${side}W`] = w.base; applyCols(); });
  }

  function wireColumns() {
    wireResize("left");
    wireResize("right");
    $("left-fold").onclick = () => fold("left");
    $("right-fold").onclick = () => fold("right", true);
    $("rail").onclick = () => fold("right", false);
    addEventListener("resize", () => applyCols(false));
    applyCols(false);
  }

  /* ---------- left column ---------- */

  /** The current kind of /api/config, and the workspace module that serves it. */
  const kindOf = (id = S.kind) => S.config.kinds.find(k => k.id === id);
  const mod = () => modules[kindOf().skill];
  const usable = k => k.ready && modules[k.skill];

  function renderKinds() {
    const nav = $("kinds");
    nav.replaceChildren(h("h3", {}, "Make"));
    for (const k of S.config.kinds) {
      nav.append(h("button", { class: k.id === S.kind ? "on" : null, disabled: !usable(k), title: k.label, onclick: () => selectKind(k.id) },
        icon(k.id), h("span", { class: "label" }, k.label), usable(k) ? null : h("span", { class: "soon" }, "soon")));
    }
  }

  async function selectKind(id) {
    S.kind = id;
    localStorage.setItem("studio-kind", id);
    renderKinds();
    $("projects-title").textContent = `${mod().tag(id)} projects`;
    $("ask").placeholder = mod().askPlaceholder || "Say what you want, in as much detail as you like.";
    await loadProjects();
    openBlank();
  }

  async function loadProjects() {
    const kind = S.kind;
    try {
      const list = await api.get("/api/projects", { kind });
      if (kind !== S.kind) return;
      S.projects = list || [];
    } catch (e) { error(`Could not list the projects: ${e.message}`); }
    renderProjects();
  }

  function renderProjects() {
    $("new-open").classList.toggle("on", !S.dir);
    $("projects").replaceChildren(...S.projects.map(p =>
      h("button", { class: "project" + (p.dir === S.dir ? " on" : ""), title: p.brief, onclick: () => openProject(p.dir) },
        p.name, h("small", {}, [p.slides != null ? plural(p.slides, "slide") : p.versions != null ? plural(p.versions, mod().versionNoun || "version") : null,
          `edited ${day(p.updated)}`]
          .filter(Boolean).join(" · ")))));
  }

  /* ---------- centre column ---------- */

  /** Empties the centre column for a module's open(): a fresh workspace element, the action bar hidden. */
  function freshWorkspace() {
    releaseDetail();
    $("actbar").hidden = true;
    const el = h("div");
    $("workspace").replaceChildren(el);
    return el;
  }

  /** Folded state of cards chosen by the user, by key; a card the user has not toggled takes its default. */
  const folds = new Map();
  /** Makes a card foldable by a click on its h2: folded, only the h2 shows, with a one-line summary after the
   *  title. `open` is the default while the user has not toggled the card (key): a workspace opens the step being
   *  worked on and folds the others. The mark and the summary are drawn by CSS from the h2's class and
   *  `data-summary`, so a module may redraw the h2's children. card.foldSummary(text) changes the summary,
   *  card.foldDefault(open) the default, card.foldBusy(on) marks a folded card's title while work runs in it.
   *  Answers the card. */
  function foldable(card, { key, open, summary = "", busy = false }) {
    const head = card.querySelector("h2");
    if (!head) return card;
    head.classList.add("fold-head");
    card.foldSummary = text => { head.dataset.summary = text || ""; };
    card.foldSummary(summary);
    const set = folded => card.classList.toggle("folded", folded);
    card.foldDefault = def => { if (!folds.has(key)) set(!def); };
    card.foldBusy = on => head.classList.toggle("busy", !!on);
    card.foldOpen = () => { folds.set(key, true); set(false); };
    set(!(folds.has(key) ? folds.get(key) : open));
    card.foldBusy(busy);
    head.addEventListener("click", e => {
      if (e.target.closest("button, a, input, select, textarea, label")) return;
      const nowOpen = card.classList.contains("folded");
      folds.set(key, nowOpen);
      set(!nowOpen);
    });
    return card;
  }

  /** Opens the folded card around `el`, as if the user had opened it, then scrolls to el or, with `focus`, focuses
   *  it. el may be null. */
  function reveal(el, { focus = false } = {}) {
    if (!el) return;
    el.closest(".card.folded")?.foldOpen?.();
    if (focus) el.focus();
    else el.scrollIntoView({ behavior: "smooth", block: "start" });
  }

  /** The bar fixed to the bottom of the centre column: the module's main action and a one-line summary. */
  function actionBar({ label, run, more }) {
    const buttons = [h("button", { class: "primary" }, label), ...(more ? [h("button", { class: "secondary" }, more.label)] : [])];
    const runs = [run, ...(more ? [more.run] : [])];
    const summary = h("span", { class: "summary" }), err = h("span", { class: "err" });
    let allowed = true;
    const enable = on => { for (const b of buttons) b.disabled = !on; };
    buttons.forEach((button, k) => button.onclick = async () => {
      enable(false);
      try { await runs[k](); } finally { enable(allowed); }
    });
    $("actbar").replaceChildren(...buttons, summary, err);
    $("actbar").hidden = false;
    return {
      summary: text => { summary.textContent = text; err.textContent = ""; },
      error: text => { err.textContent = text; },
      enable: on => { allowed = on; enable(on); },
    };
  }

  /** A blank workspace of the current kind, ready to type into; its first `generate` creates the project. */
  function openBlank() {
    S.dir = S.project = null;
    S.blankAutonomy = "step";
    renderProjects();
    renderTop();
    const el = freshWorkspace();
    mod().open(el, null, S.kind);
  }

  /** The blank workspace became the project `dir`: keep the drawn workspace and give it the project's data. */
  async function adopt(dir) {
    S.dir = dir;
    loadProjects();
    await reloadProject();
  }

  let starting = null;
  /**
   * The open project's directory; in a blank workspace, first creates an untitled project with the workspace's
   * autonomy choice and switches to it (one at a time). Null after showing the error.
   */
  function startProject() {
    if (S.dir) return Promise.resolve(S.dir);
    starting ??= (async () => {
      try {
        const { project } = await api.post("/api/new", { kind: S.kind, autonomy: S.blankAutonomy });
        if (!S.dir) await adopt(project);
        return S.dir;
      } catch (e) {
        error(`Could not create the project: ${e.message}`);
        return null;
      } finally { starting = null; }
    })();
    return starting;
  }

  async function openProject(dir) {
    let data;
    try { data = await api.get("/api/project", { dir }); } catch (e) { return error(`Could not open the project: ${e.message}`); }
    S.dir = dir;
    S.project = data;
    renderProjects();
    renderTop();
    const el = freshWorkspace();
    mod().open(el, data, S.kind);
  }

  let reloading = null, reloadAgain = false;
  /** Re-reads the open project after `changed`; one read at a time, one more if changes came meanwhile. */
  async function reloadProject() {
    if (reloading) { reloadAgain = true; return; }
    const dir = S.dir;
    reloading = api.get("/api/project", { dir }).then(data => {
      if (dir !== S.dir) return;
      S.project = data;
      renderTop();
      mod().update(data);
    }).catch(e => error(`Could not read the project: ${e.message}`));
    await reloading;
    reloading = null;
    if (reloadAgain) { reloadAgain = false; reloadProject(); }
  }

  function renderTop() {
    const p = (S.project && S.project.project) || {};
    $("top").hidden = false;
    if (!renaming) {
      $("title").textContent = S.dir ? p.name || baseName(S.dir) : "New project";
      $("title").title = S.dir ? "Click to rename" : "";
      $("title").classList.toggle("renamable", !!S.dir);
    }
    $("tag").textContent = mod().tag(S.kind);
    $("delete").hidden = !S.dir;
    const autonomy = S.dir ? p.autonomy || "step" : S.blankAutonomy;
    $("mode").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === autonomy));
  }

  /** Renaming the open project by a click on its title: Enter or leaving the field saves through /api/name,
   *  Escape cancels. */
  let renaming = false;
  function rename() {
    if (!S.dir || renaming) return;
    const dir = S.dir, p = (S.project && S.project.project) || {}, before = p.name || baseName(dir);
    renaming = true;
    const input = h("input", { type: "text", class: "rename", value: before, maxlength: 120 });
    let done = false;
    const finish = async save => {
      if (done) return;
      done = true;
      const name = input.value.trim().replace(/\s+/g, " ");
      renaming = false;
      if (save && name && name !== before && dir === S.dir) {
        try {
          const answer = await api.post("/api/name", { project: dir, name });
          Object.assign(p, { name: answer.name, named: true });
          loadProjects();
        } catch (e) { error(`Could not rename the project: ${e.message}`); }
      }
      renderTop();
    };
    input.addEventListener("keydown", e => {
      if (e.key === "Enter") { e.preventDefault(); finish(true); }
      if (e.key === "Escape") finish(false);
    });
    input.addEventListener("blur", () => finish(true));
    $("title").replaceChildren(input);
    input.focus();
    input.select();
  }

  /** Moves the open project to the Trash through /api/delete, after a confirmation; then a blank workspace. */
  async function deleteProject() {
    if (!S.dir) return;
    const dir = S.dir, name = ((S.project && S.project.project) || {}).name || baseName(dir);
    if (!confirm(`Move “${name}” to the Trash? Its folder ${dir} and every file in it go to the Trash, from where it can be put back.`)) return;
    try {
      await api.post("/api/delete", { project: dir });
    } catch (e) { error(`Could not delete the project: ${e.message}`); return; }
    if (S.dir === dir) openBlank();
    loadProjects();
  }

  /** The autonomy of the open project, or the blank workspace's choice. */
  const autonomy = () => (S.dir ? ((S.project && S.project.project) || {}).autonomy || "step" : S.blankAutonomy);

  /** Sets the autonomy of the open project, or the blank workspace's choice; the module hears {kind: "autonomy"}. */
  async function setAutonomy(value) {
    const shown = () => { renderTop(); mod().onEvent?.({ kind: "autonomy" }); };
    if (!S.dir) { S.blankAutonomy = value; shown(); return; }
    const p = S.project && S.project.project;
    if (!p || p.autonomy === value) return;
    const before = p.autonomy;
    p.autonomy = value;
    shown();
    try { p.autonomy = (await api.post("/api/autonomy", { project: S.dir, autonomy: value })).autonomy || value; shown(); }
    catch (e) { p.autonomy = before; shown(); error(`Could not change the mode: ${e.message}`); }
  }

  /* ---------- Claude column ---------- */

  /** A message in the Claude column: in `group` (a request's or a terminal turn's), else at the top level. */
  function feed(kind, text, images, id, group) {
    const el = h("div", { class: "msg " + kind, "data-req": id || null }, text || "");
    for (const path of images || []) el.append(h("img", { src: fileUrl(path), alt: "" }));
    place(el, group, kind === "you");
    return el;
  }
  const error = text => feed("error", text);

  /** Appends `el` to `parent` (the feed when null) and keeps the feed at its end when it was there, or `force`.
   *  During a replay nothing is measured; the feed goes to its end at `replayed`. */
  function place(el, parent, force) {
    const f = $("feed");
    if (S.replaying) { (parent || f).append(el); return; }
    // Measured once per frame, before the frame's first append; the scroll is made once, in the next frame.
    if (atEnd === null) atEnd = f.scrollHeight - f.scrollTop - f.clientHeight < 40;
    (parent || f).append(el);
    if (force) atEnd = true;
    if (!scrollFrame) scrollFrame = requestAnimationFrame(() => {
      if (atEnd) f.scrollTop = f.scrollHeight;
      atEnd = null;
      scrollFrame = 0;
    });
    const stick = atEnd;
    if (el.classList.contains("msg")) el.querySelectorAll("img").forEach(img => img.addEventListener("load", () => { if (stick) f.scrollTop = f.scrollHeight; }));
  }
  /** Whether the feed was at its end before this frame's appends (null: not measured yet), and the frame. */
  let atEnd = null, scrollFrame = 0;

  /* ---------- the log of each request ---------- */

  /** Groups of the Claude column: one per request by id; `outside` is the latest group of turns outside a request. */
  const groups = new Map();
  let outside = null;
  /** Tool lines by tool_use_id; subagents by id ({type, description}); the label elements of each subagent by id;
   *  asks already logged, by tool_use_id. */
  const toolLines = new Map(), agentsSeen = new Map(), agentLabels = new Map(), asksLogged = new Set();
  /** The log lines in the column, and in each group; past LINES_MAX the oldest groups not pending are removed. */
  const LINES_MAX = 20000;
  let lineCount = 0;
  const groupLines = new Map();
  /** The calls not yet ended, by request id ("" outside a request): Map of tool_use_id to {agent, text}. */
  const openCalls = new Map();

  function requestGroup(id) {
    let g = groups.get(id);
    if (!g) {
      g = h("div", { class: "group", "data-group": id });
      groups.set(id, g);
      place(g, null);
    }
    return g;
  }

  /** A new group for a main-loop turn outside a request (typed in the terminal, or a task notification) when
   *  `text` is given, else the latest such group. */
  function outsideGroup(text) {
    if (outside && text === undefined) return outside;
    const notification = (text || "").trimStart().startsWith("<task-notification>");
    const head = h("div", { class: "group-head" }, h("b", {}, notification ? "Task notification" : "In the terminal"));
    if (text && !notification) head.append(h("span", { class: "prompt", title: text }, text));
    outside = h("div", { class: "group outside" }, head);
    place(outside, null);
    return outside;
  }

  /** The group of an event: its request's, a terminal turn's for request null, else the current request's. */
  function groupOf(ev) {
    if (typeof ev.request === "string") return requestGroup(ev.request);
    if (ev.request === null) return outsideGroup();
    return S.current ? requestGroup(S.current) : null;
  }

  /** The log block at the end of `group`, a new one when the group ends with something else. */
  function logBlock(group) {
    const last = group && group.lastElementChild;
    if (last && last.classList.contains("log")) return last;
    const block = h("div", { class: "log" });
    place(block, group);
    return block;
  }

  const pad = n => String(n).padStart(2, "0");
  const timeOf = ms => { if (typeof ms !== "number") return ""; const d = new Date(ms); return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`; };
  const seconds = ms => (typeof ms !== "number" ? "" : ms < 10_000 ? `${(ms / 1000).toFixed(1)} s` : ms < 60_000 ? `${Math.round(ms / 1000)} s` : clock(ms));
  const asText = v => (typeof v === "string" ? v : v == null ? "" : JSON.stringify(v));
  const agentLabel = id => (agentsSeen.get(id) || {}).type || `agent ${id.slice(0, 6)}`;

  /** What a tool call does, as the terminal shows it: [main text, secondary text]. */
  function callText(tool, input) {
    const i = input || {};
    const join = (...parts) => parts.filter(p => typeof p === "string" && p).join("  ");
    switch (tool) {
      case "Bash": return [i.command, i.description];
      case "Skill": return [join(i.skill, i.args)];
      case "Read": case "Write": case "Edit": case "MultiEdit": return [i.file_path];
      case "NotebookEdit": return [i.notebook_path];
      case "Grep": case "Glob": return [join(i.pattern, i.path, i.glob)];
      case "Agent": case "Task": return [join(i.subagent_type, i.description)];
      case "WebFetch": return [i.url];
      case "WebSearch": return [i.query];
    }
    const key = ["description", "command", "file_path", "url", "path", "pattern", "skill", "text", "query", "prompt"]
      .find(k => typeof i[k] === "string" && i[k]);
    return [key ? i[key] : Object.entries(i).map(([k, v]) => `${k}=${asText(v)}`).join(" ")];
  }

  /** One line of a log: time, the subagent, what happened, and an end mark; `full`, when given, is shown on a click. */
  function logLine(ev, cls, what, full) {
    const line = h("div", { class: `ll ${cls}`, title: full ? "Click to show it all" : null },
      h("span", { class: "t" }, timeOf(ev.time)),
      ev.agent ? h("span", { class: "who" }, agentLabel(ev.agent)) : null,
      h("span", { class: "what" }, what),
      h("span", { class: "end" }));
    if (ev.agent) {
      if (!agentLabels.has(ev.agent)) agentLabels.set(ev.agent, []);
      agentLabels.get(ev.agent).push(line.querySelector(".who"));
    }
    if (full) {
      line.classList.add("folds");
      line.append(h("div", { class: "full" }, full));
      line.addEventListener("click", () => { if (!getSelection().toString()) line.classList.toggle("open"); });
    }
    const group = groupOf(ev);
    place(line, logBlock(group));
    if (group) groupLines.set(group, (groupLines.get(group) || 0) + 1);
    if (++lineCount > LINES_MAX) trim();
    return line;
  }

  /** Removes the oldest groups whose request is not pending until the column holds at most LINES_MAX lines. */
  function trim() {
    const live = new Set([S.current, ...S.queued, ...S.unseen].filter(Boolean));
    for (const group of [...$("feed").children]) {
      if (lineCount <= LINES_MAX) break;
      if (!group.classList.contains("group") || live.has(group.dataset.group) || group === outside) continue;
      lineCount -= groupLines.get(group) || 0;
      groupLines.delete(group);
      if (group.dataset.group) groups.delete(group.dataset.group);
      group.remove();
    }
    for (const [id, line] of toolLines) if (!line.isConnected) toolLines.delete(id);
    for (const [id, els] of agentLabels) agentLabels.set(id, els.filter(el => el.isConnected));
  }

  const REASONS = { answer: "answered", aborted: "stopped", error: "ended on an error", refusal: "refused" };

  /** Draws one event of a log. */
  function logEvent(ev) {
    const key = typeof ev.request === "string" ? ev.request : "";
    switch (ev.kind) {
      case "turn-start":
        if (!ev.agent && ev.request === null) outsideGroup(typeof ev.text === "string" ? ev.text : "");
        logLine(ev, "turn", ev.agent ? "started" : "turn started");
        break;
      case "turn-end":
        logLine(ev, "turn", [`${ev.agent ? "ended" : "turn ended"}: ${REASONS[ev.reason] || ev.reason || "?"}`,
          h("span", { class: "dim" }, `  ${seconds(ev.ms)}`)]);
        break;
      case "agent-start": {
        if (ev.agent) {
          agentsSeen.set(ev.agent, { type: ev.type, description: ev.description });
          for (const el of agentLabels.get(ev.agent) || []) el.textContent = agentLabel(ev.agent);
        }
        const what = [h("b", {}, "subagent"), ` ${ev.description || ""}`, ev.background ? h("span", { class: "dim" }, "  in the background") : null];
        logLine(ev, "agent", what, ev.prompt || null);
        break;
      }
      case "tool": {
        const [main, extra] = callText(ev.tool, ev.input);
        const full = Object.entries(ev.input || {}).map(([k, v]) => `${k}: ${asText(v)}`).join("\n");
        const line = logLine(ev, "tool", [h("b", {}, ev.tool), " ", main || "", extra ? h("span", { class: "dim" }, `  ${extra}`) : null], full || null);
        line.querySelector(".end").append(h("span", { class: "open-mark" }, "…"));
        if (ev.use) {
          toolLines.set(ev.use, line);
          if (!openCalls.has(key)) openCalls.set(key, new Map());
          openCalls.get(key).set(ev.use, { agent: ev.agent, text: [ev.tool, main].filter(Boolean).join(" ") });
        }
        break;
      }
      case "tool-end": {
        openCalls.get(key)?.delete(ev.use);
        const line = ev.use && toolLines.get(ev.use);
        const mark = h("span", { class: ev.ok ? "ok" : "bad", title: ev.ok ? null : ev.error || "failed" }, `${ev.ok ? "✓" : "✗"} ${seconds(ev.ms)}`);
        if (line) {
          line.querySelector(".end").replaceChildren(mark);
          if (!ev.ok && ev.error) {
            line.classList.add("failed");
            const full = line.querySelector(".full");
            if (full) full.append(`\nerror: ${ev.error}`);
          }
          toolLines.delete(ev.use);
        } else {
          logLine(ev, "tool", [h("b", {}, ev.tool), " ended"]).querySelector(".end").append(mark);
        }
        break;
      }
      case "text": logLine(ev, "say", ev.text, ev.text && ev.text.length > 80 ? ev.text : null); break;
      case "ask":
        if (ev.use && asksLogged.has(ev.use)) break;
        if (ev.use) asksLogged.add(ev.use);
        logLine(ev, "asks", `waits for approval in Claude Code: ${[ev.tool, ev.text].filter(Boolean).join(": ")}`);
        break;
      case "answer": logLine(ev, "asks", ev.ok ? "approval answered: the call ran" : "approval answered: refused, or the call failed"); break;
    }
    renderRunning();
  }
  const LOG_KINDS = new Set(["turn-start", "turn-end", "agent-start", "tool", "tool-end", "text", "ask", "answer"]);

  /* ---------- the running request ---------- */

  /** The block above the input box while a turn runs: what runs, the elapsed time and Stop. */
  function renderRunning() {
    const el = $("running");
    if (!S.busy || !S.connected) { el.hidden = true; el.dataset.key = ""; return; }
    const id = S.current, req = id && S.requests[id];
    const since = id ? started(id) : S.started;
    const title = req ? describe(req).text.split("\n")[0] : "A turn outside a Studio request";
    const calls = [...(openCalls.get(id || "") || new Map()).values()].slice(-3).reverse();
    const lines = calls.length ? calls.map(c => (c.agent ? `${agentLabel(c.agent)}: ` : "") + c.text) : ["Thinking"];
    const elapsed = since ? clock(Date.now() - since) : "";
    const canStop = !!req && !S.stopped.has(id);
    const key = [title, elapsed, ...lines, canStop, stopping.has(id)].join("|");
    el.hidden = false;
    if (el.dataset.key === key) return;
    el.dataset.key = key;
    el.replaceChildren(
      h("div", { class: "head" }, h("span", { class: "dot busy" }), h("b", { title }, title),
        h("span", { class: "elapsed" }, elapsed),
        !canStop ? null : stopping.has(id) ? h("span", { class: "hint" }, "Stopping…") : stopButton(id)),
      ...lines.map(text => h("div", { class: "now", title: text }, text)));
  }

  function describe(req) {
    const m = modules[req.skill];
    const d = m && m.describe && m.describe(req);
    if (d) return d;
    if (req.action === "message") return { text: req.text };
    return { text: req.action };
  }

  function sendMessage() {
    const text = $("ask").value.trim();
    if (!text) return;
    $("ask").value = "";
    request({ action: "message", text });
  }

  /** Busy dot, state line, queue notice, the right rail and Stop on the pending requests in the Claude column. */
  function renderState() {
    const dot = $("dot"), state = $("state");
    dot.className = $("rail-dot").className = "dot" + (!S.connected ? " off" : S.busy ? " busy" : "");
    state.textContent = !S.opened ? "connecting…" : !S.connected ? "disconnected" : S.busy ? "working…" : "ready";
    const waiting = S.queued.filter(id => !S.stopped.has(id)).length;
    $("queue").hidden = !waiting;
    $("queue").textContent = `${plural(waiting, "request")} waiting for the running one to finish`;
    renderRail();
    const live = new Set([S.current, ...S.queued, ...S.unseen].filter(id => id && S.requests[id] && !S.stopped.has(id) && !stopping.has(id)));
    for (const msg of $("feed").querySelectorAll(".msg.you[data-req]")) {
      const id = msg.dataset.req, button = msg.querySelector(".stop");
      if (live.has(id) && !button) msg.append(stopButton(id));
      else if (!live.has(id) && button) button.remove();
    }
    tick();
  }

  /* ---------- progress and Stop of a request ---------- */

  /** Elapsed time of `ms` milliseconds: "0:42", "12:05", "1:02:05". */
  function clock(ms) {
    const t = Math.max(0, Math.floor(ms / 1000)), hh = Math.floor(t / 3600), mm = Math.floor(t / 60) % 60, ss = String(t % 60).padStart(2, "0");
    return hh ? `${hh}:${String(mm).padStart(2, "0")}:${ss}` : `${mm}:${ss}`;
  }

  /** When the current request `id` started (ms since the epoch), else null. */
  const started = id => (id && id === S.current && S.busy ? S.started || Date.parse((S.requests[id] || {}).time) || null : null);

  const stopButton = id => h("button", { class: "mini stop", type: "button", title: "Stop this request; what is finished is kept",
    onclick: e => { e.stopPropagation(); stopRequest(id); } }, "Stop");

  /** Stops a current or queued request through /api/stop, after a confirmation. */
  /** Requests whose Stop was sent and whose `stopped` event has not come. */
  const stopping = new Set();
  async function stopRequest(id) {
    const req = S.requests[id];
    if (!req || S.stopped.has(id) || stopping.has(id)) return;
    const running = id === S.current && S.busy;
    if (!confirm(running ? "Stop this request? What is finished so far is kept." : "Take this request out of the queue?")) return;
    stopping.add(id);
    renderState();
    try { await api.post("/api/stop", { id }); }
    catch (e) { stopping.delete(id); renderState(); error(`Could not stop the request: ${e.message}`); }
  }

  /** The short status of a pending request's card, kept current by tick(). */
  const runStatus = id => { const el = h("span", { class: "run-status", "data-req": id }); paintStatus(el); return el; };

  function paintStatus(el) {
    const id = el.dataset.req, since = started(id);
    const text = stopping.has(id) ? "Stopping…" : since ? `Running ${clock(Date.now() - since)}` : "Waiting";
    if (el.textContent !== text) el.textContent = text;
  }

  /** Redraws every status and the running block; called each second, and when the state changes. */
  function tick() {
    for (const el of document.querySelectorAll(".run-status[data-req]")) paintStatus(el);
    renderRunning();
  }
  setInterval(tick, 1000);

  /* ---------- server events ---------- */

  let source = null, retry = null;
  /** Order of the `request` and `note` events, and the latest note. */
  let seq = 0, lastNote = null;
  /** The latest progress note on the request `id`: a note that came after the request, while it is current. */
  function progress(id) {
    const req = S.requests[id];
    return id && id === S.current && req && lastNote && lastNote.seq > (req.seq || 0) ? lastNote.text : null;
  }
  function connect() {
    clearTimeout(retry);
    if (source) source.close();
    source = new EventSource("/events");
    source.onopen = () => {
      const reconnected = S.opened;
      S.opened = true;
      S.replaying = true;
      resetSession();
      setConnected(true);
      if (reconnected) resync();
    };
    source.onerror = () => {
      setConnected(false);
      if (source.readyState === EventSource.CLOSED) retry = setTimeout(connect, 2000);
    };
    source.onmessage = msg => {
      let ev;
      try { ev = JSON.parse(msg.data); } catch { return; }
      handle(ev);
    };
  }

  /**
   * The server replays the session right after each connect and ends the replay with `replayed`; the module is not
   * called for the replayed kinds meanwhile and redraws once at the end.
   */
  const REPLAY_KINDS = new Set(["request", "agent", "note", "stopped", "ended", "state", ...LOG_KINDS]);

  /**
   * Forgets the conversation and the work state before the replay. Kept: the page's own error lines and the
   * requests it sent that no `state` named yet (the replay may not hold them yet).
   */
  function resetSession() {
    $("feed").replaceChildren(...$("feed").querySelectorAll(":scope > .msg.error"));
    groups.clear();
    outside = null;
    toolLines.clear();
    agentsSeen.clear();
    agentLabels.clear();
    asksLogged.clear();
    groupLines.clear();
    lineCount = 0;
    openCalls.clear();
    $("asking").hidden = true;
    S.requests = Object.fromEntries([...S.unseen].filter(id => S.requests[id]).map(id => [id, S.requests[id]]));
    S.unseen = new Set(Object.keys(S.requests));
    S.named.clear();
    S.stopped.clear();
    S.busy = false;
    S.current = S.started = null;
    S.queued = [];
    renderState();
    onChange();
  }

  function setConnected(on) {
    S.connected = on;
    $("offline").hidden = on;
    renderState();
  }

  /** After a reconnect: the server may have restarted, so read everything again. */
  function resync() {
    loadCatalogue();
    loadModels();
    if (!S.kind) return;
    loadProjects();
    if (S.dir) reloadProject();
    mod().onEvent?.({ kind: "reconnected" });
  }

  function handle(ev) {
    switch (ev.kind) {
      case "request": {
        const req = ev.request;
        remember({ ...req, seq: ++seq }, true);
        const d = describe(req), group = requestGroup(req.id);
        group.prepend(feed("you", d.text, d.images, req.id, group));
        renderState();
        break;
      }
      case "agent": feed("claude", ev.text, ev.images, null, groupOf(ev)); if (cols.right && !S.replaying) { unread = true; renderRail(); } break;
      case "note": feed("note", ev.text, null, null, groupOf(ev)); lastNote = { text: ev.text, seq: ++seq }; break;
      case "stopped": {
        S.stopped.add(ev.id);
        stopping.delete(ev.id);
        S.unseen.delete(ev.id);
        const req = S.requests[ev.id];
        feed("note", `Stopped: ${req ? describe(req).text.split("\n")[0] : "a request"}`, null, null, req ? requestGroup(ev.id) : null);
        renderState();
        break;
      }
      case "state":
        // In a replay the kept asks come before the state and the open one after it.
        if (S.replaying) $("asking").hidden = true;
        S.busy = !!ev.busy;
        S.current = ev.current || null;
        S.queued = ev.queued || [];
        S.started = typeof ev.started === "number" ? ev.started : null;
        [S.current, ...S.queued].filter(Boolean).forEach(id => { S.unseen.delete(id); S.named.add(id); });
        renderState();
        break;
      case "ask":
        logEvent(ev);
        $("asking").textContent = `Waiting for your approval in Claude Code: ${[ev.tool, ev.text].filter(Boolean).join(": ")}`;
        $("asking").hidden = false;
        renderRail();
        break;
      case "ask-done": $("asking").hidden = true; renderRail(); break;
      case "changed":
        if (ev.project_kind !== S.kind) break;
        loadProjects();
        if (ev.project === S.dir) reloadProject();
        break;
      case "projects": if (ev.project_kind === S.kind) loadProjects(); break;
      case "catalogue": loadCatalogue(); break;
      case "replayed": S.replaying = false; $("feed").scrollTop = $("feed").scrollHeight; renderState(); onChange(); return;
      case "turn-start": case "turn-end": case "agent-start": case "tool": case "tool-end": case "text": case "answer":
        logEvent(ev);
        break;
      case "ended":
        S.busy = false;
        S.current = S.started = null;
        S.queued = [];
        S.unseen.clear();
        $("asking").hidden = true;
        renderState();
        feed("note", "The Claude Code session ended. Run /studio in a new session to continue.");
        break;
    }
    if (S.kind && !(S.replaying && REPLAY_KINDS.has(ev.kind))) mod().onEvent?.(ev);
  }

  /** Called after the shell's own request bookkeeping changed, so the module can redraw placeholders. */
  function onChange() {
    if (S.kind && !S.replaying) mod().onEvent?.({ kind: "pending" });
  }

  /* ---------- detail view with marking ---------- */

  /** Marks on screen use the theme's --mark; the marked copy sent to Claude always uses the light scheme's red. */
  const MARKED_COPY_RED = "#e5382f";
  const markColour = () => getComputedStyle(document.documentElement).getPropertyValue("--mark").trim() || MARKED_COPY_RED;
  const D = { version: null, tool: "box", marks: [], drawing: null, inline: false };
  const HINTS = {
    view: "Pick a tool to mark what you want changed", box: "Drag a box around the part to change",
    point: "Click on the spot to change", loop: "Draw a loop around the part to change",
  };

  /**
   * Adds the shape of a mark (fractions of the image) to the current path of a 2D context of W x H pixels: the
   * rectangle of a box, the closed polygon of a loop, a circle of radius `r` pixels around a point. Answers the
   * pixel position of the mark's number label for a box or loop (the first corner, the first point).
   */
  function traceMark(g, W, H, m, r) {
    if (m.kind === "point") { g.arc(m.x * W, m.y * H, r, 0, 2 * Math.PI); return null; }
    if (m.kind === "box") { g.rect(m.x * W, m.y * H, m.w * W, m.h * H); return [m.x * W, m.y * H]; }
    m.points.forEach(([x, y], k) => k ? g.lineTo(x * W, y * H) : g.moveTo(x * W, y * H));
    g.closePath();
    return [m.points[0][0] * W, m.points[0][1] * H];
  }

  /**
   * Draws marks (fractions of the image) on a 2D context of W x H pixels; `unit` is the size of one
   * screen pixel in context pixels, `RED` the mark colour. Used for the preview over the image and for the marked copy.
   */
  function drawMarks(g, W, H, marks, unit, RED) {
    g.lineJoin = "round";
    for (const m of marks) {
      g.beginPath();
      g.strokeStyle = RED;
      g.lineWidth = 3 * unit;
      let lx, ly;
      if (m.kind === "point") {
        lx = m.x * W + 14 * unit; ly = m.y * H - 14 * unit;
        traceMark(g, W, H, m, 9 * unit);
        g.fillStyle = RED; g.fill();
        g.strokeStyle = "#fff"; g.lineWidth = 2 * unit; g.stroke();
      } else {
        [lx, ly] = traceMark(g, W, H, m);
        g.fillStyle = RED; g.globalAlpha = .12; g.fill(); g.globalAlpha = 1; g.stroke();
      }
      if (m.n) {
        g.beginPath();
        g.arc(lx, ly, 11 * unit, 0, 2 * Math.PI);
        g.fillStyle = RED; g.fill();
        g.fillStyle = "#fff";
        g.font = `700 ${12 * unit}px -apple-system, "Segoe UI", sans-serif`;
        g.textAlign = "center"; g.textBaseline = "middle";
        g.fillText(String(m.n), lx, ly + 0.5 * unit);
      }
    }
  }

  function redraw() {
    const img = $("d-img"), c = $("d-overlay"), dpr = window.devicePixelRatio || 1;
    const W = Math.round(img.clientWidth * dpr), H = Math.round(img.clientHeight * dpr);
    if (c.width !== W || c.height !== H) { c.width = W; c.height = H; }
    const g = c.getContext("2d");
    g.clearRect(0, 0, W, H);
    drawMarks(g, W, H, D.drawing ? [...D.marks, D.drawing] : D.marks, dpr, markColour());
  }

  /** The version's image with the marks drawn in red, as a PNG data URL. */
  function markedCopy() {
    const img = $("d-img"), W = img.naturalWidth, H = img.naturalHeight;
    const c = h("canvas", { width: W, height: H }), g = c.getContext("2d");
    g.drawImage(img, 0, 0);
    drawMarks(g, W, H, D.marks, Math.max(1, W / img.clientWidth), MARKED_COPY_RED);
    return c.toDataURL("image/png");
  }

  /** Edit mask sizes, as fractions of the image's shorter edge: the radius of a point, the growth of every mark. */
  const MASK_POINT = 0.08, MASK_GROW = 0.02;

  /**
   * Draws the edit mask of `marks` on a 2D context of W x H pixels: opaque black, alpha 0 inside every mark
   * grown by MASK_GROW on each side (its shape filled and stroked twice that wide). Partly transparent edge
   * pixels are set to alpha 0 or 255, so the mask has no soft edge.
   */
  function drawMask(g, W, H, marks) {
    const s = Math.min(W, H);
    g.fillStyle = g.strokeStyle = "#000";
    g.fillRect(0, 0, W, H);
    g.globalCompositeOperation = "destination-out";
    g.lineJoin = "round";
    g.lineWidth = 2 * MASK_GROW * s;
    for (const m of marks) {
      g.beginPath();
      traceMark(g, W, H, m, MASK_POINT * s);
      g.fill();
      g.stroke();
    }
    g.globalCompositeOperation = "source-over";
    const px = g.getImageData(0, 0, W, H), a = px.data;
    for (let i = 3; i < a.length; i += 4) a[i] = a[i] < 128 ? 0 : 255;
    g.putImageData(px, 0, 0);
  }

  /** The edit mask of the marks at the version image's natural size, as a PNG data URL. */
  function editMask() {
    const img = $("d-img"), W = img.naturalWidth, H = img.naturalHeight;
    const c = h("canvas", { width: W, height: H });
    drawMask(c.getContext("2d"), W, H, D.marks);
    return c.toDataURL("image/png");
  }

  function setTool(t) {
    D.tool = t;
    document.querySelectorAll(".tools [data-tool]").forEach(b => b.classList.toggle("on", b.dataset.tool === t));
    $("d-frame").classList.toggle("view", t === "view");
    hint(HINTS[t]);
  }
  const hint = text => { $("d-hint").textContent = text; };

  /**
   * Opens a version in the detail view: over the page, or with `into` (an element of the workspace) inside that
   * element, as the scene view of a short video shows its picture. An inline detail view stays until the workspace
   * is redrawn or releaseDetail() is called; there closeDetail() only clears the marks and the note.
   */
  function openDetail(version, { into = null } = {}) {
    placeDetail(into);
    D.version = version;
    D.marks = [];
    D.drawing = null;
    $("d-img").src = fileUrl(version.image);
    $("d-note").value = "";
    refreshDetail();
    renderMarks();
    if (!into) $("shade").hidden = false;
    setTool("box");
  }

  /** Draws the open version's title, rows and actions again, keeping the marks and the note. */
  function refreshDetail() {
    const m = mod(), version = D.version;
    if (!version) return;
    $("d-title").textContent = m.detailTitle?.(version) || `${(S.project.project || {}).name || ""} · v${version.n}`;
    $("d-meta").replaceChildren(...(m.versionInfo(version) || []).flatMap(([label, text, long]) =>
      [h("dt", {}, label), h("dd", { class: long ? "long" : null }, text)]));
    const send = h("button", { class: "primary", onclick: () => sendChange(send) }, "Send");
    $("d-acts").replaceChildren(send, ...(m.detailActions(version) || []).map(a =>
      h("button", { class: "secondary", disabled: !!a.disabled, title: a.title, onclick: () => a.run(version) }, a.label)));
  }

  /** Puts the detail view into `host` (inline) or back over the page (null). */
  function placeDetail(host) {
    const d = $("detail");
    D.inline = !!host;
    if (host) { if (d.parentNode !== host) host.append(d); }
    else if (d.parentNode !== $("shade")) $("shade").append(d);
    d.classList.toggle("inline", D.inline);
    $("d-close").hidden = D.inline;
  }

  function closeDetail() {
    if (D.inline) { D.marks = []; $("d-note").value = ""; renderMarks(); return; }
    $("shade").hidden = true;
    D.version = null;
  }

  /** Takes an inline detail view out of the workspace, back to its place over the page, closed. */
  function releaseDetail() {
    if (!D.inline) return;
    placeDetail(null);
    $("shade").hidden = true;
    D.version = null;
  }

  /** Closing by the user (×, backdrop, Escape): marks or a note are discarded only after confirmation. */
  function askClose() {
    if ((D.marks.length || $("d-note").value.trim()) && !confirm("Discard the marks and the change note?")) return;
    closeDetail();
  }

  function renderMarks(focusLast) {
    redraw();
    const list = $("d-marks");
    if (!D.marks.length) {
      list.replaceChildren(h("div", { class: "empty" }, "No marks yet. Use Box, Point or Circle freehand on the image."));
      return;
    }
    list.replaceChildren(...D.marks.map((m, i) => h("div", { class: "mk" },
      h("span", { class: "n" }, String(m.n)),
      h("textarea", { placeholder: "What should change here?", value: m.comment, oninput: e => { m.comment = e.target.value; } }),
      h("button", { class: "x", title: "Remove", onclick: () => { D.marks.splice(i, 1); renumber(); renderMarks(); } }, "×"))));
    if (focusLast) list.querySelectorAll("textarea")[D.marks.length - 1].focus();
  }
  const renumber = () => D.marks.forEach((m, i) => { m.n = i + 1; });
  const r4 = x => Math.round(x * 1e4) / 1e4;

  function addMark(m) {
    D.marks.push({ n: D.marks.length + 1, ...m, comment: "" });
    renderMarks(true);
  }

  function pos(e) {
    const b = $("d-overlay").getBoundingClientRect(), clamp = v => Math.min(1, Math.max(0, v));
    return [r4(clamp((e.clientX - b.left) / b.width)), r4(clamp((e.clientY - b.top) / b.height))];
  }

  function wireMarking() {
    const c = $("d-overlay");
    c.addEventListener("pointerdown", e => {
      if (D.tool === "view") return;
      const [x, y] = pos(e);
      if (D.tool === "point") return addMark({ kind: "point", x, y });
      D.drawing = D.tool === "box" ? { kind: "box", x0: x, y0: y, x, y, w: 0, h: 0 } : { kind: "loop", points: [[x, y]] };
      try { c.setPointerCapture(e.pointerId); } catch { /* synthetic events have no capture */ }
    });
    c.addEventListener("pointermove", e => {
      const d = D.drawing;
      if (!d) return;
      const [x, y] = pos(e);
      if (d.kind === "box") Object.assign(d, { x: Math.min(d.x0, x), y: Math.min(d.y0, y), w: r4(Math.abs(x - d.x0)), h: r4(Math.abs(y - d.y0)) });
      else {
        const [px, py] = d.points[d.points.length - 1];
        if (Math.hypot(x - px, y - py) < 0.005) return;
        d.points.push([x, y]);
      }
      redraw();
    });
    const finish = () => {
      const d = D.drawing;
      if (!d) return;
      D.drawing = null;
      if (d.kind === "box" && d.w > 0.01 && d.h > 0.01) addMark({ kind: "box", x: d.x, y: d.y, w: d.w, h: d.h });
      else if (d.kind === "loop" && d.points.length > 4) addMark({ kind: "loop", points: d.points });
      else redraw();
    };
    c.addEventListener("pointerup", finish);
    c.addEventListener("pointercancel", finish);
    document.querySelectorAll(".tools [data-tool]").forEach(b => b.addEventListener("click", () => setTool(b.dataset.tool)));
    $("d-clear").onclick = () => { D.marks = []; renderMarks(); };
    $("d-close").onclick = askClose;
    $("shade").addEventListener("click", e => { if (e.target === $("shade")) askClose(); });
    $("d-img").addEventListener("load", redraw);
    window.addEventListener("resize", () => { if (D.version) redraw(); });
    new ResizeObserver(() => { if (D.version) redraw(); }).observe($("d-img"));
  }

  /** Saves a file of the server through a temporary download link. */
  function download(path) {
    const a = h("a", { href: fileUrl(path, true), download: baseName(path), hidden: true });
    document.body.append(a);
    a.click();
    a.remove();
  }

  async function sendChange(button) {
    const v = D.version, note = $("d-note").value.trim(), extra = mod().changeFields?.(v) || {};
    if (!D.marks.length && !note) return hint("Mark an area or write what to change first");
    button.disabled = true;
    try {
      let marked = null, mask = null;
      if (D.marks.length) {
        try {
          ({ path: marked, mask } = await api.post("/api/marked",
            { project: S.dir, version: v.n, ...extra, png: markedCopy(), mask: editMask() }));
        } catch (e) { return hint(`Could not save the marked copy: ${e.message}`); }
      }
      const marks = D.marks.map(m => ({ ...m, comment: m.comment.trim() }));
      if (await request({ action: "change", version: v.n, ...extra, marks, note, marked, mask })) closeDetail();
    } finally { button.disabled = false; }
  }

  /* ---------- start ---------- */

  function wire() {
    $("send-key").textContent = `${isMac ? "⌘" : "Ctrl"} Enter to send`;
    $("send").onclick = sendMessage;
    $("ask").addEventListener("keydown", e => { if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) { e.preventDefault(); sendMessage(); } });
    $("new-open").onclick = openBlank;
    $("mode").querySelectorAll("button").forEach(b => b.addEventListener("click", () => setAutonomy(b.dataset.v)));
    $("theme").replaceWith(Object.assign(seg([["light", "Light"], ["dark", "Dark"], ["system", "System"]],
      localStorage.getItem(THEME_KEY) || "system", v => { localStorage.setItem(THEME_KEY, v); applyTheme(v); }), { id: "theme" }));
    $("gear").onclick = () => { $("pop").hidden = !$("pop").hidden; };
    document.addEventListener("click", e => { if (!e.target.closest(".settings")) $("pop").hidden = true; });
    document.addEventListener("keydown", e => {
      if (e.key !== "Escape" || $("shade").hidden) return;
      if (e.target.closest("input, textarea, select")) e.target.blur(); else askClose();
    });
    wireMarking();
    wireColumns();
  }

  async function start() {
    wire();
    resetSession();
    connect();
    loadCatalogue();
    await loadModels();
    try { S.config = await api.get("/api/config"); } catch (e) { return error(`Could not reach the studio server: ${e.message}`); }
    const ready = S.config.kinds.filter(usable).map(k => k.id);
    const saved = localStorage.getItem("studio-kind");
    renderKinds();
    if (ready.length) selectKind(ready.includes(saved) ? saved : ready[0]);
  }
  document.addEventListener("DOMContentLoaded", () => {
    for (const el of document.querySelectorAll("[data-icon]")) el.prepend(icon(el.dataset.icon));
  });
  document.addEventListener("DOMContentLoaded", start);
  document.addEventListener("DOMContentLoaded", () => {
    $("title").addEventListener("click", rename);
    $("delete").addEventListener("click", deleteProject);
  });

  return {
    register: m => { modules[m.id] = m; },
    h, icon, seg, plural, baseName, actionBar, foldable, reveal, markLines, when, day, api, fileUrl, download, request, pending, startProject,
    feed, error, openDetail, refreshDetail, closeDetail, releaseDetail, progress, autonomy, runStatus, started, stopRequest,
    stopped: id => S.stopped.has(id),
    nice, versionStyle, brandSelect, stylePicker, readDataUrl, dropZone, upload, copyToRefs, IMAGE_TYPES, refThumb, versionRows, editActions,
    describeEdit, catalogue: () => catalogue, config: () => S.config, models: () => models, withModel, drawMarks,
  };
})();
