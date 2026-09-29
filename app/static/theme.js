"use strict";
// The theme chosen in Definições ("light" / "dark"; none: follow the system), set before the page
// is painted so it never flashes the other theme. Loaded without defer, before the stylesheet.
try {
  const theme = localStorage.getItem("pdf-to-gp5.theme");
  if (theme === "light" || theme === "dark") document.documentElement.dataset.theme = theme;
} catch {
  // storage blocked: follow the system
}
