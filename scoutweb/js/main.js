/**
 * main.js — SCOUT Jobs entry point.
 * Boots the theme, binds global events, and starts the hash router.
 */

import { router, setState, bindGlobalEvents, updateSavedCount } from "./ui.js";
import { saveTheme, loadTheme } from "./store.js";
import { probeApi } from "./api.js";

// Theme first (avoid flash)
saveTheme(loadTheme());

// Router + state
setState({});
window.addEventListener("hashchange", router);

// Bootstrap
document.addEventListener("DOMContentLoaded", () => {
  bindGlobalEvents();
  updateSavedCount();
  router();

  // Probe the live API (flips the demo banner if unreachable)
  probeApi().then((live) => {
    // Only manage the banner when we're NOT on the results page — the results
    // renderer owns its banner state. This ensures no flicker on load.
    if (!location.hash.startsWith("#/search")) {
      document.getElementById("demoBanner").hidden = live;
    }
  });
});
