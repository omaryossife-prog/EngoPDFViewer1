import { badRequest, handleOptions, jsonResponse, readBody, requireText } from "../_shared/common.ts";

Deno.serve(async (req: Request) => {
  const options = await handleOptions(req);
  if (options) return options;
  try {
    const body = await readBody(req);
    const configuredClientId = Deno.env.get("ENGO_GOOGLE_DESKTOP_CLIENT_ID") || "";
    const configuredClientSecret = Deno.env.get("ENGO_GOOGLE_DESKTOP_CLIENT_SECRET") || "";
    if (!configuredClientId || !configuredClientSecret) {
      throw new Error("Google Desktop OAuth is not configured on the Engo server");
    }

    const clientId = requireText(body, "client_id", 256);
    if (clientId !== configuredClientId) throw new Error("Google OAuth client mismatch");
    const code = requireText(body, "code", 2048);
    const verifier = requireText(body, "code_verifier", 128);
    if (verifier.length < 43) throw new Error("Invalid PKCE verifier");
    const redirectUri = requireText(body, "redirect_uri", 256);
    const redirect = new URL(redirectUri);
    if (redirect.protocol !== "http:" || redirect.hostname !== "127.0.0.1" ||
        !/^\d{1,5}$/.test(redirect.port) || redirect.pathname !== "/" ||
        redirect.search || redirect.hash) {
      throw new Error("Invalid Desktop OAuth loopback redirect URI");
    }

    const tokenResponse = await fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json" },
      body: new URLSearchParams({
        client_id: configuredClientId,
        client_secret: configuredClientSecret,
        code,
        code_verifier: verifier,
        grant_type: "authorization_code",
        redirect_uri: redirectUri,
      }),
    });
    const tokenBody = await tokenResponse.json().catch(() => ({})) as Record<string, unknown>;
    if (!tokenResponse.ok) {
      const reason = String(tokenBody.error_description || tokenBody.error || "Google token exchange failed");
      return badRequest(`Google OAuth exchange failed: ${reason}`, 400);
    }
    const idToken = String(tokenBody.id_token || "");
    if (!idToken) throw new Error("Google did not return an OpenID ID token");

    // Return only the tokens required by Supabase's ID-token sign-in. Never
    // return or log the client secret, and do not persist Google tokens.
    return jsonResponse({ id_token: idToken, access_token: String(tokenBody.access_token || "") });
  } catch (error) {
    return badRequest(error instanceof Error ? error.message : "Google sign-in failed", 400);
  }
});
