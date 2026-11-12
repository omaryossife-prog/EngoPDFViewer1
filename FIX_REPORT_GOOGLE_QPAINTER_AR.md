# تقرير تاريخي: Google OAuth وQPainter

هذا التقرير يصف مرحلة سابقة من الإصلاح. في تلك المرحلة أُضيف حقل محلي باسم `google_desktop_client_secret` وتُرك حقلًا داخل ملف الإعداد. **هذا التصميم لم يعد معتمدًا**.

في تحديث 12 نوفمبر 2026 نُقل تبادل رمز Google إلى Edge Function `google-oauth-exchange`. يجب أن يظل `google_desktop_client_secret` فارغًا في `engo_license.json`، ويُحفظ `ENGO_GOOGLE_DESKTOP_CLIENT_SECRET` في Supabase Edge Function Secrets فقط. أداة المالك `tools/set_google_desktop_secret.py` تحفظ السر محليًا في مجلد `.secrets/` المستبعد من الحزمة، ثم يرفعه سكربت النشر.

راجع `GOOGLE_DESKTOP_OAUTH_SETUP_AR.md` و`README_UPDATES_20261112_AR.md` للإجراءات الحالية. لا تستخدم خطوات النسخ المحلية الواردة في أي نسخة قديمة من هذا التقرير.
