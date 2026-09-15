import type { Env } from "../types";
import { searchAllTrackers } from "../trackers";
import { upsertJobs } from "../db/queries";
import { locationMatches } from "./city-aliases";

// Wellfound, Naukri, and Indeed are excluded here on purpose — Wellfound and
// Naukri are CAPTCHA-protected (not something this project scrapes around),
// and Indeed's working path is US/global only, not the India-focused search
// this notify feature is built for. See NAUKRI_SETUP.md / WELLFOUND_SETUP.md.
const NOTIFY_PLATFORMS = ["linkedin", "glassdoor", "foundit", "shine", "cutshort", "apna"];

// No platform in NOTIFY_PLATFORMS reports a real applicant count (see
// types.ts's TrackerJob.applicants — always null in practice), so "fewer
// than 10 applicants" is approximated with the early-applicant badge
// (LinkedIn's "among the first applicants" signal, Shine's own badge) —
// the closest real low-competition signal actually available. Glassdoor,
// Foundit, Cutshort, and Apna never set this flag, so jobs from those
// platforms won't trigger a notification even when the role is a fresh,
// otherwise-matching posting.
const EARLY_APPLICANT_ONLY = true;

// A single cron tick doesn't scan every subscriber's every keyword/location
// combo — Render's proxy instances and LinkedIn's Browser Rendering slot
// both have their own per-run budgets already (see glassdoor.ts,
// shared-browser.ts), and hitting them with a dozen combos every 5 minutes
// would just trade one platform's rate limit for another. Instead this
// rotates a few combos per run (tracked via a KV cursor) so everything
// gets covered over successive runs rather than all at once.
const MAX_PAIRS_PER_RUN = 3;
const FRESH_WINDOW_MINUTES = 7; // > the 5-min cron interval, so no gap between runs

interface SubscriptionRow {
  id: number;
  email: string;
  keywords: string;
  locations: string;
}

interface FreshJobRow {
  id: string;
  source: string;
  title: string;
  company: string | null;
  location: string | null;
  link: string | null;
}

export async function runNotifyScan(env: Env): Promise<void> {
  if (!env.EMAIL_WEBHOOK_URL) {
    console.log("[Notify] EMAIL_WEBHOOK_URL not set, skipping scan");
    return;
  }

  const subsResult = await env.DB.prepare(
    `SELECT id, email, keywords, locations FROM notify_subscriptions WHERE active = 1`
  ).all<SubscriptionRow>();
  const subs = subsResult.results || [];
  if (!subs.length) {
    console.log("[Notify] No active subscriptions");
    return;
  }

  const pairs = collectPairs(subs);
  if (!pairs.length) return;

  const runPairs = await pickRotation(env, pairs);

  for (const { keyword, location } of runPairs) {
    try {
      const { jobs } = await searchAllTrackers(keyword, location, env, NOTIFY_PLATFORMS);
      if (jobs.length) {
        await upsertJobs(env.DB, jobs);
        console.log(`[Notify] Scanned "${keyword}" / "${location}": ${jobs.length} jobs`);
      }
    } catch (e: any) {
      console.warn(`[Notify] Scan failed for "${keyword}" / "${location}": ${e.message}`);
    }
  }

  await matchAndSend(env, subs);
}

function collectPairs(subs: SubscriptionRow[]): { keyword: string; location: string }[] {
  const seen = new Map<string, { keyword: string; location: string }>();
  for (const sub of subs) {
    const keywords: string[] = safeParseArray(sub.keywords);
    const locations: string[] = safeParseArray(sub.locations);
    const locs = locations.length ? locations : [""];
    for (const kw of keywords) {
      for (const loc of locs) {
        const key = `${kw.toLowerCase()}::${loc.toLowerCase()}`;
        if (!seen.has(key)) seen.set(key, { keyword: kw, location: loc });
      }
    }
  }
  return [...seen.values()];
}

async function pickRotation(
  env: Env,
  pairs: { keyword: string; location: string }[]
): Promise<{ keyword: string; location: string }[]> {
  const cursorRaw = await env.KV.get("notify:scan:cursor");
  const cursor = cursorRaw ? parseInt(cursorRaw, 10) || 0 : 0;
  const count = Math.min(MAX_PAIRS_PER_RUN, pairs.length);
  const picked: { keyword: string; location: string }[] = [];
  for (let i = 0; i < count; i++) {
    picked.push(pairs[(cursor + i) % pairs.length]);
  }
  await env.KV.put("notify:scan:cursor", String((cursor + count) % pairs.length));
  return picked;
}

async function matchAndSend(env: Env, subs: SubscriptionRow[]): Promise<void> {
  const earlyApplicantClause = EARLY_APPLICANT_ONLY ? "AND early_applicant = 1" : "";
  const freshResult = await env.DB.prepare(
    `SELECT id, source, title, company, location, link FROM jobs
     WHERE first_seen_at > datetime('now', '-${FRESH_WINDOW_MINUTES} minutes')
       ${earlyApplicantClause}`
  ).all<FreshJobRow>();
  const freshJobs = freshResult.results || [];
  if (!freshJobs.length) return;

  for (const sub of subs) {
    const keywords: string[] = safeParseArray(sub.keywords);
    const locations: string[] = safeParseArray(sub.locations);
    if (!keywords.length) continue;

    const matches = freshJobs.filter((j) => {
      const titleLower = j.title.toLowerCase();
      if (!keywords.some((kw) => titleLower.includes(kw.toLowerCase()))) return false;
      if (!locations.length) return true;
      return locations.some((loc) => j.location && locationMatches(loc, j.location as string));
    });
    if (!matches.length) continue;

    const placeholders = matches.map(() => "?").join(",");
    const alreadySent = await env.DB.prepare(
      `SELECT job_id FROM notify_log WHERE subscription_id = ? AND job_id IN (${placeholders})`
    ).bind(sub.id, ...matches.map((m) => m.id)).all<{ job_id: string }>();
    const sentIds = new Set((alreadySent.results || []).map((r) => r.job_id));
    const toSend = matches.filter((m) => !sentIds.has(m.id));
    if (!toSend.length) continue;

    const ok = await sendNotifyEmail(env, sub.email, toSend);
    if (ok) {
      const logStmt = env.DB.prepare(`INSERT INTO notify_log (subscription_id, job_id) VALUES (?, ?)`);
      await env.DB.batch(toSend.map((j) => logStmt.bind(sub.id, j.id)));
      console.log(`[Notify] Sent ${toSend.length} job(s) to ${sub.email}`);
    }
  }
}

async function sendNotifyEmail(env: Env, to: string, jobs: FreshJobRow[]): Promise<boolean> {
  const jobRows = jobs
    .map((j) => {
      const linkHtml = j.link
        ? `<a href="${escHtml(j.link)}" style="color:#2563eb;text-decoration:none;font-weight:600">View Job &rarr;</a>`
        : "";
      return `
        <tr>
          <td style="padding:14px 0;border-bottom:1px solid #e5e7eb">
            <div style="font-size:16px;font-weight:700;color:#111827;margin-bottom:4px">${escHtml(j.title)}</div>
            <div style="font-size:14px;color:#6b7280;margin-bottom:2px">${escHtml(j.company || "Unknown")} &middot; ${escHtml(j.location || "Remote")}</div>
            <div style="font-size:13px;color:#9ca3af;margin-bottom:6px">Early applicant &middot; ${escHtml(j.source)}</div>
            ${linkHtml}
          </td>
        </tr>`;
    })
    .join("");

  const htmlBody = `
    <div style="font-family:system-ui,-apple-system,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <h2 style="color:#111827;font-size:20px;margin-bottom:8px">${jobs.length} new job${jobs.length > 1 ? "s" : ""} &mdash; be the first to apply!</h2>
      <p style="color:#6b7280;font-size:14px;margin-bottom:20px">Fresh postings flagged as early-applicant opportunities</p>
      <table style="width:100%;border-collapse:collapse">${jobRows}</table>
      <p style="color:#9ca3af;font-size:12px;margin-top:24px;text-align:center">
        You're receiving this because you subscribed to SCOUT Jobs notifications.
      </p>
    </div>`;

  try {
    const resp = await fetch(env.EMAIL_WEBHOOK_URL as string, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        to,
        subject: `${jobs.length} new job${jobs.length > 1 ? "s" : ""} — be the first to apply!`,
        htmlBody,
      }),
    });
    if (!resp.ok) {
      console.warn(`[Notify] Email webhook HTTP ${resp.status} for ${to}`);
      return false;
    }
    return true;
  } catch (e: any) {
    console.warn(`[Notify] Email send failed for ${to}: ${e.message}`);
    return false;
  }
}

function safeParseArray(raw: string): string[] {
  try {
    const v = JSON.parse(raw || "[]");
    return Array.isArray(v) ? v.filter(Boolean) : [];
  } catch {
    return [];
  }
}

function escHtml(s: string): string {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
