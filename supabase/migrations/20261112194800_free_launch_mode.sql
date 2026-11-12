-- Engo free launch mode: all signed-in accounts get every metered feature without quotas.
-- The default is enabled so the initial public launch remains free until the owner disables it.

create table if not exists public.engo_runtime_settings (
    id boolean primary key default true check (id = true),
    free_unlimited_mode boolean not null default true,
    updated_at timestamptz not null default now()
);

insert into public.engo_runtime_settings (id, free_unlimited_mode)
values (true, true)
on conflict (id) do nothing;

alter table public.engo_runtime_settings enable row level security;
revoke all on table public.engo_runtime_settings from anon, authenticated;
grant all on table public.engo_runtime_settings to service_role;

create or replace function public.get_engo_runtime_settings()
returns jsonb
language sql
security definer
set search_path = ''
as $$
    select jsonb_build_object(
        'free_unlimited_mode',
        coalesce((select s.free_unlimited_mode from public.engo_runtime_settings s where s.id = true), true)
    );
$$;

create or replace function public.set_engo_free_unlimited_mode(p_enabled boolean)
returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
begin
    if p_enabled is null then
        raise exception 'p_enabled is required';
    end if;
    insert into public.engo_runtime_settings (id, free_unlimited_mode, updated_at)
    values (true, p_enabled, pg_catalog.now())
    on conflict (id) do update
      set free_unlimited_mode = excluded.free_unlimited_mode,
          updated_at = pg_catalog.now();
    return public.get_engo_runtime_settings();
end;
$$;

revoke all on function public.get_engo_runtime_settings() from public, anon, authenticated;
revoke all on function public.set_engo_free_unlimited_mode(boolean) from public, anon, authenticated;
grant execute on function public.get_engo_runtime_settings() to service_role;
grant execute on function public.set_engo_free_unlimited_mode(boolean) to service_role;

create or replace function public.get_license_context_v1(
    p_user_id uuid,
    p_device_id text,
    p_app_version text
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $$
declare
    v_device public.devices%rowtype;
    v_subscription public.subscriptions%rowtype;
    v_plan text := 'free';
    v_build_ok boolean := false;
    v_entitlements jsonb := '{}'::jsonb;
    v_status text := 'device_not_active';
    v_account_active boolean := true;
    v_profile public.profiles%rowtype;
    v_free_unlimited boolean := true;
begin
    select * into v_profile from public.profiles where user_id = p_user_id;
    v_account_active := coalesce(v_profile.account_status, 'active') = 'active';

    select * into v_device
    from public.devices
    where user_id = p_user_id and device_id = p_device_id and status = 'active'
    limit 1;

    if found then
        update public.devices
        set last_seen = pg_catalog.now(), app_version = p_app_version, updated_at = pg_catalog.now()
        where id = v_device.id
        returning * into v_device;
    end if;

    select coalesce((select s.free_unlimited_mode from public.engo_runtime_settings s where s.id = true), true)
    into v_free_unlimited;

    select exists(
        select 1 from public.trusted_builds b
        where b.app_version = p_app_version and b.is_approved = true
    ) into v_build_ok;

    if not v_free_unlimited then
        select s.* into v_subscription
        from public.subscriptions s
        join public.plans p on p.plan_id = s.plan_id and p.is_active = true
        where s.user_id = p_user_id and s.status in ('active','trialing')
          and s.starts_at <= pg_catalog.now()
          and (s.ends_at is null or s.ends_at > pg_catalog.now())
        order by s.starts_at desc
        limit 1;
        if found and v_subscription.plan_id = 'premium' then
            v_plan := 'premium';
        end if;
    else
        v_plan := 'free';
    end if;

    if not v_account_active then
        v_status := 'account_suspended';
        v_plan := 'free';
    elsif v_device.id is not null and v_build_ok then
        v_status := 'active';
    elsif v_device.id is not null and not v_build_ok then
        v_status := 'untrusted_build';
        v_plan := 'free';
    else
        v_plan := 'free';
    end if;

    if v_free_unlimited then
        select coalesce(
            jsonb_object_agg(
                feature_keys.feature_key,
                jsonb_build_object(
                    'enabled', true,
                    'limit', null,
                    'reset_period', 'lifetime',
                    'plan_id', 'free'
                )
            ),
            '{}'::jsonb
        )
        into v_entitlements
        from (
            select distinct e.feature_key
            from public.feature_entitlements e
        ) as feature_keys;
    else
        select coalesce(
            jsonb_object_agg(
                e.feature_key,
                jsonb_build_object(
                    'enabled', e.enabled,
                    'limit', case when v_plan = 'premium' then e.premium_limit else e.free_limit end,
                    'reset_period', e.reset_period,
                    'plan_id', v_plan
                )
            ),
            '{}'::jsonb
        )
        into v_entitlements
        from public.feature_entitlements e
        where e.plan_id = v_plan;
    end if;

    return jsonb_build_object(
        'user_id', p_user_id,
        'device_id', p_device_id,
        'plan_id', v_plan,
        'entitlements', v_entitlements,
        'free_unlimited_mode', v_free_unlimited,
        'expires_at', pg_catalog.now() + interval '10 minutes',
        'issued_at', pg_catalog.now(),
        'app_version', p_app_version,
        'license_status', v_status,
        'subscription', case when v_subscription.id is null then null else jsonb_build_object(
            'plan_id', v_subscription.plan_id,
            'status', v_subscription.status,
            'starts_at', v_subscription.starts_at,
            'ends_at', v_subscription.ends_at
        ) end,
        'profile', case when v_profile.user_id is null then '{}'::jsonb else jsonb_build_object(
            'display_name', v_profile.display_name,
            'avatar_url', v_profile.avatar_url
        ) end
    );
end;
$$;

create or replace function public.consume_feature_usage_v1(
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
    v_free_unlimited boolean := true;
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

    select coalesce((select s.free_unlimited_mode from public.engo_runtime_settings s where s.id = true), true)
    into v_free_unlimited;

    if v_free_unlimited then
        update public.devices
        set last_seen = pg_catalog.now(), updated_at = pg_catalog.now()
        where id = v_device.id;
        return jsonb_build_object(
            'allowed', true,
            'used', null,
            'limit', null,
            'free_unlimited_mode', true,
            'message', ''
        );
    end if;

    if p_feature_key in ('tags', 'tag_units') then
        v_scope_key := coalesce(nullif(pg_catalog.btrim(p_scope_key), ''), '');
        if v_scope_key = '' or pg_catalog.length(v_scope_key) > 128 then
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
          and s.starts_at <= pg_catalog.now()
          and (s.ends_at is null or s.ends_at > pg_catalog.now())
    ) then
        v_plan := 'premium';
    end if;

    select * into v_ent
    from public.feature_entitlements e
    where e.plan_id = v_plan and e.feature_key = p_feature_key;
    if not found or not v_ent.enabled then
        return jsonb_build_object('allowed', false, 'message', 'This feature is not enabled for the current plan');
    end if;

    v_limit := case when v_plan = 'premium' then v_ent.premium_limit else v_ent.free_limit end;

    if p_feature_key in ('tags', 'tag_units') then
        v_window := '1970-01-01 00:00:00+00'::timestamptz;
    else
        v_window := case v_ent.reset_period
            when 'daily' then pg_catalog.date_trunc('day', pg_catalog.now())
            when 'monthly' then pg_catalog.date_trunc('month', pg_catalog.now())
            else '1970-01-01 00:00:00+00'::timestamptz
        end;
        v_scope_key := '';
    end if;

    insert into public.usage_counters(
        user_id, device_id, feature_key, window_start, scope_key, used, updated_at
    )
    values (
        p_user_id, p_device_id, p_feature_key, v_window, v_scope_key, 0, pg_catalog.now()
    )
    on conflict (user_id, feature_key, window_start, scope_key) do update
        set device_id = excluded.device_id, updated_at = pg_catalog.now();

    select u.used into v_used
    from public.usage_counters u
    where u.user_id = p_user_id and u.feature_key = p_feature_key
      and u.window_start = v_window and u.scope_key = v_scope_key
    for update;

    if v_limit is not null and v_used + p_amount > v_limit then
        return jsonb_build_object('allowed', false, 'used', v_used, 'limit', v_limit, 'message', 'Usage limit reached');
    end if;

    update public.usage_counters
    set used = used + p_amount, device_id = p_device_id, updated_at = pg_catalog.now()
    where user_id = p_user_id and feature_key = p_feature_key
      and window_start = v_window and scope_key = v_scope_key
    returning used into v_used;

    update public.devices
    set last_seen = pg_catalog.now(), updated_at = pg_catalog.now()
    where id = v_device.id;

    return jsonb_build_object('allowed', true, 'used', v_used, 'limit', v_limit, 'message', '');
end;
$$;

-- These functions use SECURITY DEFINER, so they must not be callable by end users directly.
revoke all on function public.get_license_context_v1(uuid, text, text) from public, anon, authenticated;
grant execute on function public.get_license_context_v1(uuid, text, text) to service_role;
revoke all on function public.consume_feature_usage_v1(uuid, text, text, text, bigint, text) from public, anon, authenticated;
grant execute on function public.consume_feature_usage_v1(uuid, text, text, text, bigint, text) to service_role;
