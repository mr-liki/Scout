import type { Env } from "../types";
import { corsHeaders } from "../lib/cors";
import { getScrapeStatuses } from "../db/queries";

export async function handlePlatforms(
  request: Request,
  env: Env
): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  const statuses = await getScrapeStatuses(env.DB);

  const platforms = [
    { key: "linkedin", name: "LinkedIn", available: true },
    { key: "indeed", name: "Indeed", available: true },
    { key: "glassdoor", name: "Glassdoor", available: true },
    { key: "wellfound", name: "Wellfound", available: true },
    { key: "foundit", name: "Foundit", available: true },
    { key: "shine", name: "Shine", available: true },
    { key: "cutshort", name: "Cutshort", available: true },
    { key: "apna", name: "Apna", available: true },
  ];

  return Response.json(
    {
      platforms: platforms.map((p) => ({
        ...p,
        status: statuses[p.key] || null,
      })),
      count: platforms.filter((p) => p.available).length,
    },
    { headers }
  );
}
