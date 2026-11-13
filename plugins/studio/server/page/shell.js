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
 *     onEvent(event),               // optional: every server event, after the shell handled it, and two of the
 *                                   //   shell: {kind: "pending"} when its request bookkeeping changed (a request
 *                                   //   sent, the session reset before a replay), {kind: "reconnected"} after a reconnect
 *     describe(request),            // optional: {text, images} of a request for the Claude column
 *     versionInfo(version),         // rows [[label, text or node, long?], ...] of the detail view
 *     detailActions(version),       // buttons [{label, run(version)}, ...] after "Send changes to Claude"
 *     changeFields(version),        // optional: fields added to the `change` request and the /api/marked body
 *     detailTitle(version),         // optional: title of the detail view; "<project name> · v<N>" by default
 *   });
 *
 * In open(), a module that has one main action puts it in the bar at the bottom of the centre column with
 * Studio.actionBar({label, run}); it answers {summary(text), error(text)}. The button is disabled while run() runs.
 *
 * `project` is the answer of /api/project. Every request the shell sends carries the current `kind` and its `skill`.
 * The shell's helpers are the other members of `Studio`.
 */
"use strict";

const Studio = (() => {
  const $ = id => document.getElementById(id);
  const modules = {};
  const S = {
    config: null, kind: null, projects: [], dir: null, project: null,
    busy: false, current: null, queued: [], requests: {}, unseen: new Set(), named: new Set(),
    blankAutonomy: "step", creating: false, connected: false, opened: false, replaying: false,
  };
  const KIND_ICONS = { image: "🖼️", infographic: "📊", slide: "📑", "short-video": "🎬" };
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
      throw new Error(msg || `${r.status} ${r.statusText}`);
    }
    return data;
  }
  const qs = params => "?" + new URLSearchParams(params);
  const api = {
    get: (path, params) => call("GET", params ? path + qs(params) : path),
    post: (path, body) => call("POST", path, body),
  };
  const fileUrl = (path, download) => "/file" + qs(download ? { path, download: 1 } : { path });

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
      error(`The request did not reach Claude: ${e.message}`);
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
    const ids = [S.current, ...S.queued, ...S.unseen].filter((id, i, all) => id && all.indexOf(id) === i);
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

  /* ---------- left column ---------- */

  /** The current kind of /api/config, and the workspace module that serves it. */
  const kindOf = (id = S.kind) => S.config.kinds.find(k => k.id === id);
  const mod = () => modules[kindOf().skill];
  const usable = k => k.ready && modules[k.skill];

  function renderKinds() {
    const nav = $("kinds");
    nav.replaceChildren(h("h3", {}, "Make"));
    for (const k of S.config.kinds) {
      nav.append(h("button", { class: k.id === S.kind ? "on" : null, disabled: !usable(k), onclick: () => selectKind(k.id) },
        `${KIND_ICONS[k.id] || "•"} ${k.label}`, usable(k) ? null : h("span", { class: "soon" }, "soon")));
    }
  }

  async function selectKind(id) {
    S.kind = id;
    localStorage.setItem("studio-kind", id);
    renderKinds();
    $("projects-title").textContent = `${mod().tag(id)} projects`;
    $("ask").placeholder = mod().askPlaceholder || "Tell Claude what you want, in as much detail as you like.";
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
        p.name, h("small", {}, [p.slides != null ? plural(p.slides, "slide") : p.versions != null ? plural(p.versions, "version") : null,
          `edited ${day(p.updated)}`]
          .filter(Boolean).join(" · ")))));
  }

  /* ---------- centre column ---------- */

  /** Empties the centre column for a module's open(): a fresh workspace element, the action bar hidden. */
  function freshWorkspace() {
    $("actbar").hidden = true;
    const el = h("div");
    $("workspace").replaceChildren(el);
    return el;
  }

  /** The bar fixed to the bottom of the centre column: the module's main action and a one-line summary. */
  function actionBar({ label, run }) {
    const button = h("button", { class: "primary" }, label);
    const summary = h("span", { class: "summary" }), err = h("span", { class: "err" });
    button.onclick = async () => {
      button.disabled = true;
      try { await run(); } finally { button.disabled = false; }
    };
    $("actbar").replaceChildren(button, summary, err);
    $("actbar").hidden = false;
    return {
      summary: text => { summary.textContent = text; err.textContent = ""; },
      error: text => { err.textContent = text; },
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
    $("title").textContent = S.dir ? p.name || baseName(S.dir) : "New project";
    $("tag").textContent = mod().tag(S.kind);
    const autonomy = S.dir ? p.autonomy || "step" : S.blankAutonomy;
    $("mode").querySelectorAll("button").forEach(b => b.classList.toggle("on", b.dataset.v === autonomy));
  }

  async function setAutonomy(value) {
    if (!S.dir) { S.blankAutonomy = value; renderTop(); return; }
    const p = S.project && S.project.project;
    if (!p || p.autonomy === value) return;
    const before = p.autonomy;
    p.autonomy = value;
    renderTop();
    try { p.autonomy = (await api.post("/api/autonomy", { project: S.dir, autonomy: value })).autonomy || value; renderTop(); }
    catch (e) { p.autonomy = before; renderTop(); error(`Could not change the mode: ${e.message}`); }
  }

  /* ---------- Claude column ---------- */

  function feed(kind, text, images) {
    const el = h("div", { class: "msg " + kind }, text || "");
    for (const path of images || []) el.append(h("img", { src: fileUrl(path), alt: "" }));
    const f = $("feed"), atEnd = f.scrollHeight - f.scrollTop - f.clientHeight < 40;
    f.append(el);
    if (atEnd || kind === "you") f.scrollTop = f.scrollHeight;
    el.querySelectorAll("img").forEach(img => img.addEventListener("load", () => { if (atEnd) f.scrollTop = f.scrollHeight; }));
  }
  const error = text => feed("error", text);

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

  /** Busy dot, state line and queue notice. */
  function renderState() {
    const dot = $("dot"), state = $("state");
    dot.className = "dot" + (!S.connected ? " off" : S.busy ? " busy" : "");
    state.textContent = !S.opened ? "connecting…" : !S.connected ? "disconnected" : S.busy ? "working…" : "ready";
    const waiting = S.queued.length;
    $("queue").hidden = !waiting;
    $("queue").textContent = `${plural(waiting, "request")} waiting until Claude finishes`;
  }

  /* ---------- server events ---------- */

  let source = null, retry = null;
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
  const REPLAY_KINDS = new Set(["request", "agent", "note", "turn", "ended", "state", "ask"]);

  /**
   * Forgets the conversation and the work state before the replay. Kept: the page's own error lines and the
   * requests it sent that no `state` named yet (the replay may not hold them yet).
   */
  function resetSession() {
    $("feed").replaceChildren(...$("feed").querySelectorAll(".msg.error"));
    $("asking").hidden = true;
    S.requests = Object.fromEntries([...S.unseen].filter(id => S.requests[id]).map(id => [id, S.requests[id]]));
    S.unseen = new Set(Object.keys(S.requests));
    S.named.clear();
    S.busy = false;
    S.current = null;
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
    if (!S.kind) return;
    loadProjects();
    if (S.dir) reloadProject();
    mod().onEvent?.({ kind: "reconnected" });
  }

  function handle(ev) {
    switch (ev.kind) {
      case "request": {
        const req = ev.request;
        remember(req, true);
        const d = describe(req);
        feed("you", d.text, d.images);
        break;
      }
      case "agent": feed("claude", ev.text, ev.images); break;
      case "note": feed("note", ev.text); break;
      case "turn": feed("turn", ""); break;
      case "state":
        S.busy = !!ev.busy;
        S.current = ev.current || null;
        S.queued = ev.queued || [];
        [S.current, ...S.queued].filter(Boolean).forEach(id => { S.unseen.delete(id); S.named.add(id); });
        renderState();
        break;
      case "ask":
        $("asking").textContent = `Waiting for your approval in Claude Code: ${[ev.tool, ev.text].filter(Boolean).join(": ")}`;
        $("asking").hidden = false;
        break;
      case "ask-done": $("asking").hidden = true; break;
      case "changed":
        if (ev.project_kind !== S.kind) break;
        loadProjects();
        if (ev.project === S.dir) reloadProject();
        break;
      case "projects": if (ev.project_kind === S.kind) loadProjects(); break;
      case "replayed": S.replaying = false; onChange(); return;
      case "ended":
        S.busy = false;
        S.current = null;
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
  const D = { version: null, tool: "box", marks: [], drawing: null };
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

  function openDetail(version) {
    const m = mod();
    D.version = version;
    D.marks = [];
    D.drawing = null;
    $("d-img").src = fileUrl(version.image);
    $("d-title").textContent = m.detailTitle?.(version) || `${(S.project.project || {}).name || ""} · v${version.n}`;
    $("d-meta").replaceChildren(...(m.versionInfo(version) || []).flatMap(([label, text, long]) =>
      [h("dt", {}, label), h("dd", { class: long ? "long" : null }, text)]));
    $("d-note").value = "";
    const send = h("button", { class: "primary", onclick: () => sendChange(send) }, "Send changes to Claude");
    $("d-acts").replaceChildren(send, ...(m.detailActions(version) || []).map(a =>
      h("button", { class: "secondary", onclick: () => a.run(version) }, a.label)));
    renderMarks();
    $("shade").hidden = false;
    setTool("box");
  }
  function closeDetail() { $("shade").hidden = true; D.version = null; }

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
  }

  async function start() {
    wire();
    resetSession();
    connect();
    try { S.config = await api.get("/api/config"); } catch (e) { return error(`Could not reach the studio server: ${e.message}`); }
    const ready = S.config.kinds.filter(usable).map(k => k.id);
    const saved = localStorage.getItem("studio-kind");
    renderKinds();
    if (ready.length) selectKind(ready.includes(saved) ? saved : ready[0]);
  }
  document.addEventListener("DOMContentLoaded", start);

  return {
    register: m => { modules[m.id] = m; },
    h, seg, plural, baseName, actionBar, markLines, when, day, api, fileUrl, download, request, pending, startProject,
    feed, error, openDetail, closeDetail,
  };
})();
