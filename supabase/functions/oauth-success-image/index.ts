import { createClient } from "https://esm.sh/@supabase/supabase-js@2.119.0";

const corsHeaders = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, x-client-info, apikey, content-type",
  "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
};

// Source-controlled fallback. The first successful request stores this page in
// the existing private Storage bucket; later requests use the bucket's version.
const DEFAULT_HTML = "<!doctype html>\n<html lang=\"{{LANG}}\" dir=\"{{DIR}}\">\n<head>\n<meta charset=\"utf-8\"><meta name=\"viewport\" content=\"width=device-width,initial-scale=1\">\n<meta name=\"color-scheme\" content=\"dark\"><title>{{PAGE_TITLE}}</title>\n<style>\n:root{--line:#2b4568;--text:#f2f6ff;--muted:#a9bdd9;--blue:#76a9ff}\n*{box-sizing:border-box}html,body{margin:0;min-height:100%;font-family:\"Segoe UI\",\"Cairo\",Tahoma,Arial,sans-serif;color:var(--text)}\nbody{min-height:100vh;display:grid;place-items:center;padding:28px;background:radial-gradient(ellipse at 50% 0%,rgba(48,116,205,.27),transparent 55%),linear-gradient(145deg,#0a1321,#101d30 58%,#0a1422)}\n.shell{width:min(760px,100%);position:relative}.glow{position:absolute;inset:8% 12%;background:rgba(62,139,255,.18);filter:blur(70px)}\n.card{position:relative;overflow:hidden;border:1px solid rgba(126,169,225,.28);border-radius:28px;padding:clamp(26px,5vw,54px);background:linear-gradient(150deg,rgba(25,43,68,.97),rgba(15,28,47,.98));box-shadow:0 24px 70px rgba(0,0,0,.42)}\n.card:before{content:\"\";position:absolute;inset:0 0 auto;height:4px;background:linear-gradient(90deg,#5c96f4,#54c5e8,#16b981)}\n.brand{display:flex;align-items:center;gap:14px;justify-content:center;margin-bottom:28px}.logo{width:54px;height:54px;flex:0 0 54px;filter:drop-shadow(0 7px 16px rgba(65,145,255,.28))}\n.brand-name{font-size:21px;font-weight:850}.brand-sub{font-size:11px;color:var(--muted);margin-top:3px;letter-spacing:2.1px;text-transform:uppercase}\n.success-ring{width:118px;height:118px;margin:0 auto 22px;border-radius:50%;display:grid;place-items:center;background:linear-gradient(145deg,rgba(22,185,129,.2),rgba(76,143,242,.17));border:1px solid rgba(113,183,255,.45);box-shadow:0 0 0 10px rgba(91,153,238,.055),0 0 45px rgba(57,139,255,.16)}\n.check{width:62px;height:62px;border-radius:20px;background:linear-gradient(145deg,#1bc58c,#0d9e70);display:grid;place-items:center;box-shadow:0 10px 26px rgba(10,178,124,.25)}.check svg{width:34px;height:34px}\n.avatar{width:86px;height:86px;border-radius:50%;object-fit:cover;border:3px solid var(--blue);box-shadow:0 0 0 6px rgba(118,169,255,.12);margin:0 auto 15px;display:block;background:#203550}.avatar.empty{display:none}\nh1{font-size:clamp(24px,4vw,34px);text-align:center;margin:0 0 12px;font-weight:850;line-height:1.35}.subtitle{text-align:center;color:var(--muted);font-size:15px;line-height:1.9;margin:0 auto;max-width:520px}\n.email{text-align:center;color:#86b5ff;font-size:13px;margin-top:9px;direction:ltr}.rule{height:1px;background:linear-gradient(90deg,transparent,var(--line),transparent);margin:28px 0 22px}\n.status{display:flex;align-items:center;justify-content:center;gap:9px;color:#c8d8ef;font-size:13px}.status-dot{width:8px;height:8px;border-radius:50%;background:#19c58d;box-shadow:0 0 12px rgba(25,197,141,.7)}\n.actions{display:flex;justify-content:center;margin-top:28px}a.continue{display:inline-block;text-decoration:none;text-align:center;border-radius:13px;padding:15px 42px;min-width:190px;background:linear-gradient(135deg,#82b4ff,#5b94ed);color:#10213a;font-size:15px;font-weight:850;box-shadow:0 10px 24px rgba(63,130,226,.25)}\n.footer{text-align:center;color:#7289a8;font-size:11px;margin-top:20px;letter-spacing:.4px}@media(max-width:520px){body{padding:14px}.card{border-radius:22px;padding:28px 20px}.logo{width:46px;height:46px;flex-basis:46px}.brand-name{font-size:19px}}\n</style></head>\n<body><main class=\"shell\"><div class=\"glow\"></div><section class=\"card\" aria-live=\"polite\">\n<header class=\"brand\">\n<svg class=\"logo\" viewBox=\"0 0 100 100\" role=\"img\" aria-label=\"Engo logo\">\n<defs><linearGradient id=\"lg\" x1=\"0\" y1=\"0\" x2=\"1\" y2=\"1\"><stop stop-color=\"#8bc0ff\"/><stop offset=\"1\" stop-color=\"#397de0\"/></linearGradient><linearGradient id=\"pg\" x1=\"0\" y1=\"0\" x2=\"0\" y2=\"1\"><stop stop-color=\"#f9fcff\"/><stop offset=\"1\" stop-color=\"#c9e2ff\"/></linearGradient></defs>\n<rect x=\"7\" y=\"7\" width=\"86\" height=\"86\" rx=\"25\" fill=\"#102a4c\" stroke=\"#5da0fa\" stroke-width=\"3\"/><rect x=\"17\" y=\"17\" width=\"66\" height=\"66\" rx=\"18\" fill=\"url(#lg)\"/><path d=\"M37 29h28v9H47v8h16v9H47v8h18v9H37z\" fill=\"url(#pg)\"/></svg>\n<div><div class=\"brand-name\">Engo PDF</div><div class=\"brand-sub\">Viewer &amp; AI Study Agent</div></div></header>\n<div class=\"success-ring\"><div class=\"check\"><svg viewBox=\"0 0 24 24\" fill=\"none\"><path d=\"m5 12.5 4.5 4.5L19.5 7\" stroke=\"white\" stroke-width=\"2.8\" stroke-linecap=\"round\" stroke-linejoin=\"round\"/></svg></div></div>\n<img id=\"profile\" class=\"avatar {{AVATAR_CLASS}}\" src=\"{{AVATAR_DATA_URI}}\" alt=\"Profile photo\">\n<h1>{{WELCOME_TITLE}}</h1><p class=\"subtitle\">{{WELCOME_SUBTITLE}}</p><div class=\"email\">{{EMAIL}}</div><div class=\"rule\"></div>\n<div class=\"status\"><span class=\"status-dot\"></span><span>{{STATUS_TEXT}}</span></div>\n<div class=\"actions\"><a class=\"continue\" href=\"engo://continue\">{{CONTINUE_TEXT}}</a></div>\n</section><div class=\"footer\">ENGO · YOUR STUDY SPACE</div></main></body></html>";

Deno.serve(async (req: Request) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: corsHeaders });
  if (req.method !== "POST" && req.method !== "GET") {
    return new Response(JSON.stringify({ error: "Method not allowed" }), {
      status: 405, headers: { ...corsHeaders, "Content-Type": "application/json" },
    });
  }
  try {
    const url = Deno.env.get("SUPABASE_URL");
    let key = Deno.env.get("SUPABASE_SECRET_KEY") || Deno.env.get("SUPABASE_SERVICE_ROLE_KEY");
    if (!key) {
      try {
        const keyMap = JSON.parse(Deno.env.get("SUPABASE_SECRET_KEYS") || "{}") as Record<string, unknown>;
        const preferred = keyMap.default;
        const first = Object.values(keyMap).find((value) => typeof value === "string" && value.trim());
        key = typeof preferred === "string" && preferred.trim()
          ? preferred.trim()
          : (typeof first === "string" ? first.trim() : "");
      } catch {
        key = "";
      }
    }
    if (!url || !key) throw new Error("Server Supabase credentials are not configured");
    const admin = createClient(url, key, { auth: { persistSession: false, autoRefreshToken: false } });

    const bucket = admin.storage.from("Sign in");
    let { data, error } = await bucket.download("SignInSuccess.html");
    if (error || !data) {
      // The user specified this bucket. Bootstrap the HTML there if the object
      // has not been uploaded yet; never overwrite an existing customized page.
      const upload = await bucket.upload(
        "SignInSuccess.html",
        new Blob([DEFAULT_HTML], { type: "text/html; charset=utf-8" }),
        { contentType: "text/html; charset=utf-8", upsert: false },
      );
      if (upload.error && !String(upload.error.message || "").toLowerCase().includes("already exists")) {
        throw new Error("Could not initialize SignInSuccess.html in Storage bucket 'Sign in': " + upload.error.message);
      }
      const downloaded = await bucket.download("SignInSuccess.html");
      data = downloaded.data;
      error = downloaded.error;
    }
    if (error || !data) throw new Error("SignInSuccess.html is not available in Storage bucket 'Sign in'");
    return new Response(JSON.stringify({ html: await data.text() }), {
      status: 200, headers: { ...corsHeaders, "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  } catch (error) {
    const message = error instanceof Error ? error.message : "Could not load the sign-in HTML page";
    return new Response(JSON.stringify({ error: message }), {
      status: 400, headers: { ...corsHeaders, "Content-Type": "application/json", "Cache-Control": "no-store" },
    });
  }
});
