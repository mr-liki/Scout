/**
 * Sliding-window rate limiter backed by KV.
 * Returns { allowed: true } or { allowed: false, retryAfter: number }.
 */
export async function checkRateLimit(
  kv: KVNamespace,
  key: string,
  maxRequests: number,
  windowSeconds: number
): Promise<{ allowed: boolean; retryAfter?: number }> {
  const now = Date.now();
  const windowMs = windowSeconds * 1000;
  const windowStart = now - windowMs;

  const raw = await kv.get(`rl:${key}`, "json");
  const timestamps: number[] = raw || [];

  // Keep only timestamps within the current window
  const valid = timestamps.filter((t) => t > windowStart);

  if (valid.length >= maxRequests) {
    const oldest = valid[0];
    const retryAfter = Math.ceil((oldest + windowMs - now) / 1000);
    return { allowed: false, retryAfter: Math.max(1, retryAfter) };
  }

  valid.push(now);
  await kv.put(`rl:${key}`, JSON.stringify(valid), {
    expirationTtl: windowSeconds + 10,
  });

  return { allowed: true };
}
