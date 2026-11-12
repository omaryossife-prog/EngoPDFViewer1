# تقرير التحقق — Engo v17 / Supabase Live

تاريخ التحقق: 2026-11-11 (Africa/Cairo)

## حالة مشروع Supabase الفعلي

- المشروع: Engo Pdf
- Project Ref: `milksrcwbqmkczlhjfsi`
- الخطة: Free
- الحالة: ACTIVE_HEALTHY
- قاعدة البيانات: PostgreSQL 17

## ما تم تطبيقه والتحقق منه

- Migration `20261111004326_engo_accounts_licensing` — مسجلة في سجل migrations.
- Migration `20261111004443_engo_security_performance_hardening` — مسجلة في سجل migrations.
- الجداول التسعة موجودة في `public`، وجميعها يظهر أن RLS مفعّل عليها.
- `plans`: سجلان Free/Premium.
- `feature_entitlements`: 20 سجلًا أوليًا (10 لكل باقة). جميع حدود الاستخدام الرقمية `NULL` حاليًا لأنها لم تُحدد من صاحب المنتج؛ لا توجد أرقام مفترضة.
- Edge Functions الست: `account-overview`, `device-activate`, `device-transfer`, `device-heartbeat`, `license-check`, `usage-consume`، وجميعها `ACTIVE`, `verify_jwt=true`.
- `@supabase/supabase-js` داخل مصادر الوظائف مثبت على `2.119.0`.
- Security Advisor: `0` findings بعد Migration التصحيحية.
- Performance Advisor: ملاحظات INFO فقط لفهارس جديدة لم تُستخدم بعد على قاعدة جديدة؛ ليست أخطاء تشغيل.

## إعداد Google OAuth

- Google Cloud project `engo-authentication` موجود.
- OAuth consent screen من نوع External وبحالة Testing.
- تم التحقق من وجود مستخدم اختبار واحد في Audience.
- لقطة إعداد Google Provider اللاحقة أظهرت Google Enabled وحقلي Client ID وClient Secret مملوءين؛ لم يتم تأكيد الضغط على Save أو نجاح حفظ الإعداد.
- Additional Redirect URL `http://127.0.0.1:43821/callback` أُضيف بنجاح، وظهر إشعار `Successfully added 1 URL`.
- لا يوجد Client Secret داخل المستودع أو الحزم.

## إعداد توقيع الترخيص

- Edge Functions مهيأة لقراءة `ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64` من أسرار السيرفر.
- هذا السر لم يُضف بعد؛ لذلك لا تتوفر استجابات ترخيص موقعة حتى إضافته.
- `engo_license.json` يحتوي القيم العامة فقط، وحقل المفتاح العام فارغ حتى توليد زوج المفاتيح على جهاز Windows.
- لا يوجد إصدار مدرج في `trusted_builds`؛ الإصدار `2.3.6` لم يُعتمد لأن EXE لم يُبنَ ويُوقّع ويُختبر بعد.

## الاختبارات المحلية

الأمر: `python -m pytest -q tests/test_licensing_core.py tests/test_pdf_ops.py tests/test_supabase_release_assets.py`

النتيجة: `33 passed (latest targeted run)`.

الأمر: `python -m compileall -q main.py engo_licensing tools/generate_license_signing_keys.py`

النتيجة: نجاح دون أخطاء صياغة.

كما تم تنفيذ smoke test لمولد Ed25519 باستخدام مجلد مؤقت، والتحقق من كتابة مفتاح عام 32-byte في ملف إعداد مؤقت دون طباعة المفتاح الخاص. لم يتم توليد مفتاح الإنتاج الفعلي.

## ما لم يتم اختباره أو إكماله

- لم يُنفذ تسجيل دخول Google حي حتى يتم إعداد Provider في Supabase.
- لم يتم اختبار callback على Windows أو تخزين DPAPI الفعلي في جهاز المستخدم.
- لم يتم اختبار Gemini Live على Windows.
- لم يتم بناء EXE أو Installer، ولم يتم اعتماد build في `trusted_builds`.
- لا توجد بوابة دفع أو أسعار مفعلة.

لا يتم تضمين أي مفاتيح سرية في هذا التقرير أو الحزم. لا يتم طلب Billing أو Google Cloud Free Trial لهذه الخطوات.


## تحديث متابعة 2026-11-11

- تمت إضافة أداة Windows `SETUP_ENGO_SIGNING_SECRET.bat` و`tools/setup_engo_signing_secret.ps1`.
- الأداة تولد الزوج محليًا، تتحقق أن المفتاح العام يطابق الخاص، تحفظ المفتاح العام فقط داخل `engo_license.json`، وترفع الخاص باسم `ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64` باستخدام Supabase CLI.
- لم يتم توليد مفتاح الإنتاج أو رفع السر بعد؛ يلزم تشغيل الأداة على جهاز Windows الخاص بالمالك.
- يلزم تأكيد حفظ Google Provider ومطابقة Client ID/Client Secret مع نفس OAuth Client الذي يحتوي Google Callback URI. ظهرت معرفات عميلين مختلفة في لقطات Google Cloud السابقة، لذلك يجب مطابقة العميل قبل اختبار الدخول.


## تحديث 2026-11-11 — متابعة Google والتوقيع

- لقطة Supabase Provider أظهرت Google Enabled وحقلي Client ID/Secret مملوءين، لكن لم يتم التقاط رسالة نجاح الحفظ؛ يجب التأكد من الضغط على Save.
- صفحة URL Configuration أظهرت نجاح إضافة `http://127.0.0.1:43821/callback` برسالة `Successfully added 1 URL`.
- توجد نقطة مطابقة يجب التحقق منها: Client ID في لقطة Supabase Provider ينتهي بـ`933f...` بينما نافذة إنشاء OAuth Client السابقة أظهرت معرفًا ينتهي بـ`561o3...`. يجب أن يحتوي نفس OAuth Client المستخدم داخل Supabase على Google Authorized redirect URI `https://milksrcwbqmkczlhjfsi.supabase.co/auth/v1/callback`.
- أضيفت أداة Windows لتوليد Ed25519 ورفع المفتاح الخاص مباشرة باستخدام Supabase CLI، دون إدخال السر في المحادثة. لم يتم توليد مفتاح الإنتاج أو رفعه حتى الآن.
- إصلاح سياسة Startup: الحالات الموقعة `untrusted_build` و`account_suspended` و`device_not_active` تستمر في الوضع المحلي Free ولا تمنع فتح PDF؛ لا تمنح أي منها Premium.
- الاختبارات المستهدفة: `33 passed`. فحص `compileall`: ناجح. Smoke test لمولد المفتاح يستخدم زوجًا مؤقتًا فقط ويثبت تطابق الخاص والعام؛ لم يُنشأ مفتاح إنتاج.
