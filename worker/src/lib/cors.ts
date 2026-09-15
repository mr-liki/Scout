const DEFAULT_HEADERS = {
  "Access-Control-Allow-Methods": "GET, OPTIONS",
  "Access-Control-Allow-Headers": "Content-Type",
  "Access-Control-Max-Age": "86400",
};

export function corsHeaders(origin: string | null, allowedOrigins: string): Record<string, string> {
  const origins = allowedOrigins.split(",").map((o) => o.trim());
  const allowed = origin && origins.includes(origin) ? origin : origins[0] || "";

  return {
    ...DEFAULT_HEADERS,
    "Access-Control-Allow-Origin": allowed,
  };
}

export function handleOptions(request: Request, env: { ALLOWED_ORIGINS: string }): Response {
  const origin = request.headers.get("Origin");
  return new Response(null, {
    status: 204,
    headers: corsHeaders(origin, env.ALLOWED_ORIGINS),
  });
}
