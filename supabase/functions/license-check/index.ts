import { authenticatedUser, badRequest, handleOptions, jsonResponse, makeSignedLicense, readBody, requireText, requireVersion } from "../_shared/common.ts";
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req); if (options) return options;
  try {
    const user = await authenticatedUser(req);
    const body = await readBody(req);
    const deviceId = requireText(body, "device_id", 128);
    const appVersion = requireVersion(body);
    const { envelope } = await makeSignedLicense(user.id, deviceId, appVersion);
    return jsonResponse(envelope);
  } catch (error) { return badRequest(error instanceof Error ? error.message : "License check failed", 400); }
});
