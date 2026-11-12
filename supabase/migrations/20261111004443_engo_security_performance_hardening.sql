-- Engo security and performance hardening after first deployment.
-- No application data is deleted by this migration.

-- These functions are invoked by PostgreSQL triggers/event triggers, not by API clients.
revoke all on function public.handle_new_auth_user() from public, anon, authenticated;
revoke all on function public.rls_auto_enable() from public, anon, authenticated;

-- Use InitPlans so auth.uid() is evaluated once per statement rather than per row.
drop policy if exists profiles_read_own on public.profiles;
create policy profiles_read_own on public.profiles for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists devices_read_own on public.devices;
create policy devices_read_own on public.devices for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists subscriptions_read_own on public.subscriptions;
create policy subscriptions_read_own on public.subscriptions for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists usage_read_own on public.usage_counters;
create policy usage_read_own on public.usage_counters for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists license_events_read_own on public.license_events;
create policy license_events_read_own on public.license_events for select to authenticated
using ((select auth.uid()) = user_id);

drop policy if exists payment_transactions_read_own on public.payment_transactions;
create policy payment_transactions_read_own on public.payment_transactions for select to authenticated
using ((select auth.uid()) = user_id);

-- Explicit deny policies document that these datasets are server-only.
drop policy if exists feature_entitlements_deny_clients on public.feature_entitlements;
create policy feature_entitlements_deny_clients on public.feature_entitlements
for all to anon, authenticated using (false) with check (false);

drop policy if exists trusted_builds_deny_clients on public.trusted_builds;
create policy trusted_builds_deny_clients on public.trusted_builds
for all to anon, authenticated using (false) with check (false);

-- Cover foreign keys used by future admin/account queries.
create index if not exists subscriptions_by_plan on public.subscriptions(plan_id);
create index if not exists payment_transactions_by_plan on public.payment_transactions(plan_id);
create index if not exists payment_transactions_by_user on public.payment_transactions(user_id);
