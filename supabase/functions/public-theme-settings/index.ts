import { adminClient, handleOptions, jsonResponse } from "./_shared/common.ts";

Deno.serve(async (req: Request) => {
  const options = await handleOptions(req);
  if (options) return options;
  try {
    const admin = adminClient();
    const { data, error } = await admin
      .from("feature_entitlements")
      .select("enabled")
      .eq("plan_id", "free")
      .eq("feature_key", "app_themes")
      .maybeSingle();
    if (error) throw error;
    return jsonResponse({ free_app_themes_enabled: Boolean(data?.enabled) });
  } catch (_error) {
    return jsonResponse({ free_app_themes_enabled: false }, 200);
  }
});
