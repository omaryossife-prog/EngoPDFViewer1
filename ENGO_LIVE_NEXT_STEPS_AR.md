# الخطوات المتبقية لتفعيل Google Login والترخيص — Engo

> هذا الملف كان دليل إعداد سابقًا. لتحديثات 12 نوفمبر 2026، اتبع `README_UPDATES_20261112_AR.md`؛ فهو المرجع الأحدث لترتيب SQL والنشر والاشتراكات.

## Google Provider

من Supabase → Authentication → Sign In / Providers → Google:
- فعّل Google.
- احتفظ بـWeb Client ID وWeb Client Secret الحاليين في Provider.
- أضف Desktop Client ID إلى قائمة Client IDs مفصولًا بفاصلة.
- لا تضع Desktop Client Secret في تطبيق المستخدم.

## Desktop OAuth server secret

في حالة ظهور `client_secret is missing`، دوّر Desktop Client Secret الذي سبق تضمينه في أي ملف إعداد أو Build. على جهاز المالك شغّل:

```powershell
python tools/set_google_desktop_secret.py
```

ثم نفّذ `tools/deploy_supabase_production.ps1` بعد تشغيل SQL patch. سيُستخدم السر داخل Edge Function فقط. راجع `GOOGLE_DESKTOP_OAUTH_SETUP_AR.md`.

## رابط العودة

تأكد من إعداد عنوان loopback التالي ضمن إعدادات العودة التي يعتمد عليها مسار Engo:

`http://127.0.0.1:43821/callback`

## مفتاح توقيع الترخيص

مفتاح Ed25519 الخاص مستقل عن Google OAuth. لا تشغّل أدوات توليد مفاتيح جديدة على مشروع يستخدم بالفعل مفتاحًا عامًا منشورًا؛ سيؤدي ذلك إلى عدم تطابق التوقيع مع العملاء الحاليين. احتفظ بالسر الحالي `ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64` في Supabase. سكربت النشر الجديد لا يستبدله ما لم توفر النسخة الأصلية الآمنة في `.secrets/`.

## اختبارات ما قبل اعتماد Build

- تجربة تسجيل الدخول بحساب Google مسموح به.
- التأكد من عودة callback وحفظ جلسة Supabase في مخزن Windows المحمي.
- التأكد من نجاح تحقق Ed25519 بالمفتاح العام المضمن في البرنامج.
- اختبار heartbeat والترخيص عند الرفض أو الانقطاع.
- اختبار PDF وGemini Live.
- اعتماد إصدار Windows بعد بنائه وتوقيعه واختباره، ثم إضافته إلى `trusted_builds` حسب سياسة المشروع.
