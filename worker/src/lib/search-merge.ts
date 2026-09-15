import type { Job } from "../types";

/**
 * Interleave jobs round-robin by source so platforms are mixed, not grouped.
 */
export function interleaveBySource(jobs: Job[]): Job[] {
  const groups: Record<string, Job[]> = {};
  for (const j of jobs) {
    const src = j.source || "unknown";
    if (!groups[src]) groups[src] = [];
    groups[src].push(j);
  }

  const sources = Object.keys(groups);
  const maxLen = Math.max(...sources.map((s) => groups[s].length));
  const mixed: Job[] = [];

  for (let i = 0; i < maxLen; i++) {
    for (const src of sources) {
      if (groups[src][i]) mixed.push(groups[src][i]);
    }
  }

  return mixed;
}

/**
 * Build a stable job ID from source + key fields.
 */
export function makeJobId(source: string, title: string, company: string, link: string): string {
  const seed = `${source}|${title}|${company}|${link}`;
  // Simple FNV-1a hash for deterministic IDs
  let hash = 0x811c9dc5;
  for (let i = 0; i < seed.length; i++) {
    hash ^= seed.charCodeAt(i);
    hash = Math.imul(hash, 0x01000193);
  }
  return (hash >>> 0).toString(36).padStart(8, "0");
}
