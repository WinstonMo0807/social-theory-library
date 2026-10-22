/* Before hydration. Only non-sensitive appearance choices are persisted. */
(() => {
  let theme = "light", size = "standard", family = "sans";
  try {
    const saved = localStorage.getItem("library_theme");
    if (["light", "dark", "system"].includes(saved)) theme = saved;
    const text = localStorage.getItem("library_text_size");
    if (["standard", "comfortable", "large"].includes(text)) size = text;
    if (localStorage.getItem("library_font_family") === "serif") family = "serif";
  } catch { /* Disabled storage retains the PDF's paper appearance. */ }
  const root = document.documentElement;
  root.dataset.theme = theme === "dark" || (theme === "system" && matchMedia("(prefers-color-scheme: dark)").matches) ? "dark" : "light";
  root.dataset.themeChoice = theme;
  root.dataset.textSize = size;
  root.dataset.fontFamily = family;
})();
