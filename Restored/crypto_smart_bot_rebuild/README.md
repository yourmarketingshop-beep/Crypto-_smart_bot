# Crypto Smart Bot — الإصدار 24

مشروع Flutter للهاتف مع خادم FastAPI لتحليل بيانات السوق العامة من Binance والتداول الافتراضي فقط.

## رفع المشروع من الهاتف إلى GitHub
1. فك ضغط الحزمة إن أمكن، أو ارفع ملف ZIP إلى مستودعك ثم استخدم خيار Add file لرفع الملفات بعد فك الضغط محلياً.
2. يجب أن تكون محتويات هذا المجلد في جذر المستودع، وليس داخل مجلد إضافي اسمه `crypto_smart_bot_rebuild`.
3. تأكد من ظهور المجلد `.github/workflows` والملف `android-apk.yml` في المستودع.
4. افتح تبويب Actions وشغّل سير العمل `Crypto Smart Bot checks and Android APK`.
5. رابط API الافتراضي مخصص لمحاكي Android. على الهاتف الحقيقي لا بد من عنوان خادم FastAPI يمكن للهاتف الوصول إليه، ويفضل HTTPS.

## المكونات
- `backend/`: خادم FastAPI وقاعدة SQLite واختبارات التداول الافتراضي.
- `flutter_app/`: واجهة Flutter وملفات تجهيز Android وبناء APK.
- `.github/workflows/android-apk.yml`: اختبار الخادم ثم بناء APK ونشره كـ Artifact.
- `INSTALL_AR.md`: دليل التثبيت والتشغيل بالعربية.
- `docs/README_AR.md`: شرح المشروع بالعربية.

## اختبار الخادم محلياً
```bash
cd backend
python -m pip install -r requirements.txt
PYTHONPATH=. pytest -q
```

## الأمان
هذا المشروع PAPER ONLY. لا تضف مفاتيح Binance أو أسراراً أو كلمات مرور إلى المستودع. لا توجد أوامر تداول حقيقية. الاختبارات لا تضمن أرباحاً مستقبلية.
