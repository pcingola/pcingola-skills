(function () {
  var T = window.TIMING;
  function norm(s) { return String(s).toLowerCase().replace(/[^a-z0-9]/g, ""); }
  function sentence(n) {
    for (var i = 0; i < T.sentences.length; i++) {
      if (T.sentences[i].index === n) return T.sentences[i];
    }
    throw new Error("timing.js: no sentence " + n + " (scene has " + T.sentences.length + ")");
  }
  function word(n, w, k) {
    if (k === undefined) k = 1;
    var s = sentence(n), want = norm(w), seen = 0;
    for (var i = 0; i < s.words.length; i++) {
      if (norm(s.words[i].text) === want && ++seen === k) return s.words[i];
    }
    throw new Error("timing.js: word \"" + w + "\" #" + k + " not in sentence " + n + ": " + s.text);
  }
  window.S = function (n) { return sentence(n).start; };
  window.SE = function (n) { return sentence(n).end; };
  window.W = function (n, w, k) { return word(n, w, k).start; };
  window.WE = function (n, w, k) { return word(n, w, k).end; };
})();
