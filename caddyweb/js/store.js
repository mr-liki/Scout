/**
 * store.js — client-side persistence for CADDY Jobs.
 * Saved jobs + theme preference live in localStorage (no backend needed).
 */

const SAVED_KEY = "caddyjobs.saved";
const THEME_KEY = "caddyjobs.theme";

/** Load saved jobs (each is the full job object). */
export function loadSaved() {
  try {
    return JSON.parse(localStorage.getItem(SAVED_KEY) || "[]");
  } catch {
    return [];
  }
}

function persistSaved(jobs) {
  localStorage.setItem(SAVED_KEY, JSON.stringify(jobs));
}

export function isSaved(id) {
  return loadSaved().some((j) => j.id === id);
}

export function toggleSaved(job) {
  const saved = loadSaved();
  const idx = saved.findIndex((j) => j.id === job.id);
  let nowSaved = true;
  if (idx >= 0) {
    saved.splice(idx, 1);
    nowSaved = false;
  } else {
    saved.unshift(job);
  }
  persistSaved(saved);
  return nowSaved;
}

export function removeSaved(id) {
  persistSaved(loadSaved().filter((j) => j.id !== id));
}

/* ---------------- Theme ---------------- */

export function loadTheme() {
  return localStorage.getItem(THEME_KEY) || "dark";
}

export function saveTheme(theme) {
  localStorage.setItem(THEME_KEY, theme);
  document.documentElement.setAttribute("data-theme", theme);
}
