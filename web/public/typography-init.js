/* A/B is a per-tab presentation preference; it never changes account settings. */
(function () {
  function applyTypeset() {
  var selected = /^#typography=([AB])$/.exec(window.location.hash);
  selected = selected ? selected[1] : null;
  var mode = "B";
  try {
    if (selected === "A" || selected === "B") sessionStorage.setItem("stl-typography", selected);
    mode = sessionStorage.getItem("stl-typography") === "A" ? "A" : "B";
  } catch (_) {
    mode = selected === "A" ? "A" : "B";
  }
  document.documentElement.dataset.typeset = mode;
  }
  applyTypeset();
  window.addEventListener("hashchange", applyTypeset);
})();
