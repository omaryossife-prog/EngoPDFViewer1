-- Add an annual Premium subscription period (12 months).
alter table public.subscription_prices
    drop constraint if exists subscription_prices_billing_period_check;
alter table public.subscription_prices
    add constraint subscription_prices_billing_period_check
    check (billing_period = any (array['monthly'::text, 'quarterly'::text, 'semiannual'::text, 'annual'::text]));

alter table public.subscription_prices
    drop constraint if exists subscription_prices_duration_months_check;
alter table public.subscription_prices
    add constraint subscription_prices_duration_months_check
    check (duration_months = any (array[1, 3, 6, 12]));

alter table public.subscription_prices
    drop constraint if exists subscription_prices_check;
alter table public.subscription_prices
    add constraint subscription_prices_check
    check (
        (billing_period = 'monthly' and duration_months = 1) or
        (billing_period = 'quarterly' and duration_months = 3) or
        (billing_period = 'semiannual' and duration_months = 6) or
        (billing_period = 'annual' and duration_months = 12)
    );

-- Keep the annual option visible in Engo Admin. The admin sets the real price.
insert into public.subscription_prices
    (plan_id, billing_period, duration_months, amount, currency, is_active)
values
    ('premium', 'annual', 12, 0, 'EGP', true)
on conflict (plan_id, billing_period) do nothing;

create or replace function public.admin_approve_qr_payment_v1(p_payment_id uuid)
returns jsonb
language plpgsql
set search_path to ''
as $function$
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
$function$;
