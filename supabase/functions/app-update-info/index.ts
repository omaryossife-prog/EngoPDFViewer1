import { adminClient, badRequest, handleOptions, jsonResponse } from "../_shared/common.ts";

function parseVersion(value: unknown): number[] | null {
  const text = String(value ?? "").trim();
  if (!/^\d+(?:\.\d+){1,3}$/.test(text)) return null;
  return text.split(".").map((part) => Number.parseInt(part, 10));
}

function compareVersions(left: number[], right: number[]): number {
  const length = Math.max(left.length, right.length);
  for (let index = 0; index < length; index += 1) {
    const a = left[index] ?? 0;
    const b = right[index] ?? 0;
    if (a !== b) return a > b ? 1 : -1;
  }
  return 0;
}

Deno.serve(async (req: Request) => {
  const options = await handleOptions(req);
  if (options) return options;
  if (req.method !== "POST") {
    return jsonResponse({ error: "Method not allowed" }, 405);
  }

  try {
    const body = await req.json().catch(() => ({}));
    const currentVersion = parseVersion(body?.app_version);
    if (!currentVersion) {
      throw new Error("A valid app_version is required");
    }

    const admin = adminClient();
    const { data, error } = await admin
      .from("app_update_settings")
      .select("enabled,latest_version,update_url,message_ar,message_en")
      .eq("id", true)
      .maybeSingle();
    if (error) throw new Error(error.message);

    const settings = data ?? {
      enabled: false,
      latest_version: "2.3.6",
      update_url: null,
      message_ar: null,
      message_en: null,
    };
    const latestVersion = parseVersion(settings.latest_version);
    const updateUrl = String(settings.update_url ?? "").trim();
    let safeUrl: string | null = null;
    try {
      const parsedUrl = new URL(updateUrl);
      if (parsedUrl.protocol === "https:" && parsedUrl.hostname) safeUrl = parsedUrl.toString();
    } catch {
      safeUrl = null;
    }
    const enabled = Boolean(settings.enabled);
    const updateAvailable = Boolean(
      enabled && latestVersion && safeUrl &&
      compareVersions(latestVersion, currentVersion) > 0
    );

    return jsonResponse({
      enabled,
      current_version: String(body.app_version),
      latest_version: String(settings.latest_version ?? "2.3.7"),
      update_url: enabled ? safeUrl : null,
      message_ar: String(settings.message_ar ?? ""),
      message_en: String(settings.message_en ?? ""),
      update_available: updateAvailable,
    });
  } catch (error) {
    return badRequest(error instanceof Error ? error.message : "Update information could not be loaded", 400);
  }
});
