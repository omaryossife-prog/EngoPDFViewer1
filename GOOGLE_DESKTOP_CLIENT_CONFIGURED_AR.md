# إعداد Google Desktop Client في Engo

Desktop Client ID العام المستخدم في إعداد Engo:

`1091311923605-uk5q13ptile9poq88sp8sg7n08uo5v1c.apps.googleusercontent.com`

في Supabase → Authentication → Sign In / Providers → Google، احتفظ بـWeb Client ID الحالي وأضف Desktop Client ID إلى حقل **Client IDs** مفصولًا بفاصلة. احتفظ بسر Web Client الحالي كما هو، ولا تستخدمه في تبادل Desktop.

لا تضع Desktop Client Secret في `engo_license.json` أو أي ملف توزيع. إذا طلبت استجابة Google السر، أدخله من جهاز المالك باستخدام `python tools/set_google_desktop_secret.py` ثم ارفعه بواسطة `tools/deploy_supabase_production.ps1` بعد تشغيل SQL patch. راجع `GOOGLE_DESKTOP_OAUTH_SETUP_AR.md` للتفاصيل.
