-- Refund abandoned text-chat reservations after two hours.
-- This is a safety net for process crashes or a lost network response where
-- the client never received the reservation ID needed for immediate settlement.

create or replace function public.reserve_text_chat_usage_v1(
    p_user_id uuid,
    p_device_id text,
    p_app_version text,
    p_amount bigint default 1
) returns jsonb
language plpgsql
security definer
set search_path = ''
as $function$
declare
    v_device public.devices%rowtype;
    v_plan text := 'free';
    v_ent public.feature_entitlements%rowtype;
    v_window timestamptz;
    v_used bigint;
    v_limit bigint;
    v_free_unlimited boolean := true;
    v_reservation_id uuid;
    v_expired public.usage_reservations%rowtype;
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

    -- Recover reservations stranded by a crash or a lost server response.
    -- Two hours is deliberately much longer than the normal AI request timeout.
    for v_expired in
        select r.*
        from public.usage_reservations r
        where r.user_id = p_user_id
          and r.device_id = p_device_id
          and r.feature_key = 'text_chat'
          and r.status = 'pending'
          and r.created_at < pg_catalog.now() - interval '2 hours'
        order by r.created_at
        for update
    loop
        update public.usage_counters
        set used = greatest(0::bigint, used - v_expired.amount),
            updated_at = pg_catalog.now()
        where user_id = v_expired.user_id
          and feature_key = v_expired.feature_key
          and window_start = v_expired.window_start
          and scope_key = v_expired.scope_key;

        update public.usage_reservations
        set status = 'refunded', settled_at = pg_catalog.now()
        where id = v_expired.id and status = 'pending';
    end loop;

    select coalesce((
        select s.free_unlimited_mode
        from public.engo_runtime_settings s
        where s.id = true
    ), true) into v_free_unlimited;

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

    if exists (
        select 1 from public.trusted_builds b
        where b.app_version = p_app_version and b.is_approved = true
    ) and exists (
        select 1
        from public.subscriptions s
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
    where e.plan_id = v_plan and e.feature_key = 'text_chat';
    if not found or not v_ent.enabled then
        return jsonb_build_object('allowed', false, 'message', 'This feature is not enabled for the current plan');
    end if;

    v_limit := case when v_plan = 'premium' then v_ent.premium_limit else v_ent.free_limit end;
    v_window := case v_ent.reset_period
        when 'daily' then pg_catalog.date_trunc('day', pg_catalog.now())
        when 'monthly' then pg_catalog.date_trunc('month', pg_catalog.now())
        else '1970-01-01 00:00:00+00'::timestamptz
    end;

    insert into public.usage_counters(
        user_id, device_id, feature_key, window_start, scope_key, used, updated_at
    )
    values (
        p_user_id, p_device_id, 'text_chat', v_window, '', 0, pg_catalog.now()
    )
    on conflict (user_id, feature_key, window_start, scope_key) do update
        set device_id = excluded.device_id, updated_at = pg_catalog.now();

    select u.used into v_used
    from public.usage_counters u
    where u.user_id = p_user_id and u.feature_key = 'text_chat'
      and u.window_start = v_window and u.scope_key = ''
    for update;

    if v_limit is not null and v_used + p_amount > v_limit then
        return jsonb_build_object(
            'allowed', false, 'used', v_used, 'limit', v_limit, 'message', 'Usage limit reached'
        );
    end if;

    update public.usage_counters
    set used = used + p_amount, device_id = p_device_id, updated_at = pg_catalog.now()
    where user_id = p_user_id and feature_key = 'text_chat'
      and window_start = v_window and scope_key = ''
    returning used into v_used;

    v_reservation_id := gen_random_uuid();
    insert into public.usage_reservations(
        id, user_id, device_id, feature_key, window_start, scope_key, amount, status
    ) values (
        v_reservation_id, p_user_id, p_device_id, 'text_chat', v_window, '', p_amount, 'pending'
    );

    update public.devices
    set last_seen = pg_catalog.now(), updated_at = pg_catalog.now()
    where id = v_device.id;

    return jsonb_build_object(
        'allowed', true,
        'used', v_used,
        'limit', v_limit,
        'reservation_id', v_reservation_id,
        'message', ''
    );
end;
$function$;

revoke all on function public.reserve_text_chat_usage_v1(uuid, text, text, bigint) from public, anon, authenticated;
grant execute on function public.reserve_text_chat_usage_v1(uuid, text, text, bigint) to service_role;
