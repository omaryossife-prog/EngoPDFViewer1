import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse, makeSignedLicense, readBody, requireText, requireVersion } from "./_shared/common.ts";
const allowedFeatures = new Set(["pdf_merge","page_themes","app_themes","smart_theme","text_chat","voice_chat","tags","tag_units","translations","ai_search"]);
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const deviceId = requireText(body, "device_id", 128);
    const appVersion = requireVersion(body);
    const feature = requireText(body, "feature_key", 64);
    if (!allowedFeatures.has(feature)) throw new Error("Unknown feature key");
    const amount = Number(body.amount ?? 1);
    if (!Number.isInteger(amount) || amount < 1 || amount > 1000) throw new Error("Invalid usage amount");
    const scopeKey = String(body.scope_key ?? "").trim().slice(0, 128);
    const admin = adminClient();
    // Validate that the server can produce a signed license BEFORE reserving usage.
    // Otherwise a missing/invalid signing key could consume a user's quota even
    // though the desktop must (correctly) deny the feature without a signed reply.
    const license = await makeSignedLicense(user.id, deviceId, appVersion);
    const usageResult = await admin.rpc("consume_feature_usage_v1", {
      p_user_id: user.id, p_device_id: deviceId, p_app_version: appVersion,
      p_feature_key: feature, p_amount: amount, p_scope_key: scopeKey,
    });
    if (usageResult.error) throw new Error(usageResult.error.message);
    const usage = usageResult.data as Record<string, unknown>;
    const context = license.context;
    const validLicense = context.license_status === "active" || context.license_status === "untrusted_build";
    const enabled = Boolean((context.entitlements as Record<string, {enabled?: boolean}> | undefined)?.[feature]?.enabled);
    const allowed = validLicense && enabled && Boolean(usage?.allowed);
    return jsonResponse({
      allowed,
      used: usage?.used ?? null,
      limit: usage?.limit ?? null,
      message: allowed ? "" : String(usage?.message ?? (validLicense ? "Feature unavailable" : "License is not active")),
      license: license.envelope,
    });
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Usage check failed", 400); }
});
