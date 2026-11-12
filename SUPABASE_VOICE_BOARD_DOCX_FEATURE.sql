-- Premium-only Word export for the Voice & Learn teaching board.
-- Safe to run more than once: the (plan_id, feature_key) pair is unique.
insert into public.feature_entitlements
    (plan_id, feature_key, enabled, free_limit, premium_limit, reset_period, updated_at)
values
    ('free', 'voice_board_docx', false, 0, null, 'lifetime', now()),
    ('premium', 'voice_board_docx', true, null, null, 'lifetime', now())
on conflict (plan_id, feature_key) do update
set enabled = excluded.enabled,
    free_limit = excluded.free_limit,
    premium_limit = excluded.premium_limit,
    reset_period = excluded.reset_period,
    updated_at = now();
