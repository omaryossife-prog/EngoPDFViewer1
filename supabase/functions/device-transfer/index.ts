import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse, readBody, requireText, requireVersion } from "../_shared/common.ts";
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const admin = adminClient();
    const { data, error } = await admin.rpc("activate_device_v1", {
      p_user_id: user.id,
      p_device_id: requireText(body, "device_id", 128),
      p_device_name: requireText(body, "device_name", 160),
      p_app_version: requireVersion(body),
      p_allow_transfer: true,
    });
    if (error) throw new Error(error.message);
    const result = data as Record<string, unknown>;
    if (result?.status !== "transferred" && result?.status !== "active") throw new Error(String(result?.message ?? "Device transfer failed"));
    return jsonResponse(result);
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Device transfer failed", 400); }
});
