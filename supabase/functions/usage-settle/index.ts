import {
  adminClient,
  authenticatedUser,
  badRequest,
  handleOptions,
  jsonResponse,
  readBody,
  requireText,
} from "./_shared/common.ts";

Deno.serve(async (req: Request) => {
  const options = await handleOptions(req);
  if (options) return options;

  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const deviceId = requireText(body, "device_id", 128);
    const reservationId = requireText(body, "reservation_id", 64).toLowerCase();
    const outcome = requireText(body, "outcome", 16).toLowerCase();

    if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/.test(reservationId)) {
      throw new Error("Invalid text-chat reservation ID");
    }
    if (outcome !== "success" && outcome !== "failure") {
      throw new Error("Invalid text-chat settlement outcome");
    }

    const admin = adminClient();
    const { data, error } = await admin.rpc("settle_text_chat_usage_v1", {
      p_user_id: user.id,
      p_device_id: deviceId,
      p_reservation_id: reservationId,
      p_outcome: outcome,
    });
    if (error) throw new Error(error.message);

    const result = data as Record<string, unknown> | null;
    if (!result || result.settled !== true) {
      throw new Error("The text-chat reservation could not be settled");
    }

    return jsonResponse({
      settled: true,
      already_settled: Boolean(result.already_settled),
      status: String(result.status || ""),
      used: result.used ?? null,
    });
  } catch (error) {
    return badRequest(error instanceof Error ? error.message : "Text-chat settlement failed", 400);
  }
});
