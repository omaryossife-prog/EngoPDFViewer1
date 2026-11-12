# Engo v17 — Production preparation validation report

Date: 2026-11-11

## Verification completed in this environment

- `python -m pytest -q tests`: **26 passed**.
- Python bytecode/syntax compilation: passed for `main.py`, all top-level `engo_*.py`, `engo_licensing/*.py`, `tools/*.py`, and `tests/*.py`.
- TypeScript syntax transpilation: passed for all 7 Edge Function TypeScript files (`_shared/common.ts` plus the 6 endpoint files). This is syntax transpilation, not a Deno type check.
- Ed25519 key-generator smoke test: generated a temporary keypair outside the project and verified that the public key matched the private key. The tool did not print private material; the temporary directory was deleted.
- CI dependency pin: `google-genai==2.34.0` remains in `requirements.txt` and the build workflow; no EXE or Installer build was started.
- Client API-key handling: the Supabase Publishable key is sent only in the `apikey` header; `Authorization` is sent only when a real user access token exists.
- Edge Functions read the current Supabase injected key maps (`SUPABASE_PUBLISHABLE_KEYS` and `SUPABASE_SECRET_KEYS`) first, with backward-compatible fallbacks to legacy variable names.
- Migration static checks: repaired `public.devices` table declaration; usage counters consolidate to account/feature/window; inactive plans cannot grant Premium; suspended accounts cannot activate/transfer devices.
- Packaging checks: ZIP integrity is checked before delivery; generated Python caches, local secrets and private-key files are excluded.

## Checks not available here

- Full repository `python -m pytest -q` collection stops at `tools/test_pen_shape_recognition.py` because PyQt6 is not installed in this container. The dedicated project suite under `tests/` passes.
- No PostgreSQL server/client (`psql`) or Supabase CLI is installed here, so the SQL migration was not executed against a real PostgreSQL instance and no remote Supabase project was changed.
- Deno is not installed. TypeScript syntax transpilation does not verify Deno type resolution, hosted Edge Function runtime behavior or deployment.
- PyQt6 desktop runtime, Splash/Account layout and RTL, Windows DPAPI/Credential Manager and Windows ACL behavior, real Google OAuth, and Gemini Live audio were not run here; they require the Windows development machine and the owner's account credentials.

## Production preparation corrections

1. Repaired the malformed `CREATE TABLE public.devices` SQL and added an idempotent `account_status` constraint.
2. Consolidated historical usage counters by account, feature and reset window before enforcing the unique key; moving devices no longer resets the server counter.
3. Considered `plans.is_active` in Premium selection and blocked suspended accounts from device activation/transfer.
4. Updated Edge Functions to use Supabase's current injected Publishable/Secret key maps, retaining legacy names as fallback.
5. Updated desktop config to accept `ENGO_SUPABASE_PUBLISHABLE_KEY` / `supabase_publishable_key`, preserving old anon-key aliases.
6. Fixed HTTP headers so public Publishable keys are never sent as bearer tokens.
7. Added an Ed25519 generator that writes private key material locally without printing it; the Windows path applies a current-user-only folder ACL using `icacls` (Windows execution still needs verification).
8. Added an exact-project-ref-confirmed PowerShell deployment script. It uploads only the Engo signing private key secret, runs the remote migration, deploys the six Edge Functions, and removes its temporary env file.
9. Added Arabic production setup instructions and static deployment-asset regression tests.

## Owner actions still required

- Create the real Supabase project and configure the Google provider with the Google OAuth Client ID/Secret.
- Generate the production signing key on a trusted Windows machine.
- Run the deployment script for the correct project and approve the migration prompt after reviewing the target project.
- Put only the project URL, Publishable key and public Ed25519 verification key in the desktop config.
- Approve the exact release version in `trusted_builds`, choose actual Free quotas, and run real Windows + Google OAuth + Gemini Live checks.
- Only after those checks pass, build and Authenticode-sign the EXE and installer.

This is a production-preparation package. It is not a claim that a real Supabase project has been deployed or that a Windows release has passed end-to-end testing.
