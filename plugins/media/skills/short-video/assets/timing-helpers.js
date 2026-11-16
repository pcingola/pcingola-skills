(function () {
  var T = window.TIMING;
  // A world page (T.scenes) names the scene first: S("id", n). A scene page: S(n).
  var WORLD = Array.isArray(T.scenes);
  function norm(s) { return String(s).toLowerCase().replace(/[^a-z0-9]/g, ""); }
  function scene(id) {
    if (!WORLD) throw new Error("timing.js: ST/STE and scene ids exist only in a world page");
    for (var i = 0; i < T.scenes.length; i++) {
      if (T.scenes[i].id === id) return T.scenes[i];
    }
    throw new Error("timing.js: no scene \"" + id + "\" in this world");
  }
  function sentence(sentences, n) {
    for (var i = 0; i < sentences.length; i++) {
      if (sentences[i].index === n) return sentences[i];
    }
    throw new Error("timing.js: no sentence " + n + " (scene has " + sentences.length + ")");
  }
  function word(s, w, k) {
    if (k === undefined) k = 1;
    var want = norm(w), seen = 0;
    for (var i = 0; i < s.words.length; i++) {
      if (norm(s.words[i].text) === want && ++seen === k) return s.words[i];
    }
    throw new Error("timing.js: word \"" + w + "\" #" + k + " not in sentence " + s.index + ": " + s.text);
  }
  // args: (n, ...) in a scene page, ("id", n, ...) in a world page.
  function pick(args) {
    if (WORLD) {
      if (typeof args[0] !== "string") throw new Error("timing.js: a world page names the scene first, S(\"id\", n)");
      return { s: sentence(scene(args[0]).sentences, args[1]), rest: Array.prototype.slice.call(args, 2) };
    }
    return { s: sentence(T.sentences, args[0]), rest: Array.prototype.slice.call(args, 1) };
  }
  window.S = function () { return pick(arguments).s.start; };
  window.SE = function () { return pick(arguments).s.end; };
  window.W = function () { var p = pick(arguments); return word(p.s, p.rest[0], p.rest[1]).start; };
  window.WE = function () { var p = pick(arguments); return word(p.s, p.rest[0], p.rest[1]).end; };
  window.ST = function (id) { return scene(id).start; };
  window.STE = function (id) { return scene(id).end; };
})();
