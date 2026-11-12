> **Engo production update (2026-11-12):** This document contains earlier generic integration steps. For the current Engo project, follow `README_UPDATES_20261112_AR.md` and `ENGO_SIGNING_SETUP_AR.md`. The app config already contains a public Ed25519 key, so never regenerate it implicitly; key rotation must be explicit and coordinated. Google Desktop OAuth secrets, the Ed25519 private key, and `service_role` must remain server/owner-side and must never ship in the desktop build.

# Engo Accounts, Device Licensing and Entitlements

This integration adds a standalone licensing package without replacing the PDF renderer, document tabs, AI providers, chat workers, or Gemini Live worker.

## Client files and startup flow

- `engo_licensing/core.py`: Supabase Auth PKCE, DPAPI/keyring session storage, stable install UUID, signed Ed25519 license verification, heartbeat state, device activation/transfer and usage reservation.
- `engo_licensing/ui.py`: animated frameless startup screen and account/subscription dialog.
- `supabase/migrations/202611100001_engo_accounts_licensing.sql`: tables, RLS, atomic device activation/transfer and usage RPCs.
- `supabase/functions/*`: authenticated Edge Functions. The only client-side Supabase key is the public anon/publishable key.

On startup, a stored account is refreshed and its device and signed license are checked. No account, missing project configuration, a failed request, an invalid/expired signature, an unapproved build or a device conflict results in Free mode. The application remains usable for local files. Premium is never restored from a local cache.

A server response is a `{payload, signature}` envelope. The Edge Functions sign canonical UTF-8 JSON with Ed25519. The private signing key stays in Supabase Edge Function secrets; the desktop app receives only the public key. The client checks signature, user, device, version and timestamps.

## Supabase setup (current production key model)

1. Create a dedicated Supabase project. Keep its project ref, database password and API keys in your own password manager.
2. In the project API settings, copy the **Project URL** and the **Publishable key** (`sb_publishable_...`). The desktop app uses only these public values. Do not copy a `Secret` (`sb_secret_...`) key into Engo.
3. Configure Google OAuth in **Authentication → Providers → Google**. Create a Google OAuth client of type **Web application**. In Google Cloud, set its Authorized redirect URI to `https://<PROJECT_REF>.supabase.co/auth/v1/callback` (use the exact callback displayed by the Supabase Google provider page). Paste the Google Client ID and Client Secret into the Supabase provider settings and enable Google.
4. In **Authentication → URL Configuration → Redirect URLs**, add the loopback callback pattern `http://127.0.0.1:*/callback?state=*`. This supports Engo's temporary local callback port and per-login anti-CSRF nonce. Supabase supports wildcard redirect patterns; keep the allow-list loopback-only. For a fixed-port deployment, set the same fixed value in `ENGO_OAUTH_REDIRECT_URI` and the allow-list.
5. Generate the production signing pair locally with `python tools/generate_license_signing_keys.py`. The script stores the private PKCS#8 key under `.secrets/` without printing it, and prints only the public key. Keep `.secrets/` outside source control and back it up in an encrypted secret manager.
6. Deploy the migration and six Edge Functions using the PowerShell script below. It uploads only `ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64`. Supabase supplies its own `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEYS` and `SUPABASE_SECRET_KEYS` runtime variables; the functions support the legacy names as a fallback. Do not set `SUPABASE_*` values manually as Edge Function secrets.
7. After deployment, approve the exact release version in `trusted_builds` from the Supabase SQL Editor. Until approved, the application remains in Free mode. Example only:

```sql
insert into public.trusted_builds(app_version,is_approved,notes,approved_at)
values ('2.3.6', true, 'Approved production release', now())
on conflict (app_version) do update
set is_approved=true, notes=excluded.notes, approved_at=now();
```

8. Put a file named `engo_license.json` next to `main.exe`, using only the public project URL, publishable key and public Ed25519 verification key:

```json
{
  "supabase_url": "https://<PROJECT_REF>.supabase.co",
  "supabase_publishable_key": "sb_publishable_REPLACE_ME",
  "license_public_key_b64": "PUBLIC_KEY_BASE64_FROM_GENERATOR",
  "request_timeout": 12,
  "oauth_timeout": 180,
  "oauth_redirect_uri": "",
  "app_version": "2.3.6",
  "expected_signer_thumbprint": ""
}
```

The old `supabase_anon_key` JSON field and `ENGO_SUPABASE_ANON_KEY` environment variable remain accepted for backward compatibility. New installations should use `supabase_publishable_key` or `ENGO_SUPABASE_PUBLISHABLE_KEY`.

### Automated Windows deployment

Open PowerShell in the project directory after creating the Supabase project, configuring Google OAuth, installing the Supabase CLI and generating the signing key:

```powershell
.\tools\deploy_supabase_production.ps1 -ProjectRef YOUR_20_CHARACTER_PROJECT_REF
```

The script requires you to type the project ref exactly before proceeding. It logs in to the Supabase CLI, links the selected project, uploads the signing key through a temporary ignored env file, asks Supabase before applying remote migrations, then deploys the six functions. It aborts if a step fails and removes the temporary env file. It does not create a Supabase project, configure Google OAuth, approve builds, choose quotas or build an EXE.

## Future admin-console data map

The schema supports an admin console without granting desktop write access: `profiles.account_status` controls whether an account is active or suspended; `plans` defines Free/Premium; `feature_entitlements` stores per-plan enabled flags, numerical limits and reset periods; `subscriptions` stores plan and subscription dates/status; `devices` lists and revokes installs through the server-side transfer flow; `trusted_builds` approves exact app versions; and `payment_transactions` is reserved for future payment-provider reconciliation. No admin web UI or payment gateway is included in this implementation.

## Entitlements and quotas

The migration creates rows for all ten feature keys under Free and Premium but leaves numerical limits NULL because product quotas have not been specified. NULL means no configured numerical cap. Premium should retain `premium_limit = NULL` for included features. Set Free limits from an admin-only SQL/management surface, for example:

```sql
update public.feature_entitlements
set free_limit = 12, reset_period = 'daily', updated_at = now()
where plan_id = 'free' and feature_key = 'text_chat';
```

The number above is an example only and must be replaced by the product owner's chosen quota. Free and Premium rows are server-managed; no desktop API grants users direct update access. Feature keys are `pdf_merge`, `page_themes`, `app_themes`, `smart_theme`, `text_chat`, `voice_chat`, `tags`, `tag_units`, `translations`, and `ai_search`.

Premium subscription activation is an admin/payment-provider operation and is intentionally not exposed to the desktop client. No prices, checkout integration or payment provider are included.

## BYOK and usage enforcement boundaries

Provider API keys and PDF/chat content are not sent to the Engo licensing endpoints. The usage API receives only the feature key, unit count, device ID and app version. Counters are keyed by account + feature + reset window (the device ID is retained only as the latest-use audit value), so transferring devices does not reset Free usage. The AI request still goes directly from the user's device to their chosen provider using their own key.

Because BYOK requests are executed by a modifiable desktop client, a determined attacker can patch out client-side usage calls, inspect local memory, or call an AI provider independently. Supabase-side counters and signed entitlements prevent ordinary clients from changing quotas, subscriptions or device records, but do not create tamper-proof enforcement over an API key controlled by the user. Free quotas therefore deter normal overuse; they cannot be made unconditionally unbypassable without proxying the AI request through infrastructure (which this product explicitly does not want to pay for or receive document content).

The desktop app switches to Free on failed verification. Local/offline PDF viewing remains available. Offline Free usage cannot be reliably counted by the server; in that case the client keeps local work available and reports that usage was not tracked. No offline Premium grace period is implemented.

## Single-device behavior

Each install gets a random persistent UUID stored under the Engo application data directory. It is not derived from the motherboard, CPU or other hardware. The database serializes activation/transfer by locking the profile row and adds a unique partial index allowing at most one active device per user. Transfer revokes the old device in the same database transaction and activates the new one. The old device loses premium access on its next heartbeat or next server-side feature reservation; an offline device cannot receive an immediate push. A 5-minute heartbeat is used instead of Realtime in this first pass.

## Local testing

- Unit tests: `python -m pytest tests/test_licensing_core.py -q`
- Syntax check: `python -m py_compile main.py engo_*.py engo_licensing/*.py`
- Run the desktop app on Windows with Python 3.13 and the normal `run.bat` launcher.
- Test against a separate Supabase development project and a dedicated test Google OAuth client. Do not add production secrets to the repository.

The current container did not have PyQt6, pywin32, keyring or google-genai installed, so GUI, Windows Credential Manager/DPAPI and provider runtime tests must be run on the Windows development machine after dependencies are installed. This handoff does not claim those tests have passed.

## Signing key generation and rotation

Run `python tools/generate_license_signing_keys.py` on a trusted administrator machine. The script stores the base64 PKCS#8 private key under `.secrets/engo-license-signing-private.pkcs8.b64` and the raw public key under `.secrets/engo-license-signing-public.raw.b64`. It prints only the public value. The private key must be uploaded only as the `ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64` Edge Function secret and must never be shipped with the desktop application.

The current client accepts one pinned public key. Rotating it requires a coordinated release: publish the new public key in the client config, deploy the matching private key to Supabase, and ensure old client versions are retired or supported during a planned transition. Do not overwrite the only backup of a production private key without a recovery plan.

## Local mock environment (no Google or Supabase account required)

A loopback-only mock Auth/Edge Functions server is included for development:

1. Copy `tools/engo_license.mock.json.example` to the project root as `engo_license.json`.
2. In a terminal, run `python tools/mock_licensing_server.py --plan free --free-limit 3`.
3. Launch Engo using the normal Python launcher. In **Account**, choose **Sign in with Google**. The mock server simulates the local OAuth PKCE redirect and returns a clearly fake `student@engo.local` account; it does not contact Google.
4. For Premium UI testing, stop the mock server and restart it with `--plan premium`. Reset its in-memory state by restarting the server.
5. The mock signing key and `engo_license.mock.json.example` are public test fixtures only. Never use them in a release, production database or shipped EXE. The mock quota is a simplified per-feature test cap, not the SQL daily/monthly counter implementation. An authenticated but unapproved build receives only the signed Free entitlements and is still metered against Free counters; an inactive/revoked device receives no server grants and retains local Free-only functions.

## Release and Windows validation checklist

On a Windows 10/11 development machine with Python 3.13 x64, install the normal project dependencies, confirm `google-genai==2.34.0`, and run:

```powershell
python -m py_compile main.py engo_*.py engo_licensing/*.py
python -m pytest -q tests
python main.py
```

The local GUI run is required to validate PyQt animation, Windows DPAPI/Credential Manager, live Google OAuth, and the current Gemini Live audio path. This source integration does not build an EXE or installer. Only after those checks pass should the existing `BUILD_SETUP.bat` / release workflow be used; sign the final executable and installer with the same trusted Authenticode publisher certificate, then pin the certificate thumbprint in the client config.

## Release code signing

Import a real OV/EV code-signing certificate with its private key into the Windows certificate store. Sign the built app and the installer separately from the release process:

```powershell
.\\tools\\sign_release.ps1 -FilePath .\\dist\\Engo.exe -CertificateThumbprint YOUR_CERT_THUMBPRINT
.\\tools\\sign_release.ps1 -FilePath .\\dist\\EngoSetup.exe -CertificateThumbprint YOUR_CERT_THUMBPRINT
```

Set the same certificate thumbprint in `ENGO_SIGNER_THUMBPRINT` or `expected_signer_thumbprint` in the public desktop configuration. The app then requires both a valid Authenticode signature and the expected publisher thumbprint for frozen Windows builds. Keep the signing certificate and its private key out of source control and CI logs.

## Feature gate integration points

The client gates these user actions before continuing: PDF merge, page themes, application themes, Smart Theme, text chat, voice chat, tag creation, tag-region units, translation and AI search. PDF merge is a new local PyMuPDF operation; the existing “Link PDFs” chat-context feature is unchanged. `NULL` limits are intentionally left in the migration until the owner chooses Free quotas. A feature is not charged for a rejected request at the SQL usage-counter layer.

The first release uses server-side heartbeat every five minutes plus server authorization immediately before each metered action. It does not yet open a persistent Supabase Realtime WebSocket. This means online devices are denied on their next metered request and otherwise switch on the next heartbeat; a disconnected device cannot receive a push notification. It has no offline Premium grace.
