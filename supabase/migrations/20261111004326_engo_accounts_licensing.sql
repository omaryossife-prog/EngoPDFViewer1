-- Engo account, subscription, device and entitlement foundation.
-- Safe to re-run. Prices and payment providers intentionally remain unset.

create extension if not exists pgcrypto;

create table if not exists public.profiles (
    user_id uuid primary key references auth.users(id) on delete cascade,
    display_name text,
    avatar_url text,
    account_status text not null default 'active' check (account_status in ('active','suspended')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
alter table public.profiles
    add column if not exists account_status text not null default 'active';

do $$
begin
    if not exists (
        select 1 from pg_constraint
        where conrelid = 'public.profiles'::regclass
          and conname = 'profiles_account_status_check'
    ) then
        alter table public.profiles
            add constraint profiles_account_status_check
            check (account_status in ('active','suspended'));
    end if;
end;
$$;

create table if not exists public.devices (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    device_id text not null,
    device_name text not null default 'Windows PC',
    activated_at timestamptz not null default now(),
    last_seen timestamptz not null default now(),
    status text not null default 'active' check (status in ('active','revoked','inactive')),
    app_version text not null,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique(user_id, device_id)
);
create unique index if not exists devices_one_active_per_user
    on public.devices(user_id) where status = 'active';
create index if not exists devices_by_user_last_seen on public.devices(user_id, last_seen desc);

create table if not exists public.plans (
    plan_id text primary key check (plan_id in ('free','premium')),
    name text not null,
    is_active boolean not null default true,
    created_at timestamptz not null default now()
);

create table if not exists public.subscriptions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    plan_id text not null references public.plans(plan_id),
    status text not null default 'active' check (status in ('trialing','active','past_due','cancelled','expired','paused')),
    starts_at timestamptz not null default now(),
    ends_at timestamptz,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);
create index if not exists subscriptions_user_status on public.subscriptions(user_id, status, ends_at desc);

create table if not exists public.feature_entitlements (
    id bigserial primary key,
    plan_id text not null references public.plans(plan_id) on delete cascade,
    feature_key text not null,
    enabled boolean not null default true,
    free_limit bigint,
    premium_limit bigint,
    reset_period text not null default 'lifetime' check (reset_period in ('daily','monthly','lifetime')),
    updated_at timestamptz not null default now(),
    unique(plan_id, feature_key),
    check (free_limit is null or free_limit >= 0),
    check (premium_limit is null or premium_limit >= 0)
);

create table if not exists public.usage_counters (
    id bigserial primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    device_id text not null,
    feature_key text not null,
    window_start timestamptz not null,
    used bigint not null default 0 check (used >= 0),
    updated_at timestamptz not null default now()
);
-- Quotas belong to the account, not the current installation. Moving the
-- account between devices must not reset a daily/monthly/lifetime counter.
alter table public.usage_counters
    drop constraint if exists usage_counters_user_id_device_id_feature_key_window_start_key;

-- If an earlier development build recorded counters separately per device,
-- consolidate them by account/feature/window before creating the new unique index.
with grouped as (
    select user_id, feature_key, window_start, sum(used)::bigint as total_used
    from public.usage_counters
    group by user_id, feature_key, window_start
), keepers as (
    select distinct on (user_id, feature_key, window_start)
           id, user_id, feature_key, window_start, device_id
    from public.usage_counters
    order by user_id, feature_key, window_start, updated_at desc, id desc
)
update public.usage_counters u
set used = g.total_used, device_id = k.device_id, updated_at = now()
from grouped g
join keepers k using (user_id, feature_key, window_start)
where u.id = k.id;

with keepers as (
    select distinct on (user_id, feature_key, window_start)
           id, user_id, feature_key, window_start
    from public.usage_counters
    order by user_id, feature_key, window_start, updated_at desc, id desc
)
delete from public.usage_counters u
using keepers k
where u.user_id = k.user_id
  and u.feature_key = k.feature_key
  and u.window_start = k.window_start
  and u.id <> k.id;

create unique index if not exists usage_counters_account_feature_window
    on public.usage_counters(user_id, feature_key, window_start);
create index if not exists usage_counters_by_user on public.usage_counters(user_id, feature_key, window_start desc);

create table if not exists public.trusted_builds (
    app_version text primary key,
    is_approved boolean not null default false,
    notes text,
    approved_at timestamptz,
    created_at timestamptz not null default now()
);

create table if not exists public.license_events (
    id bigserial primary key,
    user_id uuid not null references auth.users(id) on delete cascade,
    device_id text,
    event_type text not null,
    details jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now()
);
create index if not exists license_events_user_time on public.license_events(user_id, created_at desc);

create table if not exists public.payment_transactions (
    id uuid primary key default gen_random_uuid(),
    user_id uuid not null references auth.users(id) on delete cascade,
    plan_id text references public.plans(plan_id),
    amount numeric(12,2),
    currency text,
    provider text,
    provider_reference text,
    status text not null default 'pending' check (status in ('pending','succeeded','failed','refunded','cancelled')),
    metadata jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

insert into public.plans(plan_id, name, is_active) values
    ('free','Free',true), ('premium','Premium',true)
on conflict (plan_id) do update set name = excluded.name, is_active = excluded.is_active;

-- Feature rows exist from day one, but limits remain NULL until Engo's owner
-- chooses actual Free quotas. NULL means no configured numerical cap.
insert into public.feature_entitlements(plan_id, feature_key, enabled, free_limit, premium_limit, reset_period)
select p.plan_id, f.feature_key, true, null, null, f.reset_period
from public.plans p
cross join (values
    ('pdf_merge','lifetime'), ('page_themes','lifetime'), ('app_themes','lifetime'),
    ('smart_theme','lifetime'), ('text_chat','daily'), ('voice_chat','daily'),
    ('tags','lifetime'), ('tag_units','lifetime'), ('translations','daily'), ('ai_search','daily')
) as f(feature_key, reset_period)
on conflict (plan_id, feature_key) do nothing;

-- Create a profile automatically for first-time Google/Supabase Auth users.
create or replace function public.handle_new_auth_user()
returns trigger
language plpgsql
security definer
set search_path = public
as $$
begin
    insert into public.profiles(user_id, display_name, avatar_url)
    values (
        new.id,
        coalesce(new.raw_user_meta_data->>'full_name', new.raw_user_meta_data->>'name'),
        new.raw_user_meta_data->>'avatar_url'
    )
    on conflict (user_id) do nothing;
    return new;
end;
$$;

drop trigger if exists on_auth_user_created_engo on auth.users;
create trigger on_auth_user_created_engo
after insert on auth.users
for each row execute procedure public.handle_new_auth_user();

-- Atomic single-device activation and account transfer. The profile row lock
-- serializes concurrent requests, while the partial unique index is the final guard.
create or replace function public.activate_device_v1(
    p_user_id uuid,
    p_device_id text,
    p_device_name text,
    p_app_version text,
    p_allow_transfer boolean default false
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_active public.devices%rowtype;
    v_profile_exists boolean;
    v_now timestamptz := now();
begin
    if p_device_id is null or length(trim(p_device_id)) < 16 or length(p_device_id) > 128 then
        return jsonb_build_object('status','invalid_device','message','Invalid device identifier');
    end if;
    if p_app_version is null or length(trim(p_app_version)) = 0 then
        return jsonb_build_object('status','invalid_build','message','Application version is required');
    end if;

    select true into v_profile_exists from public.profiles where user_id = p_user_id for update;
    if not coalesce(v_profile_exists,false) then
        insert into public.profiles(user_id, display_name, avatar_url)
        select u.id,
               coalesce(u.raw_user_meta_data->>'full_name', u.raw_user_meta_data->>'name'),
               u.raw_user_meta_data->>'avatar_url'
        from auth.users u where u.id = p_user_id
        on conflict (user_id) do nothing;
        perform 1 from public.profiles where user_id = p_user_id for update;
    end if;

    if exists (
        select 1 from public.profiles
        where user_id = p_user_id and account_status <> 'active'
    ) then
        return jsonb_build_object('status','account_suspended','message','Account is suspended');
    end if;

    select * into v_active from public.devices
    where user_id = p_user_id and status = 'active'
    order by activated_at desc limit 1 for update;

    if found and v_active.device_id <> p_device_id and not p_allow_transfer then
        return jsonb_build_object(
            'status','device_conflict',
            'active_device', jsonb_build_object('device_name',v_active.device_name,'device_id',v_active.device_id,'last_seen',v_active.last_seen)
        );
    end if;

    if found and v_active.device_id <> p_device_id and p_allow_transfer then
        update public.devices set status='revoked', updated_at=v_now
        where user_id=p_user_id and device_id=v_active.device_id and status='active';
        insert into public.license_events(user_id,device_id,event_type,details)
        values (p_user_id,v_active.device_id,'device_revoked',jsonb_build_object('moved_to',p_device_id));
    end if;

    insert into public.devices(user_id,device_id,device_name,activated_at,last_seen,status,app_version,updated_at)
    values (p_user_id,p_device_id,coalesce(nullif(trim(p_device_name),''),'Windows PC'),v_now,v_now,'active',p_app_version,v_now)
    on conflict (user_id,device_id) do update set
        device_name=excluded.device_name,
        last_seen=v_now,
        status='active',
        app_version=excluded.app_version,
        updated_at=v_now;

    insert into public.license_events(user_id,device_id,event_type,details)
    values (p_user_id,p_device_id,
            case when p_allow_transfer then 'device_transferred' else 'device_activated' end,
            jsonb_build_object('app_version',p_app_version));

    return jsonb_build_object('status',case when p_allow_transfer then 'transferred' else 'active' end,
                              'device_id',p_device_id,'activated_at',v_now);
end;
$$;

create or replace function public.get_license_context_v1(
    p_user_id uuid,
    p_device_id text,
    p_app_version text
) returns jsonb
language plpgsql
security definer
set search_path = public
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
begin
    select * into v_profile from public.profiles where user_id=p_user_id;
    v_account_active := coalesce(v_profile.account_status, 'active') = 'active';
    select * into v_device from public.devices where user_id=p_user_id and device_id=p_device_id and status='active' limit 1;
    if found then
        update public.devices set last_seen=now(), app_version=p_app_version, updated_at=now()
        where id=v_device.id returning * into v_device;
    end if;

    select exists(select 1 from public.trusted_builds where app_version=p_app_version and is_approved=true)
    into v_build_ok;

    select s.* into v_subscription
    from public.subscriptions s
    join public.plans p on p.plan_id = s.plan_id and p.is_active = true
    where s.user_id=p_user_id and s.status in ('active','trialing')
      and s.starts_at <= now() and (s.ends_at is null or s.ends_at > now())
    order by s.starts_at desc limit 1;
    if found and v_subscription.plan_id='premium' then
        v_plan := 'premium';
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

    select coalesce(jsonb_object_agg(feature_key, jsonb_build_object(
        'enabled',enabled,
        'limit',case when v_plan='premium' then premium_limit else free_limit end,
        'reset_period',reset_period,
        'plan_id',v_plan
    )), '{}'::jsonb)
    into v_entitlements
    from public.feature_entitlements
    where plan_id=v_plan;

    return jsonb_build_object(
        'user_id',p_user_id,
        'device_id',p_device_id,
        'plan_id',v_plan,
        'entitlements',v_entitlements,
        'expires_at',now() + interval '10 minutes',
        'issued_at',now(),
        'app_version',p_app_version,
        'license_status',v_status,
        'subscription',case when v_subscription.id is null then null else jsonb_build_object(
            'plan_id',v_subscription.plan_id,'status',v_subscription.status,
            'starts_at',v_subscription.starts_at,'ends_at',v_subscription.ends_at
        ) end,
        'profile',case when v_profile.user_id is null then '{}'::jsonb else jsonb_build_object(
            'display_name',v_profile.display_name,'avatar_url',v_profile.avatar_url
        ) end
    );
end;
$$;

create or replace function public.consume_feature_usage_v1(
    p_user_id uuid,
    p_device_id text,
    p_app_version text,
    p_feature_key text,
    p_amount bigint default 1
) returns jsonb
language plpgsql
security definer
set search_path = public
as $$
declare
    v_device public.devices%rowtype;
    v_plan text := 'free';
    v_ent public.feature_entitlements%rowtype;
    v_window timestamptz;
    v_used bigint;
    v_limit bigint;
begin
    if not exists(select 1 from public.profiles where user_id=p_user_id and account_status='active') then
        return jsonb_build_object('allowed',false,'message','Account is suspended or unavailable');
    end if;
    select * into v_device from public.devices
    where user_id=p_user_id and device_id=p_device_id and status='active' limit 1;
    if not found then
        return jsonb_build_object('allowed',false,'message','This device is not active');
    end if;
    if p_amount < 1 or p_amount > 1000 then
        return jsonb_build_object('allowed',false,'message','Invalid usage amount');
    end if;

    if exists(select 1 from public.trusted_builds b where b.app_version=p_app_version and b.is_approved=true)
       and exists(select 1 from public.subscriptions s
              join public.plans p on p.plan_id=s.plan_id and p.is_active=true
              where s.user_id=p_user_id and s.plan_id='premium'
              and s.status in ('active','trialing') and s.starts_at <= now()
              and (s.ends_at is null or s.ends_at > now())) then
        v_plan := 'premium';
    end if;
    select * into v_ent from public.feature_entitlements
    where plan_id=v_plan and feature_key=p_feature_key;
    if not found or not v_ent.enabled then
        return jsonb_build_object('allowed',false,'message','This feature is not enabled for the current plan');
    end if;
    v_limit := case when v_plan='premium' then v_ent.premium_limit else v_ent.free_limit end;
    v_window := case v_ent.reset_period
        when 'daily' then date_trunc('day',now())
        when 'monthly' then date_trunc('month',now())
        else '1970-01-01 00:00:00+00'::timestamptz
    end;

    insert into public.usage_counters(user_id,device_id,feature_key,window_start,used,updated_at)
    values(p_user_id,p_device_id,p_feature_key,v_window,0,now())
    on conflict(user_id,feature_key,window_start) do update
        set device_id=excluded.device_id, updated_at=now();
    select used into v_used from public.usage_counters
    where user_id=p_user_id and feature_key=p_feature_key and window_start=v_window
    for update;
    if v_limit is not null and v_used + p_amount > v_limit then
        return jsonb_build_object('allowed',false,'used',v_used,'limit',v_limit,'message','Usage limit reached');
    end if;
    update public.usage_counters set used=used+p_amount, device_id=p_device_id, updated_at=now()
    where user_id=p_user_id and feature_key=p_feature_key and window_start=v_window
    returning used into v_used;
    update public.devices set last_seen=now(), updated_at=now() where id=v_device.id;
    return jsonb_build_object('allowed',true,'used',v_used,'limit',v_limit,'message','');
end;
$$;

-- RLS: clients may read their own account state, never modify server-owned fields.
alter table public.profiles enable row level security;
alter table public.devices enable row level security;
alter table public.plans enable row level security;
alter table public.subscriptions enable row level security;
alter table public.feature_entitlements enable row level security;
alter table public.usage_counters enable row level security;
alter table public.trusted_builds enable row level security;
alter table public.license_events enable row level security;
alter table public.payment_transactions enable row level security;

drop policy if exists profiles_read_own on public.profiles;
create policy profiles_read_own on public.profiles for select to authenticated using (auth.uid()=user_id);
drop policy if exists devices_read_own on public.devices;
create policy devices_read_own on public.devices for select to authenticated using (auth.uid()=user_id);
drop policy if exists plans_read_active on public.plans;
create policy plans_read_active on public.plans for select to authenticated using (is_active=true);
drop policy if exists subscriptions_read_own on public.subscriptions;
create policy subscriptions_read_own on public.subscriptions for select to authenticated using (auth.uid()=user_id);
drop policy if exists usage_read_own on public.usage_counters;
create policy usage_read_own on public.usage_counters for select to authenticated using (auth.uid()=user_id);
drop policy if exists license_events_read_own on public.license_events;
create policy license_events_read_own on public.license_events for select to authenticated using (auth.uid()=user_id);
drop policy if exists payment_transactions_read_own on public.payment_transactions;
create policy payment_transactions_read_own on public.payment_transactions for select to authenticated using (auth.uid()=user_id);
-- feature_entitlements and trusted_builds intentionally have no client policies.

-- Explicit table grants: user-facing reads are RLS-scoped; all writes remain server-only.
grant select on public.profiles, public.devices, public.plans, public.subscriptions,
    public.usage_counters, public.license_events, public.payment_transactions to authenticated;
revoke insert, update, delete, truncate, references, trigger on public.profiles, public.devices,
    public.plans, public.subscriptions, public.feature_entitlements, public.usage_counters,
    public.trusted_builds, public.license_events, public.payment_transactions from anon, authenticated;
grant all on public.profiles, public.devices, public.plans, public.subscriptions,
    public.feature_entitlements, public.usage_counters, public.trusted_builds,
    public.license_events, public.payment_transactions to service_role;
grant usage, select on all sequences in schema public to service_role;

-- Only the Edge Functions' service-role client may call privileged procedures.
revoke all on function public.activate_device_v1(uuid,text,text,text,boolean) from public, anon, authenticated;
revoke all on function public.get_license_context_v1(uuid,text,text) from public, anon, authenticated;
revoke all on function public.consume_feature_usage_v1(uuid,text,text,text,bigint) from public, anon, authenticated;
grant execute on function public.activate_device_v1(uuid,text,text,text,boolean) to service_role;
grant execute on function public.get_license_context_v1(uuid,text,text) to service_role;
grant execute on function public.consume_feature_usage_v1(uuid,text,text,text,bigint) to service_role;

-- Development setup is deliberately separate. Before a build can activate a
-- license, explicitly approve its exact APP_VERSION from a trusted admin session:
-- insert into public.trusted_builds(app_version,is_approved,notes,approved_at)
-- values ('2.3.6', true, 'Development-approved build', now())
-- on conflict (app_version) do update set is_approved=true, approved_at=now();
