/*
 * Short-video workspace (kind `short-video`, workspace skill `videos`), in two views of the centre column.
 * Storyboard view: 1 what the film is about, 2 picture style (with the style samples while the film's style is to be
 * picked), 3 storyboard, 4 voice, 5 music, 6 scenes (each scene's recording and animation, Remake), 7 films; a step
 * shows a check once what it makes exists. The action bar makes the film, in both views. A button is disabled while a
 * pending request of the project would duplicate or conflict with the one it sends (`blocker`). Scene view: 1 the picture in the
 * shell's detail view, placed in the page, with its versions; 2 the sentences, each with a collapsed voice part;
 * 3 movement and timing; the scene's own style; 4 what to change in this scene. The scene view holds the plan only;
 * "See the result" opens the scene's row in step 6.
 * A scene drawn in its page (an HTML scene without `image`) has no picture: its step 1 shows the stills of its page
 * versions (picture versions whose sidecar names `page_version`) where the others show pictures, and it has no own style.
 * The page edits storyboard.json directly (/api/storyboard, one write at a time, with the base it read) and the film
 * settings with /api/film. Registers with the Studio shell (shell.js), which draws everything around it.
 */
"use strict";

(() => {
  const { h, seg, plural, baseName, when, api, fileUrl, download, request, pending, startProject, error, nice,
    versionStyle, brandSelect, stylePicker, dropZone, upload, refThumb, versionRows, editActions, describeEdit,
    openDetail, refreshDetail, releaseDetail, progress, copyToRefs, IMAGE_TYPES, runStatus, started } = Studio;

  const SHAPES = [["16:9", "Wide (16:9)"], ["9:16", "Phone (9:16)"]];
  const shapeLabel = ratio => (SHAPES.find(s => s[0] === ratio) || [ratio, ratio])[1];
  const LENGTHS = [[30, "About 30 seconds", "about 30 seconds"], [60, "About 1 minute", "about 1 minute"],
    [120, "About 2 minutes", "about 2 minutes"], [180, "About 3 minutes", "about 3 minutes"]];
  const aim = s => (LENGTHS.find(l => l[0] === s) || [s, "", `about ${s} seconds`])[2];
  /** The model id of a config.yaml task (speech, music, video, presenter), or null. */
  const taskModel = task => Studio.models().tasks[task] || null;
  /** The speech models of the voice picker (media:voiceover's routes), the default (config.yaml's speech model) first. */
  const speechModels = () => Studio.models().speech || [];
  /** The entry of a voice's model id; the default one for null. */
  const speechModel = id => speechModels().find(m => (id ? m.id === id : m.default)) || null;
  /** A voice's model id; null is the default, shown by its id. */
  const modelName = id => id || (speechModel(null) || {}).id || "no speech model in config.yaml";
  const SPEEDS = [[0.9, "Slower"], [1, "Normal"], [1.1, "Faster"]];
  const speedLabel = v => (SPEEDS.find(s => s[0] === Number(v)) || [v, `${v}×`])[1];
  const hasSpeed = id => Boolean((speechModel(id) || {}).speed);
  const hasStyle = id => Boolean((speechModel(id) || {}).style);
  const voiceLabel = v => `${modelName(v.model)}, ${v.name || "default voice"}`;
  /** The settings of a new film, from /api/config (its "Made by" from the AUTHOR_NAME setting). */
  const defaultFilm = () => Studio.config().film;
  const MUSIC_MODES = [["made", "Made for this film"], ["own", "My own track"], ["none", "No music"]];
  const VOLUMES = [["quiet", "Quiet"], ["normal", "Normal"], ["louder", "Louder"]];
  /** The style cards that leave the film's style to the agent, by `style` value. */
  const CARDS = {
    auto: { icon: "auto", title: "Choose for me", line: "3 styles picked to suit the brief", asked: "3 catalogue styles to choose from" },
    invent: { icon: "invent", title: "Invent new styles", line: "3 new styles made for this film", asked: "3 new styles to choose from" },
  };
  const KIND_WORDS = { title: "title card", summary: "summary card", end: "closing card", manim: "animation", video: "video model", presenter: "presenter", clip: "video clip" };
  /** The engines of a scene that is neither a template nor a clip: [engine, label, config task or null]. `html` is the
   *  storyboard without `engine`. */
  const ENGINES = [["html", "Animated page (HyperFrames)", null], ["manim", "Manim animation", null],
    ["video", "Video model, from the scene's picture", "video"],
    ["presenter", "Presenter: the person in the scene's picture speaks the narration", "presenter"]];
  /** Engines that animate the scene's picture, so they need one; the presenter takes no brief. */
  const NEEDS_PICTURE = ["video", "presenter"];
  const STATES = { ready: ["st-ready", "Ready"], voice: ["st-voice", "Needs voice"], render: ["st-render", "Needs render"] };
  const AUDIO = [".mp3", ".wav", ".m4a", ".aac", ".flac", ".ogg"];
  const SOURCES = [".pdf", ".txt", ".md", ".docx", ".pptx", ".xlsx", ".csv", ".html", ...AUDIO];
  /** Reference videos by suffix, with the type the server takes, and their largest size (the server's REF_VIDEO_MAX). */
  const VIDEO_REFS = { ".mp4": "video/mp4", ".mov": "video/quicktime", ".webm": "video/webm" };
  const REF_VIDEO_MB = 45;
  const isVideoRef = path => suffix(path) in VIDEO_REFS;
  const suffix = name => (name.match(/\.[^.]+$/) || [""])[0].toLowerCase();
  /** Requests that write pictures of the scene they name (`use-still`: a drawn scene's still), and those that write
   *  pictures of many scenes. */
  const PICTURE_ACTIONS = ["change", "variations", "other-styles", "use-still"];
  const MANY_PICTURES = ["storyboard", "use-style", "style-samples", "add-scene"];
  const WORDS_PER_SECOND = 2.5;

  const clone = x => (x == null ? x : structuredClone(x));
  const same = (a, b) => JSON.stringify(a) === JSON.stringify(b);
  /** "the_injection" -> "The injection". */
  const titleOf = id => (id ? id.charAt(0).toUpperCase() + id.slice(1).replace(/_/g, " ") : "");
  function mmss(s) {
    const t = Math.round(s || 0);
    return `${Math.floor(t / 60)}:${String(t % 60).padStart(2, "0")}`;
  }
  const words = text => (text.trim() ? text.trim().split(/\s+/).length : 0);

  /* ---------- state ---------- */

  let root = null;         // the workspace element
  let project = null;      // answer of /api/project; null in a blank workspace
  let sb = null;           // the storyboard as edited here
  let mtime = null;        // storyboard_mtime of the last read or write
  let film = null;        // the film settings shown: project.json's film, or a new film's
  let blankFilm = null;    // the film settings chosen in a blank workspace, given to the project it becomes
  let form = null;         // the storyboard request being edited: brief, refs, sources, style
  let view = null;         // the open scene's id, or null for the storyboard view
  let shown = null;        // scene view: the picture version shown, {scene, n}
  let notice = null;       // the notice of a refused storyboard write
  let writeHint = null;    // why the storyboard is not saved while being edited
  let fromCatalogue = false; // style samples: the catalogue shown instead
  let ownStyle = false;    // scene view: "Own style" chosen before a style is picked
  let adding = false;      // storyboard view: the box for a new scene is open
  let bar = null, barKey = null;
  const openParts = new Set(); // keys of the <details> the user opened
  const fixes = new Map();     // per "<project>:<film n>": the findings unchecked (k) and the note of its Fix
  let sections = [];

  const P = () => (project && project.project) || {};
  const V = () => (project && project.video) || {};
  const scenes = () => (sb && Array.isArray(sb.scenes) ? sb.scenes : []);
  const sceneOf = id => scenes().find(s => s.id === id) || null;
  const indexOf = id => scenes().findIndex(s => s.id === id);
  const info = id => (V().scenes || []).find(s => s.id === id) || { id, state: null, pictures: [], picture: null, still: null, recording: null, clip: null, page: null };
  const samples = () => P().samples || null;
  const reqs = () => (project ? pending(project.dir) : []);

  /** The picture of a scene: its version, else the file its `image` names when that is not a version still to be
   *  made (a new storyboard reserves `<id>/v<N>.png` before the picture exists), else null. */
  function pictureOf(scene) {
    const i = info(scene.id), v = i.pictures.find(p => p.n === i.picture);
    if (v) return v.image;
    if (!scene.image || !project || /^[a-z0-9_]+\/v\d+\.png$/.test(scene.image)) return null;
    return `${project.dir}/images/${scene.image}`;
  }
  /** Seconds of a scene: its `length` (a silent HTML scene), its recording, else its words at 2.5 a second, else its clip. */
  function secs(scene) {
    const i = info(scene.id);
    if (typeof scene.length === "number") return scene.length;
    if (i.recording && i.recording.duration) return i.recording.duration;
    const n = words((scene.narration || []).join(" "));
    return n ? n / WORDS_PER_SECOND : (i.clip && i.clip.duration) || 0;
  }
  const total = () => scenes().reduce((a, s) => a + secs(s), 0);
  const kindWord = s => KIND_WORDS[s.template] || KIND_WORDS[s.engine] || "";
  /** A scene drawn in its page: an HTML scene (no template, engine absent or html) without `image`. It has no
   *  picture, so it is never a missing picture and its scene view has no picture step. */
  const drawn = s => !!s && !s.template && (!s.engine || s.engine === "html") && !s.image;
  /** What a drawn scene shows, for its placeholder: its first beat (the On screen text), else its brief. */
  const drawnText = s => ((s.beats || [])[0] || s.brief || "").trim();
  /** The placeholder of a drawn scene where a picture would be: the pencil, "Drawn scene" and what it shows, on the
   *  dotted paper that marks a drawn scene (a missing picture is grey stripes). */
  const drawnThumb = s => h("div", { class: "noimg drawn", title: (s.brief || "").trim() },
    h("b", {}, Studio.icon("draw"), "Drawn scene"), h("span", {}, drawnText(s)));
  /** Whether a picture version is a still of a drawn scene's page: its sidecar names the `page_version`. */
  const isStill = v => !!v && typeof v.page_version === "string";
  /** The still a drawn scene shows where a picture would be: its newest still (the server's `still`), else null. */
  function stillOf(scene) {
    const i = info(scene.id), v = drawn(scene) && i.still != null ? i.pictures.find(p => p.n === i.still) : null;
    return v ? v.image : null;
  }
  /** Whether a scene still lacks what step 3 makes: a picture it names, or a drawn scene's still. */
  const missing = s => (s.image && !pictureOf(s)) || (drawn(s) && !stillOf(s));
  /** What a scene's thumbnail shows: its picture, else its still. */
  const thumbOf = scene => pictureOf(scene) || stillOf(scene);
  const stateOf = id => info(id).state;
  /** Step 3 is shown once the storyboard has scenes or one is being written. */
  const boardShown = () => !!project && (scenes().length > 0 || reqs().some(p => p.request.action === "storyboard"));

  /** The current make-film request, or null. */
  const filmRun = () => (reqs().find(p => p.current && makesFilm(p.request)) || {}).request || null;
  /** Whether a request makes a film of this project: `make-film`, `export-mp4`, `fix`, a `storyboard` with `make_film`
   *  or in `auto` autonomy, and a `style-samples` in `auto` autonomy. */
  const makesFilm = r => ["make-film", "export-mp4", "fix"].includes(r.action) ||(r.action === "storyboard" && (r.make_film || Studio.autonomy() === "auto"))
    || (r.action === "style-samples" && Studio.autonomy() === "auto");
  /** Whether a film-making request ends with an MP4 (`export-mp4`, `fix`); the others end with the HTML film. */
  const mp4Run = r => ["export-mp4", "fix"].includes(r.action);
  /** Whether an ISO time is at or after `since` (ms since the epoch). */
  const madeSince = (iso, since) => !!(iso && since && Date.parse(iso) >= since);
  /** Where the current make-film `r` stands with scene `id`, from the files written since it started: null when the
   *  scene needs nothing, else "voice" (it needs a recording and has no new one), "recorded" (a new recording, no new
   *  clip), "render" (it needs only a render, no new clip yet) or "done" (a new clip). */
  function filmStage(r, id) {
    const since = started(r.id), i = info(id), s = sceneOf(id) || {};
    // In a run that ends with the HTML film, an HTML scene is done with a new page version; in an MP4 run, with a clip.
    const voiced = madeSince(i.recording && i.recording.created, since), rendered = madeSince(i.clip && i.clip.created, since)
      || (!mp4Run(r) && madeSince(i.page && i.page.created, since));
    if (rendered) return "done";
    if (voiced) return "recorded";
    if (stateOf(id) === "ready") return null;
    return stateOf(id) === "voice" && (s.narration || []).length ? "voice" : "render";
  }

  /** "New picture…" ("New still…" for a drawn scene) while the current request makes pictures of the scene, else
   *  null: the storyboard's mark. */
  const pictureBusy = id => (reqs().some(({ request: r, current }) => current && r.scene === id && PICTURE_ACTIONS.includes(r.action))
    ? (drawn(sceneOf(id)) ? "New still…" : "New picture…") : null);
  /** What the current request does to a scene's recording or animation, as its chip in step 6 says: null when nothing. */
  function busyText(id) {
    for (const { request: r, current } of reqs()) {
      if (!current) continue;
      if (r.scene === id && r.action === "remake-scene") return "Remaking…";
      if (makesFilm(r)) {
        const stage = filmStage(r, id);
        if (stage === "voice" || stage === "render") return "Being made…";
        if (stage === "recorded") return "Recorded, rendering…";
      }
    }
    return null;
  }
  /**
   * Which pending requests a request blocks on, by its action: one that it would repeat, or whose work it would undo
   * or make pointless (a film or a scene remade from a storyboard about to be replaced).
   */
  const BLOCKS = {
    "make-film": r => ["make-film", "export-mp4", "fix", "storyboard", "style-samples"].includes(r.action),
    "export-mp4": r => ["make-film", "export-mp4", "fix", "storyboard", "style-samples"].includes(r.action),
    fix: r => ["make-film", "export-mp4", "fix", "storyboard", "style-samples"].includes(r.action),
    "remake-scene": (r, f) => ["make-film", "export-mp4", "fix", "storyboard"].includes(r.action) ||(r.action === "remake-scene" && r.scene === f.scene),
    storyboard: r => r.action === "storyboard",
    "style-samples": r => ["storyboard", "style-samples", "use-style"].includes(r.action),
    "use-style": r => ["storyboard", "style-samples", "use-style"].includes(r.action),
    music: r => r.action === "music",
    "own-music": r => r.action === "own-music",
    phone: (r, f) => r.action === "phone" && r.version === f.version,
    review: (r, f) => r.action === "review" && r.version === f.version,
  };
  /** The pending request of the project that the request `fields` would duplicate or conflict with, or null. */
  const blocker = fields => {
    const blocks = BLOCKS[fields.action];
    return (blocks && reqs().find(p => blocks(p.request, fields))) || null;
  };
  /** What a pending request is, for a button's title and the bar's summary: "Running: Make the film". */
  const pendingText = p => `${p.current ? "Running" : "Waiting"}: ${(describe(p.request) || { text: p.request.action }).text.split("\n")[0]}`;
  /** Sends a request unless a pending one blocks it; answers its id, or null. */
  const send = fields => (blocker(fields) ? null : request(fields));
  /** The attributes of a button that sends `fields`: disabled, with why, while a pending request blocks it. */
  const guard = fields => { const b = blocker(fields); return { disabled: !!b, title: b ? pendingText(b) : null }; };

  /** True while the current or a queued request writes pictures of the scene. */
  const picturesLocked = id => reqs().some(({ request: r }) =>
    (r.scene === id && PICTURE_ACTIONS.includes(r.action)) || MANY_PICTURES.includes(r.action));

  function chip(id) {
    const busy = busyText(id), run = filmRun();
    if (busy) return h("span", { class: "state st-busy" }, busy);
    if (run && filmStage(run, id) === "done") return h("span", { class: "state st-ready" }, "Made");
    const [cls, label] = STATES[stateOf(id)] || STATES.voice;
    return h("span", { class: `state ${cls}` }, label);
  }

  /* ---------- voices ---------- */

  /**
   * The voice of a sentence as media:short-video resolves it: `own` (per-sentence settings) over `base` (its
   * speaker's voice, else the film's); an own model other than the base's drops the base's name. A null model is
   * config.yaml's speech model; speed and style only for a model that takes them.
   */
  function resolve(own, base) {
    const set = Object.fromEntries(Object.entries(own || {}).filter(([, x]) => x != null && x !== ""));
    const v = { model: null, name: null, speed: null, style: null, ...(base || {}) };
    if ("model" in set && set.model !== (v.model ?? null)) v.name = null;
    Object.assign(v, set);
    const model = v.model || null;
    return { model, name: v.name || null, speed: hasSpeed(model) ? Number(v.speed ?? 1) : 1, style: hasStyle(model) ? v.style || null : null };
  }
  const speakerOf = (scene, k) => (scene.speakers ? scene.speakers[k] : null) || null;
  const speakerVoice = name => (name && sb && sb.speakers ? sb.speakers[name] || null : null);
  const baseVoice = (scene, k) => speakerVoice(speakerOf(scene, k)) || film.voice;
  const inherited = (scene, k) => resolve(null, baseVoice(scene, k));
  const sentenceVoice = (scene, k) => resolve((scene.voices || [])[k], baseVoice(scene, k));
  const voiceText = v => [voiceLabel(v), hasSpeed(v.model) ? `${speedLabel(v.speed).toLowerCase()} speed` : null].filter(Boolean).join(", ");
  /** Number of different voices that speak the scene. */
  const voicesUsed = scene => new Set((scene.narration || []).map((_, k) => JSON.stringify(sentenceVoice(scene, k)))).size;

  /* ---------- storyboard writes ---------- */

  const W = { timer: null, inflight: false, again: false };
  const writing = () => !!(W.inflight || W.timer || W.again);

  /** The rules of the server's storyboard check that the page's edits can break; a message, or null. */
  function check(b) {
    if (!b.scenes.length) return "A storyboard needs a scene.";
    const ended = new Set();
    let previous = null;
    for (const [i, s] of b.scenes.entries()) {
      const html = !s.template && (s.engine === undefined || s.engine === null || s.engine === "html");
      const clip = (s.engine === "clip" && !s.template) || typeof s.length === "number";
      const said = s.narration || [], shown = s.beats || [];
      const world = typeof s.world === "string" ? s.world : null;
      if (world !== previous && previous !== null) ended.add(previous);
      if (world !== null && ended.has(world))
        return `Scene ${i + 1} belongs to world "${world}", whose scenes must follow each other; move it next to them.`;
      previous = world;
      if (world !== null && (!html || s.image !== undefined))
        return `Scene ${i + 1} is a scene of world "${world}", which is HTML only, with no picture; keep the HTML engine and remove the picture.`;
      if (s.length !== undefined && (!html || said.length))
        return `Scene ${i + 1} has a fixed length, which only an HTML scene without narration has; keep the HTML engine and no sentences.`;
      if (!said.length && !clip) return `Scene ${i + 1} needs a sentence.`;
      if (said.some(t => !t.trim()) || shown.some(t => !t.trim()))
        return `Scene ${i + 1}: write what is said and what is on screen in every sentence; it is saved once both are filled in.`;
      if (!s.template && s.engine !== "clip" && s.engine !== "presenter" && !(s.brief || "").trim())
        return `Scene ${i + 1}: write ${drawn(s) ? "what the scene draws and how it moves" : "how the picture moves"}; it is saved once that is filled in.`;
      if (s.engine === "video" && !s.image) return `Scene ${i + 1}: a video model animates the scene's picture; add a picture first.`;
      if (s.engine === "presenter" && !s.image) return `Scene ${i + 1}: the presenter is the person in the scene's picture; add a picture first.`;
    }
    return null;
  }

  /** The storyboard changed here: a text edit is saved 1 s after the last keystroke, any other edit at once. */
  function edited(text) {
    clearTimeout(W.timer);
    W.timer = null;
    if (text) W.timer = setTimeout(flush, 1000);
    else flush();
  }

  async function flush() {
    clearTimeout(W.timer);
    W.timer = null;
    if (!project || !sb) return;
    if (W.inflight) { W.again = true; return; }
    const problem = check(sb);
    if (problem !== writeHint) { writeHint = problem; render(); }
    if (problem) return;
    W.inflight = true;
    const dir = project.dir;
    try {
      const { storyboard_mtime } = await api.post("/api/storyboard", { project: dir, storyboard: clone(sb), base: mtime });
      if (project && dir === project.dir) mtime = storyboard_mtime;
    } catch (e) {
      if (e.status === 409 && e.data && project && dir === project.dir) {
        sb = clone(e.data.storyboard);
        mtime = e.data.storyboard_mtime;
        W.again = false;
        clearTimeout(W.timer);
        W.timer = null;
        notice = "The storyboard changed meanwhile; your last edit was not saved";
        if (view && !sceneOf(view)) { view = null; build(); } else render();
      } else error(`Could not save the storyboard: ${e.message}`);
    } finally {
      W.inflight = false;
      if (W.again) { W.again = false; flush(); }
    }
  }

  /** A text field leaves: its pending write goes now. */
  const leave = () => { if (W.timer) flush(); };
  /** An edit other than typing: the storyboard is redrawn and saved at once. */
  const commit = () => { notice = null; render(); edited(false); };

  /* ---------- sections: redrawn only when what they show changed ---------- */

  /** A part of the view: its element, a signature of what it shows, and how to build it. */
  function section(sig, build) {
    const s = { el: h("div"), sig, build, last: null };
    sections.push(s);
    return s;
  }

  /** The focused text field (by its data-k) and its selection, so a redraw can give them back. */
  function focused() {
    const a = document.activeElement;
    return a && root && root.contains(a) && a.dataset.k ? { k: a.dataset.k, s: a.selectionStart, e: a.selectionEnd } : null;
  }
  function refocus(f) {
    if (!f) return;
    const el = root.querySelector(`[data-k="${CSS.escape(f.k)}"]`);
    if (!el || document.activeElement === el) return;
    el.focus({ preventScroll: true });
    try { if (f.s != null) el.setSelectionRange(f.s, f.e); } catch { /* selects have no selection */ }
  }

  function render() {
    if (!root) return;
    const f = focused();
    for (const s of sections) {
      const sig = s.sig();
      if (sig === s.last) continue;
      s.last = sig;
      s.el.replaceChildren(...[s.build()].flat().filter(Boolean));
    }
    refocus(f);
    refold();
    afterRender();
    summary();
  }
  /** After the user's own typing what the sections show is current: no redraw for it. */
  const touch = () => { for (const s of sections) s.last = s.sig(); summary(); };

  /** The notice of a refused storyboard write, until hidden or the next edit. */
  const noticeBox = () => (notice ? h("div", { class: "notice inline sv-notice" }, notice,
    h("button", { class: "x", title: "Hide", onclick: () => { notice = null; render(); } }, "×")) : null);

  /** A <details> that remembers being open across redraws. */
  const details = (key, attrs, ...kids) => h("details", { ...attrs, open: openParts.has(key),
    ontoggle: e => { if (e.target.open) openParts.add(key); else openParts.delete(key); } }, ...kids);

  /** A text field of the storyboard: set(value) on each keystroke, saved 1 s later or when it loses focus. */
  const textField = (tag, key, value, set, { onedit, ...attrs } = {}) => h(tag, { ...attrs, "data-k": key, value,
    oninput: e => { set(e.target.value); edited(true); touch(); onedit?.(); }, onblur: leave });

  /* ---------- one shared audio player ---------- */

  const player = new Audio();
  let playing = null; // the ▶ button of what plays
  function play(path, button) {
    const again = playing === button;
    player.pause();
    if (playing) { playing.classList.remove("on"); playing.textContent = "▶"; }
    playing = null;
    if (again || !path) return;
    player.src = fileUrl(path);
    player.play().catch(e => error(`Could not play the sound: ${e.message}`));
    playing = button;
    button.classList.add("on");
    button.textContent = "■";
  }
  player.addEventListener("ended", () => { if (playing) play(null, playing); });

  const sameVoice = (a, b) => (a.model || null) === (b.model || null) && (a.name || null) === (b.name || null)
    && Number(a.speed || 1) === Number(b.speed || 1) && (a.style || null) === (b.style || null);
  /** Plays the newest sample of the voice, or asks for one. */
  async function sample(voice, button) {
    const v = { model: voice.model ?? null, name: voice.name ?? null, speed: Number(voice.speed || 1), style: voice.style || null };
    const s = (V().samples || []).find(x => x.voice && sameVoice(x.voice, v));
    if (s) return play(s.path, button);
    const waiting = "A sample is being made; press ▶ again once it is listed";
    if (reqs().some(p => p.request.action === "voice-sample" && p.request.voice && sameVoice(p.request.voice, v))) { button.title = waiting; return; }
    if (!(await startProject())) return;
    if (await request({ action: "voice-sample", voice: v })) button.title = waiting;
  }
  const playButton = (title, run) => {
    const b = h("button", { class: "play", type: "button", title }, "▶");
    b.onclick = e => { e.stopPropagation(); run(b); };
    return b;
  };

  /* ---------- film settings ---------- */

  /** "Made by" of the last film settings changed in this browser, null when never changed: a blank workspace starts
   *  with it, else with the AUTHOR_NAME setting's names. */
  const AUTHOR_KEY = "studio-author";
  const savedAuthor = () => { try { const a = JSON.parse(localStorage.getItem(AUTHOR_KEY)); return Array.isArray(a) ? a : null; } catch { return null; } };

  const filmOf = data => {
    const d = defaultFilm(), saved = data ? null : savedAuthor();
    const f = { ...clone(d), ...(saved ? { author: saved } : {}), ...clone((data && data.project && data.project.film) || {}) };
    f.voice = { ...d.voice, ...(f.voice || {}) };
    f.music = { ...d.music, ...(f.music || {}) };
    return f;
  };

  /** Changes keys of the film settings: here at once, in project.json through /api/film. */
  async function setFilm(patch) {
    Object.assign(film, clone(patch));
    if (patch.author) localStorage.setItem(AUTHOR_KEY, JSON.stringify(patch.author));
    render();
    if (!project) return;
    try {
      const answer = await api.post("/api/film", { project: project.dir, film: patch });
      if (answer && answer.film) { film = { ...film, ...answer.film }; P().film = clone(answer.film); }
    } catch (e) {
      error(`Could not change the film settings: ${e.message}`);
      film = filmOf(project);
    }
    render();
  }

  /* ---------- storyboard view ---------- */

  function boardSections() {
    const has = () => scenes().length > 0;
    section(() => JSON.stringify([notice, writeHint]), () => [noticeBox(), writeHint ? h("div", { class: "notice inline sv-notice" }, writeHint) : null]);
    const pend = actions => reqs().filter(p => actions.includes(p.request.action)).map(p => [p.request.id, p.current]);
    section(() => JSON.stringify([!!project, has(), film.brand, film.shape, film.length, film.author, film.silent, film.review, form.refs, form.sources,
      V().error, pend(["storyboard"])]),
      fold("brief", () => step() === "brief", briefSummary, stepBrief, () => false, has));
    section(() => JSON.stringify([has(), samples(), fromCatalogue, P().style, Studio.autonomy(), sampleData(), project && project.dir, form.style,
      earlierSamples(samples() ? samples().scene : keyScene(), (samples() && samples().versions) || []).map(v => v.n),
      pend(["storyboard", "style-samples", "use-style"])]),
      fold("style", () => step() === "style", styleSummary, stepStyle, () => busyWith(["style-samples", "use-style"]),
        () => !!P().style && !samples()));
    section(() => JSON.stringify([project && project.dir, sb && sb.speakers, scenes(), V().scenes, P().scene_styles, samples(), adding,
      film.length, film.voice, reqs().map(p => [p.request.id, p.current]), project && reqs().filter(p => p.request.action === "add-scene").length]),
      fold("board", () => step() === "board", () => `${plural(scenes().length, "scene")} · ${mmss(total())}`, stepBoard,
        () => busyWith(["storyboard", "add-scene", ...PICTURE_ACTIONS]),
        () => has() && !scenes().some(missing)));
    section(() => JSON.stringify([!!project, has(), boardShown(), film.voice, film.silent, sb && sb.speakers]),
      fold("voice", () => step() === "voice", () => (film.silent ? "silent film: no narration" : `voice ${voiceText(film.voice)}`), stepVoice, () => busyWith(["voice-sample"]), voiced));
    section(() => JSON.stringify([!!project, has(), boardShown(), film.music, V().music, V().music_used, pend(["music", "own-music"])]),
      fold("music", () => step() === "voice", musicSummary, stepMusic, () => busyWith(["music", "own-music"]),
        () => film.music.mode === "none" || V().music_used != null));
    section(() => JSON.stringify([!!project, samples(), scenes(), V().scenes, openClip, openPlayer, Studio.autonomy(), reqs().filter(p => makesFilm(p.request) || ["remake-scene", "storyboard"].includes(p.request.action))
      .map(p => [p.request.id, p.current, progress(p.request.id)])]),
      fold("scenes", () => step() === "films", scenesSummary, stepScenes,
        () => busyWith(["remake-scene"]) || reqs().some(p => makesFilm(p.request)), animated));
    section(() => JSON.stringify([project && project.dir, openPlayer]), playerSection);
    section(() => JSON.stringify([!!project, samples(), scenes(), V().films, V().html_films, V().scenes, V().music, V().music_used, film.shape, film.music.mode, film.review, Studio.autonomy(),
      reqs().filter(p => makesFilm(p.request) || ["review", "phone", "storyboard", "style-samples"].includes(p.request.action)).map(p => [p.request.id, p.current, progress(p.request.id)])]),
      fold("films", () => step() === "films", filmsSummary, stepFilms,
        () => busyWith(["review"]) || reqs().some(p => makesFilm(p.request)), () => !filmChanges()));
  }

  /**
   * The step being worked on, the one card open by default: the brief until the storyboard has scenes (the board
   * while one is written), the style until the film has one, then the board while scene pictures are missing or
   * being made, the voice and the music (both open) once every picture is there and no film is made, the scenes and
   * the films while one is made, and the board again once there is a film. A project that cannot be opened shows its brief card.
   */
  function step() {
    if (V().error) return "brief";
    if (!scenes().length) return busyWith(["storyboard"]) ? "board" : "brief";
    if (samples() || !P().style) return "style";
    if (reqs().some(p => makesFilm(p.request))) return "films";
    if ((V().films || []).length || (V().html_films || []).length) return "board";
    const pictures = busyWith(["storyboard", "use-style", "add-scene", ...PICTURE_ACTIONS])
      || scenes().some(missing);
    return pictures ? "board" : "voice";
  }
  /** Whether a request of one of `actions` is pending on the project. */
  const busyWith = actions => reqs().some(p => actions.includes(p.request.action));

  /** The steps made foldable by fold(), with their last card, so each redraw gives them their current default. */
  let folders = [];
  /** A step's builder made foldable by its title: `open()` is its default fold, `sum()` the line shown folded,
   *  `busy()` whether work runs in it. */
  const fold = (key, open, sum, build, busy = () => false, done = () => false) => {
    const f = { card: null, open, busy, done };
    folders.push(f);
    return () => {
      const el = build();
      f.card = el instanceof Element && el.classList.contains("card")
        ? Studio.foldable(el, { key: `${project ? project.dir : ""}:${key}`, open: open(), summary: sum(), busy: busy() }) : null;
      markDone(f);
      return el;
    };
  };
  /** A finished step shows a check in place of its number. */
  function markDone(f) {
    const num = f.card && f.card.querySelector(":scope > h2 > .num");
    if (num) num.classList.toggle("done", !!f.done());
  }
  /** Gives every step card its current default fold, busy mark and done mark. */
  function refold() {
    for (const f of folders) if (f.card && f.card.isConnected) { f.card.foldDefault(f.open()); f.card.foldBusy(f.busy()); markDone(f); }
  }
  const briefSummary = () => [form.brief || P().brief || "", shapeLabel(film.shape), aim(film.length), film.silent ? "silent" : null, film.review ? "each MP4 reviewed" : null]
    .filter(Boolean).join(" · ");
  const musicSummary = () => (film.music.mode === "none" ? "no music" : V().music_used != null ? `music v${V().music_used}`
    : film.music.mode === "made" ? "made with the film" : "own track not uploaded");
  function styleSummary() {
    const st = scenes().length ? P().style : null;
    if (st) return st.invented ? `${st.invented.name} (new)` : nice(st.name);
    const v = form.style || "auto";
    return CARDS[v] ? CARDS[v].title : nice(v);
  }

  function stepBrief() {
    if (V().error) return h("section", { class: "card" }, h("h2", {}, "This project cannot be opened here"), h("div", { class: "err" }, V().error));
    const has = scenes().length > 0;
    ui.brief = h("textarea", { id: "brief", value: form.brief, "data-k": "brief",
      placeholder: "For example: a one-minute explainer for new starters on how expenses work, from the policy I attach",
      oninput: e => { form.brief = e.target.value; e.target.closest(".card")?.foldSummary?.(briefSummary()); } });
    const refs = h("div", { class: "refs" },
      dropZone("Drop sources (notes, articles, PDFs), pictures and reference videos (MP4, MOV, WebM) to use here, or click to choose files",
        [...IMAGE_TYPES, ...Object.keys(VIDEO_REFS), ...SOURCES].join(","), addFiles),
      form.sources.map(path => h("div", { class: "src", title: baseName(path) }, Studio.icon("file"), baseName(path),
        h("button", { class: "x", title: "Remove", onclick: () => { form.sources = form.sources.filter(p => p !== path); render(); } }, "×"))),
      form.refs.map(path => {
        const remove = () => { form.refs = form.refs.filter(p => p !== path); render(); };
        return isVideoRef(path) ? h("div", { class: "ref", title: `${baseName(path)} · reference video` },
          h("video", { src: fileUrl(path) + "#t=0.5", muted: true, preload: "metadata", style: "width:100%;height:100%;object-fit:cover" }),
          h("button", { type: "button", title: "Remove", onclick: remove }, "×")) : refThumb(path, remove);
      }));
    const shape = h("select", { disabled: has, title: has ? "A storyboard with scenes keeps its shape; a phone version is made from a film" : null,
      onchange: e => setFilm({ shape: e.target.value }) }, SHAPES.map(([v, l]) => h("option", { value: v }, l)));
    shape.value = film.shape;
    const length = h("select", { onchange: e => setFilm({ length: +e.target.value }) }, LENGTHS.map(([v, l]) => h("option", { value: v }, l)));
    length.value = String(film.length);
    const author = h("input", { type: "text", value: (film.author || []).join(", "), "data-k": "author", placeholder: "For example: Alice Example, Bob Example",
      onchange: e => setFilm({ author: e.target.value.split(",").map(x => x.trim()).filter(Boolean) }) });
    const field = (label, control) => h("div", {}, h("label", { class: "f" }, label), control);
    return h("section", { class: "card", id: "sv-brief" },
      h("h2", {}, h("span", { class: "num" }, "1"), "What is the film about?",
        h("span", { class: "hint" }, "who it is for and what they should take away; plain words are fine")),
      ui.brief, refs,
      h("div", { class: "sv-row" },
        field("Brand", brandSelect(film.brand, v => setFilm({ brand: v }))),
        field("Shape", shape), field("Length", length), field("Made by (shown in the credits)", author)),
      h("label", { class: "switch", style: "margin-top:12px" },
        h("input", { type: "checkbox", checked: !!film.silent, onchange: e => setFilm({ silent: e.target.checked }) }), h("span"),
        "Silent film", h("span", { class: "hint" }, " · no narration: each scene lasts a set time, with music only")),
      h("label", { class: "switch", style: "margin-top:12px" },
        h("input", { type: "checkbox", checked: !!film.review, onchange: e => setFilm({ review: e.target.checked }) }), h("span"),
        "Review each new MP4", h("span", { class: "hint" }, " · after Export MP4 a second model watches it and lists what to fix; in automatic mode the fixes are made too")),
      has ? h("div", { class: "foot" },
        h("button", { class: "secondary", ...guard({ action: "storyboard" }), onclick: e => writeStoryboard(e.currentTarget) }, "Write a new storyboard from this"),
        h("span", { class: "hint" }, "Replaces the scenes below; older films are kept."))
        : h("div", { class: "foot" }, h("span", { class: "hint" }, "Then press Make the film at the bottom, or Write the storyboard first to check the scenes before the film is made.")));
  }

  async function addFiles(files) {
    const pictures = files.filter(f => IMAGE_TYPES.includes(f.type));
    // A video's type is taken from its suffix: browsers give a .mov no type or another one.
    const videos = files.filter(f => !IMAGE_TYPES.includes(f.type) && isVideoRef(f.name)
      && (f.size <= REF_VIDEO_MB * 1024 * 1024 || (error(`${f.name} is larger than ${REF_VIDEO_MB} MB; a reference video is at most ${REF_VIDEO_MB} MB. Cut it or lower its resolution.`), false)))
      .map(f => new File([f], f.name, { type: VIDEO_REFS[suffix(f.name)] }));
    const others = files.filter(f => !IMAGE_TYPES.includes(f.type) && !isVideoRef(f.name)
      && (SOURCES.includes(suffix(f.name)) || (error(`${f.name} cannot be used: a source is a PDF, text, Word, PowerPoint, Excel, CSV, HTML or audio file, a picture a PNG, JPEG or WebP image, a reference video an MP4, MOV or WebM file.`), false)));
    for (const path of await upload("/api/refs", [...pictures, ...videos])) if (!form.refs.includes(path)) form.refs.push(path);
    for (const path of await upload("/api/sources", others)) if (!form.sources.includes(path)) form.sources.push(path);
    render();
  }

  /** Sends `storyboard`; with `makeFilm`, the agent goes on to the finished film whatever the autonomy. */
  async function writeStoryboard(button, makeFilm = false) {
    if (blocker({ action: "storyboard" })) return;
    const brief = (ui.brief.value || "").trim();
    if (!brief) { bar.error("Write in step 1 what the film is about first."); Studio.reveal(ui.brief, { focus: true }); return; }
    if (scenes().length && !confirm("Write a new storyboard from this brief? The scenes are replaced; every picture, recording and film made so far is kept.")) return;
    if (button) button.disabled = true;
    try {
      const style = form.style || "auto";
      if (await request({ action: "storyboard", brief, refs: [...form.refs], sources: [...form.sources], style, film: clone(film), ...(makeFilm ? { make_film: true } : {}) }))
        Studio.reveal(root.querySelector("#sv-board"));
    } finally { if (button) button.disabled = !!blocker({ action: "storyboard" }); }
  }

  /** The sample pictures of samples.versions: [{n, version or null}]. */
  function sampleData() {
    const s = samples();
    if (!s) return null;
    const pics = info(s.scene).pictures;
    return (s.versions || []).map(n => ({ n, v: pics.find(p => p.n === n) || null }));
  }

  /** The key scene, on which style samples are made: the first scene with a picture that is not a template scene,
   *  else the first drawn scene, else the first template scene. */
  function keyScene() {
    const list = scenes(), first = test => (list.find(test) || {}).id;
    return first(x => !!x.image) || first(drawn) || first(x => !!x.template) || null;
  }
  /** The stills of `scene` with a page style that are not in `except`: earlier style samples, newest first. */
  function earlierSamples(scene, except) {
    return (scene ? info(scene).pictures : []).filter(v => isStill(v) && v.page_style && !except.includes(v.n));
  }

  /** One style sample: its picture or still, its style and a "Use this style" button sending use-style. */
  const sampleCard = (v, scene, disabled) => h("div", { class: "sample" },
    h("img", { src: fileUrl(v.image), alt: "", onclick: () => openDetail(adopt(v, scene)) }),
    h("div", { class: "t" }, h("b", {}, versionStyle(v)),
      h("span", {}, v.invented ? v.invented.description : (Studio.catalogue().styles.find(x => x.name === v.style) || {}).description || ""),
      isStill(v) && pageStyleText(v) ? h("span", {}, pageStyleText(v)) : null,
      h("button", { class: "primary", ...guard({ action: "use-style" }), ...(disabled ? { disabled: true } : {}),
        onclick: () => send({ action: "use-style", version: v.n }) }, "Use this style")));
  /** Earlier style samples of `scene` (not in `except`), under a heading; null when there are none. */
  function earlierPart(scene, except, disabled) {
    const list = earlierSamples(scene, except);
    return list.length ? [h("div", { class: "sampling" }, h("b", {}, "Earlier style samples"),
      h("span", { class: "hint" }, `stills of scene ${indexOf(scene) + 1} made in other styles; any of them can still be the film's style`)),
      h("div", { class: "samples" }, list.map(v => sampleCard(v, scene, disabled)))] : null;
  }

  /** The page style of a still's sidecar (`page_style`) in one line: 2D or 3D, light, typography, camera. */
  const pageStyleText = v => {
    const p = (v && v.page_style) || {};
    return [p.dimension, p.light, p.typography, p.camera].filter(x => typeof x === "string" && x.trim()).join(" · ");
  };

  function stepStyle() {
    const head = hint => [h("h2", {}, h("span", { class: "num" }, "2"), "Picture style", hint),
      Studio.autonomy() === "auto" ? h("div", { class: "auto-hint" }, "Automatic: the style is picked and the whole film made without waiting for you.") : null];
    const s = samples();
    const styling = reqs().find(p => ["style-samples", "use-style"].includes(p.request.action));
    const styleNotice = styling ? h("div", { class: "notice inline sv-notice" }, pendingText(styling), runStatus(styling.request.id)) : null;
    if (s && !fromCatalogue) {
      const k = indexOf(s.scene);
      const invent = s.style === "invent", paged = drawn(sceneOf(s.scene));
      return h("section", { class: "card" }, head(h("span", { class: "hint" }, "one style for every scene")), styleNotice,
        h("div", { class: "sampling" },
          h("b", {}, `${invent ? "3 styles invented for this film" : "3 styles picked for this film"}: pick one before the rest is made`),
          h("span", { class: "hint" }, k < 0 ? "The scene they were drawn on is no longer in the storyboard; ask for new samples."
            : paged ? `Each is a still of scene ${k + 1}'s page in that style. Every other scene gets its page or picture once you pick a style.`
            : `Each is shown on scene ${k + 1}. The other scenes with a picture get theirs once you pick a style.`)),
        h("div", { class: "samples" }, sampleData().map(({ n, v }) => v ? sampleCard(v, s.scene, k < 0)
          : h("div", { class: "sample pending" }, h("div", { class: "ph" }, h("div", { class: "spin" }), `${paged ? "Building" : "Drawing"} sample v${n}…`)))),
        earlierPart(s.scene, s.versions || [], k < 0),
        h("div", { class: "foot" },
          h("button", { class: "secondary", ...guard({ action: "style-samples" }), onclick: () => send({ action: "style-samples", style: s.style }) }, invent ? "Invent others" : "Choose others"),
          h("button", { class: "secondary", onclick: () => { fromCatalogue = true; render(); } }, "Pick from the catalogue instead")));
    }
    const has = scenes().length > 0;
    const current = has ? (P().style && P().style.name) || null : form.style;
    const picker = stylePicker({ cards: s ? {} : CARDS, value: current, onPick: name => pickStyle(name, picker) });
    const style = P().style;
    return h("section", { class: "card" },
      head(h("span", { class: "hint" }, "for every scene · ", picker.count)), styleNotice,
      style && style.invented ? h("div", { class: "overrides film-style" }, "The film's style: ", h("b", {}, style.invented.name), " ",
        h("span", { class: "tag" }, "new"), style.invented.description ? ` · ${style.invented.description}` : "") : null,
      s ? h("div", { class: "foot top" }, h("button", { class: "secondary", onclick: () => { fromCatalogue = false; render(); } }, "← Back to the 3 samples")) : null,
      s || !has ? null : earlierPart(keyScene(), [], false),
      picker.el);
  }

  /** A style picked in step 2: the next storyboard's style, or, once there are scenes, a request. */
  async function pickStyle(name, picker) {
    if (!scenes().length) { form.style = name; summary(); return; }
    const card = CARDS[name], b = blocker({ action: card ? "style-samples" : "use-style" });
    if (b) { error(`${pendingText(b)}. Pick a style once it is done.`); picker.el.set((P().style && P().style.name) || null); return; }
    const ok = confirm(card ? `Make the first scene with a picture (with none, the first drawn scene) in ${card.asked.replace("to choose from", "")}to choose the film's style from?`
      : `Make every scene's picture and page again in ${nice(name)}? Scenes with their own style keep it; every picture and page made so far is kept.`);
    if (!ok) { picker.el.set((P().style && P().style.name) || null); return; }
    if (await request(card ? { action: "style-samples", style: name } : { action: "use-style", style: name })) fromCatalogue = false;
    render();
  }

  /* ---------- step 3: storyboard ---------- */

  let dragId = null;

  function stepBoard() {
    if (!boardShown()) return null;
    const list = scenes(), t = total(), s = samples();
    const making = reqs().find(p => p.request.action === "storyboard");
    const strip = h("div", { class: "strip-wrap" }, h("div", { class: "strip" }, list.map((x, i) => {
      const pic = s ? null : thumbOf(x);
      const paper = !pic && drawn(x);
      return h("div", { "data-n": i + 1, "data-id": x.id, class: paper ? "drawn" : null,
        style: `flex:${Math.max(secs(x), 1)};${pic ? `background-image:url("${fileUrl(pic)}")` : paper ? "" : "background:var(--stripe)"}` },
        paper ? Studio.icon("draw") : null);
    })), h("div", { class: "strip-tip", hidden: true }));
    const rows = h("div", { class: "scenes" }, list.map((x, i) => sceneRow(x, i)),
      reqs().filter(p => p.request.action === "add-scene").map(p => h("div", { class: "srow pending" },
        h("span"), h("div", { class: "thumb" }, h("div", { class: "noimg" }, p.current ? h("div", { class: "spin" }) : null)),
        h("div", { class: "what" }, h("b", {}, "New scene"), h("div", {}, `“${p.request.text}”`), runStatus(p.request.id)),
        h("span"), h("span", { class: "state st-busy" }, p.current ? "Being written…" : "Waiting"), h("span"))));
    wireDrag(rows);
    wireStrip(strip, rows);
    return h("section", { class: "card", id: "sv-board" },
      h("h2", {}, h("span", { class: "num" }, "3"), "Storyboard", h("span", { class: "hint" }, "click a scene to open it; drag ⋮⋮ to move it"),
        h("span", { class: "right hint" }, list.length ? `${plural(list.length, "scene")} · ${mmss(t)} · aim: ${aim(film.length)}` : "")),
      making ? h("div", { class: "notice inline" }, !making.current ? "A new storyboard is waiting to be written."
        : list.length && !samples() ? "The storyboard is written; its pictures are being made…" : "A new storyboard is being written…",
        runStatus(making.request.id)) : null,
      list.length ? [strip, h("div", { class: "strip-scale" }, h("span", {}, "0:00"), h("span", {}, mmss(t)))] : null,
      rows,
      adding ? addSceneBox() : h("button", { class: "add-scene", disabled: !list.length, onclick: () => { adding = true; render(); root.querySelector("[data-k=add-scene]")?.focus(); } }, "+ Add a scene"));
  }

  function sceneRow(x, i) {
    const s = samples(), id = x.id, busy = pictureBusy(id);
    const sampled = s && s.scene === id, waiting = s && !sampled;
    const sampleV = sampled ? (sampleData().find(d => d.v) || {}).v : null;
    const pic = waiting ? null : sampled ? sampleV && sampleV.image : thumbOf(x);
    const tags = [kindWord(x) ? h("span", { class: "kind" }, kindWord(x)) : null,
      (P().scene_styles || {})[id] ? h("span", { class: "own" }, "own style") : null,
      voicesUsed(x) > 1 ? h("span", { class: "own" }, `${voicesUsed(x)} voices`) : null];
    return h("div", { class: "srow", "data-id": id, onclick: e => { if (!e.target.closest(".grip")) openScene(id); } },
      h("span", { class: "grip", title: "Drag to move" }, "⋮⋮"),
      h("div", { class: "thumb" + (busy ? " busy" : "") }, pic ? h("img", { src: fileUrl(pic), alt: "", loading: "lazy" }) : drawn(x) ? drawnThumb(x) : h("div", { class: "noimg" }),
        h("span", { class: "num" }, String(i + 1)), busy ? h("div", { class: "spin" }) : null),
      h("div", { class: "what" }, h("b", {}, titleOf(id), tags), h("div", {}, `“${(x.narration || []).join(" ")}”`)),
      h("span", { class: "dur" }, mmss(secs(x))),
      waiting ? h("span", { class: "state st-wait" }, "Waiting for the style") : sampled ? h("span", { class: "state st-voice" }, "3 samples")
        : !pic && (x.image || drawn(x)) && reqs().some(p => MANY_PICTURES.includes(p.request.action))
          ? h("span", { class: "state st-wait" }, drawn(x) ? "Still to come" : "Picture to come")
        : busy ? h("span", { class: "state st-busy" }, busy) : h("span"),
      h("span", { class: "go" }, "›"));
  }

  /** The strip and the rows light up together under the pointer; the tip over the strip names the scene (number,
   *  title, length); a click on the strip opens the scene. */
  function wireStrip(wrap, rows) {
    const tip = wrap.querySelector(".strip-tip");
    const show = id => {
      for (const el of [...wrap.querySelectorAll(".strip > div"), ...rows.querySelectorAll(".srow[data-id]")]) el.classList.toggle("hl", !!id && el.dataset.id === id);
      const seg = id ? [...wrap.querySelectorAll(".strip > div")].find(el => el.dataset.id === id) : null;
      tip.hidden = !seg;
      if (!seg) return;
      tip.textContent = `Scene ${indexOf(id) + 1} · ${titleOf(id)} · ${mmss(secs(sceneOf(id) || {}))}${drawn(sceneOf(id)) ? " · drawn in its page" : ""}`;
      tip.style.left = `${seg.offsetLeft + seg.offsetWidth / 2}px`;
    };
    const segOf = e => e.target.closest(".strip > div");
    wrap.addEventListener("mouseover", e => { const seg = segOf(e); if (seg) show(seg.dataset.id); });
    wrap.addEventListener("mouseleave", () => show(null));
    wrap.addEventListener("click", e => { const seg = segOf(e); if (seg) openScene(seg.dataset.id); });
    rows.addEventListener("mouseover", e => { if (dragId) return; const row = e.target.closest(".srow[data-id]"); show(row ? row.dataset.id : null); });
    rows.addEventListener("mouseleave", () => show(null));
  }

  /** Drag a scene by its ⋮⋮ to another place: one storyboard write with the new order. */
  function wireDrag(list) {
    const slot = h("div", { class: "dropslot" });
    let at = null;
    list.addEventListener("pointerdown", e => {
      const row = e.target.closest(".grip") && e.target.closest(".srow");
      if (row) row.draggable = true;
    });
    list.addEventListener("dragstart", e => {
      const row = e.target.closest(".srow");
      if (!row) return;
      dragId = row.dataset.id;
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", dragId);
      requestAnimationFrame(() => row.classList.add("lifted-from"));
    });
    list.addEventListener("dragover", e => {
      if (!dragId) return;
      e.preventDefault();
      const rows = [...list.querySelectorAll(".srow[data-id]")];
      at = rows.findIndex(r => { const b = r.getBoundingClientRect(); return e.clientY < b.top + b.height / 2; });
      if (at < 0) at = rows.length;
      if (rows[at]) list.insertBefore(slot, rows[at]); else list.append(slot);
    });
    list.addEventListener("drop", e => {
      e.preventDefault();
      if (!dragId || at == null) return;
      const from = indexOf(dragId);
      const [moved] = sb.scenes.splice(from, 1);
      sb.scenes.splice(at > from ? at - 1 : at, 0, moved);
      dragId = null;
      commit();
    });
    list.addEventListener("dragend", () => {
      dragId = null;
      slot.remove();
      list.querySelectorAll(".srow").forEach(r => { r.draggable = false; r.classList.remove("lifted-from"); });
    });
  }

  function addSceneBox() {
    const text = h("textarea", { "data-k": "add-scene", placeholder: "What the new scene shows and says. For example: a closing scene with the three things to remember" });
    const send = async () => {
      const t = text.value.trim();
      if (!t) { text.focus(); return; }
      if (await request({ action: "add-scene", after: null, text: t })) { adding = false; render(); }
    };
    return h("div", { class: "slide-ask add-box" }, text,
      h("button", { class: "primary", onclick: send }, "Send"),
      h("button", { class: "secondary", onclick: () => { adding = false; render(); } }, "Cancel"));
  }

  /* ---------- steps 4 and 5: voice, music ---------- */

  /** The number of the voice step: 4, or 3 while the storyboard step is hidden; the music step is the next. */
  const voiceNum = () => (boardShown() ? 4 : 3);
  /** The films step's number: after the scenes step when that is shown, else after the music. */
  const filmsNum = () => voiceNum() + (scenes().length && !samples() ? 3 : 2);

  function stepVoice() {
    const v = film.voice;
    const key = m => (m.default ? null : m.id);
    const pickVoice = m => ({ model: key(m), name: key(m) === (v.model ?? null) ? v.name ?? null : null,
      speed: m.speed ? v.speed || 1 : 1, style: m.style ? v.style : null });
    const voices = speechModels().length ? h("div", { class: "voices" }, speechModels().map(m => h("div", {
      class: "voice" + (key(m) === (v.model ?? null) ? " on" : ""), onclick: () => setFilm({ voice: pickVoice(m) }) },
      h("span", { class: "r" }), h("div", {}, h("b", {}, m.id), h("span", {}, m.default ? m.why : `${m.when}: ${m.why}`)),
      playButton("Play a sample", btn => sample(pickVoice(m), btn)))))
      : h("div", { class: "hint" }, Studio.models().speech_error || "config.yaml names no speech model: the setup:settings skill adds one.");
    const cur = speechModel(v.model) || {};
    const name = h("input", { type: "text", value: v.name || "", "data-k": "film-voice-name",
      placeholder: `Empty: the model's default voice${cur.voice ? ` (${cur.voice})` : ""}${cur.clones ? "; or a cloned voice" : ""}`,
      onchange: e => setFilm({ voice: { ...v, name: e.target.value.trim() || null } }) });
    const style = h("input", { type: "text", value: v.style || "", disabled: !hasStyle(v.model), "data-k": "film-style",
      placeholder: hasStyle(v.model) ? "For example: calm documentary narrator" : "This model takes no style",
      onchange: e => setFilm({ voice: { ...v, style: e.target.value.trim() || null } }) });
    const speed = seg(SPEEDS.map(([x, l]) => [x, l]), Number(v.speed || 1), x => setFilm({ voice: { ...v, speed: +x } }));
    if (!hasSpeed(v.model)) speed.classList.add("off");
    return h("section", { class: "card", id: "sv-voices" },
      h("h2", {}, h("span", { class: "num" }, String(voiceNum())), "Voice", h("span", { class: "hint" }, film.silent ? "not used: the film is silent (step 1)" : "for the whole film. Press ▶ to hear a sample")),
      voices,
      h("div", { class: "opts" },
        h("div", {}, h("label", { class: "f" }, "Voice name (optional)"), name),
        h("div", {}, h("label", { class: "f" }, "Speed"), speed),
        h("div", {}, h("label", { class: "f" }, "Speaking style (models that take one)"), style)),
      scenes().length ? speakersPart() : null);
  }

  function stepMusic() {
    const m = film.music, has = scenes().length > 0;
    const brief = h("textarea", { id: "music-brief", value: m.brief, "data-k": "music-brief",
      placeholder: "For example: calm, hopeful piano with soft strings, no drums, quiet enough to talk over",
      onchange: e => setFilm({ music: { ...film.music, brief: e.target.value } }) });
    const musicBody = m.mode === "none" ? [h("div", { class: "hint", style: "margin-top:12px" }, "The film has no background music.")]
      : [m.mode === "made" ? [h("label", { class: "f", for: "music-brief", style: "margin-top:12px" }, "What should it sound like?"), brief] : ownTrack(),
        h("div", { class: "opts music-opts" },
          h("div", {}, h("label", { class: "f" }, "Music volume under the voice"),
            seg(VOLUMES, m.volume, x => setFilm({ music: { ...film.music, volume: x } }))),
          m.mode === "made" && has ? h("button", { class: "secondary", ...guard({ action: "music" }), onclick: makeMusic }, "Make new music") : null),
        tracks()];
    return h("section", { class: "card", id: "sv-music" },
      h("h2", {}, h("span", { class: "num" }, String(voiceNum() + 1)), "Background music", h("span", { class: "hint" }, "for the whole film")),
      h("div", { style: "max-width:560px" }, seg(MUSIC_MODES.map(([x, l]) => [x, x === "made" ? Studio.withModel(l, taskModel("music")) : l]), m.mode, x => setFilm({ music: { ...film.music, mode: x } }))), musicBody);
  }

  /** How a music version was made: `source` when the server gives it, else from its brief (an own track has none). */
  const trackSource = t => t.source || (t.brief ? "made" : "own");

  function tracks() {
    const list = (V().music || []).filter(t => trackSource(t) === film.music.mode);
    const making = reqs().filter(p => p.request.action === "music" || p.request.action === "own-music");
    return h("div", { class: "tracks" },
      making.map(p => h("div", { class: "track pending" }, h("div", { class: "spin" }),
        h("div", {}, h("b", {}, p.request.action === "music" ? "New music" : "Your track"), ` · ${p.current ? "being made…" : "waiting"}`,
          runStatus(p.request.id)), h("span"))),
      list.map(t => h("div", { class: "track" }, playButton("Play", b => play(t.path, b)),
        h("div", {}, h("b", {}, `Music v${t.n}`), [t.duration ? mmss(t.duration) : null, t.note || t.brief || null].filter(Boolean).map(x => ` · ${x}`),
          h("div", { class: "wave" + (t.n % 2 ? " b" : "") })),
        t.n === V().music_used ? h("span", { class: "used" }, "✓ used in the film")
          : h("button", { class: "mini", onclick: () => setFilm({ music: { ...film.music, version: t.n } }) }, "Use this"))));
  }

  function ownTrack() {
    const input = h("input", { type: "file", accept: AUDIO.join(","), hidden: true, onchange: async e => {
      const [file] = e.target.files;
      e.target.value = "";
      if (!file) return;
      if (!AUDIO.includes(suffix(file.name))) return error(`${file.name} is not an MP3, WAV, M4A, AAC, FLAC or OGG file.`);
      const [path] = await upload("/api/sources", [file]);
      if (path) await send({ action: "own-music", file: path });
    } });
    return h("div", { class: "foot" }, input, h("button", { class: "secondary", ...guard({ action: "own-music" }), onclick: () => input.click() }, "Upload my own track"),
      h("span", { class: "hint" }, "MP3, WAV, M4A, AAC, FLAC or OGG"));
  }

  async function makeMusic() {
    const brief = (film.music.brief || "").trim() || (root.querySelector("#music-brief")?.value || "").trim();
    if (!brief) { root.querySelector("#music-brief")?.focus(); return; }
    await send({ action: "music", brief });
  }

  /** The storyboard's speakers: name, engine, voice, speed, tone; each change is one storyboard write. */
  function speakersPart() {
    const list = Object.entries(sb.speakers || {});
    const row = ([name, v]) => {
      const set = patch => { sb.speakers[name] = { ...v, ...patch }; commit(); };
      const engine = h("select", { onchange: e => {
        const m = e.target.value || null;
        set({ model: m, name: null, speed: hasSpeed(m) ? v.speed ?? 1 : null, style: hasStyle(m) ? v.style : null });
      } }, speechModels().map(m => h("option", { value: m.default ? "" : m.id }, m.default ? `${m.id} (default)` : m.id)));
      engine.value = v.model || "";
      const voice = h("input", { type: "text", value: v.name || "", "data-k": `spk-voice-${name}`,
        placeholder: "Default voice", onchange: e => set({ name: e.target.value.trim() || null }) });
      const speed = seg(SPEEDS, Number(v.speed || 1), x => set({ speed: +x }));
      if (!hasSpeed(v.model)) speed.classList.add("off");
      return h("div", { class: "spk" },
        h("input", { type: "text", value: name, "data-k": `spk-${name}`, onchange: e => renameSpeaker(name, e.target.value.trim()) }),
        engine, voice, speed,
        h("input", { type: "text", value: v.style || "", disabled: !hasStyle(v.model), "data-k": `spk-style-${name}`,
          placeholder: hasStyle(v.model) ? "For example: warm, unhurried" : "This model takes no style",
          onchange: e => set({ style: e.target.value.trim() || null }) }),
        playButton("Play a sample", b => sample(resolve(null, v), b)),
        h("button", { class: "mini danger", title: "Delete speaker", onclick: () => deleteSpeaker(name) }, "Delete"));
    };
    return details("speakers", { class: "adv-in", id: "sv-speakers" },
      h("summary", {}, h("b", {}, "Advanced: more speakers"), h("span", { class: "hint" }, list.length ? list.map(x => x[0]).join(", ") : "none")),
      h("div", { class: "hint", style: "margin:10px 0" }, `Most films need none. A sentence names a speaker in its scene; every other sentence is spoken by the film's voice (${voiceLabel(film.voice)}).`),
      list.length ? h("div", { class: "spk-list" },
        h("div", { class: "spk head" }, ["Name", "Engine", "Voice", "Speed", "Tone or speaking style", "", ""].map(x => h("span", {}, x))),
        list.map(row)) : null,
      h("button", { class: "mini", style: "margin-top:8px", onclick: () => addSpeaker() }, "+ Add a speaker"));
  }

  /** Adds a speaker with the film's voice; answers its name. */
  function addSpeaker() {
    sb.speakers = sb.speakers || {};
    let k = Object.keys(sb.speakers).length + 1;
    while (sb.speakers[`speaker_${k}`]) k++;
    const name = `speaker_${k}`;
    sb.speakers[name] = { ...clone(film.voice) };
    openParts.add("speakers");
    commit();
    return name;
  }

  function renameSpeaker(from, to) {
    if (to === from) return;
    if (!/^[a-z0-9_]+$/.test(to)) { error("A speaker's name is lower-case letters, digits and _ only, for example narrator_2."); render(); return; }
    if (sb.speakers[to]) { error(`There is already a speaker called ${to}.`); render(); return; }
    sb.speakers = Object.fromEntries(Object.entries(sb.speakers).map(([n, v]) => [n === from ? to : n, v]));
    for (const s of scenes()) if (s.speakers) s.speakers = s.speakers.map(x => (x === from ? to : x));
    commit();
  }

  function deleteSpeaker(name) {
    if (!confirm(`Delete the speaker ${name}? Its sentences are spoken by the film's voice.`)) return;
    delete sb.speakers[name];
    for (const s of scenes()) if (s.speakers) s.speakers = s.speakers.map(x => (x === name ? null : x));
    if (!Object.keys(sb.speakers).length) delete sb.speakers;
    commit();
  }

  /* ---------- step 6: films ---------- */

  /**
   * What the current make-film `r` has done, from the project's files written since it started: the recordings and
   * renders of the scenes that need them, the music and the assemblies. Null before the start is known.
   */
  function filmDone(r) {
    const since = started(r.id);
    if (!since) return null;
    const stages = scenes().map(x => filmStage(r, x.id)).filter(Boolean);
    const voices = scenes().filter(x => { const i = info(x.id); return filmStage(r, x.id) === "voice"
      || madeSince(i.recording && i.recording.created, since); });
    const voiced = voices.filter(x => madeSince(info(x.id).recording?.created, since)).length;
    // A track's studio.json `created` is the time of the request that made it, so it is compared with this one's.
    const newMusic = (V().music || []).find(m => m.source === film.music.mode && madeSince(m.created, Date.parse(r.time)));
    const music = film.music.mode === "none" ? "none" : newMusic ? `v${newMusic.n} made` : V().music_used != null ? `v${V().music_used}` : "to make";
    const assembled = (V().films || []).filter(f => madeSince(f.created, since));
    const built = (V().html_films || []).filter(f => madeSince(f.created, since));
    const made = mp4Run(r) ? (assembled.length ? `MP4 v${assembled[0].n} assembled` : "not assembled yet")
      : built.length ? `HTML v${built[0].n} made` : "not made yet";
    return [["Voices", `${voiced} of ${voices.length}`], ["Scenes", `${stages.filter(x => x === "done").length} of ${stages.length}`],
      ["Music", music], ["Film", made]];
  }

  /* ---------- step 6: scenes, each scene's recording and animation ---------- */

  /** The scene whose animation player is open in step 6, or null: one at a time, so one plays. */
  let openClip = null;
  /** The HTML scene whose scene player is open below step 6, or null, and its player (kept across redraws). */
  let openPlayer = null, scenePlayer = null;
  /** Opens or hides a scene's animation: the scene player for an HTML scene's latest page, rendered or not, else its
   *  video. */
  function toggleAnimation(id) {
    if (playing) play(null, playing);
    const html = !!info(id).page, open = openClip === id || openPlayer === id;
    if (scenePlayer) { scenePlayer.close(); scenePlayer = null; }
    openClip = !open && !html ? id : null;
    openPlayer = !open && html ? id : null;
    render();
    if (openPlayer) requestAnimationFrame(() => Studio.reveal(root.querySelector("#sv-player")));
  }
  /** The scene player section: the open HTML scene's player, built once per opened scene. */
  function playerSection() {
    if (!openPlayer || !project || !info(openPlayer).page) return null;
    if (!scenePlayer || scenePlayer.scene !== openPlayer)
      scenePlayer = makeScenePlayer(openPlayer);
    return scenePlayer.el;
  }

  /* ---------- scene player: an HTML scene's page, played, paused and marked ---------- */

  /** Seconds the Send button waits for the element ids under a mark; then it sends with none. */
  const HITS_WAIT_MS = 1000;
  /** The colour of the mark drawn into the marked still sent to Claude (the shell's marked copy red). */
  const STILL_RED = "#e5382f";
  const MARK_TOOLS = [["point", "Point", "Click on the spot to change"], ["box", "Box", "Drag a box around the part to change"]];

  /**
   * The player of an HTML scene's newest render: its page in a sandboxed iframe (served under /scene/ with
   * scene-player.js), Play/Pause, a scrub bar and the time. The page owns time: the narration's <audio> time, or a
   * clock for a silent scene, sent as `sv:seek` each frame. Paused, the user marks a point or a box; the iframe
   * answers the element ids under it (`sv:hits`). Send draws the marked still from scene.mp4 at that time, writes
   * it with /api/scene-marked and sends a `mark-scene` request. sync() follows a newer render at the same time.
   */
  function makeScenePlayer(id) {
    const S = { scene: id, page: info(id).page, t: 0, playing: false, ready: false, W: 1920, H: 1080, tool: "point",
      mark: null, drawing: null, ids: null, qid: 0, origin: 0, raf: 0, sending: false };
    const iframe = h("iframe", { sandbox: "allow-scripts", title: "Scene animation", src: S.page.page_url });
    const overlay = h("canvas", { class: "sp-overlay" });
    const stage = h("div", { class: "sp-stage" + (film.shape === "9:16" ? " tall" : "") }, iframe, overlay);
    const playB = h("button", { type: "button", class: "secondary sp-play", onclick: () => (S.playing ? pause() : play()) }, "Play");
    const scrub = h("input", { type: "range", class: "sp-scrub", min: "0", step: "0.01", value: "0",
      oninput: e => { pause(false); clearMark(); seek(parseFloat(e.target.value)); } });
    const clock = h("span", { class: "sp-time" });
    const tools = seg(MARK_TOOLS, S.tool, v => { S.tool = v; clearMark(); });
    const idsLine = h("div", { class: "sp-ids" });
    const text = h("textarea", { class: "sp-text", rows: 2, placeholder: "What to change at this moment. For example: make this label larger and move it left." ,
      oninput: paintSend });
    const sendB = h("button", { class: "primary sp-send", type: "button", disabled: true, onclick: () => send() }, "Send");
    const status = h("span", { class: "hint sp-status" });
    const markPart = h("div", { class: "sp-mark" },
      h("div", { class: "line" }, tools, h("span", { class: "hint" }, "Pause, then mark what to change on the frame")),
      idsLine, text, h("div", { class: "line" }, sendB, status));
    const commentsEl = h("div", { class: "sp-comments" });
    const heading = h("span", {});
    const el = h("section", { class: "card sp", id: "sv-player" },
      h("h2", {}, heading, h("button", { class: "mini", type: "button", onclick: () => toggleAnimation(id) }, "Hide")),
      stage, h("div", { class: "line sp-controls" }, playB, scrub, clock), markPart, commentsEl);
    const audio = new Audio();

    const duration = () => Number(S.page.duration) || 0;
    const post = msg => { if (iframe.contentWindow) iframe.contentWindow.postMessage(msg, "*"); };

    function paint() {
      heading.textContent = `Scene ${indexOf(id) + 1}, ${titleOf(id)} · v${S.page.n}`;
      playB.textContent = S.playing ? "Pause" : "Play";
      scrub.max = String(duration());
      scrub.value = String(S.t);
      clock.textContent = `${S.t.toFixed(2)} / ${duration().toFixed(2)} s`;
      markPart.hidden = S.playing;
      overlay.classList.toggle("on", !S.playing && S.ready);
      paintSend();
    }
    function paintSend() {
      sendB.disabled = S.sending || !S.mark || S.ids === null || !text.value.trim();
      idsLine.textContent = !S.mark ? "" : S.ids === null ? "Finding the elements under the mark…"
        : S.ids.length ? `Elements: ${S.ids.join(", ")}` : "No element with an id under the mark";
    }
    function seek(t) {
      S.t = Math.min(Math.max(Number(t) || 0, 0), duration());
      if (S.ready) post({ type: "sv:seek", t: (Number(S.page.start) || 0) + S.t });
      paint();
    }
    function frame(now) {
      if (!S.playing) return;
      const t = S.page.narration ? audio.currentTime : (now - S.origin) / 1000;
      if (t >= duration()) { seek(duration()); pause(); return; }
      seek(t);
      S.raf = requestAnimationFrame(frame);
    }
    function play() {
      if (!S.ready) return;
      if (S.t >= duration()) S.t = 0;
      clearMark();
      S.playing = true;
      if (S.page.narration) {
        if (audio.dataset.src !== S.page.narration) { audio.src = fileUrl(S.page.narration); audio.dataset.src = S.page.narration; }
        audio.currentTime = S.t;
        audio.play().catch(e => error(`Could not play the narration: ${e.message}`));
      } else S.origin = performance.now() - S.t * 1000;
      S.raf = requestAnimationFrame(frame);
      paint();
    }
    function pause(redraw = true) {
      S.playing = false;
      cancelAnimationFrame(S.raf);
      audio.pause();
      if (redraw) seek(S.t);
    }

    /* marking, in fractions of the frame; the query and the request take frame pixels */
    function clearMark() {
      S.mark = S.drawing = null;
      S.ids = null;
      S.qid++;
      redraw();
      paintSend();
    }
    function redraw() {
      const dpr = window.devicePixelRatio || 1, W = Math.round(overlay.clientWidth * dpr), H = Math.round(overlay.clientHeight * dpr);
      if (overlay.width !== W || overlay.height !== H) { overlay.width = W; overlay.height = H; }
      const g = overlay.getContext("2d");
      g.clearRect(0, 0, W, H);
      const marks = [S.drawing || S.mark].filter(Boolean);
      Studio.drawMarks(g, W, H, marks, dpr, getComputedStyle(document.documentElement).getPropertyValue("--mark").trim() || STILL_RED);
    }
    const frameMark = m => (m.kind === "point"
      ? { point: { x: Math.round(m.x * S.W * 10) / 10, y: Math.round(m.y * S.H * 10) / 10 } }
      : { rect: { x: Math.round(m.x * S.W * 10) / 10, y: Math.round(m.y * S.H * 10) / 10, w: Math.round(m.w * S.W * 10) / 10, h: Math.round(m.h * S.H * 10) / 10 } });
    function setMark(m) {
      S.mark = m;
      S.drawing = null;
      S.ids = null;
      const qid = ++S.qid;
      post({ type: "sv:query", qid, ...frameMark(m) });
      setTimeout(() => { if (S.qid === qid && S.ids === null) { S.ids = []; paintSend(); } }, HITS_WAIT_MS);
      redraw();
      paintSend();
    }
    const at = e => {
      const r = overlay.getBoundingClientRect();
      return [Math.min(Math.max((e.clientX - r.left) / r.width, 0), 1), Math.min(Math.max((e.clientY - r.top) / r.height, 0), 1)];
    };
    overlay.addEventListener("pointerdown", e => {
      if (S.playing || !S.ready) return;
      const [x, y] = at(e);
      if (S.tool === "point") return setMark({ kind: "point", x, y });
      overlay.setPointerCapture(e.pointerId);
      S.start = [x, y];
      S.drawing = { kind: "box", x, y, w: 0, h: 0 };
    });
    overlay.addEventListener("pointermove", e => {
      if (!S.drawing) return;
      const [x, y] = at(e), [x0, y0] = S.start;
      S.drawing = { kind: "box", x: Math.min(x, x0), y: Math.min(y, y0), w: Math.abs(x - x0), h: Math.abs(y - y0) };
      redraw();
    });
    overlay.addEventListener("pointerup", () => {
      const d = S.drawing;
      if (!d) return;
      if (d.w > 0.01 && d.h > 0.01) setMark(d);
      else { S.drawing = null; redraw(); }
    });

    function onMessage(ev) {
      const m = ev.data;
      if (ev.source !== iframe.contentWindow || !m || typeof m.type !== "string") return;
      if (m.type === "sv:ready") {
        S.ready = true;
        S.W = Number(m.width) || S.W;
        S.H = Number(m.height) || S.H;
        stage.style.aspectRatio = `${S.W} / ${S.H}`;
        status.textContent = (m.errors || []).length ? `The page reported: ${m.errors.join("; ")}` : "";
        seek(S.t);
      } else if (m.type === "sv:hits" && m.qid === S.qid && S.mark) {
        S.ids = Array.isArray(m.ids) ? m.ids.filter(x => typeof x === "string") : [];
        paintSend();
      }
    }
    window.addEventListener("message", onMessage);

    /** The frame of scene.mp4 at scene time t with the mark drawn, as a PNG data URL. */
    function still(t, mark) {
      return new Promise((resolve, reject) => {
        const v = h("video", { muted: true, preload: "auto", playsinline: true });
        v.addEventListener("error", () => reject(new Error("the render could not be read")));
        v.addEventListener("loadedmetadata", () => { v.currentTime = Math.min(t, Math.max(0, v.duration - 0.01)); }, { once: true });
        v.addEventListener("seeked", () => {
          const W = v.videoWidth, H = v.videoHeight, c = h("canvas", { width: W, height: H }), g = c.getContext("2d");
          g.drawImage(v, 0, 0, W, H);
          Studio.drawMarks(g, W, H, [mark], Math.max(1, W / (overlay.clientWidth || W)), STILL_RED);
          resolve(c.toDataURL("image/png"));
        }, { once: true });
        v.src = fileUrl(S.page.video);
      });
    }

    async function send() {
      const mark = S.mark, ids = S.ids, words = text.value.trim(), t = Math.round(S.t * 1000) / 1000, page = S.page;
      if (!mark || ids === null || !words) return;
      S.sending = true;
      paintSend();
      try {
        let marked = null;
        if (page.video) {
          status.textContent = "Drawing the marked still…";
          const png = await still(t, mark);
          marked = (await api.post("/api/scene-marked", { project: project.dir, scene: id, version: page.n, t, png })).path;
        }
        const sent = await request({ action: "mark-scene", scene: id, version: page.n, t, mark: frameMark(mark), ids, marked, text: words,
          world: page.world || null, world_t: page.world ? Math.round(((Number(page.start) || 0) + t) * 1000) / 1000 : null });
        if (sent) { text.value = ""; clearMark(); paintComments(); status.textContent = "Sent to Claude"; }
        else status.textContent = "";
      } catch (e) {
        status.textContent = `Could not send: ${e.message}`;
      } finally {
        S.sending = false;
        paintSend();
      }
    }

    function paintComments() {
      const open = reqs().filter(p => p.request.action === "mark-scene" && p.request.scene === id);
      commentsEl.replaceChildren(...open.map(p => h("div", { class: "notice inline sp-comment", "data-req": p.request.id },
        h("span", {}, `${Number(p.request.t).toFixed(2)} s: ${p.request.text}`), runStatus(p.request.id),
        h("button", { class: "mini", type: "button", onclick: () => Studio.stopRequest(p.request.id) }, "Stop"))));
    }

    /** Follows a newer page version of the scene: it opens at the same time once ready. A new render of the same
     *  version only gives the scene.mp4 the marked still is drawn from. */
    function sync() {
      const page = info(id).page;
      if (page && page.n !== S.page.n) {
        pause(false);
        clearMark();
        S.page = page;
        S.ready = false;
        audio.removeAttribute("src");
        delete audio.dataset.src;
        iframe.src = page.page_url;
      } else if (page) S.page = page;
      paintComments();
      paint();
    }

    function close() {
      pause(false);
      window.removeEventListener("message", onMessage);
    }

    paintComments();
    paint();
    return { scene: id, el, sync, close, state: S };
  }
  const narrated = x => (x.narration || []).length > 0;
  /** Step 4 is done once every scene with narration has a recording that matches it. */
  const voiced = () => scenes().length > 0 && scenes().every(x => !narrated(x) || (info(x.id).recording && stateOf(x.id) !== "voice"));
  /** Step 6 is done once every scene has an animation that matches it. */
  const animated = () => scenes().length > 0 && scenes().every(x => (info(x.id).clip || info(x.id).page) && stateOf(x.id) === "ready");
  const scenesSummary = () => `${scenes().filter(x => (info(x.id).clip || info(x.id).page) && stateOf(x.id) === "ready").length} of ${plural(scenes().length, "scene")} ready`;
  /** What a scene's recording is: made, to make again, to make, or none without narration. */
  function voiceLine(x) {
    const rec = info(x.id).recording;
    if (!narrated(x)) return "no narration";
    if (!rec) return "to record";
    return `v${rec.n} · ${mmss(rec.duration)}${stateOf(x.id) === "voice" ? " · to record again, the words or voice changed" : ""}`;
  }
  /** What a scene's animation is: made, to make again, or to make. */
  function clipLine(x) {
    const clip = info(x.id).clip, page = info(x.id).page;
    if (page && (!clip || page.video !== clip.path))
      return `page v${page.n} · ${mmss(page.duration)}${page.video ? "" : " · not rendered"}${stateOf(x.id) === "ready" ? "" : " · to make again, the scene changed"}`;
    if (!clip) return "to make";
    return `v${clip.n} · ${mmss(clip.duration)}${stateOf(x.id) === "ready" ? "" : " · to make again, the scene changed"}`;
  }
  /** A still of a scene's animation at 80% of its length (a drawn scene's drawing is mostly on screen by then). */
  function clipStill(clip) {
    const t = Math.round((clip.duration || 0) * 0.8 * 100) / 100;
    return h("video", { class: "frame", src: `${fileUrl(clip.path)}#t=${t}`, muted: true, playsinline: true, preload: "metadata",
      onloadedmetadata: e => { if (e.target.currentTime < t) e.target.currentTime = t; } });
  }
  /** Opens the storyboard view at a scene's row of step 6. */
  function seeResult(id) {
    openScene(null);
    requestAnimationFrame(() => Studio.reveal(root.querySelector(`[data-result="${CSS.escape(id)}"]`)));
  }

  function stepScenes() {
    if (!project || samples() || !scenes().length) return null;
    const rows = scenes().map((x, i) => {
      const id = x.id, inf = info(id), clip = inf.clip, rec = inf.recording, busy = busyText(id);
      const pic = thumbOf(x);
      const thumb = h("div", { class: "thumb" + (busy ? " busy" : "") },
        clip ? clipStill(clip) : pic ? h("img", { src: fileUrl(pic), alt: "", loading: "lazy" }) : drawn(x) ? drawnThumb(x) : h("div", { class: "noimg" }),
        h("span", { class: "num" }, String(i + 1)), busy ? h("div", { class: "spin" }) : null);
      const showing = openClip === id && clip;
      return h("div", { class: "rrow", "data-result": id },
        thumb,
        h("div", { class: "what" }, h("b", {}, titleOf(id), kindWord(x) ? h("span", { class: "kind" }, kindWord(x)) : null),
          h("div", { class: "line" }, rec && narrated(x) ? playButton("Play this scene’s recording", b => { if (openClip) { openClip = null; render(); } play(rec.path, b); }) : h("span", { class: "noplay" }),
            h("span", { class: "lab" }, "Voice"), h("span", {}, voiceLine(x))),
          h("div", { class: "line" }, clip || inf.page ? playButton(showing || openPlayer === id ? "Hide the animation" : "Play this scene’s animation", () => toggleAnimation(id))
            : h("span", { class: "noplay" }), h("span", { class: "lab" }, "Animation"), h("span", {}, clipLine(x)))),
        chip(id),
        h("div", { class: "acts" },
          h("button", { class: "mini", ...guard({ action: "remake-scene", scene: id }), onclick: () => send({ action: "remake-scene", scene: id }) }, "Remake this scene"),
          h("button", { class: "mini", onclick: () => openScene(id) }, "Edit in the storyboard")),
        showing ? h("div", { class: "rplayer player" + (film.shape === "9:16" ? " tall" : "") },
          h("video", { src: fileUrl(clip.path), controls: true, autoplay: true, preload: "auto" })) : null);
    });
    const remaking = reqs().filter(p => p.request.action === "remake-scene")
      .map(p => h("div", { class: "notice inline" }, pendingText(p), runStatus(p.request.id)));
    return h("section", { class: "card", id: "sv-scenes" },
      h("h2", {}, h("span", { class: "num" }, String(voiceNum() + 2)), "Scenes", h("span", { class: "hint" }, "each scene’s recording and animation, made with the film")),
      remaking, h("div", { class: "rrows" }, rows));
  }

  function stepFilms() {
    if (!project || samples()) return null;
    const films = V().films || [];
    const htmlFilms = V().html_films || [];
    const next = Math.max(0, ...films.map(f => f.n)) + 1, nextHtml = Math.max(0, ...htmlFilms.map(f => f.n)) + 1;
    const making = reqs().filter(p => makesFilm(p.request));
    if (!films.length && !htmlFilms.length && !making.length) return scenes().length ? filmPlan() : null;
    /** The pending requests on film `n` (review, phone), each with its line; a fix is shown by its film-making card. */
    const ON_FILM = { review: "Review", phone: "Phone version" };
    const onFilm = n => reqs().filter(p => ON_FILM[p.request.action] && p.request.version === n)
      .map(p => h("div", { class: "changed" }, h("b", {}, ON_FILM[p.request.action]), runStatus(p.request.id)));
    const exporting = blocker({ action: "export-mp4" });
    let mp4s = 0, htmls = 0;
    return h("section", { class: "card", id: "sv-films" },
      h("h2", {}, h("span", { class: "num" }, String(filmsNum())), "Films", h("span", { class: "hint" }, "every version is kept, newest first")),
      h("div", { class: "films" },
        making.map(p => {
          const done = p.current ? filmDone(p.request) : null, note = p.current ? progress(p.request.id) : null;
          const label = mp4Run(p.request) ? `MP4 v${next + mp4s++}` : `HTML v${nextHtml + htmls++}`;
          return h("div", { class: "film pending" },
            h("div", { class: "ph" }, p.current ? h("div", { class: "spin" }) : null, p.current ? makingText(p.request, next) : "Waiting"),
            h("div", { class: "t" }, h("b", {}, label), h("span", {}, p.current ? "being made" : "queued")),
            h("div", { class: "made" },
              done ? h("div", { class: "counts" }, done.map(([label, value]) => h("span", {}, `${label} `, h("b", {}, value)))) : null,
              note ? h("div", { class: "note" }, note) : null,
              runStatus(p.request.id)));
        }),
        // The newest HTML film plays here, in a sandbox without Studio's origin (the server's CSP says the same);
        // older ones open in a tab, since each embeds every scene and its audio.
        htmlFilms.map((f, k) => h("div", { class: "film" },
          k === 0 ? h("div", { class: "player" + (film.shape === "9:16" ? " tall" : "") },
            h("iframe", { src: fileUrl(f.path), sandbox: "allow-scripts", allow: "fullscreen", allowfullscreen: true, title: `HTML film v${f.n}`,
              style: `width:100%;border:0;display:block;aspect-ratio:${film.shape === "9:16" ? "9 / 16" : "16 / 9"}` })) : null,
          h("div", { class: "t" }, h("b", {}, `HTML v${f.n}`), h("span", {}, [f.duration ? mmss(f.duration) : null, when(f.created)].filter(Boolean).join(" · ")),
            h("span", { class: "acts" }, h("a", { class: "mini", href: fileUrl(f.path), target: "_blank", rel: "noopener" }, k === 0 ? "Open in a tab" : "Watch the film"),
              k === 0 ? [" ", h("button", { class: "mini", disabled: !!exporting, title: exporting ? pendingText(exporting)
                : "Renders every scene and assembles film.mp4 from the current scenes; review and phone version work on the MP4",
                onclick: () => send({ action: "export-mp4" }) }, "Export MP4")] : null)),
          f.changes ? h("div", { class: "changed" }, f.changes) : null)),
        films.map(f => {
          const video = h("video", { src: fileUrl(f.path), controls: true, preload: "metadata" });
          return h("div", { class: "film" },
            h("div", { class: "player" + (film.shape === "9:16" ? " tall" : "") }, video),
            h("div", { class: "t" }, h("b", {}, `MP4 v${f.n}`), h("span", {}, [f.duration ? mmss(f.duration) : null, when(f.created)].filter(Boolean).join(" · ")),
              h("span", { class: "acts" }, h("button", { class: "mini", onclick: () => download(f.path) }, "⬇ Download"), " ",
                f.review ? null : [h("button", { class: "mini", ...guard({ action: "review", version: f.n }), onclick: () => send({ action: "review", version: f.n }) }, "Review this film"), " "],
                film.shape === "16:9" ? h("button", { class: "mini", ...guard({ action: "phone", version: f.n }), onclick: () => phone(f) }, "Phone version") : null)),
            f.changes ? h("div", { class: "changed" }, f.changes) : null,
            f.review ? reviewPart(f, video, f.n === films[0].n) : null,
            onFilm(f.n));
        })));
  }

  /**
   * What differs between the newest film (the newest HTML film, else the newest MP4) and the project as it is now:
   * null when the film is up to date; otherwise the number of scenes that changed (added, removed, moved, needing a
   * recording or a new version, or with a newer page or clip than the film plays) and whether the music changed (an
   * MP4 only: an HTML film plays the newest music version). `label` names the film. With no film, every scene is to
   * make.
   */
  function filmChanges() {
    const hf = (V().html_films || [])[0], mf = (V().films || [])[0], list = scenes();
    if (!hf && !mf) return { scenes: list.length, music: false, none: true };
    const used = (hf ? hf.scenes : mf.scenes) || [];
    const moved = used.length !== list.length || used.some((e, k) => !e || e.id !== list[k].id);
    /** The source the HTML film plays for scene `id` now: its page version directory, else its clip. */
    const source = id => {
      const { page, clip } = info(id);
      if (page) return page.world ? `worlds/${page.world}/v${page.n}` : `scenes/${id}/v${page.n}`;
      return clip ? `scenes/${id}/v${clip.n}/scene.mp4` : null;
    };
    const stale = hf ? (x, k) => source(x.id) === null || used[k].source !== source(x.id)
      : (x, k) => !info(x.id).clip || used[k].scene_version !== `v${info(x.id).clip.n}`;
    const changed = moved ? list.length : list.filter((x, k) => stateOf(x.id) !== "ready" || stale(x, k)).length;
    const music = !hf && (film.music.mode === "none" ? null : V().music_used) !== (mf.music ?? null);
    return changed || music ? { scenes: changed, music, none: false, label: hf ? `HTML v${hf.n}` : `MP4 v${mf.n}` } : null;
  }
  /** The films step's line: "not made yet", what changed since the newest film, or the number of films. */
  function filmsSummary() {
    const c = filmChanges(), films = (V().html_films || []).length + (V().films || []).length;
    if (!c) return plural(films, "film");
    if (c.none) return "not made yet";
    return [c.scenes ? `${plural(c.scenes, "scene")} changed` : null, c.music ? "music changed" : null].filter(Boolean).join(" and ")
      + ` since film ${c.label}`;
  }
  /** The films step before the first film: what "Make the film" will do. */
  function filmPlan() {
    const n = scenes().length, music = film.music.mode === "none" ? "no music"
      : V().music_used != null ? `music: track v${V().music_used}` : film.music.mode === "made" ? "make the music" : "music: choose a track in step 5";
    const plan = [`Record the voice of ${plural(scenes().filter(x => (x.narration || []).length).length, "scene")}`,
      `Animate ${plural(n, "scene")}`, music[0].toUpperCase() + music.slice(1), "Put the film together as one HTML page you play here"];
    return h("section", { class: "card", id: "sv-films" },
      h("h2", {}, h("span", { class: "num" }, String(filmsNum())), "Film", h("span", { class: "hint" }, "not made yet")),
      h("p", { class: "hint" }, "“Make the film” does all of this:"),
      h("ol", { class: "plan" }, plan.map(t => h("li", {}, t))),
      h("p", { class: "hint" }, `Export MP4 on the film then renders a video file${film.review ? ", which a second model reviews" : ""}; the review and the phone version work on the MP4.`));
  }

  /** The findings listed of a review: those with a number `k` and numeric `start` and `end`. */
  const findingsOf = review => (review && Array.isArray(review.findings) ? review.findings : [])
    .filter(x => x && Number.isInteger(x.k) && Number.isFinite(x.start) && Number.isFinite(x.end));

  /** What the current film-making request `r` is doing: making the HTML film; for an MP4 run (export-mp4, fix)
   *  making MP4 v`next`, then, once it has assembled one since it started and the film is reviewed, reviewing it, and
   *  in auto autonomy fixing it once its review has a finding. A fix is not reviewed. */
  function makingText(r, next) {
    if (!mp4Run(r)) return "Making the film…";
    const since = started(r.id);
    const assembled = (V().films || []).filter(f => madeSince(f.created, since));
    if (!assembled.length || !film.review || r.action === "fix") return `Making MP4 v${next}…`;
    const reviewed = assembled.find(f => f.review);
    const auto = Studio.autonomy() === "auto";
    if (reviewed && auto && findingsOf(reviewed.review).length) return `Fixing MP4 v${reviewed.n}…`;
    return `Reviewing MP4 v${(reviewed || assembled[0]).n}…`;
  }

  /** The findings of film `f`'s review, each with its time range (a click seeks `video` there); on the newest film
   *  (`editable`) each with a check box, then a note box and Fix, which sends the checked findings and the note. */
  function reviewPart(f, video, editable) {
    const key = `${project.dir}:${f.n}`;
    if (!fixes.has(key)) fixes.set(key, { off: new Set(), note: "" });
    const st = fixes.get(key);
    const findings = findingsOf(f.review);
    const fields = () => ({ action: "fix", version: f.n, findings: findings.map(x => x.k).filter(k => !st.off.has(k)), note: st.note });
    const fix = h("button", { class: "primary" }, "Fix");
    const sync = () => {
      const b = blocker({ action: "fix" }), x = fields();
      fix.disabled = !!b || (!x.findings.length && !x.note.trim());
      fix.title = b ? pendingText(b) : fix.disabled ? "Check a finding or write what to change" : "";
    };
    fix.onclick = async () => {
      const x = fields();
      if (fix.disabled || blocker(x)) return;
      if (await send(x)) { fixes.delete(key); render(); }
    };
    const seek = x => { video.currentTime = Number(x.start) || 0; video.play().catch(() => {}); };
    const rows = findings.map(x => {
      const id = `sv-fx-${f.n}-${x.k}`;
      return h("div", { class: "finding" + (editable ? "" : " fixed") },
        editable ? h("input", { type: "checkbox", id, checked: !st.off.has(x.k),
          onchange: e => { if (e.target.checked) st.off.delete(x.k); else st.off.add(x.k); sync(); } }) : null,
        h("button", { class: "when", type: "button", title: "Play the film from here", onclick: () => seek(x) },
          `${mmss(x.start)}–${mmss(x.end)}`),
        h("label", { for: editable ? id : null }, h("span", {}, x.problem || ""), x.change ? h("span", { class: "change" }, x.change) : null));
    });
    const note = h("textarea", { "data-k": `fix-note-${f.n}`, rows: 2, placeholder: "Anything else to change in this film", value: st.note,
      oninput: e => { st.note = e.target.value; sync(); } });
    sync();
    return h("div", { class: "review" },
      h("div", { class: "head" }, h("b", {}, "Review"), h("span", { class: "hint" },
        [f.review.model, findings.length ? plural(findings.length, "finding") : null].filter(Boolean).join(" · "))),
      rows.length ? rows : h("div", { class: "hint" }, "No findings"),
      editable ? [note, h("div", { class: "foot" }, fix)] : null);
  }

  async function phone(f) {
    if (blocker({ action: "phone", version: f.n })) return;
    if (!confirm(`Make a phone version (9:16, about 1 minute) of film v${f.n}? It becomes a new project in the list.`)) return;
    await request({ action: "phone", version: f.n });
  }

  /* ---------- scene view ---------- */

  const ui = {};

  function sceneSections() {
    const id = view;
    const sc = () => sceneOf(id) || {};
    section(() => JSON.stringify([id, scenes().length, indexOf(id), secs(sc()), notice, !!samples()]), sceneNav);
    section(() => JSON.stringify([id, info(id).pictures, info(id).picture, info(id).still, info(id).page, drawn(sc()), sc().image, shown, picturesLocked(id), P().name,
      reqs().filter(p => p.request.scene === id).map(p => [p.request.id, p.current])]), scenePicture);
    section(() => JSON.stringify([id, sc().narration, sc().beats, sc().speakers, sc().voices, sb && sb.speakers, film.voice,
      info(id).recording && info(id).recording.duration, writeHint, drawn(sc())]), sceneLines);
    section(() => JSON.stringify([id, !!info(id).recording, sc().template, sc().engine, sc().brief, secs(sc()),
      scenes().slice(0, Math.max(0, indexOf(id))).map(secs), drawn(sc())]), sceneMovement);
    section(() => JSON.stringify([id, (P().scene_styles || {})[id], P().style, ownStyle, drawn(sc())]), sceneStyle);
    section(() => JSON.stringify([id, drawn(sc())]), sceneAsk);
  }

  function sceneNav() {
    const i = indexOf(view), n = scenes().length, s = sceneOf(view);
    if (!s) return null;
    return [
      noticeBox(),
      h("div", { class: "snav" },
        h("button", { class: "secondary", onclick: () => openScene(null) }, "← Back to storyboard"),
        h("h1", {}, `Scene ${i + 1} of ${n} · ${titleOf(view)}`), h("span", { class: "muted" }, mmss(secs(s))),
        h("button", { class: "secondary", disabled: !!samples(), title: samples() ? "Shown once a style is picked from the 3 samples in step 2"
          : "This scene's recording and animation, in step 6 of the storyboard view", onclick: () => seeResult(view) }, "See the result"),
        h("div", { class: "pn" },
          h("button", { class: "secondary", disabled: i <= 0, onclick: () => openScene(scenes()[i - 1].id) }, `‹ Scene ${i || ""}`),
          h("button", { class: "secondary", disabled: i >= n - 1, onclick: () => openScene(scenes()[i + 1].id) }, `Scene ${i < n - 1 ? i + 2 : ""} ›`),
          h("button", { class: "secondary danger", title: n > 1 ? "Delete this scene" : "A storyboard keeps at least one scene", disabled: n <= 1, onclick: deleteScene }, "Delete scene")))];
  }

  function deleteScene() {
    const i = indexOf(view);
    if (!confirm(`Delete scene ${i + 1}, ${titleOf(view)}? Its pictures, recordings and clips stay on disk.`)) return;
    sb.scenes.splice(i, 1);
    view = null;
    edited(false);
    build();
  }

  /** Gives a picture version its scene, so the detail view and its actions know it. */
  const adopt = (v, scene) => Object.assign(v, { sceneId: scene });

  /** Pictures a pending request on the scene makes. */
  function expected(r) {
    switch (r.action) {
      case "change": case "use-still": return 1;
      case "variations": return r.count || 3;
      case "other-styles": return (r.styles && r.styles.length) || 3;
      default: return 0;
    }
  }

  /** The number of a scene view step. */
  const stepNum = n => String(n);
  /** Whether still `v` is of the page version the film uses (the scene's latest page). */
  const stillInFilm = (v, id) => !!info(id).page && info(id).page.page === `${project.dir}/${v.page_version}/index.html`;

  /** Step 1 of the scene view: the picture versions, or for a drawn scene the stills of its page versions, with the
   *  chosen one in the shell's detail view. */
  function scenePicture() {
    const id = view, i = info(id), paged = drawn(sceneOf(id));
    const pics = i.pictures.filter(v => !paged || isStill(v)).map(v => adopt(v, id));
    const used = paged ? i.still : i.picture;
    // A version the page just wrote (`waiting`) stays chosen until the project's reload lists it.
    if (shown && shown.scene === id && !shown.waiting && !pics.some(v => v.n === shown.n)) shown = null;
    if (!shown || shown.scene !== id) shown = pics.length ? { scene: id, n: used ?? pics[0].n } : null;
    let v = shown && pics.find(p => p.n === shown.n);
    if (v) delete shown.waiting;
    else if (shown && shown.waiting) v = pics.find(p => p.n === used) || pics[0] || null;
    let next = Math.max(0, ...pics.map(p => p.n)) + 1;
    const cards = [];
    for (const p of reqs().filter(p => p.request.scene === id && PICTURE_ACTIONS.includes(p.request.action))) {
      const made = p.current && p.request.time ? pics.filter(x => new Date(x.created) >= new Date(p.request.time)).length : 0;
      for (let k = made; k < expected(p.request); k++) cards.push(h("div", { class: "ver pending" },
        h("div", { class: "ph" }, p.current ? h("div", { class: "spin" }) : null, p.current ? `Making v${next++}…` : "Waiting"),
        h("div", { class: "t" }, h("b", {}, p.current ? `v${next - 1}` : "queued"), h("span", {}, p.request.action === "change" ? `change of v${p.request.version}`
          : p.request.action === "use-still" ? `page of v${p.request.version}` : p.request.action.replace("-", " "))),
        k === made ? h("div", { class: "t" }, runStatus(p.request.id)) : null));
    }
    cards.push(...pics.map(p => h("div", { class: "ver" + (v && p.n === v.n ? " on" : ""), onclick: () => { shown = { scene: id, n: p.n }; render(); } },
      h("img", { src: fileUrl(p.image), alt: "", loading: "lazy" }),
      (paged ? stillInFilm(p, id) : p.n === i.picture) ? h("span", { class: "badge" }, "In the film") : null,
      h("div", { class: "t" }, h("b", {}, `v${p.n}`), h("span", {}, p.action === "own-picture" ? "your picture" : versionStyle(p)), h("span", {}, when(p.created))))));
    ui.wantDetail = v || null;
    return h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, "1"), paged ? "Still of the page" : "Picture", h("span", { class: "hint" },
        paged ? "a frame of the scene's page; every version is kept, newest first; mark what to change in the page"
          : "every version is kept, newest first; mark what to change")),
      v ? ui.detailHost : paged ? h("div", { class: "nopic drawn-note" }, Studio.icon("draw"),
        h("span", {}, "This scene is drawn in its page. Its page is built and a still taken where the other scenes get their pictures."))
        : h("div", { class: "nopic" }, h("span", {}, "This scene has no picture yet."),
          h("button", { class: "secondary", disabled: picturesLocked(id), onclick: () => ownPicture(id) }, "Use my own picture")),
      cards.length ? h("div", { class: "pics" }, cards) : null);
  }

  /** After a redraw: the detail view shows the chosen version, or only its rows and actions again. */
  function afterRender() {
    if (!view || !ui.detailHost) return;
    const v = ui.wantDetail;
    if (!v) { if (ui.detailOf) { releaseDetail(); ui.detailOf = null; } return; }
    const key = `${view}:${v.n}`;
    if (ui.detailOf !== key) { ui.detailOf = key; openDetail(v, { into: ui.detailHost }); }
    else refreshDetail();
  }

  function usePicture(v) {
    const s = sceneOf(v.sceneId);
    if (!s) return;
    s.image = `${v.sceneId}/v${v.n}.png`;
    commit();
  }

  /** The user's own picture: converted to PNG, written with /api/picture, then used by the scene. */
  function ownPicture(id) {
    const input = h("input", { type: "file", accept: IMAGE_TYPES.join(","), hidden: true });
    input.onchange = async () => {
      const [file] = input.files;
      if (!file) return;
      if (!IMAGE_TYPES.includes(file.type)) return error(`${file.name} is not a PNG, JPEG or WebP image.`);
      try {
        const data = await pngDataUrl(file);
        const { version } = await api.post("/api/picture", { project: project.dir, scene: id, name: file.name, data });
        const s = sceneOf(id);
        if (s) { s.image = `${id}/v${version}.png`; shown = { scene: id, n: version, waiting: true }; commit(); }
      } catch (e) { error(`Could not use ${file.name}: ${e.message}`); }
    };
    input.click();
  }

  async function pngDataUrl(file) {
    if (file.type === "image/png") return Studio.readDataUrl(file);
    const bitmap = await createImageBitmap(file);
    const c = h("canvas", { width: bitmap.width, height: bitmap.height });
    c.getContext("2d").drawImage(bitmap, 0, 0);
    return c.toDataURL("image/png");
  }

  /* ---------- scene view: the sentences ---------- */

  function sceneLines() {
    const s = sceneOf(view);
    if (!s) return null;
    const spk = !!s.speakers, names = Object.keys(sb.speakers || {});
    const clip = s.engine === "clip" && !s.template;
    const rows = s.narration.flatMap((said, k) => {
      const who = spk ? h("td", { class: "who" }, (() => {
        const sel = h("select", { onchange: e => setSpeaker(s, k, e.target.value) },
          h("option", { value: "" }, "Film voice"), names.map(n => h("option", { value: n }, n)), h("option", { value: "+" }, "+ New speaker…"));
        sel.value = speakerOf(s, k) || "";
        return sel;
      })()) : null;
      return [
        h("tr", {},
          h("td", { class: "n", "data-when": k }),
          who,
          h("td", {}, textField("textarea", `said-${view}-${k}`, said, t => { s.narration[k] = t; }, { onedit: renderTimes })),
          h("td", {}, textField("textarea", `beat-${view}-${k}`, s.beats[k] || "", t => { s.beats[k] = t; })),
          h("td", { class: "x" }, h("button", { title: "Remove sentence", disabled: s.narration.length <= 1 && !clip, onclick: () => removeSentence(s, k) }, "×"))),
        h("tr", { class: "vrow" }, h("td"), h("td", { colspan: spk ? 4 : 3 }, voicePart(s, k)))];
    });
    const out = h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, stepNum(2)), "What is said and what is on screen", h("span", { class: "hint" }, "one row per sentence, in the order spoken; type to change")),
      h("label", { class: "switch" }, h("input", { type: "checkbox", checked: spk, onchange: e => switchSpeakers(s, e.target.checked) }), h("span"),
        "Advanced: a different voice per sentence"),
      h("table", { class: "lines" },
        h("thead", {}, h("tr", {}, h("th", { class: "n" }, "When"), spk ? h("th", { class: "who" }, "Speaker") : null,
          h("th", {}, "What is said"), h("th", {}, "What is on screen meanwhile"), h("th", { class: "x" }))),
        h("tbody", {}, rows)),
      writeHint ? h("div", { class: "notice inline" }, writeHint) : null,
      h("div", { class: "foot" }, h("button", { class: "mini", onclick: () => addSentence(s) }, "+ Add a sentence"),
        h("span", { class: "hint" }, "Changed words need a new recording; it is made with the next film.")));
    requestAnimationFrame(renderTimes);
    return out;
  }

  /** The "When" column: each sentence's share of the scene by its words, scaled to the recording when there is one. */
  function renderTimes() {
    const s = sceneOf(view);
    if (!s || !root) return;
    const lens = s.narration.map(t => Math.max(words(t), 1) / WORDS_PER_SECOND);
    const sum = lens.reduce((a, b) => a + b, 0) || 1, rec = info(view).recording;
    const scale = rec && rec.duration ? rec.duration / sum : 1;
    let t = 0;
    lens.forEach((len, k) => {
      const cell = root.querySelector(`[data-when="${k}"]`);
      if (cell) cell.textContent = `${mmss(t)}–${mmss(t + len * scale)}`;
      t += len * scale;
    });
  }

  /** Adds or removes `speakers` and `voices` entries with a sentence. */
  function addSentence(s) {
    s.narration.push("");
    s.beats.push("");
    if (s.speakers) s.speakers.push(null);
    if (s.voices) s.voices.push(null);
    render();
    root.querySelector(`[data-k="said-${view}-${s.narration.length - 1}"]`)?.focus();
    flush();
  }

  function removeSentence(s, k) {
    for (const key of ["narration", "beats", "speakers", "voices"]) if (s[key]) s[key].splice(k, 1);
    if (s.voices && s.voices.every(x => x == null)) delete s.voices;
    commit();
  }

  function switchSpeakers(s, on) {
    if (on) s.speakers = s.narration.map(() => null);
    else delete s.speakers;
    commit();
  }

  function setSpeaker(s, k, value) {
    if (value === "+") {
      const name = addSpeaker();
      s.speakers[k] = name;
      commit();
      openScene(null);
      requestAnimationFrame(() => Studio.reveal(root.querySelector("#sv-speakers")));
      return;
    }
    s.speakers[k] = value || null;
    commit();
  }

  /**
   * The collapsed voice part of sentence k: model, voice, speed and tone, each unset by default and showing what it
   * inherits from the sentence's speaker or the film. Model and voice are set together (no model without a voice).
   */
  function voicePart(s, k) {
    const own = (s.voices || [])[k] || {}, inh = inherited(s, k), eff = sentenceVoice(s, k);
    const from = speakerOf(s, k) || "the film";
    const set = [own.model || own.name ? `voice ${voiceLabel(eff)}` : null,
      own.speed != null ? `speed ${speedLabel(own.speed).toLowerCase()}` : null,
      own.style ? `tone “${own.style}”` : null].filter(Boolean);
    const line = set.length ? `Voice: ${set.join(", ")}` : `Voice: as ${from} (${voiceText(inh)})`;
    const save = patch => {
      const next = { model: null, name: null, speed: null, style: null, ...own, ...patch };
      const b = next.model || inh.model;
      if (!hasSpeed(b)) next.speed = null;
      if (!hasStyle(b)) next.style = null;
      const empty = Object.values(next).every(x => x == null);
      if (!s.voices && empty) return;
      s.voices = s.voices || s.narration.map(() => null);
      s.voices[k] = empty ? null : next;
      if (s.voices.every(x => x == null)) delete s.voices;
      commit();
    };
    const opt = (value, label) => h("option", { value }, label);
    const model = h("select", { onchange: e => {
      const m = e.target.value;
      if (!m) return save({ model: null, name: null });
      save({ model: m, name: own.model === m ? own.name : null });
    } }, opt("", `As ${from}: ${modelName(inh.model)}`), speechModels().map(m => opt(m.id, m.id)));
    model.value = own.model || "";
    const voice = h("input", { type: "text", value: own.name || "", "data-k": `voice-${view}-${k}`,
      placeholder: `As ${from}: ${voiceLabel(inh)}`, onchange: e => save({ name: e.target.value.trim() || null }) });
    const speed = h("select", { disabled: !hasSpeed(eff.model), onchange: e => save({ speed: e.target.value ? +e.target.value : null }) },
      opt("", hasSpeed(eff.model) ? `As ${from}: ${speedLabel(inh.speed)}` : "Normal (this voice has one speed)"),
      SPEEDS.map(([x, l]) => opt(x, l)));
    speed.value = own.speed != null ? String(own.speed) : "";
    const tone = h("input", { type: "text", value: own.style || "", disabled: !hasStyle(eff.model), "data-k": `tone-${view}-${k}`,
      placeholder: hasStyle(eff.model) ? (inh.style ? `As ${from}: ${inh.style}` : "For example: whispering, excited") : "This model takes no style",
      onchange: e => save({ style: e.target.value.trim() || null }) });
    const field = (label, control) => h("div", {}, h("label", { class: "f" }, label), control);
    return details(`voice-${view}-${k}`, { class: "svoice" + (set.length ? " set" : "") },
      h("summary", {}, line),
      h("div", { class: "svoice-grid" }, field("Model", model), field("Voice", voice), field("Speed", speed), field("Tone or speaking style", tone),
        h("div", { class: "svoice-play" }, playButton("Play a sample of this voice", b => sample(eff, b)))));
  }

  /* ---------- scene view: narration, movement, own style, what to change ---------- */

  /** The plan of the scene's movement: how its picture moves (what a drawn scene draws), none for a template
   *  scene, then its length and start. Its recording and animation are in step 6. */
  function sceneMovement() {
    const s = sceneOf(view);
    if (!s) return null;
    const rec = info(view).recording, k = indexOf(view);
    const start = scenes().slice(0, k).reduce((a, x) => a + secs(x), 0);
    return h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, stepNum(3)), s.template ? "Timing" : "Movement and timing"),
      s.template || s.engine === "clip" ? null : enginePart(s),
      s.template ? null : [h("label", { class: "f" }, drawn(s) ? "What the scene draws and how it moves"
        : s.engine === "manim" ? "What moves and transforms" : s.engine === "video" ? "What the video model animates (its prompt)"
        : s.engine === "presenter" ? "How the presenter moves (optional; empty uses the model's own prompt)"
        : "How the picture moves"),
        textField("textarea", `brief-${view}`, s.brief || "", t => { s.brief = t; }, { class: "sv-brief" })],
      h("dl", { class: "facts", style: "margin-top:12px" },
        h("dt", {}, "Length"), h("dd", {}, `${mmss(secs(s))}, ${rec ? "set by the spoken words" : "estimated from the words"}`),
        h("dt", {}, "Starts at"), h("dd", {}, `${mmss(start)} in the film`)));
  }

  /** The engine that animates a scene: html (the default, no `engine`), manim, or a video model of config.yaml,
   *  disabled when the config names none. Each change is one storyboard write. */
  function enginePart(s) {
    const select = h("select", { onchange: e => {
      if (e.target.value === "html") delete s.engine; else s.engine = e.target.value;
      if (s.engine !== "video") delete s.ambience;  // only a video scene has a model sound track
      commit();
    } }, ENGINES.map(([v, label, task]) => h("option", { value: v,
      disabled: s.engine !== v && ((!!task && !taskModel(task)) || (NEEDS_PICTURE.includes(v) && !s.image)) },
      task ? Studio.withModel(label, taskModel(task)) : label)));
    select.value = s.engine || "html";
    return h("div", { style: "margin-bottom:12px;max-width:420px" }, h("label", { class: "f" }, "Animated by"), select);
  }

  function sceneStyle() {
    if (drawn(sceneOf(view))) return null;
    const id = view, mine = (P().scene_styles || {})[id] || null, filmStyle = P().style;
    const filmName = filmStyle ? (filmStyle.invented ? filmStyle.invented.name : nice(filmStyle.name)) : "not chosen yet";
    const own = !!mine || ownStyle;
    const choose = async style => {
      try {
        const { scene_styles } = await api.post("/api/scene-style", { project: project.dir, scene: id, style });
        P().scene_styles = scene_styles;
        ownStyle = false;
        render();
      } catch (e) { error(`Could not change the scene's style: ${e.message}`); }
    };
    const picker = own ? stylePicker({ value: mine, onPick: choose }) : null;
    return details("own-style", { class: "card adv" },
      h("summary", {}, h("b", {}, "Advanced: this scene’s own style"), h("span", { class: "hint" }, mine ? `own style: ${nice(mine)}` : "Same as the film")),
      h("div", { style: "margin-top:14px; max-width:560px" },
        seg([["film", `Same as the film (${filmName})`], ["own", "Own style"]], own ? "own" : "film",
          v => { if (v === "own") { ownStyle = true; render(); } else if (mine) choose(null); else { ownStyle = false; render(); } }),
        own ? h("div", { class: "overrides" }, mine ? `New pictures of this scene use ${nice(mine)}; the other scenes keep ${filmName}.`
          : "Pick the style of this scene's new pictures, for example a diagram scene in an illustrated film.") : null),
      own ? h("div", { class: "adv-picker" }, h("label", { class: "f" }, "Style of this scene, from the same catalogue as the film's", " · ", picker.count), picker.el) : null);
  }

  function sceneAsk() {
    const k = indexOf(view);
    const text = h("textarea", { id: "scene-ask", "data-k": `ask-${view}`, placeholder: "For example: this scene is too slow, cut the last sentence and make the push-in faster" });
    const send = h("button", { class: "primary", style: "padding:9px 18px" }, "Send");
    send.onclick = async () => {
      const t = text.value.trim();
      if (!t) { text.focus(); return; }
      send.disabled = true;
      try { if (await request({ action: "message", text: t, scene: view })) text.value = ""; } finally { send.disabled = false; }
    };
    return h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, stepNum(4)), "What to change in this scene", h("span", { class: "hint" }, "anything at all, about this scene")),
      text, h("div", { class: "foot" }, send, h("span", { class: "hint" }, `Sent as “Scene ${k + 1}: …”. Use the box on the right for the whole film.`)));
  }

  /* ---------- views and the action bar ---------- */

  /** Draws the current view from scratch. */
  function build() {
    sections = [];
    folders = [];
    if (view && !sceneOf(view)) view = null;
    if (view) {
      ui.detailHost = ui.detailHost || h("div", { class: "dhost" });
      sceneSections();
    } else {
      releaseDetail();
      ui.detailOf = null;
      boardSections();
    }
    root.replaceChildren(...sections.map(s => s.el));
    makeBar();
    render();
  }

  function openScene(id) {
    if (view && ui.detailOf) { releaseDetail(); ui.detailOf = null; }
    view = id;
    ownStyle = false;
    build();
    document.querySelector(".main").scrollTop = 0;
  }

  async function makeFilm() {
    if (film.music.mode === "own" && V().music_used == null) { bar.error(`Upload your own track in step ${voiceNum() + 1} first, or choose other music.`); Studio.reveal(root.querySelector("#sv-music")); return; }
    await send({ action: "make-film" });
  }

  /** The bar's main action: Make the film once the storyboard has scenes, in both views, else on a new project
   *  Make the film (storyboard and film in one request) with Write the storyboard first beside it. */
  function makeBar() {
    const want = scenes().length ? { key: "film", label: "Make the film", run: makeFilm }
      : { key: "new", label: "Make the film", run: () => writeStoryboard(null, true), more: { label: "Write the storyboard first", run: () => writeStoryboard() } };
    if (bar && barKey === want.key) return;
    barKey = want.key;
    bar = Studio.actionBar(want);
  }

  function summary() {
    if (!bar) return;
    makeBar();
    if (!project || !sb || (!view && !scenes().length)) {
      const writing = blocker({ action: "storyboard" });
      bar.enable(!(project && V().error) && !writing);
      bar.summary(project && V().error ? "" : writing ? pendingText(writing)
        : "Make the film: storyboard, style and film made without stopping. Write the storyboard first: you check scenes and style before the film.");
      return;
    }
    const v = film.voice;
    if (samples()) { bar.enable(false); bar.summary("Pick one of the 3 styles in step 2 first"); return; }
    const b = blocker({ action: "make-film" });
    if (b) { bar.enable(false); bar.summary(pendingText(b)); return; }
    const list = scenes(), need = list.filter(s => stateOf(s.id) === "voice").length, rend = list.filter(s => stateOf(s.id) === "render").length;
    const music = film.music.mode === "none" ? "no music" : V().music_used != null ? `music v${V().music_used}` : film.music.mode === "made" ? "music made with the film" : "own music not uploaded";
    const work = need || rend ? [need ? `${plural(need, "scene")} ${need === 1 ? "needs" : "need"} a voice` : null,
      rend ? `${rend} ${rend === 1 ? "needs" : "need"} a render` : null].filter(Boolean).join(", ") : "every scene up to date";
    bar.enable(list.length > 0);
    bar.summary([plural(list.length, "scene"), mmss(total()), shapeLabel(film.shape), `voice ${voiceText(v)}`, music, work,
      film.review ? "MP4 reviewed" : null].filter(Boolean).join(" · "));
  }

  /* ---------- module ---------- */

  function open(el, data) {
    root = el;
    project = data;
    sb = clone(data && data.video ? data.video.storyboard : null);
    mtime = data && data.video ? data.video.storyboard_mtime : null;
    film = filmOf(data);
    blankFilm = data ? null : film;
    const p = (data && data.project) || {}, s = p.settings || {};
    form = { brief: s.brief || p.brief || "", refs: [...(s.refs || [])], sources: [...(s.sources || [])], style: s.style || "auto" };
    view = null;
    shown = null;
    notice = writeHint = null;
    fromCatalogue = adding = false;
    ui.detailOf = null;
    clearTimeout(W.timer);
    Object.assign(W, { timer: null, inflight: false, again: false });
    build();
    if (!data) ui.brief && ui.brief.focus();
  }

  function update(data) {
    const was = project;
    project = data;
    if (!writing()) {
      const fresh = data.video ? data.video.storyboard : null;
      if (!same(sb, fresh)) sb = clone(fresh);
      mtime = data.video ? data.video.storyboard_mtime : null;
    }
    if (!was && blankFilm) {
      // The blank workspace became a project: the film settings chosen meanwhile go into it.
      const chosen = blankFilm, now = filmOf(data);
      blankFilm = null;
      film = now;
      const patch = Object.fromEntries(Object.keys(chosen).filter(k => !same(chosen[k], now[k])).map(k => [k, chosen[k]]));
      if (Object.keys(patch).length && !(data.video && data.video.storyboard)) setFilm(patch);
    } else film = filmOf(data);
    if (!samples()) fromCatalogue = false;
    if (view && !sceneOf(view)) { view = null; build(); return; }
    if (scenePlayer) scenePlayer.sync();
    render();
  }

  function onEvent(ev) {
    if (!form || !root) return;
    if (["state", "request", "pending", "turn", "note", "autonomy", "catalogue", "stopped", "done"].includes(ev.kind)) render();
    if (scenePlayer && ["state", "request", "stopped", "done"].includes(ev.kind)) scenePlayer.sync();
  }

  /** Text of a request in the Claude column. */
  function describe(req) {
    const here = project && req.project === project.dir;
    const k = id => (here && indexOf(id) >= 0 ? `scene ${indexOf(id) + 1}` : `scene “${titleOf(id)}”`);
    const K = id => k(id).replace(/^s/, "S");
    switch (req.action) {
      case "storyboard": {
        const f = req.film || {};
        const style = CARDS[req.style] ? CARDS[req.style].asked : nice(req.style);
        return { text: `Write the storyboard · ${shapeLabel(f.shape)} · ${aim(f.length)} · ${style}\n${req.brief}` };
      }
      case "use-style": return { text: req.version != null ? `Use the style of sample v${req.version} for every scene` : `Use ${nice(req.style)} for every scene` };
      case "style-samples": {
        // "other" only while samples are shown, from "Choose others" or "Invent others".
        const other = here && samples() ? " other" : "";
        return { text: req.style === "invent" ? `Invent 3${other} styles to choose from` : `Pick 3${other} catalogue styles to choose from` };
      }
      case "change": case "variations": case "other-styles":
        return describeEdit(req, `${k(req.scene)} · ${here && drawn(sceneOf(req.scene)) ? "still" : "picture"} `);
      case "use-still": return { text: `${K(req.scene)}: use the page of still v${req.version}` };
      case "add-scene": return { text: `Add a scene${req.after ? ` after ${k(req.after)}` : ""}:\n${req.text}` };
      case "remake-scene": return { text: `Remake ${k(req.scene)}` };
      case "mark-scene": return { text: `${K(req.scene)} at ${Number(req.t).toFixed(2)} s${req.ids && req.ids.length ? ` · ${req.ids.join(", ")}` : ""}:\n${req.text}`,
        images: req.marked ? [req.marked] : [] };
      case "music": return { text: `Make new music:\n${req.brief}` };
      case "own-music": return { text: `Use my own track ${baseName(req.file || "")}` };
      case "voice-sample": return { text: `A sample of the voice ${voiceText(resolve(null, req.voice))}` };
      case "make-film": return { text: "Make the film" };
      case "export-mp4": return { text: "Export the film as MP4" };
      case "review": return { text: `Review film v${req.version}` };
      case "fix": {
        const n = (req.findings || []).length;
        return { text: `Fix film v${req.version}${n ? ` · ${plural(n, "finding")}` : ""}${req.note && req.note.trim() ? `\n${req.note}` : ""}` };
      }
      case "phone": return { text: `Phone version of film v${req.version}` };
      case "message": return req.scene ? { text: `${K(req.scene)}: ${req.text}` } : null;
      default: return null;
    }
  }

  /** A version's rows in the detail view; a still adds the page version and time it was taken from, and its page style. */
  const versionInfo = v => [...versionRows(v, shapeLabel),
    ...(isStill(v) ? [["Page", `${v.page_version}${Number.isFinite(v.t) ? ` at ${v.t} s` : ""}`], ["Page style", pageStyleText(v)]] : [])]
    .filter(r => r[1]);

  /** The detail actions of a version: a picture's (variations, other styles, own picture, use it); a still takes a
   *  change (Send), "Use this still" when its page is not the film's (a `use-still` request makes that page the
   *  scene's latest page version), "Use as reference" and Download. */
  function detailActions(v) {
    const id = v.sceneId, locked = picturesLocked(id);
    const acts = editActions(v, async () => {
      // A storyboard's refs are files in refs/: the picture is copied there.
      const ref = await copyToRefs(v.image);
      if (ref && !form.refs.includes(ref)) form.refs.push(ref);
      openScene(null);
      requestAnimationFrame(() => Studio.reveal(root.querySelector("#sv-brief")));
    });
    // editActions: 3 variations, other styles, use as reference, download.
    if (isStill(v)) {
      const still = acts.slice(2);
      if (info(id).page && !stillInFilm(v, id)) still.unshift({ label: "Use this still",
        disabled: locked, title: locked ? "Stills of this scene are being made; wait until they are done" : null,
        run: () => send({ action: "use-still", scene: id, version: v.n }) });
      return still;
    }
    acts.splice(3, 0, { label: "Use my own picture", disabled: locked, run: () => ownPicture(id),
      title: locked ? "Pictures of this scene are being made; wait until they are done" : null });
    if (info(id).picture !== v.n) acts.unshift({ label: "Use this picture", run: () => usePicture(v) });
    return acts;
  }

  const changeFields = v => (v.sceneId ? { scene: v.sceneId } : {});
  const detailTitle = v => `${P().name || ""} · scene ${indexOf(v.sceneId) + 1} · ${isStill(v) ? "still" : "picture"} v${v.n}`;

  Studio.register({ id: "videos", tag: () => "Short video", versionNoun: "film", open, update, onEvent, describe, versionInfo,
    detailActions, changeFields, detailTitle,
    askPlaceholder: "What you want, about the whole film or one scene. For example: scene 3 is too long, cut it to one sentence." });
})();
