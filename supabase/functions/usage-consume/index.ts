import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse, makeSignedLicense, readBody, requireText, requireVersion } from "./_shared/common.ts";
const allowedFeatures = new Set(["pdf_merge","app_themes","smart_theme","text_chat","voice_chat","voice_board_docx","tags","tag_units","translations","ai_search","open_other_formats"]);
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
    const context = license.context;
    if (feature === "open_other_formats") {
      // This format gate is Premium-only even while the temporary free-unlimited
      // launch switch is enabled. A verified, active build and live Premium
      // subscription are both required; the client-side gate is not authoritative.
      if (context.license_status !== "active") {
        return jsonResponse({
          allowed: false, used: null, limit: null,
          message: "Opening other file formats requires an active Premium subscription.",
          license: license.envelope,
        });
      }
      const now = new Date().toISOString();
      const { data: premiumSubscription, error: subscriptionError } = await admin
        .from("subscriptions")
        .select("id")
        .eq("user_id", user.id)
        .eq("plan_id", "premium")
        .in("status", ["active", "trialing"])
        .lte("starts_at", now)
        .or(`ends_at.is.null,ends_at.gt.${now}`)
        .limit(1)
        .maybeSingle();
      if (subscriptionError) throw new Error(subscriptionError.message);
      if (!premiumSubscription) {
        return jsonResponse({
          allowed: false, used: null, limit: null,
          message: "Opening other file formats requires an active Premium subscription.",
          license: license.envelope,
        });
      }
    }
    const entitlements = context.entitlements as Record<string, { enabled?: boolean; limit?: number | null }> | undefined;
    const entitlement = entitlements?.[feature];
    const enabled = Boolean(entitlement?.enabled);
    const featureIsLimited = enabled && entitlement?.limit !== null && entitlement?.limit !== undefined;
    if (context.license_status === "untrusted_build" &&
        !Boolean(context.free_unlimited_mode) && featureIsLimited) {
      return jsonResponse({
        allowed: false,
        used: null,
        limit: entitlement?.limit ?? null,
        message: "update_required",
        license: license.envelope,
      });
    }
    // Text chat is a reservation, not a final charge. The desktop settles it
    // as committed only after a non-empty provider answer, or refunds it after
    // an API error / user cancellation. Other metered features remain immediate.
    const usageResult = feature === "text_chat"
      ? await admin.rpc("reserve_text_chat_usage_v1", {
          p_user_id: user.id, p_device_id: deviceId,
          p_app_version: appVersion, p_amount: amount,
        })
      : await admin.rpc("consume_feature_usage_v1", {
          p_user_id: user.id, p_device_id: deviceId, p_app_version: appVersion,
          p_feature_key: feature, p_amount: amount, p_scope_key: scopeKey,
        });
    if (usageResult.error) throw new Error(usageResult.error.message);
    const usage = usageResult.data as Record<string, unknown>;
    const freeFeatureIsUnlimited = entitlement?.limit === null || entitlement?.limit === undefined;
    const validLicense = context.license_status === "active" || (
      context.license_status === "untrusted_build" &&
      (Boolean(context.free_unlimited_mode) || (enabled && freeFeatureIsUnlimited))
    );
    const allowed = validLicense && enabled && Boolean(usage?.allowed);
    return jsonResponse({
      allowed,
      used: usage?.used ?? null,
      limit: usage?.limit ?? null,
      message: allowed ? "" : String(usage?.message ?? (validLicense ? "Feature unavailable" : "License is not active")),
      reservation_id: feature === "text_chat" ? (usage?.reservation_id ?? null) : null,
      license: license.envelope,
    });
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Usage check failed", 400); }
});
