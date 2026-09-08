/**
 * ui.js — Templates + rendering + routing for SCOUT Jobs.
 * Updated for production async search polling.
 */

import * as store from "./store.js";
import { searchJobs as apiSearchJobs, createLinkedInSearch, resumeSearch, fetchLinkedInDetail } from "./api.js";

const PLATFORMS = ["LinkedIn", "Indeed", "Glassdoor", "Wellfound"];
const PLAT_CLASS = { LinkedIn: "li", Indeed: "in", Glassdoor: "gd", Wellfound: "wf" };

export const svg = {
  search: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="11" cy="11" r="7"/><path d="m21 21-4.3-4.3"/></svg>',
  pin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 0 1 16 0z"/><circle cx="12" cy="10" r="3"/></svg>',
  clock: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v5l3 3"/></svg>',
  coin: '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><circle cx="12" cy="12" r="9"/><path d="M12 7v10M9.5 9.5h4a1.5 1.5 0 0 1 0 3h-3a1.5 1.5 0 0 0 0 3h4"/></svg>',
};

function esc(s) {
  return String(s ?? "")
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
}

function platClass(src) {
  return PLAT_CLASS[src] || "li";
}

function timeAgo(dateStr) {
  if (!dateStr) return "";
  const t = new Date(dateStr).getTime();
  if (isNaN(t)) return dateStr;
  const days = Math.floor((Date.now() - t) / 86400000);
  if (days <= 0) return "Today";
  if (days === 1) return "1d ago";
  if (days < 30) return `${days}d ago`;
  const months = Math.floor(days / 30);
  return `${months}mo ago`;
}

/* ============================================================
   Shared components
   ============================================================ */

export function jobCard(job, opts = {}) {
  const saved = store.isSaved(job.id);
  const badges = [];
  if (job.early_applicant) badges.push('<span class="job-tag tag-early">🔥 Early applicant</span>');
  if (job.easy_apply) badges.push('<span class="job-tag tag-easy">⚡ Easy apply</span>');
  if (job.remote) badges.push('<span class="job-tag tag-remote">🌍 Remote</span>');
  const initials = (job.company || "?").slice(0, 2).toUpperCase();
  return `
  <article class="job-card plat-${platClass(job.source)}" data-id="${esc(job.id)}" data-role="card">
    <span class="job-source">${esc(job.source)}</span>
    <div class="job-card-top">
      <div class="job-avatar">${esc(initials)}</div>
      <div>
        <h3 class="job-title">${esc(job.title)}</h3>
        <div class="job-company">${esc(job.company)}</div>
      </div>
    </div>
    ${badges.length ? `<div class="job-badges">${badges.join("")}</div>` : ""}
    <div class="job-meta">
      ${job.location ? `<span>${svg.pin} ${esc(job.location)}</span>` : ""}
      ${job.salary ? `<span class="job-salary">${svg.coin} ${esc(job.salary)}</span>` : ""}
      ${job.posted_date ? `<span>${svg.clock} ${esc(timeAgo(job.posted_date))}</span>` : ""}
    </div>
    <div class="job-card-foot">
      <span class="job-date">${esc(job.source)}</span>
      <button class="job-save ${saved ? "saved" : ""}" data-action="save" data-id="${esc(job.id)}">
        ${saved ? "✓ Saved" : "☆ Save"}
      </button>
      <button class="job-open" data-action="open" data-id="${esc(job.id)}">View job →</button>
    </div>
  </article>`;
}

function skeletonCard() {
  return `
  <article class="job-card" aria-hidden="true">
    <div class="job-card-top">
      <div class="skeleton" style="width:46px;height:46px;border-radius:12px"></div>
      <div style="flex:1">
        <div class="skeleton" style="width:70%;height:18px;margin-bottom:8px"></div>
        <div class="skeleton" style="width:40%;height:14px"></div>
      </div>
    </div>
    <div class="skeleton" style="width:60%;height:13px;margin-top:14px"></div>
    <div class="skeleton" style="width:85%;height:13px;margin-top:8px"></div>
  </article>`;
}

export function toast(msg, kind = "ok") {
  const root = document.getElementById("toastRoot");
  const el = document.createElement("div");
  el.className = `toast ${kind}`;
  el.textContent = msg;
  root.appendChild(el);
  setTimeout(() => {
    el.classList.add("out");
    setTimeout(() => el.remove(), 320);
  }, 2600);
}

/* ============================================================
   Router
   ============================================================ */

let state = null;

export function setState(s) {
  state = s;
}

export function router() {
  const hash = location.hash || "#/";
  const [path, query] = hash.slice(1).split("?");
  const params = new URLSearchParams(query || "");
  switch (path) {
    case "/saved":
      renderSaved();
      break;
    case "/about":
      renderAbout();
      break;
    case "/search":
      renderResults(params.get("q") || "", params.get("location") || "");
      break;
    default:
      renderHome();
  }
  document.querySelectorAll(".nav-link").forEach((a) => {
    a.classList.toggle("active", a.dataset.route === (path || "/"));
  });
}

/* ============================================================
   Home
   ============================================================ */
function renderHome() {
  const app = document.getElementById("app");
  app.innerHTML = `
  <section class="hero">
    <span class="hero-eyebrow">🚀 4 job boards · 1 search · 100% free</span>
    <h1>Every job board.<br /><span class="grad">One search.</span></h1>
    <p class="hero-sub">Search LinkedIn, Indeed, Glassdoor and Wellfound at once — no accounts, no API keys, no paywalls.</p>
    <div class="search-wrap">
      <form class="search-form" id="heroForm">
        <div class="search-input-wrap">
          ${svg.search}
          <input class="search-input" id="heroKeywords" placeholder="Job title, skill, or keyword…" autocomplete="off" />
        </div>
        <div class="search-loc">
          ${svg.pin}
          <input class="search-input" id="heroLocation" placeholder="Location (optional)" autocomplete="off" />
        </div>
        <button class="btn btn-primary search-btn" type="submit">Search</button>
      </form>
    </div>
    <div class="popular" id="popularChips">
      <span class="popular-label">Popular:</span>
      <button class="chip" data-q="Python Developer">Python Developer</button>
      <button class="chip" data-q="Data Scientist">Data Scientist</button>
      <button class="chip" data-q="AI Engineer">AI Engineer</button>
      <button class="chip" data-q="DevOps Engineer">DevOps Engineer</button>
    </div>
    <div class="platform-strip">
      <span class="plat-tile li"><span class="dot"></span>LinkedIn</span>
      <span class="plat-tile in"><span class="dot"></span>Indeed</span>
      <span class="plat-tile gd"><span class="dot"></span>Glassdoor</span>
      <span class="plat-tile wf"><span class="dot"></span>Wellfound</span>
    </div>
  </section>

  <section class="section">
    <div class="section-head">
      <h2>Why SCOUT Jobs?</h2>
      <p>One interface over the four biggest job sources — built to be fast, honest and free.</p>
    </div>
    <div class="feature-grid">
      <div class="feature-card"><div class="feature-ico">⚡</div><h3>Real-time merged results</h3><p>Every search hits all platforms in parallel and merges the best matches — tagged by source.</p></div>
      <div class="feature-card"><div class="feature-ico">🔎</div><h3>No accounts, ever</h3><p>Search instantly. No sign-up, no resume upload, no recruiter spam. Just results.</p></div>
      <div class="feature-card"><div class="feature-ico">💰</div><h3>Salary signals</h3><p>Glassdoor and Wellfound include pay estimates and equity ranges where available.</p></div>
      <div class="feature-card"><div class="feature-ico">🔥</div><h3>Early-applicant alerts</h3><p>Spot low-competition postings and beat the crowd before everyone else applies.</p></div>
      <div class="feature-card"><div class="feature-ico">📌</div><h3>Saved jobs</h3><p>Bookmark roles locally in your browser — they persist between sessions.</p></div>
      <div class="feature-card"><div class="feature-ico">🌙</div><h3>Dark mode &amp; mobile</h3><p>Built responsive with a light/dark theme that remembers your preference.</p></div>
    </div>
  </section>

  <section class="section" style="padding-top:0">
    <div class="section-head">
      <h2>Four platforms, one feed</h2>
      <p>Each source covers a different slice of the market.</p>
    </div>
    <div class="platform-grid">
      <div class="platform-card li"><div class="pname"><span class="dot" style="width:12px;height:12px;border-radius:50%;background:var(--plat)"></span>LinkedIn</div><p class="pdesc">The biggest professional network — millions of roles with early-applicant signals.</p><span class="pbadge">Broadest coverage</span></div>
      <div class="platform-card in"><div class="pname"><span class="dot" style="width:12px;height:12px;border-radius:50%;background:var(--plat)"></span>Indeed</div><p class="pdesc">The world's largest job site — huge volume, easy apply, global postings.</p><span class="pbadge">Huge volume</span></div>
      <div class="platform-card gd"><div class="pname"><span class="dot" style="width:12px;height:12px;border-radius:50%;background:var(--plat)"></span>Glassdoor</div><p class="pdesc">Company reviews plus jobs — with salary estimates attached to listings.</p><span class="pbadge">Salary estimates</span></div>
      <div class="platform-card wf"><div class="pname"><span class="dot" style="width:12px;height:12px;border-radius:50%;background:var(--plat)"></span>Wellfound</div><p class="pdesc">Startup jobs with equity — early-stage companies that skip the big boards.</p><span class="pbadge">Startups &amp; equity</span></div>
    </div>
  </section>

  <div class="cta-band">
    <div class="cta-box">
      <h2>Find your next role.</h2>
      <p>Type a job title above and search all four platforms at once.</p>
      <button class="btn btn-primary" id="ctaSearch">Start searching</button>
    </div>
  </div>`;

  const form = document.getElementById("heroForm");
  form.addEventListener("submit", (e) => {
    e.preventDefault();
    goSearch(document.getElementById("heroKeywords").value, document.getElementById("heroLocation").value);
  });
  document.querySelectorAll(".chip").forEach((c) => {
    c.addEventListener("click", () => goSearch(c.dataset.q, ""));
  });
  document.getElementById("ctaSearch").addEventListener("click", () => {
    document.getElementById("heroKeywords").focus();
    document.getElementById("heroKeywords").scrollIntoView({ behavior: "smooth", block: "center" });
  });
}

/* ============================================================
   Results (with async polling support)
   ============================================================ */
let currentJobs = [];
let currentState = null;
let pollInterval = null;

async function renderResults(q, location) {
  const app = document.getElementById("app");
  app.innerHTML = `
  <div class="results-wrap">
    <div class="results-topbar">
      <h1 class="results-title">Jobs for <span class="q">${esc(q || "…")}</span></h1>
      <span class="results-meta" id="resMeta">Searching…</span>
    </div>
    <div class="results-layout">
      <aside class="filters" id="filters">
        <h4>Filters</h4>
        <div class="filter-group">
          <label class="filter-opt"><input type="checkbox" id="fEarly" /> 🔥 Early applicants only</label>
          <label class="filter-opt"><input type="checkbox" id="fRemote" /> 🌍 Remote only</label>
        </div>

        <h4>LinkedIn Options</h4>
        <div class="filter-group">
          <label class="filter-label">Posted within</label>
          <select class="sort-select" id="fFreshness" style="width:100%">
            <option value="">Any time</option>
            <option value="5m">Last 5 minutes</option>
            <option value="10m">Last 10 minutes</option>
            <option value="30m">Last 30 minutes</option>
            <option value="1h">Last 1 hour</option>
            <option value="24h">Last 24 hours</option>
            <option value="7d">Last 7 days</option>
          </select>
          <label class="filter-opt"><input type="checkbox" id="fUnder10" /> 🔥 Under 10 applicants</label>
          <label class="filter-opt"><input type="checkbox" id="fEasyApply" /> ⚡ Easy Apply</label>
        </div>

        <h4>Sources</h4>
        <div class="filter-group" id="srcFilters">
          ${PLATFORMS.map((p) => `<label class="filter-opt"><input type="checkbox" data-src="${p}" checked /> ${p}</label>`).join("")}
        </div>
        <h4>Sort</h4>
        <select class="sort-select" id="sortSel" style="width:100%">
          <option value="relevance">Relevance</option>
          <option value="newest">Newest first</option>
          <option value="company">Company A–Z</option>
        </select>
      </aside>
      <div>
        <div class="results-toolbar">
          <div class="source-filter-group" id="srcChips">
            ${PLATFORMS.map((p) => `<span class="src-chip plat-${platClass(p)} on" data-chip="${p}"><span class="dot"></span>${p}</span>`).join("")}
          </div>
        </div>
        <div class="job-list" id="jobList">
          ${skeletonCard()}${skeletonCard()}${skeletonCard()}${skeletonCard()}${skeletonCard()}${skeletonCard()}
        </div>
        <div class="load-more-wrap" id="loadMoreWrap" hidden>
          <button class="btn btn-ghost" id="loadMoreBtn">Load more jobs</button>
        </div>
        <div id="linkedinStatus" class="linkedin-status" hidden></div>
        <div id="resumeWrap" class="resume-wrap" hidden>
          <button class="btn btn-primary" id="resumeBtn">Resume search</button>
        </div>
      </div>
    </div>
  </div>`;

  wireFilters();
  currentState = { q, location, searchId: null };
  currentJobs = [];

  // Clean up any previous poll interval
  if (pollInterval) {
    clearInterval(pollInterval);
    pollInterval = null;
  }

  const freshness = document.getElementById("fFreshness").value;
  const under10 = document.getElementById("fUnder10").checked;
  const easyApply = document.getElementById("fEasyApply").checked;

  // Always use the production async search (POST /api/v1/searches) -- it
  // already probes the API and falls back to demo mode on its own when the
  // backend isn't reachable. The legacy GET /api/search path this used to
  // gate on for a plain search has no route in the production FastAPI app,
  // so it always 404ed and silently landed on fake demo data.
  await startAsyncSearch(q, location, {
    posted_within: freshness || undefined,
    under_10: under10,
    easy_apply: easyApply,
    sort: "newest",
    limit: 10,
  });
}

async function startAsyncSearch(q, location, options) {
  const statusEl = document.getElementById("linkedinStatus");
  const resumeWrap = document.getElementById("resumeWrap");

  try {
    const { search_id, poll_fn, initial_status, demo } = await createLinkedInSearch({
      keywords: q,
      location: location,
      ...options,
    });

    if (demo) {
      // Fall back to demo
      document.getElementById("demoBanner").hidden = false;
      const { result } = await apiSearchJobs(q, location);
      currentJobs = result.jobs || [];
      currentState.result = result;
      renderJobList();
      return;
    }

    if (!search_id) {
      statusEl.hidden = false;
      statusEl.innerHTML = '<div class="status-failed">❌ Failed to start search</div>';
      return;
    }

    currentState.searchId = search_id;
    document.getElementById("resMeta").textContent = "Searching LinkedIn…";

    // Start polling
    pollInterval = setInterval(async () => {
      const data = await poll_fn();
      if (!data) return;

      // Update jobs progressively
      if (data.jobs && data.jobs.length > currentJobs.length) {
        currentJobs = data.jobs;
        renderJobList();
      }

      // Update status
      if (data.status === "success" || data.status === "partial" || data.status === "failed") {
        clearInterval(pollInterval);
        pollInterval = null;

        currentState.result = {
          jobs: data.jobs,
          total: data.total_jobs,
          search_status: data.status,
        };

        document.getElementById("resMeta").textContent = `${data.total_jobs} jobs found · ${data.status}`;

        if (data.status === "partial") {
          statusEl.hidden = false;
          statusEl.innerHTML = '<div class="status-partial">⚠️ Partial results — some jobs may be missing due to rate limiting.</div>';
        }

        if (data.resume?.available) {
          resumeWrap.hidden = false;
          document.getElementById("resumeBtn").onclick = async () => {
            resumeWrap.hidden = true;
            statusEl.innerHTML = '<div class="status-partial">🔄 Resuming search…</div>';
            statusEl.hidden = false;
            await startAsyncSearch(q, location, { ...options, start: data.resume.start });
          };
        }
      }
    }, 1000);
  } catch (e) {
    statusEl.hidden = false;
    statusEl.innerHTML = `<div class="status-failed">❌ Search error: ${esc(e.message)}</div>`;
  }
}

function wireFilters() {
  const onFilter = () => renderJobList();

  ["fEarly", "fRemote"].forEach((id) => {
    document.getElementById(id).addEventListener("change", onFilter);
  });

  const linkedinFilterIds = ["fFreshness", "fUnder10", "fEasyApply"];
  linkedinFilterIds.forEach((id) => {
    const el = document.getElementById(id);
    if (el) {
      el.addEventListener("change", () => {
        const { q, location } = currentState || {};
        if (q) renderResults(q, location || "");
      });
    }
  });

  document.querySelectorAll("#srcFilters input").forEach((el) => {
    el.addEventListener("change", () => {
      const chip = document.querySelector(`.src-chip[data-chip="${el.dataset.src}"]`);
      chip.classList.toggle("on", el.checked);
      renderJobList();
    });
  });
  document.querySelectorAll("#srcChips .src-chip").forEach((chip) => {
    chip.addEventListener("click", () => {
      chip.classList.toggle("on");
      const cb = document.querySelector(`#srcFilters input[data-src="${chip.dataset.chip}"]`);
      cb.checked = chip.classList.contains("on");
      renderJobList();
    });
  });
  document.getElementById("sortSel").addEventListener("change", renderJobList);
  document.getElementById("loadMoreBtn").addEventListener("click", () => {
    document.getElementById("jobList").dataset.limit =
      Number(document.getElementById("jobList").dataset.limit || 8) + 8;
    renderJobList();
  });
}

function renderJobList() {
  const list = document.getElementById("jobList");
  if (!list) return;
  const res = currentState?.result;
  if (!res) return;

  const fEarly = document.getElementById("fEarly").checked;
  const fRemote = document.getElementById("fRemote").checked;
  const activeSrcs = [...document.querySelectorAll("#srcFilters input:checked")].map((i) => i.dataset.src);
  const sort = document.getElementById("sortSel").value;
  const limit = Number(list.dataset.limit || 8);

  let jobs = currentJobs.filter(
    (j) => activeSrcs.includes(j.source) && (!fEarly || j.early_applicant) && (!fRemote || j.remote)
  );
  if (sort === "newest") jobs = [...jobs].sort((a, b) => (b.posted_date || "").localeCompare(a.posted_date || ""));
  if (sort === "company") jobs = [...jobs].sort((a, b) => (a.company || "").localeCompare(b.company || ""));

  const shown = jobs.slice(0, limit);
  const meta = document.getElementById("resMeta");
  const platCounts = Object.entries(res.platforms || {})
    .filter(([, n]) => n > 0)
    .map(([p, n]) => `${n} ${p}`)
    .join(" + ");

  if (!shown.length) {
    meta.textContent = "No matches with current filters.";
    list.innerHTML = `
      <div class="state-box"><div class="state-ico">🔍</div>
      <h3>No jobs found</h3><p>Try different keywords, a broader location, or clear the filters.</p>
      <button class="btn btn-primary" onclick="location.hash='#/'">New search</button></div>`;
    document.getElementById("loadMoreWrap").hidden = true;
    return;
  }

  const total = res.total || res.total_jobs || jobs.length;
  meta.textContent = `${total} job${total !== 1 ? "s" : ""} found · ${platCounts || res.search_status || ""}`;
  list.innerHTML = shown.map((j) => jobCard(j)).join("");
  document.getElementById("loadMoreWrap").hidden = jobs.length <= shown.length;

  list.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const job = currentJobs.find((j) => j.id === id);
      if (!job) return;
      if (btn.dataset.action === "open") openModal(job);
      if (btn.dataset.action === "save") {
        const saved = store.toggleSaved(job);
        btn.textContent = saved ? "✓ Saved" : "☆ Save";
        btn.classList.toggle("saved", saved);
        toast(saved ? "Saved to your list" : "Removed from saved", saved ? "ok" : "warn");
        updateSavedCount();
      }
    });
  });
}

/* ============================================================
   Job detail modal (with lazy LinkedIn detail loading)
   ============================================================ */
async function openModal(job) {
  const saved = store.isSaved(job.id);
  const badges = [];
  if (job.early_applicant) badges.push('<span class="job-tag tag-early">🔥 Early applicant</span>');
  if (job.easy_apply) badges.push('<span class="job-tag tag-easy">⚡ Easy apply</span>');
  if (job.remote) badges.push('<span class="job-tag tag-remote">🌍 Remote</span>');
  const link = job.link || job.url || "#";
  const isLinkedIn = job.source === "LinkedIn";

  let linkedinJobId = null;
  if (isLinkedIn) {
    const providerId = job.provider_metadata?.provider_job_id;
    if (providerId && /^\d+$/.test(providerId)) {
      linkedinJobId = providerId;
    }
  }

  const root = document.getElementById("modalRoot");
  root.innerHTML = `
  <div class="modal-overlay" id="modalOverlay">
    <div class="modal" role="dialog" aria-modal="true">
      <button class="modal-close" id="modalClose" aria-label="Close">✕</button>
      <div class="modal-head">
        <span class="job-source" style="position:static;display:inline-block;margin-bottom:10px">${esc(job.source)}</span>
        <h2 class="modal-title">${esc(job.title)}</h2>
        <div class="modal-company">${esc(job.company)}</div>
      </div>
      <div class="modal-body">
        <div class="modal-meta">
          ${job.location ? `<span>📍 <b>${esc(job.location)}</b></span>` : ""}
          ${job.salary ? `<span>💰 <b>${esc(job.salary)}</b></span>` : ""}
          ${job.posted_date ? `<span>📅 <b>${esc(timeAgo(job.posted_date))}</b></span>` : ""}
        </div>
        ${badges.length ? `<div class="modal-badges">${badges.join("")}</div>` : ""}
        <div id="modalDesc">
          ${job.description
            ? `<div class="modal-desc">${esc(job.description)}</div>`
            : isLinkedIn && linkedinJobId
              ? `<div class="modal-desc modal-loading">Loading job details…</div>`
              : `<p class="modal-desc">Full description is available on ${esc(job.source)} — click the button below to open the original listing and apply.</p>`
          }
        </div>
        <div class="modal-foot">
          <a class="btn btn-primary" href="${esc(link)}" target="_blank" rel="noopener noreferrer">Apply on ${esc(job.source)} ↗</a>
          <button class="btn btn-ghost" id="modalSave">${saved ? "✓ Saved" : "☆ Save job"}</button>
        </div>
        <p class="modal-source">SCOUT Jobs aggregates listings — always verify and apply on the original site.</p>
      </div>
    </div>
  </div>`;

  if (linkedinJobId && !job.description) {
    fetchLinkedInDetail(linkedinJobId).then((detail) => {
      const descEl = document.getElementById("modalDesc");
      if (!descEl) return;
      if (detail && detail.description) {
        descEl.innerHTML = `<div class="modal-desc">${esc(detail.description)}</div>`;
        job.description = detail.description;
      } else {
        descEl.innerHTML = `<p class="modal-desc">Full description is available on ${esc(job.source)} — click the button below to open the original listing and apply.</p>`;
      }
    }).catch(() => {
      const descEl = document.getElementById("modalDesc");
      if (descEl) {
        descEl.innerHTML = `<p class="modal-desc">Full description is available on ${esc(job.source)} — click the button below to open the original listing and apply.</p>`;
      }
    });
  }

  const close = () => (root.innerHTML = "");
  document.getElementById("modalClose").addEventListener("click", close);
  document.getElementById("modalOverlay").addEventListener("click", (e) => {
    if (e.target.id === "modalOverlay") close();
  });
  document.addEventListener("keydown", function escKey(e) {
    if (e.key === "Escape") {
      close();
      document.removeEventListener("keydown", escKey);
    }
  });
  document.getElementById("modalSave").addEventListener("click", (e) => {
    const savedNow = store.toggleSaved(job);
    e.target.textContent = savedNow ? "✓ Saved" : "☆ Save job";
    toast(savedNow ? "Saved to your list" : "Removed from saved", savedNow ? "ok" : "warn");
    updateSavedCount();
  });
}

/* ============================================================
   Saved
   ============================================================ */
function renderSaved() {
  const app = document.getElementById("app");
  const saved = store.loadSaved();
  if (!saved.length) {
    app.innerHTML = `
      <div class="saved-empty">
        <div class="big">📌</div>
        <h2>Nothing saved yet</h2>
        <p style="color:var(--text-2);margin:10px 0 24px">Tap the ☆ on any job to keep it here.</p>
        <a class="btn btn-primary" href="#/">Search jobs</a>
      </div>`;
    return;
  }
  app.innerHTML = `
    <div class="results-wrap">
      <div class="results-topbar">
        <h1 class="results-title">Saved jobs</h1>
        <span class="results-meta">${saved.length} saved · stored in your browser</span>
      </div>
      <div class="job-list" id="savedList">${saved.map((j) => jobCard(j)).join("")}</div>
    </div>`;
  const list = document.getElementById("savedList");
  list.querySelectorAll("[data-action]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopPropagation();
      const id = btn.dataset.id;
      const job = saved.find((j) => j.id === id);
      if (btn.dataset.action === "open") openModal(job);
      if (btn.dataset.action === "save") {
        store.removeSaved(id);
        toast("Removed from saved", "warn");
        updateSavedCount();
        renderSaved();
      }
    });
  });
}

/* ============================================================
   About
   ============================================================ */
function renderAbout() {
  const app = document.getElementById("app");
  app.innerHTML = `
    <div class="about-hero">
      <h1>How <span class="grad" style="background:linear-gradient(120deg,var(--primary),var(--accent));-webkit-background-clip:text;background-clip:text;color:transparent">SCOUT Jobs</span> works</h1>
      <p>One honest search across the web's biggest job boards — free, fast, and privacy-friendly.</p>
    </div>
    <div class="about-body">
      <h2>🔍 What it searches</h2>
      <p>Each query is sent to <b>LinkedIn, Indeed, Glassdoor and Wellfound</b> in parallel using free public sources — no API keys, no logins, no scraping fees. Results are merged, de-duplicated, and tagged with their source so you know where to apply.</p>

      <h2>LinkedIn Advanced Search</h2>
      <p>LinkedIn searches support additional filters: <b>Freshness</b> (posted within 5m/10m/30m/1h/24h/7d), <b>Under 10 applicants</b> (low competition), and <b>Easy Apply</b>. These use LinkedIn's public guest API with adaptive rate limiting.</p>

      <h2>🧠 The story</h2>
      <p>SCOUT started as a hacker-style terminal chatbot for job hunting. This web app is the productized version: the same search engines that powered the terminal, wrapped in a modern interface you can host for free and share with anyone.</p>

      <h2>🌍 How it's hosted (free)</h2>
      <ul>
        <li><b>Vercel</b> — recommended. Hosts the frontend + the Python API on the free hobby plan with zero config.</li>
        <li><b>Netlify</b> — equally easy, Python functions included.</li>
        <li><b>GitHub Pages</b> — static only; the site automatically falls back to demo data when the API isn't reachable.</li>
      </ul>

      <h2>🛡️ Privacy</h2>
      <p>Saved jobs live in <b>your browser</b> (localStorage). SCOUT Jobs has no database, no accounts, and no tracking — every search goes straight to the job sources.</p>

      <h2>⚖️ Honest limitations</h2>
      <ul>
        <li>Some sources (like Naukri) sit behind aggressive bot protection and aren't included.</li>
        <li>Indeed is scoped to the US index; Glassdoor is country-aware (India routes to glassdoor.co.in).</li>
        <li>Posting timestamps and salaries appear only where the source exposes them.</li>
        <li>LinkedIn uses approximate relative posting age ("5 minutes ago"), not exact timestamps.</li>
      </ul>
    </div>`;
}

/* ============================================================
   Helpers
   ============================================================ */

export function goSearch(q, loc) {
  const params = new URLSearchParams();
  if (q) params.set("q", q);
  if (loc) params.set("location", loc);
  window.location.hash = `#/search?${params}`;
  window.scrollTo({ top: 0 });
}

export function updateSavedCount() {
  const el = document.getElementById("savedCount");
  const n = store.loadSaved().length;
  el.hidden = n === 0;
  el.textContent = n;
}

export function bindGlobalEvents() {
  document.getElementById("themeToggle").addEventListener("click", () => {
    const next = document.documentElement.getAttribute("data-theme") === "dark" ? "light" : "dark";
    store.saveTheme(next);
  });
  document.getElementById("demoDismiss").addEventListener("click", () => {
    document.getElementById("demoBanner").hidden = true;
  });
}
