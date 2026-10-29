/* Presentation trials stay in this tab; account reading preferences are unchanged. */
(function () {
  function applyTypeset() {
    var params = new URLSearchParams(window.location.hash.slice(1));
    var selected = params.get("typography");
    var face = params.get("font");
    var mode = selected === "B" ? "B" : "A";
    var font = /^(balanced|song|sans|wenkai)$/.test(face || "") ? face : null;
    try {
      // A is the user's chosen edition. Old B trial preferences must not override it.
      if (selected === "A" || selected === "B") sessionStorage.setItem("stl-typeset-20261029", selected);
      mode = sessionStorage.getItem("stl-typeset-20261029") === "B" ? "B" : "A";
      if (font) sessionStorage.setItem("stl-font-trial", font);
      font = font || sessionStorage.getItem("stl-font-trial");
    } catch (_) { /* The URL still works when tab storage is unavailable. */ }
    document.documentElement.dataset.typeset = mode;
    document.documentElement.dataset.typeface = /^(song|sans|wenkai)$/.test(font || "") ? font : "balanced";
  }
  applyTypeset();
  window.addEventListener("hashchange", applyTypeset);
})();
