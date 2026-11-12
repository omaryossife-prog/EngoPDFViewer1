import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse, readBody } from "../_shared/common.ts";
const periods: Record<string, { months: number }> = {
  monthly: { months: 1 }, quarterly: { months: 3 }, semiannual: { months: 6 },
};
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const period = String(body.billing_period ?? "").trim().toLowerCase();
    const periodInfo = periods[period];
    if (!periodInfo) throw new Error("Invalid subscription period");
    const admin = adminClient();
    const { data: runtimeSettings, error: runtimeError } = await admin.rpc("get_engo_runtime_settings", {});
    if (runtimeError) throw new Error(runtimeError.message);
    if (Boolean(runtimeSettings?.free_unlimited_mode ?? true)) {
      throw new Error("Subscriptions are disabled while Engo free unlimited mode is active");
    }
    const { data: price, error: priceError } = await admin.from("subscription_prices")
      .select("plan_id,billing_period,duration_months,amount,currency,is_active")
      .eq("plan_id", "premium").eq("billing_period", period).eq("is_active", true).maybeSingle();
    if (priceError) throw new Error(priceError.message);
    if (!price || Number(price.amount) <= 0) throw new Error("This Premium price has not been configured by Engo Admin yet");
    if (Number(price.duration_months) !== periodInfo.months) throw new Error("Subscription duration configuration is invalid");
    const { data: settings, error: settingsError } = await admin.from("subscription_settings")
      .select("qr_image_url,payment_instructions").eq("id", true).maybeSingle();
    if (settingsError) throw new Error(settingsError.message);
    let qrImageUrl: string | null = null;
    if (String(settings?.qr_image_url ?? "") === "storage://QR/QR.png") {
      const { data: signedQr, error: qrError } = await admin.storage.from("QR").createSignedUrl("QR.png", 60 * 60);
      if (qrError) throw new Error(qrError.message);
      qrImageUrl = signedQr?.signedUrl ?? null;
    }
    const { data: payment, error: insertError } = await admin.from("payment_transactions").insert({
      user_id: user.id, plan_id: "premium", amount: price.amount, currency: price.currency || "EGP",
      provider: "manual_qr", status: "pending",
      metadata: { source: "in_app_qr", billing_period: period, duration_months: periodInfo.months,
        payment_method: "manual_qr", requested_at: new Date().toISOString() },
    }).select("id,amount,currency,status,created_at").single();
    if (insertError) throw new Error(insertError.message);
    return jsonResponse({ payment, billing_period: period, duration_months: periodInfo.months,
      qr_image_url: qrImageUrl, payment_instructions: "" });
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Could not create payment request", 400); }
});
