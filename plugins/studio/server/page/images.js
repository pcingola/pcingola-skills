/*
 * Image workspace: 1 brief, references and settings; 2 style; Generate; 3 results.
 * Serves every kind of project whose skill is `images` (images, infographics, slides); the kind sets the words of
 * step 1, the styles listed and the default shape. A slide project is a deck: step 1 describes the deck, Generate
 * makes or rewrites it, and the deck parts add 3 the list of slides, 4 the versions of the selected slide (the
 * results step, every action carrying that `slide`) and the PowerPoint assembly. Registers with the Studio shell
 * (shell.js), which draws everything around it.
 */
"use strict";

(() => {
  const { h, seg, plural, when, api, fileUrl, download, request, pending, closeDetail, error, nice, versionStyle, foldable,
    brandSelect, stylePicker, dropZone, upload, IMAGE_TYPES: REF_TYPES, refThumb, versionRows, editActions, describeEdit, runStatus } = Studio;

  const SHAPES = [["1:1", "Square (1:1)"], ["4:3", "Photo (4:3)"], ["16:9", "Slide (16:9)"], ["9:16", "Phone (9:16)"]];
  const shapeLabel = ratio => (SHAPES.find(s => s[0] === ratio) || [ratio, ratio])[1];
  // image-gen tiers (`--tier`), each a model of image-gen's config: image_best, image_multi_ref, image (image_edit with references).
  const MODELS = [["best", "Best"], ["multi-ref", "Multi-reference"], ["fast", "Fast draft"]];
  const COUNTS = [1, 2, 3, 4].map(n => [n, String(n)]);
  const AUTO_STYLES = 3;
  /** The picker cards that leave the style to Claude, by `style` value. */
  const CLAUDE_STYLES = {
    auto: { icon: "auto", title: "Let Claude choose", line: `Claude picks ${AUTO_STYLES} styles from the catalogue that suit the brief`,
      summary: `${AUTO_STYLES} styles chosen by Claude`, label: "style chosen by Claude", asked: "catalogue styles you choose" },
    invent: { icon: "invent", title: "Invent new styles", line: `Claude makes up ${AUTO_STYLES} new styles that are in no catalogue`,
      summary: `${AUTO_STYLES} new styles invented by Claude`, label: "new style by Claude", asked: "new styles you invent" },
  };
  /** The same cards for a deck: one style for every slide. */
  const DECK_STYLES = {
    auto: { ...CLAUDE_STYLES.auto, line: "Claude picks one style from the catalogue that suits the deck",
      summary: "style chosen by Claude" },
    invent: { ...CLAUDE_STYLES.invent, title: "Invent a new style", line: "Claude makes up a new style for the deck, one that is in no catalogue",
      summary: "new style invented by Claude", asked: "a new style you invent" },
  };
  const styleCards = () => (kind.deck ? DECK_STYLES : CLAUDE_STYLES);
  /** Values of `assembly`: an images-only deck or an editable (native) PowerPoint. */
  const ASSEMBLY = [["images", "Images only (fast, not editable)"], ["native", "Editable PowerPoint (slower)"]];
  const assemblyLabel = id => (ASSEMBLY.find(a => a[0] === id) || [id, id])[1];
  /** Number of slides of a deck: null leaves it to Claude. */
  const SLIDE_COUNTS = [["", "Let Claude decide"], ...Array.from({ length: 20 }, (_, i) => [String(i + 1), String(i + 1)])];
  /**
   * What depends on the kind of project: the tag, step 1's title, hint and placeholder, the reference drop text, the
   * message for an empty brief and the default shape; `deck` for the kind whose project is a deck of slides, with its
   * shape fixed.
   */
  const KINDS = {
    image: {
      tag: "Image", title: "What should the image show?", hint: "plain words are fine",
      placeholder: "For example: a cyclist repairing a flat tyre at the side of a country road in morning light",
      drop: "Drop reference images here (a photo to edit, a logo, a sketch), or click to choose files",
      empty: "Describe the image in step 1 first.", shape: "4:3",
    },
    infographic: {
      tag: "Infographic", title: "What should the infographic explain, and from which facts?",
      hint: "one concept; plain words are fine",
      placeholder: "For example: how a heat pump moves heat from cold outdoor air into a house, using the facts in the summary I pasted below",
      drop: "Drop reference images here (a chart, a diagram, a photo, a logo, a sketch), or click to choose files",
      empty: "Write in step 1 what the infographic should explain first.", shape: "4:3",
    },
    slide: {
      tag: "Deck", title: "What is the deck about?", hint: "who it is for, its message and the facts; plain words are fine",
      placeholder: "For example: a five-minute talk for a neighbourhood meeting on the new community garden: what we did, what we learned and what we need next, from the notes I pasted below",
      drop: "Drop reference images here (a chart, a photo, a logo, a sketch), or click to choose files",
      empty: "Write in step 1 what the deck is about first.", shape: "16:9", deck: true,
    },
  };

  let kind = KINDS.image; // KINDS entry of the open workspace
  let project = null;     // answer of /api/project; null in a blank workspace
  let slide = null;       // deck: the selected slide's number (one past the last: a slide to add), or null
  /** Deck: the slides of /api/project, [] in a blank workspace. */
  const slides = () => (project && project.deck ? project.deck.slides : []);
  const slideOf = k => slides().find(s => s.k === k) || null;
  /** The versions the results step shows: the project's, or the selected slide's. */
  const versions = () => (!project ? [] : kind.deck ? (slideOf(slide) || { versions: [] }).versions : project.versions);
  let form = null;        // the generate fields being edited
  const ui = {};          // containers redrawn on their own

  const modelLabel = id => (MODELS.find(m => m[0] === id) || [id, id])[1];
  /** The model id of config.yaml that tier `id` takes, with reference images (`refs`) or without; null when none. */
  function tierModel(id, refs) {
    const t = Studio.models().tiers.find(x => x.id === id);
    return t ? (refs ? t.ref_model : t.model) : null;
  }
  /** The Quality options, each labelled with its model and disabled without one; a tier with no model gives way to
   *  the first tier that has one. */
  function modelOptions(select) {
    const refs = form.refs.length > 0;
    select.replaceChildren(...MODELS.map(([v, label]) =>
      h("option", { value: v, disabled: !tierModel(v, refs) }, Studio.withModel(label, tierModel(v, refs)))));
    const first = MODELS.find(([v]) => tierModel(v, refs));
    if (!tierModel(form.model, refs) && first) form.model = first[0];
    select.value = form.model;
  }

  /* ---------- step 1: brief, references, settings ---------- */

  function stepBrief() {
    const brief = ui.brief = h("textarea", { id: "brief", value: form.brief, placeholder: kind.placeholder,
      oninput: e => { form.brief = e.target.value; ui.step1?.foldSummary?.(form.brief); summary(); } });
    ui.refs = h("div", { class: "refs" }, dropZone(kind.drop, REF_TYPES.join(","), addFiles));
    const brand = brandSelect(form.brand, v => { form.brand = v; summary(); });
    const model = ui.model = h("select", { onchange: e => { form.model = e.target.value; summary(); } });
    modelOptions(model);
    const shape = h("select", { disabled: kind.deck, title: kind.deck ? "Every slide is 16:9" : null,
      onchange: e => { form.shape = e.target.value; summary(); } },
      SHAPES.map(([v, label]) => h("option", { value: v }, label)));
    shape.value = form.shape;
    const count = kind.deck
      ? h("select", { onchange: e => { form.count = e.target.value ? +e.target.value : null; summary(); } },
        SLIDE_COUNTS.map(([v, label]) => h("option", { value: v }, label)))
      : seg(COUNTS, form.count, v => { form.count = +v; summary(); });
    if (kind.deck) count.value = form.count == null ? "" : String(form.count);
    const field = (label, control) => h("div", {}, h("label", { class: "f" }, label), control);
    ui.step1 = h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, "1"), kind.title, h("span", { class: "hint" }, kind.hint)),
      brief, ui.refs,
      h("div", { class: "row" },
        field("Brand", brand),
        field("Shape", shape),
        field("Quality", model),
        field(kind.deck ? "Slides" : "How many", count)));
    renderRefs();
    return stepFold(ui.step1, "brief", form.brief);
  }

  function renderRefs() {
    ui.refs.querySelectorAll(".ref").forEach(el => el.remove());
    ui.refs.append(...form.refs.map(path => refThumb(path, () => { form.refs = form.refs.filter(p => p !== path); renderRefs(); })));
    if (ui.model) { modelOptions(ui.model); summary(); }
  }

  async function addFiles(files) {
    const images = files.filter(file => REF_TYPES.includes(file.type) || (error(`${file.name} is not a PNG, JPEG or WebP image.`), false));
    for (const path of await upload("/api/refs", images)) if (!form.refs.includes(path)) form.refs.push(path);
    renderRefs();
  }

  /* ---------- step 2: style ---------- */

  function stepStyle() {
    const picker = stylePicker({ cards: styleCards(), value: form.style,
      onPick: name => { form.style = name; card.foldSummary(styleName()); summary(); } });
    const card = ui.style = h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, "2"), "Pick a style", picker.count), picker.el);
    return stepFold(card, "style", styleName());
  }
  /** The chosen style in words: a card's summary or the style's name. */
  const styleName = () => { const c = styleCards()[form.style]; return c ? c.summary : nice(form.style); };
  /** The key of a step's fold state: per project (blank workspaces share one) and kind. */
  const foldKey = step => `${project ? project.dir : `blank:${kind.id}`}:${step}`;
  /** A step that folds by its title, open when it is a step being worked on. */
  const stepFold = (card, step, summary = "") => foldable(card, { key: foldKey(step), open: openSteps().has(step), summary });

  /**
   * The steps being worked on, the cards open by default. An image or infographic: the brief until there is a
   * version or a request, then the results. A deck: the brief until it has slides or a request, then the slides,
   * with the selected slide's versions, and the PowerPoint step while one is made or once every slide has a chosen
   * version and none is made yet.
   */
  function openSteps() {
    const busy = project ? pending(project.dir) : [];
    if (!kind.deck) return new Set([versions().length || busy.length ? "results" : "brief"]);
    if (!slides().length && !busy.length) return new Set(["brief"]);
    const open = new Set(["deck"]);
    if (slide != null) open.add("results");
    const decks = (project && project.deck && project.deck.decks) || [];
    if (busy.some(p => p.request.action === "assemble") || (!decks.length && slides().every(s => s.chosen != null))) open.add("assembly");
    return open;
  }
  /** Gives every step card its current default fold and the busy mark of the work running in it. */
  function refold() {
    const open = openSteps(), busy = project ? pending(project.dir) : [];
    const cards = { brief: ui.step1, style: ui.style, results: ui.results, deck: kind.deck && ui.deck, assembly: kind.deck && ui.assembly };
    const working = {
      results: busy.some(p => p.request.action !== "assemble" && (!kind.deck || (slide != null && p.request.slide === slide))),
      deck: busy.some(p => p.request.action === "generate"),
      assembly: busy.some(p => p.request.action === "assemble"),
    };
    for (const [step, card] of Object.entries(cards)) if (card && card.foldDefault) { card.foldDefault(open.has(step)); card.foldBusy(working[step]); }
  }

  /* ---------- generate ---------- */

  /** The current choices in one line for the action bar, e.g. "2 images · 4:3 · Clay miniature · Best". */
  function summary() {
    if (!ui.bar) return;
    const c = styleCards()[form.style];
    const amount = kind.deck ? (form.count ? plural(form.count, "slide") : "slides: Claude decides") : plural(form.count, "image");
    const what = c ? (kind.deck ? [amount, c.summary] : [c.summary]) : [amount, nice(form.style)];
    ui.bar.summary([what[0], shapeLabel(form.shape), ...what.slice(1), Studio.withModel(modelLabel(form.model), tierModel(form.model, form.refs.length > 0)), form.brand].filter(Boolean).join(" · "));
  }

  async function generate() {
    const brief = form.brief.trim();
    if (!brief) { ui.bar.error(kind.empty); Studio.reveal(ui.brief, { focus: true }); return; }
    const { refs, brand, shape, model, count, style } = form;
    if (!tierModel(model, refs.length > 0)) { ui.bar.error(Studio.models().error || `config.yaml names no model for ${modelLabel(model)}.`); return; }
    if (kind.deck && slides().length && !confirm("Rewrite the whole deck from this brief? The slides are written again, with a new version of every slide; every version made so far is kept.")) return;
    const fields = { action: "generate", brief, refs: [...refs], brand, shape, model, count, style };
    if (kind.deck) fields.slide = null;
    if (await request(fields)) {
      refold();
      Studio.reveal(kind.deck ? ui.deck : ui.results);
    }
  }

  /* ---------- step 3: results ---------- */

  function stepResults() {
    ui.versions = h("div", { class: "versions" + (kind.deck ? " wide" : "") });
    ui.resultsHead = h("h2");
    ui.slideAsk = kind.deck ? h("div", { class: "slide-ask" }) : null;
    ui.results = h("section", { class: "card" }, ui.resultsHead, ui.slideAsk, ui.versions);
    renderResults();
    return stepFold(ui.results, "results", plural(versions().length, "version"));
  }

  /** Images a request makes (in a deck: of one slide). */
  function expected(req) {
    switch (req.action) {
      case "generate": return req.kind === "slide" ? req.count || 1 : CLAUDE_STYLES[req.style] ? AUTO_STYLES : req.count || 1;
      case "variations": return req.count || 3;
      case "other-styles": return (req.styles && req.styles.length) || AUTO_STYLES;
      case "change": return 1;
      default: return 0;
    }
  }

  function what(req) {
    if (req.action === "generate" && req.kind === "slide" && req.slide != null) return "in the deck's style";
    if (req.action === "generate") return styleCards()[req.style] ? styleCards()[req.style].label : nice(req.style);
    if (req.action === "change") return `edit of v${req.version}`;
    if (req.action === "variations") return `variation of v${req.version}`;
    if (req.action === "other-styles") return `v${req.version} in another style`;
    return "";
  }

  const maxVersion = () => Math.max(0, ...versions().map(v => v.n));

  function placeholders() {
    const cards = [];
    let next = maxVersion() + 1;
    if (!project) return cards;
    for (const p of pending(project.dir).filter(p => !kind.deck || p.request.slide === slide)) {
      const made = p.current && p.request.time ? versions().filter(v => new Date(v.created) >= new Date(p.request.time)).length : 0;
      for (let i = made; i < expected(p.request); i++) {
        const label = p.current ? `Generating v${next++}…` : "Waiting";
        cards.push(h("div", { class: "ver pending" },
          h("div", { class: "ph" }, p.current ? h("div", { class: "spin" }) : null, label),
          h("div", { class: "t" }, h("b", {}, p.current ? `v${next - 1}` : "queued"), h("span", {}, what(p.request))),
          i === made ? h("div", { class: "t" }, runStatus(p.request.id)) : null));
      }
    }
    return cards;
  }

  function renderResults() {
    const s = kind.deck ? slideOf(slide) : null;
    const chosen = s ? s.chosen : null;
    const cards = [...placeholders(), ...versions().map(v =>
      h("div", { class: "ver" + (v.n === chosen ? " chosen" : ""), onclick: () => Studio.openDetail(v) },
        h("img", { src: fileUrl(v.image), alt: "", loading: "lazy" }),
        v.n === chosen ? h("span", { class: "badge" }, "In the PowerPoint") : null,
        h("div", { class: "t" }, h("b", {}, `v${v.n}`), h("span", {}, versionStyle(v)), h("span", {}, when(v.created)))))];
    ui.versions.replaceChildren(...cards);
    ui.results.foldSummary?.(plural(versions().length, "version"));
    if (!kind.deck) {
      ui.resultsHead.replaceChildren(h("span", { class: "num" }, "3"), "Results",
        h("span", { class: "hint" }, "every version is kept; click one to open it and mark what to change"));
      ui.results.hidden = !cards.length;
      return;
    }
    renderSlideHead(s);
    ui.results.hidden = !project || slide == null;
    renderAssembly();
  }

  /* ---------- detail view ---------- */

  function versionInfo(v) {
    const rows = versionRows(v, shapeLabel);
    if (v.slide != null) rows.unshift(["Slide", slideName(slideOf(v.slide)) + (slideOf(v.slide)?.chosen === v.n ? " · in the PowerPoint" : "")]);
    return rows;
  }

  function detailActions(v) {
    const s = v.slide != null ? slideOf(v.slide) : null;
    return [
      ...(s && s.chosen !== v.n ? [{ label: "Use this version", run: () => choose(s, v.n) }] : []),
      ...editActions(v, () => {
        if (!form.refs.includes(v.image)) form.refs.push(v.image);
        renderRefs();
        Studio.reveal(ui.step1);
      }),
    ];
  }

  /** Text of a request in the Claude column. */
  function describe(req) {
    const deck = req.kind === "slide";
    const on = deck && req.slide != null ? `slide ${req.slide} ` : "";
    const styles = deck ? DECK_STYLES : CLAUDE_STYLES;
    switch (req.action) {
      case "generate": {
        const style = styles[req.style] ? styles[req.style].asked : nice(req.style);
        if (deck && req.slide == null) {
          const n = req.count ? plural(req.count, "slide") : "as many slides as you think best";
          return { text: `Make the deck · ${n} · ${style}\n${req.brief}` };
        }
        if (deck) return { text: `New version of slide ${req.slide} in the deck's style${req.brief ? "\n" + req.brief : ""}` };
        return { text: `Generate ${plural(expected(req), "image")} · ${shapeLabel(req.shape)} · ${style}\n${req.brief}` };
      }
      case "change": case "variations": case "other-styles": return describeEdit(req, on);
      case "assemble": {
        const used = Object.entries(req.versions || {}).map(([k, n]) => `${k}: v${n}`).join(", ");
        return { text: `Make the PowerPoint · ${assemblyLabel(req.assembly)}${used ? "\nSlides " + used : ""}` };
      }
      default: return null;
    }
  }

  /* ---------- deck: slides, the selected slide, the PowerPoint ---------- */

  const slideName = s => (s ? `${s.k}. ${s.title || "Untitled slide"}` : "");
  const chosenVersion = s => s.versions.find(v => v.n === s.chosen) || null;
  const deckPending = () => (project ? pending(project.dir) : []);
  /** Fields a request about one version carries: the version's slide in a deck. */
  const changeFields = v => (v.slide != null ? { slide: v.slide } : {});

  function stepDeck() {
    ui.slides = h("div", { class: "slides" });
    ui.deck = h("section", { class: "card" },
      h("h2", {}, h("span", { class: "num" }, "3"), "Slides",
        h("span", { class: "hint" }, "click a slide to see its versions, mark changes and choose the one that goes into the PowerPoint")),
      ui.slides);
    return stepFold(ui.deck, "deck", plural(slides().length, "slide"));
  }

  function stepAssembly() {
    ui.assemblyNum = h("span", { class: "num" }, "5");
    ui.assemblyChoice = seg(ASSEMBLY, "images", setAssembly);
    ui.assembleButton = h("button", { class: "primary", onclick: assemble }, "Make the PowerPoint");
    ui.assemblyNote = h("span", { class: "hint" });
    ui.decks = h("div", { class: "decks" });
    ui.assembly = h("section", { class: "card" },
      h("h2", {}, ui.assemblyNum, "Make the PowerPoint", h("span", { class: "hint" }, "from the chosen version of each slide")),
      h("div", { class: "assemble" }, ui.assemblyChoice, ui.assembleButton, ui.assemblyNote), ui.decks);
    return stepFold(ui.assembly, "assembly");
  }

  /** The list of slides, with a card for the deck's pending generate and one to add a slide. */
  function renderDeck() {
    if (!kind.deck) return;
    const list = slides();
    const making = deckPending().find(p => p.request.action === "generate" && p.request.slide == null);
    const thumb = s => {
      if (s.error) return h("div", { class: "ph err" }, "Cannot be read");
      const v = chosenVersion(s);
      if (v) return h("img", { src: fileUrl(v.image), alt: "", loading: "lazy" });
      const busy = deckPending().some(p => p.current && p.request.action === "generate" && (p.request.slide == null || p.request.slide === s.k));
      return h("div", { class: "ph" }, busy ? h("div", { class: "spin" }) : null, busy ? "Generating…" : "No image yet");
    };
    const cards = list.map(s => h("div", { class: "ver sl" + (s.k === slide ? " on" : ""), onclick: () => select(s.k) },
      thumb(s),
      h("div", { class: "t", title: s.error || null }, h("b", {}, slideName(s)), h("span", {}, s.error ? "not a directory of the deck" : plural(s.versions.length, "version")))));
    if (making) {
      cards.unshift(h("div", { class: "ver sl pending" },
        h("div", { class: "ph" }, making.current ? h("div", { class: "spin" }) : null,
          making.current ? (list.length ? "Rewriting the deck…" : "Writing the deck…") : "Waiting"),
        h("div", { class: "t" }, h("b", {}, list.length ? "Rewrite" : "New deck"), h("span", {}, what(making.request))),
        h("div", { class: "t" }, runStatus(making.request.id))));
    }
    if (list.length) {
      const k = list.length + 1;
      cards.push(h("div", { class: "ver sl add" + (slide === k ? " on" : ""), onclick: () => select(k) },
        h("div", { class: "ph" }, "+ Add a slide")));
    }
    ui.slides.replaceChildren(...cards);
    ui.deck.foldSummary?.(plural(list.length, "slide"));
    ui.deck.hidden = !cards.length;
  }

  /** The head of the results step for the selected slide, with the box for a new version of it. */
  function renderSlideHead(s) {
    const k = slide;
    const adding = k != null && !s;
    ui.resultsHead.replaceChildren(h("span", { class: "num" }, "4"), adding ? `New slide ${k}` : slideName(s),
      h("span", { class: "hint" }, adding ? "say what it should show; it is added to the deck"
        : "every version is kept; click one to open it, mark what to change or use it in the PowerPoint"));
    const key = `${k}:${adding}`;
    if (ui.slideAsk.dataset.key === key) return; // keep what the user is typing
    ui.slideAsk.dataset.key = key;
    const text = h("textarea", { placeholder: adding ? "What should the new slide show? For example: a closing slide with the three asks"
      : "Optional: what to change in this slide. Empty: a new version of the slide as it is" });
    const go = h("button", { class: "secondary" }, adding ? `Make slide ${k}` : `New version of slide ${k}`);
    go.onclick = async () => {
      const brief = text.value.trim();
      if (adding && !brief) { text.focus(); return; }
      const { refs, brand, shape, model } = form;
      go.disabled = true;
      try {
        // A slide is made in the deck's style ("auto"), whatever style step 2 shows.
        if (await request({ action: "generate", slide: k, brief, refs: [...refs], brand, shape, model, count: 1, style: "auto" })) text.value = "";
      } finally { go.disabled = false; }
    };
    ui.slideAsk.replaceChildren(text, go);
  }

  function renderAssembly() {
    if (!kind.deck || !ui.assembly) return;
    const list = slides(), decks = project && project.deck ? project.deck.decks : [];
    ui.assembly.hidden = !list.length;
    ui.assemblyNum.textContent = slide != null ? "5" : "4";
    ui.assemblyChoice.set((project && project.project.assembly) || "images");
    const missing = list.filter(s => s.chosen == null).map(s => s.k);
    ui.assembleButton.disabled = !!missing.length;
    ui.assemblyNote.textContent = missing.length ? `Slide ${missing.join(", ")} has no image yet.` : "";
    const rows = deckPending().filter(p => p.request.action === "assemble").map(p =>
      h("div", { class: "deckrow pending" }, p.current ? h("div", { class: "spin" }) : null,
        h("b", {}, p.current ? "Making the PowerPoint…" : "Waiting"), h("span", {}, assemblyLabel(p.request.assembly)), runStatus(p.request.id)));
    rows.push(...decks.map(d => h("div", { class: "deckrow" },
      h("span", { class: "icon" }, Studio.icon("slide")), h("b", {}, `deck-${d.n}.pptx`), h("span", {}, assemblyLabel(d.assembly)),
      h("span", {}, d.versions ? Object.entries(d.versions).map(([k, n]) => `${k}: v${n}`).join(" · ") : ""),
      h("span", { class: "grow" }), h("span", {}, when(d.created)),
      h("button", { class: "secondary", onclick: () => download(d.path) }, "Download"))));
    ui.decks.replaceChildren(...rows);
    ui.assembly.foldSummary?.(decks.length ? plural(decks.length, "PowerPoint") : "none made yet");
  }

  function select(k) {
    slide = k;
    renderDeck();
    renderResults();
    refold();
    Studio.reveal(ui.results);
  }

  async function choose(s, n) {
    try {
      const { chosen } = await api.post("/api/chosen", { project: project.dir, slide: s.k, version: n });
      project.project.chosen = chosen;
      s.chosen = n;
      closeDetail();
      renderDeck();
      renderResults();
    } catch (e) { error(`Could not choose the version: ${e.message}`); }
  }

  async function setAssembly(value) {
    const before = project.project.assembly;
    project.project.assembly = value;
    try { await api.post("/api/assembly", { project: project.dir, assembly: value }); }
    catch (e) { project.project.assembly = before; renderAssembly(); error(`Could not change the PowerPoint choice: ${e.message}`); }
  }

  async function assemble() {
    const assembly = (project && project.project.assembly) || "images";
    if (await request({ action: "assemble", assembly })) renderAssembly();
  }

  /** Gives each version of a deck its slide number, so the detail view and its actions know the slide. */
  function adoptData(data) {
    for (const s of (data && data.deck ? data.deck.slides : [])) for (const v of s.versions) v.slide = s.k;
    return data;
  }

  /* ---------- module ---------- */

  function open(el, data, kindId) {
    kind = KINDS[kindId] || KINDS.image;
    project = adoptData(data);
    slide = null;
    const p = (data && data.project) || {}, s = p.settings || {};
    form = {
      brief: s.brief || p.brief || "", refs: [...(s.refs || [])], brand: s.brand || null,
      shape: kind.deck ? kind.shape : s.shape || kind.shape, model: MODELS.some(m => m[0] === s.model) ? s.model : "best",
      count: kind.deck ? s.count ?? null : s.count || 1, style: s.style || "auto",
    };
    ui.bar = Studio.actionBar({ label: kind.deck ? "Generate the deck" : "Generate", run: generate });
    if (kind.deck) {
      el.append(stepBrief(), stepStyle(), stepDeck(), stepResults(), stepAssembly());
      renderDeck();
      renderAssembly();
      // An open deck starts at its slides, below the long style picker.
    } else el.append(stepBrief(), stepStyle(), stepResults());
    refold();
    summary();
    if (!data) ui.brief.focus();
  }

  function update(data) {
    project = adoptData(data);
    if (kind.deck && slide != null && !slideOf(slide) && slide !== slides().length + 1) slide = null;
    renderDeck();
    renderResults();
    refold();
  }

  function onEvent(ev) {
    if (!form) return;
    if (["state", "request", "pending", "turn", "stopped"].includes(ev.kind)) { renderDeck(); renderResults(); refold(); }
  }

  const detailTitle = v => (v.slide != null ? `${(project.project || {}).name || ""} · slide ${v.slide} · v${v.n}` : null);

  const askPlaceholder = "Say what you want, in as much detail as you like. For example: the technician should look more relaxed, and the lab should have more natural light.";

  const tag = kindId => (KINDS[kindId] || KINDS.image).tag;

  Studio.register({ id: "images", tag, askPlaceholder, open, update, onEvent, describe, versionInfo, detailActions,
    changeFields, detailTitle });
})();
