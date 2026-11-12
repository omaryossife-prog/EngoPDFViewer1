create table if not exists public.app_update_settings (
    id boolean primary key default true check (id is true),
    enabled boolean not null default false,
    latest_version text not null default '2.3.7',
    update_url text,
    message_ar text,
    message_en text,
    updated_at timestamptz not null default now(),
    constraint app_update_settings_latest_version_format
        check (latest_version ~ '^[0-9]+(\\.[0-9]+){1,3}$'),
    constraint app_update_settings_update_url_https
        check (update_url is null or update_url ~* '^https://')
);

insert into public.app_update_settings (
    id, enabled, latest_version, update_url, message_ar, message_en, updated_at
) values (
    true, false, '2.3.7', null, null, null, now()
) on conflict (id) do nothing;

alter table public.app_update_settings enable row level security;
revoke all on table public.app_update_settings from public, anon, authenticated;
grant all on table public.app_update_settings to service_role;

-- The source release introduced with this migration is trusted by default.
-- Older versions remain independently switchable from the Trusted Builds tab.
insert into public.trusted_builds (app_version, is_approved, notes, approved_at)
values ('2.3.7', true, 'ENGO update notifications and supported-build policy', now())
on conflict (app_version) do nothing;
