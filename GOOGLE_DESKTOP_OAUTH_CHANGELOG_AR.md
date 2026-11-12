# سجل تحديث Google Desktop OAuth

- يفتح Engo Google مباشرة باستخدام Authorization Code + PKCE + state + nonce، ثم يعيد ID Token إلى Supabase Auth لإنشاء جلسة المستخدم.
- Desktop Client ID قيمة عامة ويمكن تضمينها في البرنامج.
- تم نقل تبادل الرمز إلى Edge Function باسم `google-oauth-exchange`؛ سر Desktop Client لا يُقرأ من إعداد Engo ولا يُرسل من جهاز المستخدم.
- يُخزن سر Google Desktop في Supabase Edge Function Secrets باسم `ENGO_GOOGLE_DESKTOP_CLIENT_SECRET`، ويُدخل على جهاز المالك من خلال `tools/set_google_desktop_secret.py`.
- يظل حقل `google_desktop_client_secret` في `engo_license.json` فارغًا للتوافق مع ملفات الإعداد القديمة.
- لا تستخدم Web Client Secret في مسار Desktop. احتفظ بإعداد Web Provider في Supabase كما هو وأضف Desktop Client ID إلى Client IDs.
- لاختبار إصدار حالي، راجع `GOOGLE_DESKTOP_OAUTH_SETUP_AR.md` ثم `README_UPDATES_20261112_AR.md`.
