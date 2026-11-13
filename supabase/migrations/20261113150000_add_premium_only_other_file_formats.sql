-- Keep all non-PDF formats Premium-only, independent of the Free launch-mode switch.
insert into public.feature_entitlements
    (plan_id, feature_key, enabled, free_limit, premium_limit, reset_period)
values
    ('free', 'open_other_formats', false, 0, null, 'lifetime'),
    ('premium', 'open_other_formats', true, null, null, 'lifetime')
on conflict (plan_id, feature_key) do update
set enabled = excluded.enabled,
    free_limit = excluded.free_limit,
    premium_limit = excluded.premium_limit,
    reset_period = excluded.reset_period,
    updated_at = now();
