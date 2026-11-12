# إعداد Engo للإنتاج — ملاحظات تاريخية

هذا الدليل يصف إعداد الترخيص السابق وقد يحتوي على خطوات لم تعد مناسبة للنسخة الحالية. اتبع `README_UPDATES_20261112_AR.md` أولًا لترتيب SQL والاشتراكات والنشر، و`GOOGLE_DESKTOP_OAUTH_SETUP_AR.md` لإعداد Google OAuth.

**تنبيه مفتاح التوقيع:** `engo_license.json` يحتوي على مفتاح Ed25519 عام بالفعل. يجب أن يطابقه المفتاح الخاص في جهاز المالك أو في Supabase. لا تشغّل `tools/generate_license_signing_keys.py` دون قصد تدوير المفتاح؛ الأداة تتطلب الآن `--rotate-existing-public-key` للتدوير الصريح. راجع `ENGO_SIGNING_SETUP_AR.md` إذا كان المفتاح الخاص غير متاح.

مفاتيح `service_role` و`ENGO_LICENSE_SIGNING_PRIVATE_KEY_PKCS8_B64` و`ENGO_GOOGLE_DESKTOP_CLIENT_SECRET` تبقى على جهاز المالك/خادم Supabase فقط. لا تُضمّن في Build المستخدم.
