import { adminClient, badRequest, handleOptions, jsonResponse } from "../_shared/common.ts";

// This endpoint exposes only a short-lived signed URL for the single branded
// OAuth-success illustration. It does not accept a caller-supplied bucket/path.
Deno.serve(async (req: Request) => {
  const options = await handleOptions(req);
  if (options) return options;
  try {
    const admin = adminClient();
    const { data, error } = await admin.storage
      .from("QR")
      .createSignedUrl("SignInSuccess.png", 60 * 60);
    if (error) {
      // The app's built-in success artwork remains visible until the owner
      // uploads SignInSuccess.png to the existing private QR bucket.
      return jsonResponse({ image_url: null });
    }
    return jsonResponse({ image_url: data?.signedUrl ?? null });
  } catch (error) {
    return badRequest(error instanceof Error ? error.message : "Could not load sign-in artwork", 400);
  }
});
