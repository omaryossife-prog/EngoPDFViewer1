# استكشاف أخطاء Google Desktop OAuth

## خطأ `client_secret is missing`

يجب ألا يوضع السر داخل ملف البرنامج. التبادل أصبح يتم من خلال Edge Function باسم `google-oauth-exchange`، والسر يقرأه الخادم من `ENGO_GOOGLE_DESKTOP_CLIENT_SECRET`.

1. افتح Google Cloud → Google Auth Platform → Clients.
2. استخدم Client Secret الخاص بعميل `Engo Windows Desktop` من نوع Desktop app، وليس سر عميل Web.
3. إذا كان السر قد سبق وضعه في `engo_license.json` أو توزيعه داخل حزمة، ألغِه/دوّره أولًا من Google Cloud.
4. على جهاز المالك شغّل `python tools/set_google_desktop_secret.py` وأدخل السر الجديد في الحقل المخفي.
5. خذ نسخة احتياطية من قاعدة البيانات، شغّل `SUPABASE_PATCH_20261112.sql` في SQL Editor، ثم شغّل `tools/deploy_supabase_production.ps1` لرفع السر ونشر الدالة.
6. تحقق من أن إعداد `google_desktop_client_id` في Engo يطابق Desktop Client ID الذي أُعد على Google.

ملف الإعداد العام يجب أن يظل بالشكل التالي، من دون أي قيمة سرية:

```json
{
  "google_desktop_client_id": "YOUR_DESKTOP_CLIENT_ID.apps.googleusercontent.com",
  "google_desktop_client_secret": ""
}
```

## خطأ أن سر الخادم غير مضبوط

إذا أرجعت الدالة رسالة تفيد أن السر غير مضبوط، أعد تشغيل أداة `set_google_desktop_secret.py` ثم أعد تنفيذ سكربت النشر. تأكد أنك تنشر إلى مشروع Supabase الصحيح. لا ترسل السر في المحادثة أو إلى Git.

## خطأ `redirect_uri_mismatch`

تأكد من استعمال OAuth Client من النوع Desktop app. عنوان العودة في Engo هو loopback المحلي، ولا ينبغي استخدام Web Client أو Web callback مكانه.

## الفرق بين السر الخاص بـGoogle ومفتاح Ed25519

سر Google Desktop يستخدم فقط لإتمام تبادل رمز OAuth على الخادم. مفتاح Ed25519 الخاص يستخدم لتوقيع سياق الترخيص على الخادم. لا تخلط بينهما ولا تضع أيًّا منهما في برنامج المستخدم. إذا كان مفتاح Ed25519 الحالي مضبوطًا في Supabase فلا تنشئ بديلًا؛ أي تدوير يتطلب نشر المفتاح العام المطابق في إعدادات كل العملاء.
