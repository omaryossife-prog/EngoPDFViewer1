import { createClient, SupabaseClient } from "https://esm.sh/@supabase/supabase-js@2.119.0";

export const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};

export function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { ...corsHeaders, "Content-Type": "application/json", "Cache-Control": "no-store" },
  });
}

export function badRequest(message: string, status = 400): Response {
  return jsonResponse({ error: message }, status);
}

function readDefaultKeyMap(variableName: string): string | null {
  const raw = Deno.env.get(variableName);
  if (!raw) return null;
  try {
    const parsed = JSON.parse(raw) as Record<string, unknown>;
    const preferred = parsed.default;
    if (typeof preferred === "string" && preferred.trim()) return preferred.trim();
    const first = Object.values(parsed).find((value) => typeof value === "string" && value.trim());
    return typeof first === "string" ? first.trim() : null;
  } catch {
    return null;
  }
}

function firstConfigured(...values: Array<string | null | undefined>): string | null {
  for (const value of values) {
    if (typeof value === "string" && value.trim()) return value.trim();
  }
  return null;
}

function supabasePublishableKey(): string | null {
  return firstConfigured(
    readDefaultKeyMap("SUPABASE_PUBLISHABLE_KEYS"),
    Deno.env.get("SUPABASE_PUBLISHABLE_KEY"),
    Deno.env.get("SUPABASE_ANON_KEY"),
  );
}

function supabaseSecretKey(): string | null {
  return firstConfigured(
    readDefaultKeyMap("SUPABASE_SECRET_KEYS"),
    Deno.env.get("SUPABASE_SECRET_KEY"),
    Deno.env.get("SUPABASE_SERVICE_ROLE_KEY"),
  );
}

export function adminClient(): SupabaseClient {
  const url = Deno.env.get("SUPABASE_URL");
  const key = supabaseSecretKey();
  if (!url || !key) throw new Error("Server Supabase credentials are not configured");
  return createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });
}

export async function authenticatedUser(req: Request): Promise<{ id: string; email?: string }> {
  const authorization = req.headers.get("Authorization") || "";
  const match = authorization.match(/^Bearer\s+(.+)$/i);
  if (!match) throw new Error("Authentication required");
  const url = Deno.env.get("SUPABASE_URL");
  const anon = supabasePublishableKey();
  if (!url || !anon) throw new Error("Supabase Auth is not configured");
  const client = createClient(url, anon, {
    global: { headers: { Authorization: `Bearer ${match[1]}` } },
    auth: { persistSession: false, autoRefreshToken: false },
  });
  const { data, error } = await client.auth.getUser(match[1]);
  if (error || !data.user) throw new Error("Invalid or expired account session");
  return { id: data.user.id, email: data.user.email };
}

export function readBody(req: Request): Promise<Record<string, unknown>> {
  return req.json().then((body) => {
    if (!body || typeof body !== "object" || Array.isArray(body)) throw new Error("Invalid request body");
    return body as Record<string, unknown>;
  });
}

export function requireText(body: Record<string, unknown>, key: string, max = 256): string {
  const value = String(body[key] ?? "").trim();
  if (!value || value.length > max) throw new Error(`Invalid ${key}`);
  return value;
}

export function requireVersion(body: Record<string, unknown>): string {
  return requireText(body, "app_version", 64);
}

function toBase64(bytes: Uint8Array): string {
  let binary = "";
  for (const byte of bytes) binary += String.fromCharCode(byte);
  return btoa(binary);
}

function sortForCanonicalJson(value: unknown): unknown {
  if (Array.isArray(value)) return value.map(sortForCanonicalJson);
  if (value && typeof value === "object") {
    const source = value as Record<string, unknown>;
    const sorted: Record<string, unknown> = {};
    for (const key of Object.keys(source).sort()) sorted[key] = sortForCanonicalJson(source[key]);
    return sorted;
  }
  return value;
}

export async function signPayload(payload: Record<string, unknown>): Promise<Record<string, unknown>> {
  const encodedPrivate = Deno.env.get("ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64");
  if (!encodedPrivate) throw new Error("Ed25519 signing key is not configured on the server");
  const privateDer = Uint8Array.from(atob(encodedPrivate), (character) => character.charCodeAt(0));
  const privateKey = await crypto.subtle.importKey("pkcs8", privateDer, { name: "Ed25519" }, false, ["sign"]);
  const canonical = JSON.stringify(sortForCanonicalJson(payload));
  const signature = await crypto.subtle.sign("Ed25519", privateKey, new TextEncoder().encode(canonical));
  return { payload, signature: toBase64(new Uint8Array(signature)) };
}

export async function makeSignedLicense(userId: string, deviceId: string, appVersion: string) {
  const admin = adminClient();
  const { data, error } = await admin.rpc("get_license_context_v1", {
    p_user_id: userId,
    p_device_id: deviceId,
    p_app_version: appVersion,
  });
  if (error || !data || typeof data !== "object") throw new Error(error?.message || "Could not load license context");
  const source = data as Record<string, unknown>;
  const payload: Record<string, unknown> = {
    user_id: source.user_id,
    device_id: source.device_id,
    plan_id: source.plan_id,
    entitlements: source.entitlements,
    expires_at: source.expires_at,
    issued_at: source.issued_at,
    app_version: source.app_version,
    license_status: source.license_status,
    free_unlimited_mode: Boolean(source.free_unlimited_mode),
    message: source.license_status === "active" ? "" : String(source.license_status ?? "License unavailable"),
  };
  return { envelope: await signPayload(payload), context: source };
}

export async function handleOptions(req: Request): Promise<Response | null> {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST") return badRequest("Method not allowed", 405);
  return null;
}
