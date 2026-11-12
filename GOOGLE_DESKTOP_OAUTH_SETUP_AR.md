# إعداد تسجيل الدخول باسم Engo على Google (Windows Desktop)

هذا المسار يفتح Google مباشرة من Engo، ويستقبل Authorization Code على loopback محلي باستخدام PKCE، ثم يرسل Google ID Token إلى Supabase Auth لإنشاء جلسة Engo. لا يحتاج المسار إلى Custom Domain مدفوع.

## 1) إعداد Google OAuth Desktop Client

1. افتح Google Cloud → Google Auth Platform → Clients.
2. أنشئ OAuth Client من نوع **Desktop app** باسم `Engo Windows Desktop`، أو استخدم العميل الحالي.
3. احتفظ بـ **Client ID** العام. لا تضع `client_secret` في `engo_license.json` أو `.env` الخاص ببرنامج المستخدم.
4. تأكد من إعداد شاشة الموافقة وBranding وقائمة Test users حسب وضع النشر.

## 2) إعداد Supabase Google Provider

من Supabase → Authentication → Sign In / Providers → Google:

- احتفظ بـ Web Client ID الحالي وأضف Desktop Client ID في حقل **Client IDs**، مفصولًا بفاصلة.
- احتفظ بسر Web Client الحالي في إعدادات Google Provider؛ لا تستبدله بسر Desktop.
- اترك خيار Skip nonce checks مغلقًا.

## 3) إعداد Engo Desktop Client ID

تأكد أن `google_desktop_client_id` في `engo_license.json` هو Desktop Client ID. هذا المعرّف ليس سرًا ويمكن أن يظهر داخل EXE. ملف المشروع المرفق يحتوي المعرّف العام المحدد للمشروع.

## 4) حفظ سر Desktop على الخادم فقط

في الاختبار السابق أرجع Google الخطأ `client_secret is missing`. لذلك يحتفظ Engo بسر عميل Desktop على خادم Supabase فقط، ولا يرسله البرنامج من جهاز المستخدم.

1. من Google Cloud ألغِ/دوّر أي Desktop Client Secret قديم سبق وضعه داخل ملف إعداد أو حزمة مستخدم.
2. على جهاز المالك فقط، شغّل:

   ```powershell
   python tools/set_google_desktop_secret.py
   ```

   أدخل السر الجديد في نافذة الإدخال المخفية. سيُحفظ في `.secrets/engo-google-desktop-client-secret.txt`، ويظل حقل `google_desktop_client_secret` فارغًا في JSON.
3. بعد أخذ نسخة احتياطية من قاعدة البيانات وتشغيل SQL patch الخاص بالتحديثات، شغّل `tools/deploy_supabase_production.ps1` لرفع السر إلى Edge Function Secrets ونشر `google-oauth-exchange`.

لا تضع السر في محادثة أو Git أو أي ملف توزيع. لا تستخدم Web Client Secret بدل Desktop Client Secret.

## 5) طريقة التحقق

1. شغّل Engo واضغط تسجيل الدخول باستخدام Google.
2. يجب أن يفتح المتصفح صفحة Google مباشرة ثم يعيد المستخدم إلى `127.0.0.1` داخل Engo.
3. بعد إتمام التبادل، يتحقق Supabase Auth من Google ID Token ويصدر جلسة Engo.

إذا ظهر `redirect_uri_mismatch` فتأكد أن العميل من النوع Desktop app، وأن إعدادات OAuth في Google صحيحة. لا تضف رابط Supabase callback إلى Desktop Client.

## ملاحظات أمان

- يستخدم المسار PKCE S256 و`state` وOIDC `nonce`.
- دالة `google-oauth-exchange` تتحقق من Client ID ومن عنوان loopback وتنفذ تبادل الرمز مع Google باستخدام السر المحفوظ على الخادم.
- `google_desktop_client_secret` في إعداد البرنامج يظل فارغًا، والدالة لا تعيد السر إلى العميل.
- Google Desktop Client ID والمفتاح العام Ed25519 ومفتاح Supabase publishable بيانات عامة. أما `ENGO_GOOGLE_DESKTOP_CLIENT_SECRET` ومفتاح Ed25519 الخاص و`service_role` فهي أسرار خادم/مالك ولا يجوز تضمينها في EXE.
- إعداد توقيع الترخيص Ed25519 مستقل عن Google OAuth. لا تولّد مفتاح توقيع جديدًا إذا كان المشروع يستخدم مفتاحًا منشورًا بالفعل؛ يجب أن يظل المفتاح الخاص مطابقًا للمفتاح العام الموجود في إعداد Engo.
