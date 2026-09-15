import puppeteer, { type Browser } from "@cloudflare/puppeteer";
import type { Env } from "../types";

// The account's Browser Rendering concurrency is effectively one session at
// a time. LinkedIn and Foundit both want Browser Rendering to get past an
// IP-based block (see their tracker files) — if each independently calls
// puppeteer.launch(), they race for that single slot every request and one
// of them (or both) loses. A browser can host multiple pages at once with
// no extra concurrency cost, so the fix is one shared launch per search
// request, handed out to whichever trackers need it.
//
// Safe to hold as a per-request closure (not module-level state): Workers
// can multiplex concurrent requests on one isolate, so a module-level
// singleton would leak a browser session across unrelated requests. This
// is created fresh inside searchAllTrackers for each call.
export function createSharedBrowser(env: Env) {
  let launchPromise: Promise<Browser> | null = null;

  return {
    get: (): Promise<Browser> => {
      if (!launchPromise) launchPromise = puppeteer.launch(env.BROWSER);
      return launchPromise;
    },
    close: async (): Promise<void> => {
      if (!launchPromise) return;
      try {
        const browser = await launchPromise;
        await browser.close();
      } catch {
        // Already closed, failed to launch, or the connection dropped —
        // nothing more to clean up.
      }
    },
  };
}

export type SharedBrowser = ReturnType<typeof createSharedBrowser>;
