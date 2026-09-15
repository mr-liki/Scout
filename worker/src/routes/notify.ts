import type { Env } from "../types";
import { corsHeaders } from "../lib/cors";

export async function handleNotifySubscribe(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405, headers });
  }

  try {
    const { email, keywords, locations } = await request.json() as { email: string; keywords: string[]; locations?: string[] };

    if (!email || !email.includes("@")) {
      return Response.json({ error: "Valid email required" }, { status: 400, headers });
    }
    if (!keywords || !Array.isArray(keywords) || keywords.length === 0) {
      return Response.json({ error: "At least one keyword required" }, { status: 400, headers });
    }

    const keywordsJson = JSON.stringify(keywords.map(k => k.trim().toLowerCase()).filter(Boolean));
    const locationsJson = JSON.stringify((locations || []).map(l => l.trim()).filter(Boolean));

    await env.DB.prepare(
      `INSERT INTO notify_subscriptions (email, keywords, locations, active, updated_at)
       VALUES (?, ?, ?, 1, datetime('now'))
       ON CONFLICT(email) DO UPDATE SET
         keywords = excluded.keywords,
         locations = excluded.locations,
         active = 1,
         updated_at = datetime('now')`
    ).bind(email.toLowerCase().trim(), keywordsJson, locationsJson).run();

    return Response.json({ ok: true, message: "Subscribed successfully" }, { headers });
  } catch (e: any) {
    return Response.json({ error: "Failed to subscribe", message: e.message }, { status: 500, headers });
  }
}

export async function handleNotifySubscription(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  const url = new URL(request.url);
  const email = url.searchParams.get("email");

  if (!email) {
    return Response.json({ error: "Email parameter required" }, { status: 400, headers });
  }

  try {
    const row = await env.DB.prepare(
      `SELECT * FROM notify_subscriptions WHERE email = ?`
    ).bind(email.toLowerCase().trim()).first();

    if (!row) {
      return Response.json({ subscribed: false }, { headers });
    }

    return Response.json({
      subscribed: !!row.active,
      email: row.email,
      keywords: JSON.parse(row.keywords as string),
      locations: JSON.parse((row.locations as string) || "[]"),
      created_at: row.created_at,
    }, { headers });
  } catch (e: any) {
    return Response.json({ error: "Failed to get subscription", message: e.message }, { status: 500, headers });
  }
}

export async function handleNotifyUnsubscribe(request: Request, env: Env): Promise<Response> {
  const origin = request.headers.get("Origin");
  const headers = corsHeaders(origin, env.ALLOWED_ORIGINS);

  if (request.method !== "POST") {
    return Response.json({ error: "Method not allowed" }, { status: 405, headers });
  }

  try {
    const { email } = await request.json() as { email: string };

    if (!email) {
      return Response.json({ error: "Email required" }, { status: 400, headers });
    }

    await env.DB.prepare(
      `UPDATE notify_subscriptions SET active = 0, updated_at = datetime('now') WHERE email = ?`
    ).bind(email.toLowerCase().trim()).run();

    return Response.json({ ok: true, message: "Unsubscribed successfully" }, { headers });
  } catch (e: any) {
    return Response.json({ error: "Failed to unsubscribe", message: e.message }, { status: 500, headers });
  }
}
