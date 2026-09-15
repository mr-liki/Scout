// A plain fetch() with no timeout can hang until the tracker's own 20s
// outer race in trackers/index.ts kills it — and since searchAllTrackers
// uses Promise.allSettled, the WHOLE response waits on the slowest tracker.
// One rate-limited/hanging platform (any of them, not just LinkedIn) then
// adds up to 20s to every search. This bounds each individual request so a
// single bad platform fails fast instead of holding up the rest.
export async function fetchWithTimeout(
  url: string,
  init: RequestInit = {},
  timeoutMs = 8000
): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(url, { ...init, signal: controller.signal });
  } catch (err: any) {
    if (err?.name === "AbortError") {
      throw new Error(`Request timed out after ${timeoutMs}ms: ${url}`);
    }
    throw err;
  } finally {
    clearTimeout(timer);
  }
}
