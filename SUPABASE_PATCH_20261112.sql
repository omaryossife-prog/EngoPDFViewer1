-- ENGO patch 2026-11-12
-- Apply this file once in Supabase Dashboard -> SQL Editor, against the Engo project.
-- It is additive and preserves existing usage counters and account data.

begin;

-- ---------------------------------------------------------------------
-- 1) Per-PDF usage scope for Tags and Tag Units
-- ---------------------------------------------------------------------
alter table public.usage_counters
    add column if not exists scope_key text not null default '';

drop index if exists public.usage_counters_account_feature_window;
create unique index if not exists usage_counters_account_feature_scope_window
    on public.usage_counters(user_id, feature_key, window_start, scope_key);

alter table public.feature_entitlements
    drop constraint if exists feature_entitlements_reset_period_check;
alter table public.feature_entitlements
    add constraint feature_entitlements_reset_period_check
    check (reset_period = any (array['daily'::text, 'monthly'::text, 'lifetime'::text, 'per_file'::text]));

-- Tags and tag units are now lifetime counters scoped by the PDF content hash.
update public.feature_entitlements
set reset_period = 'per_file', updated_at = now()
where feature_key in ('tags', 'tag_units');

-- Replace the five-argument RPC with a scope-aware six-argument version.
drop function if exists public.consume_feature_usage_v1(uuid, text, text, text, bigint);

create function public.consume_feature_usage_v1(
    p_user_id uuid,
    p_device_id text,
    p_app_version text,
    p_feature_key text,
    p_amount bigint default 1,
    p_scope_key text default ''
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_device public.devices%rowtype;
    v_plan text := 'free';
    v_ent public.feature_entitlements%rowtype;
    v_window timestamptz;
    v_scope_key text := '';
    v_used bigint;
    v_limit bigint;
begin
    if not exists (
        select 1 from public.profiles
        where user_id = p_user_id and account_status = 'active'
    ) then
        return jsonb_build_object('allowed', false, 'message', 'Account is suspended or unavailable');
    end if;

    select * into v_device
    from public.devices
    where user_id = p_user_id and device_id = p_device_id and status = 'active'
    limit 1;
    if not found then
        return jsonb_build_object('allowed', false, 'message', 'This device is not active');
    end if;

    if p_amount is null or p_amount < 1 or p_amount > 1000 then
        return jsonb_build_object('allowed', false, 'message', 'Invalid usage amount');
    end if;

    if p_feature_key in ('tags', 'tag_units') then
        v_scope_key := coalesce(nullif(trim(p_scope_key), ''), '');
        if v_scope_key = '' or length(v_scope_key) > 128 then
            return jsonb_build_object('allowed', false, 'message', 'A valid PDF scope is required for per-file tag limits');
        end if;
    end if;

    if exists (
        select 1 from public.trusted_builds b
        where b.app_version = p_app_version and b.is_approved = true
    ) and exists (
        select 1 from public.subscriptions s
        join public.plans p on p.plan_id = s.plan_id and p.is_active = true
        where s.user_id = p_user_id and s.plan_id = 'premium'
          and s.status in ('active', 'trialing')
          and s.starts_at <= now()
          and (s.ends_at is null or s.ends_at > now())
    ) then
        v_plan := 'premium';
    end if;

    select * into v_ent
    from public.feature_entitlements
    where plan_id = v_plan and feature_key = p_feature_key;
    if not found or not v_ent.enabled then
        return jsonb_build_object('allowed', false, 'message', 'This feature is not enabled for the current plan');
    end if;

    v_limit := case when v_plan = 'premium' then v_ent.premium_limit else v_ent.free_limit end;

    if p_feature_key in ('tags', 'tag_units') then
        -- One independent counter for every PDF, with no time-based reset.
        v_window := '1970-01-01 00:00:00+00'::timestamptz;
    else
        -- Other features keep their existing time/lifetime behavior.
        v_window := case v_ent.reset_period
            when 'daily' then date_trunc('day', now())
            when 'monthly' then date_trunc('month', now())
            else '1970-01-01 00:00:00+00'::timestamptz
        end;
        v_scope_key := '';
    end if;

    insert into public.usage_counters(user_id, device_id, feature_key, window_start, scope_key, used, updated_at)
    values (p_user_id, p_device_id, p_feature_key, v_window, v_scope_key, 0, now())
    on conflict (user_id, feature_key, window_start, scope_key) do update
        set device_id = excluded.device_id, updated_at = now();

    select used into v_used
    from public.usage_counters
    where user_id = p_user_id and feature_key = p_feature_key
      and window_start = v_window and scope_key = v_scope_key
    for update;

    if v_limit is not null and v_used + p_amount > v_limit then
        return jsonb_build_object('allowed', false, 'used', v_used, 'limit', v_limit, 'message', 'Usage limit reached');
    end if;

    update public.usage_counters
    set used = used + p_amount, device_id = p_device_id, updated_at = now()
    where user_id = p_user_id and feature_key = p_feature_key
      and window_start = v_window and scope_key = v_scope_key
    returning used into v_used;

    update public.devices
    set last_seen = now(), updated_at = now()
    where id = v_device.id;

    return jsonb_build_object('allowed', true, 'used', v_used, 'limit', v_limit, 'message', '');
end;
$$;

revoke all on function public.consume_feature_usage_v1(uuid, text, text, text, bigint, text)
    from public, anon, authenticated;
grant execute on function public.consume_feature_usage_v1(uuid, text, text, text, bigint, text)
    to service_role;

-- ---------------------------------------------------------------------
-- 2) Approximate active-use time from the existing five-minute heartbeat
-- ---------------------------------------------------------------------
create table if not exists public.user_activity_daily (
    user_id uuid not null references auth.users(id) on delete cascade,
    device_id text not null,
    activity_date date not null,
    active_seconds bigint not null default 0 check (active_seconds >= 0),
    updated_at timestamptz not null default now(),
    primary key (user_id, device_id, activity_date)
);

create index if not exists user_activity_daily_by_user_date
    on public.user_activity_daily(user_id, activity_date desc);

create or replace function public.record_device_active_time_v1()
returns trigger
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_seconds bigint;
    v_activity_date date;
begin
    if old.status <> 'active' or new.status <> 'active'
       or old.last_seen is null or new.last_seen is null
       or new.last_seen <= old.last_seen then
        return new;
    end if;

    -- Heartbeats are sent every five minutes. The ten-minute cap avoids
    -- counting long offline gaps as active time after a PC wakes up.
    v_seconds := least(600::bigint, greatest(0::bigint,
        floor(extract(epoch from (new.last_seen - old.last_seen)))::bigint));
    if v_seconds <= 0 then
        return new;
    end if;

    v_activity_date := (new.last_seen at time zone 'UTC')::date;
    insert into public.user_activity_daily(user_id, device_id, activity_date, active_seconds, updated_at)
    values (new.user_id, new.device_id, v_activity_date, v_seconds, now())
    on conflict (user_id, device_id, activity_date) do update
       set active_seconds = public.user_activity_daily.active_seconds + excluded.active_seconds,
           updated_at = now();

    return new;
end;
$$;

revoke all on function public.record_device_active_time_v1() from public, anon, authenticated;
drop trigger if exists devices_record_active_time on public.devices;
create trigger devices_record_active_time
    after update of last_seen on public.devices
    for each row execute function public.record_device_active_time_v1();

-- ---------------------------------------------------------------------
-- 3) Configurable Premium prices and QR-payment instructions
-- ---------------------------------------------------------------------
create table if not exists public.subscription_prices (
    plan_id text not null references public.plans(plan_id) on delete cascade,
    billing_period text not null check (billing_period in ('monthly', 'quarterly', 'semiannual', 'annual')),
    duration_months integer not null check (duration_months in (1, 3, 6, 12)),
    amount numeric(12,2) not null default 0 check (amount >= 0),
    currency text not null default 'EGP',
    is_active boolean not null default true,
    updated_at timestamptz not null default now(),
    primary key (plan_id, billing_period),
    check (
        (billing_period = 'monthly' and duration_months = 1) or
        (billing_period = 'quarterly' and duration_months = 3) or
        (billing_period = 'semiannual' and duration_months = 6) or
        (billing_period = 'annual' and duration_months = 12)
    )
);

insert into public.subscription_prices(plan_id, billing_period, duration_months, amount, currency, is_active)
values
    ('premium', 'monthly', 1, 0, 'EGP', true),
    ('premium', 'quarterly', 3, 0, 'EGP', true),
    ('premium', 'semiannual', 6, 0, 'EGP', true),
    ('premium', 'annual', 12, 0, 'EGP', true)
on conflict (plan_id, billing_period) do nothing;

create table if not exists public.subscription_settings (
    id boolean primary key default true check (id = true),
    qr_image_url text,
    payment_instructions text,
    updated_at timestamptz not null default now()
);

insert into public.subscription_settings(id, qr_image_url, payment_instructions)
values (true, null, 'استبدل صورة QR التجريبية وأضف تعليمات التحويل من تبويب الخطط والأسعار في Engo Admin.')
on conflict (id) do nothing;

-- These tables are read/written only by trusted Edge Functions and the local
-- owner-only Engo Admin tool, both using the service_role key.
alter table public.user_activity_daily enable row level security;
alter table public.subscription_prices enable row level security;
alter table public.subscription_settings enable row level security;

drop policy if exists user_activity_daily_deny_clients on public.user_activity_daily;
create policy user_activity_daily_deny_clients on public.user_activity_daily
    for all to anon, authenticated using (false) with check (false);
drop policy if exists subscription_prices_deny_clients on public.subscription_prices;
create policy subscription_prices_deny_clients on public.subscription_prices
    for all to anon, authenticated using (false) with check (false);
drop policy if exists subscription_settings_deny_clients on public.subscription_settings;
create policy subscription_settings_deny_clients on public.subscription_settings
    for all to anon, authenticated using (false) with check (false);

revoke all on public.user_activity_daily, public.subscription_prices, public.subscription_settings
    from anon, authenticated;
grant all on public.user_activity_daily, public.subscription_prices, public.subscription_settings
    to service_role;

grant select, insert, update, delete on public.usage_counters to service_role;

-- Verification queries are documented after the transaction at the end of this file.

-- ---------------------------------------------------------------------
-- 4) Atomic owner-only approval/rejection of manual QR subscription orders
-- ---------------------------------------------------------------------
create or replace function public.admin_approve_qr_payment_v1(p_payment_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_payment public.payment_transactions%rowtype;
    v_period text;
    v_months integer;
    v_now timestamptz := now();
    v_ends_at timestamptz;
    v_metadata jsonb;
begin
    select * into v_payment
    from public.payment_transactions
    where id = p_payment_id
    for update;
    if not found or v_payment.status <> 'pending' then
        raise exception 'Payment request is not pending';
    end if;
    if v_payment.provider <> 'manual_qr' or v_payment.plan_id <> 'premium' then
        raise exception 'Payment request is not a Premium QR order';
    end if;

    v_period := lower(coalesce(v_payment.metadata->>'billing_period', ''));
    v_months := case v_period
        when 'monthly' then 1
        when 'quarterly' then 3
        when 'semiannual' then 6
        when 'annual' then 12
        else null
    end;
    if v_months is null then
        raise exception 'Payment request has an invalid subscription duration';
    end if;

    v_ends_at := v_now + make_interval(months => v_months);
    update public.subscriptions
    set status = 'cancelled', updated_at = v_now
    where user_id = v_payment.user_id and status in ('active', 'trialing');

    insert into public.subscriptions(user_id, plan_id, status, starts_at, ends_at)
    values (v_payment.user_id, 'premium', 'active', v_now, v_ends_at);

    v_metadata := coalesce(v_payment.metadata, '{}'::jsonb) || jsonb_build_object(
        'approved_by', 'admin_panel', 'approved_at', v_now,
        'activated_until', v_ends_at
    );
    update public.payment_transactions
    set status = 'succeeded', metadata = v_metadata, updated_at = v_now
    where id = p_payment_id;

    insert into public.license_events(user_id, event_type, details)
    values (v_payment.user_id, 'admin_approved_qr_subscription',
        jsonb_build_object('payment_id', p_payment_id, 'billing_period', v_period, 'ends_at', v_ends_at));

    return jsonb_build_object('approved', true, 'user_id', v_payment.user_id,
        'payment_id', p_payment_id, 'billing_period', v_period, 'ends_at', v_ends_at);
end;
$$;

create or replace function public.admin_reject_qr_payment_v1(p_payment_id uuid)
returns jsonb
language plpgsql
security invoker
set search_path = ''
as $$
declare
    v_payment public.payment_transactions%rowtype;
    v_now timestamptz := now();
begin
    select * into v_payment
    from public.payment_transactions
    where id = p_payment_id
    for update;
    if not found or v_payment.status <> 'pending' then
        raise exception 'Payment request is not pending';
    end if;
    update public.payment_transactions
    set status = 'failed',
        metadata = coalesce(metadata, '{}'::jsonb) || jsonb_build_object('rejected_by', 'admin_panel', 'rejected_at', v_now),
        updated_at = v_now
    where id = p_payment_id;
    insert into public.license_events(user_id, event_type, details)
    values (v_payment.user_id, 'admin_rejected_qr_subscription', jsonb_build_object('payment_id', p_payment_id));
    return jsonb_build_object('rejected', true, 'payment_id', p_payment_id);
end;
$$;

revoke all on function public.admin_approve_qr_payment_v1(uuid) from public, anon, authenticated;
revoke all on function public.admin_reject_qr_payment_v1(uuid) from public, anon, authenticated;
grant execute on function public.admin_approve_qr_payment_v1(uuid) to service_role;
grant execute on function public.admin_reject_qr_payment_v1(uuid) to service_role;

commit;

-- Verification queries (run separately after the patch):
-- select feature_key, reset_period from public.feature_entitlements where feature_key in ('tags','tag_units') order by feature_key, plan_id;
-- select plan_id, billing_period, duration_months, amount, currency, is_active from public.subscription_prices order by duration_months;
-- select column_name from information_schema.columns where table_schema='public' and table_name='usage_counters' and column_name='scope_key';
-- select trigger_name from information_schema.triggers where event_object_table='devices' and trigger_name='devices_record_active_time';
