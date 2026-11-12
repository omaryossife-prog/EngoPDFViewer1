# تقرير التحقق — وضع الإطلاق المجاني ENGO

- اختبارات مجلد `tests/`: **59 ناجحة**.
- `compileall` لملفات `engo_licensing` و`engo_admin.py` و`main.py`: ناجح.
- Supabase runtime flag: `free_unlimited_mode = true`.
- ترخيص جهاز نشط: 10 ميزات مفعّلة، وكلها بلا حدود.
- استهلاك `tags` دون `scope_key`: `allowed = true`, `used = null`, `limit = null`.
- Edge Functions المنشورة: `account-overview` v6، `subscription-request` v4، `license-check` v4، `device-heartbeat` v4، `usage-consume` v5.

ملاحظات الاختبار:
- أمر pytest على المستودع كله لم يكتمل لأن `tools/test_pen_shape_recognition.py` يتطلب PyQt6، وهو غير مثبت في بيئة العمل. اختبارات مجلد `tests/` اكتملت جميعها.
- لم يتم بناء ملف EXE أو تنفيذ اختبار GUI فعلي على Windows.
- Supabase Security Advisor أظهر معلومة RLS enabled/no policies على `engo_runtime_settings`؛ هذا مقصود: لا توجد صلاحيات للـ anon/authenticated، والوصول من لوحة Engo Admin ودوال الخادم فقط باستخدام service_role. كما أظهر تحذيرًا سابقًا/عامًا بأن حماية كلمات المرور المسرّبة غير مفعّلة في إعداد Auth.
