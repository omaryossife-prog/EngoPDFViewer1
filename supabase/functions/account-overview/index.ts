import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse } from "../_shared/common.ts";
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const admin = adminClient();
    const [profile, devices, subscription, prices, paymentSettings, entitlements, runtimeSettings] = await Promise.all([
      admin.from("profiles").select("display_name,avatar_url,account_status,created_at").eq("user_id", user.id).maybeSingle(),
      admin.from("devices").select("device_id,device_name,activated_at,last_seen,status,app_version").eq("user_id", user.id).order("last_seen", { ascending: false }),
      admin.from("subscriptions").select("plan_id,status,starts_at,ends_at").eq("user_id", user.id).order("starts_at", { ascending: false }).limit(1).maybeSingle(),
      admin.from("subscription_prices").select("billing_period,duration_months,amount,currency,is_active").eq("plan_id", "premium").order("duration_months", { ascending: true }),
      admin.from("subscription_settings").select("qr_image_url,payment_instructions").eq("id", true).maybeSingle(),
      admin.from("feature_entitlements").select("plan_id,feature_key,enabled,free_limit,premium_limit,reset_period").in("plan_id", ["free", "premium"]).order("feature_key"),
      admin.rpc("get_engo_runtime_settings", {}),
    ]);
    const failure = profile.error?.message || devices.error?.message || subscription.error?.message || prices.error?.message || paymentSettings.error?.message || entitlements.error?.message || runtimeSettings.error?.message;
    if (failure) throw new Error(failure);
    let signedQrUrl: string | null = null;
    let qrImageError: string | null = null;
    const qrLocator = String(paymentSettings.data?.qr_image_url ?? "");
    if (qrLocator === "storage://QR/QR.png") {
      const { data: signed, error } = await admin.storage.from("QR").createSignedUrl("QR.png", 60 * 60);
      if (error) qrImageError = error.message;
      else signedQrUrl = signed?.signedUrl ?? null;
    }
    // Return the current per-PDF counters for the two offline-capable tag features.
    // Scope keys are content hashes, not file names or paths.
    const tagUsage: Array<{ feature_key: string; scope_key: string; used: number }> = [];
    let tagUsageAvailable = true;
    try {
      for (let offset = 0; offset < 100000; offset += 1000) {
        const { data, error } = await admin.from("usage_counters")
          .select("feature_key,scope_key,used")
          .eq("user_id", user.id)
          .in("feature_key", ["tags", "tag_units"])
          .neq("scope_key", "")
          .order("feature_key", { ascending: true })
          .order("scope_key", { ascending: true })
          .range(offset, offset + 999);
        if (error) throw error;
        const page = data ?? [];
        tagUsage.push(...page.map((row) => ({
          feature_key: String(row.feature_key),
          scope_key: String(row.scope_key ?? ""),
          used: Number(row.used ?? 0),
        })));
        if (page.length < 1000) break;
      }
    } catch {
      // Account details remain available even if quota history cannot be loaded.
      // The client will keep its previous encrypted snapshot or deny offline use.
      tagUsageAvailable = false;
    }
    const freeUnlimited = Boolean((runtimeSettings.data ?? {}).free_unlimited_mode ?? true);
    return jsonResponse({
      profile: profile.data, devices: devices.data ?? [], subscription: subscription.data ?? null,
      prices: prices.data ?? [], payment_settings: { ...(paymentSettings.data ?? {}), qr_image_url: signedQrUrl, qr_image_error: qrImageError },
      entitlements: entitlements.data ?? [], tag_usage: tagUsageAvailable ? tagUsage : null,
      free_unlimited_mode: freeUnlimited, email: user.email ?? null,
    });
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Could not load account", 400); }
});
