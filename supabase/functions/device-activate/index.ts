import { adminClient, authenticatedUser, badRequest, handleOptions, jsonResponse, readBody, requireText, requireVersion } from "../_shared/common.ts";
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const deviceId = requireText(body, "device_id", 128);
    const deviceName = requireText(body, "device_name", 160);
    const appVersion = requireVersion(body);
    const admin = adminClient();
    const { data, error } = await admin.rpc("activate_device_v1", {
      p_user_id: user.id, p_device_id: deviceId, p_device_name: deviceName,
      p_app_version: appVersion, p_allow_transfer: false,
    });
    if (error) throw new Error(error.message);
    const result = data as Record<string, unknown>;
    if (result?.status === "device_conflict") return jsonResponse(result);
    return jsonResponse(result ?? { status: "active" });
  } catch (error) { return badRequest(error instanceof Error ? error.message : "Device activation failed", 401); }
});
