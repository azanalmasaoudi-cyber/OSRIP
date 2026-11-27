# تشغيل OSRIP مركزيًا لكل الفريق

النسخة الإنجليزية: `docs/CENTRAL_HOSTING_EN.md`. تفاصيل الخادم: `docs/DEPLOYMENT.md`.

**الحالة في 27 نوفمبر 2026: غير منشور.** العنوان `https://osrip.vercel.app` يعرض الواجهة فقط. الأمر
`python tools/check_public_osrip.py https://osrip.vercel.app` ينجح في الصفحة وHSTS ويفشل في الخادم:
المسار `/api/v1/health/ready` يجيب بخطأ 404 من Vercel دون ترويسة `X-OSRIP-API` الخاصة بـ OSRIP. لم يُقدَّم
خادم ولا حساب استضافة ولا صلاحية DNS، ولم يُنشأ أو يُدفع أي شيء. لا تُعلن أن OSRIP منشور قبل نجاح هذا الفحص
على العنوان الحقيقي ونجاح اختبارات القبول في آخر هذه الصفحة من جهازين.

## التصميم (موجود في `deploy/`)

```
5 أجهزة -> HTTPS (Caddy، المنفذان 80 و443) -> الواجهة و/api/v1 -> FastAPI -> PostgreSQL 17 (خاص)
```

يشغّل `deploy/docker-compose.yml` خمس خدمات:
- `db`: PostgreSQL 17، وبياناته على المجلد الدائم `pgdata`؛
- `migrate`: مهمة لمرة واحدة (`alembic upgrade head`)؛
- `api`: FastAPI، بمستخدم غير جذري، ولا يبدأ إلا بعد نجاح الترحيلات؛
- `web`: Caddy يعرض الواجهة ويمرر `/api`، مع شهادات HTTPS تلقائية وترويسات الأمان؛
- `backup`: نسخة `pg_dump` ليلية تُحفظ 14 يومًا.

ما رُوجع في 27 نوفمبر 2026 وصار يفرضه `deploy/predeploy_check.py` واختبارات
`backend/tests/test_hosting_tools.py`:
- **خادم الويب وحده ينشر منافذ (80 و443).** لا ينشر PostgreSQL ولا الخادم أي منفذ. لا تفتح المنفذ 5432
  للإنترنت أبدًا.
- **قاعدة البيانات على المجلد الدائم**، وينتظر الخادم انتهاء الترحيلات، وصورته تعمل بمستخدم غير جذري.
- **لا يدخل سر ولا نسخة احتياطية في أي صورة:** ملفات `.env` و`*.backup` و`*.dump` و`.osrip-local.json`
  مستبعدة في `.dockerignore`.
- **لا بيانات تجريبية مُصطنعة على خادم حقيقي.** يحمّلها `deploy/remote_up.sh` فقط مع
  `OSRIP_LOAD_SYNTHETIC_DEMO_DATA=1`، وكان قبل 27 نوفمبر يحمّلها دائمًا.
- **فحص ما قبل النشر يعرف مزوّدي الذكاء الاصطناعي الحقيقيين** (anthropic وopenai وgemini وdeepseek أو
  disabled). ما زال يرفض مزوّد الاختبار، وينبّه عند غياب المفتاح أو النموذج أو موافقة الفوترة لـ DeepSeek.
- **الحسابات اسم مستخدم وكلمة مرور**، فصار `.env.example` يضبط `OSRIP_EMAIL_BACKEND=disabled`. ومزوّد
  الذكاء الاصطناعي معطّل افتراضيًا: الاستخدام المدفوع يحتاج موافقة المالك.

Docker غير مثبت على جهاز التطوير، فلم تُبنَ الصور ولم تُشغَّل هنا. فُحص ملف compose فحصًا ثابتًا: قُرئ،
واختُبرت كل قاعدة أعلاه.

## ما يقدمه المالك وحده

1. **خادم Linux** (مثل Ubuntu 24.04، معالجان افتراضيان، 4 جيجابايت ذاكرة، قرص دائم) مع Docker وCompose، وقرار
   الدفع مقابله.
2. **اسم DNS تملكه** يشير إلى الخادم، مثل `osrip.<نطاقك>`. لا تستخدم `osrip.project.com` إلا إن كنت تتحكم
   في ذلك النطاق.
3. **قرار البيانات:**
   - نقل كل شيء من الجهاز الأصلي (الحسابات وتجزئات كلمات المرور والسجل)؛ أو
   - نشر البيانات الرسمية المعتمدة فقط على قاعدة جديدة.
4. **مفتاح الذكاء الاصطناعي اختياريًا**، يُدخل على الخادم فقط.

لا ترسل كلمات مرور ولا مفاتيح ولا نسخ قواعد بيانات في المحادثات، ولا ترفعها إلى المستودع.

## 1. نسخة احتياطية من الجهاز الأصلي (Windows)

وقاعدة التطوير تعمل (شغّل OSRIP مرة، أو
`backend\.venv\Scripts\python.exe backend\scripts\devdb.py start`):

```powershell
powershell -ExecutionPolicy Bypass -File .\tools\Backup-OSRIP-Local.ps1
```

ما يفعله:
- يقرأ `osrip_dev` ولا يغيّرها أبدًا. يكتب `Documents\OSRIP-Backups\osrip_dev-<التاريخ>-<الوقت>.backup`
  ومعه بيان `.backup.json`: بصمة SHA-256 ونسخة الترحيل والعدد الدقيق لصفوف كل جدول، ولا أسرار فيه.
- قبل إعلان النجاح يتحقق من أن `pg_restore` يقرأ الأرشيف.
- يرفض مجلدًا داخل المستودع ولا يستبدل ملفًا موجودًا.

الخيار `-Database osrip_preview` ينسخ قاعدة محلية أخرى.

النسخة تحوي كل الحسابات وتجزئات كلمات المرور والسجلات: احفظها مشفرة (مثل BitLocker أو أرشيف 7-Zip بتشفير AES)،
وبعيدًا عن GitHub والبريد والمحادثات. يرفض `.gitignore` وفحص ما قبل النشر الملفات `*.backup` و`*.dump`
والمجلد `OSRIP-Backups/` داخل المستودع.

## 2أ. النقل إلى جهاز Windows آخر

1. ثبّت Git وPython 3.13 وNode.js 24، وانسخ المستودع، وشغّل `start-osrip.cmd` مرة. هذا ينشئ عنقود قاعدة
   التطوير وقاعدة `osrip_dev` ببيانات العرض التجريبية. ثم أوقفه.
2. انقل ملف `.backup` وبيانه `.backup.json` إلى ذلك الجهاز بطريقة خاصة، ثم:

   ```powershell
   powershell -ExecutionPolicy Bypass -File .\tools\Restore-OSRIP-Backup.ps1 -Backup <الملف.backup> -Database osrip_restored -Migrate
   ```

   - يطابق بصمة SHA-256 للملف مع البيان.
   - يستعيد في القاعدة **الجديدة** دون `--clean` أبدًا. ترفض أي قاعدة موجودة مثل `osrip_dev`، ولا تُستبدل.
   - يقارن عدد صفوف كل جدول ونسخة الترحيل بالبيان.
   - الخيار `-Migrate` يطبّق بعدها ترحيلات النسخة الحالية من المستودع على النسخة المستعادة.
3. ضع `{"database": "osrip_restored"}` في ملف `.osrip-local.json` لتلك النسخة وشغّل OSRIP. سجّل الدخول بحساب
   موجود وافحص قطاعًا والخريطة ودراسة محفوظة. أما استبدال `osrip_dev` نفسها فقرار منفصل للمالك وحده.

تم التحقق على هذا الجهاز في 27 نوفمبر 2026 (`docs/TEST_RESULTS.md`): نسخ `osrip_dev`، ثم الاستعادة في قاعدة
جديدة، ثم مقارنة 70 جدولًا دون أي اختلاف، ثم الترحيل من 0034 إلى 0036. وحُذفت قاعدة التجربة بعدها.

## 2ب. نقل البيانات إلى الخادم (خادم جديد فارغ)

على الخادم، من جذر المستودع، وبعد ملء `deploy/.env` (الخطوة 3):

```bash
compose() { docker compose -f deploy/docker-compose.yml --env-file deploy/.env "$@"; }
compose up -d db                                  # قاعدة البيانات وحدها
compose exec -T db psql -U osrip -d osrip -tAc \
  "SELECT count(*) FROM information_schema.tables WHERE table_schema='public'"
# يجب أن يطبع 0: الاستعادة في قاعدة فارغة فقط
compose exec -T db pg_restore -U osrip -d osrip --no-owner --no-acl --exit-on-error \
  < osrip_dev-YYYYMMDD-HHMMSS.backup
compose exec -T db psql -U osrip -d osrip -tA -c "$(python3 tools/compare_restore_counts.py --sql)" > counts.txt
python3 tools/compare_restore_counts.py osrip_dev-YYYYMMDD-HHMMSS.backup.json counts.txt
# يجب أن يطبع "Match: ... as in the backup" قبل المتابعة
compose up -d --build                             # يرحّل migrate إلى أحدث نسخة، ثم يبدأ api وweb
```

قواعد:
- **لا تستخدم أبدًا** `pg_restore --clean` أو `--if-exists` أو `DROP DATABASE` على قاعدة فيها بيانات، إلا بقرار
  صريح من المالك ونسخة احتياطية حديثة منها.
- على خادم فيه مستخدمون، انسخ قاعدته أولًا (`compose exec -T db pg_dump -U osrip -Fc osrip > before-restore.dump`)،
  ثم استعد في قاعدة منفصلة وقارن قبل تحويل أي شيء.
- نسخة PostgreSQL: عنقود التطوير 17.11 وصورة الخادم `postgres:17`، فتُستعاد النسخ مباشرة.
- إن أردت نشر البيانات الرسمية المعتمدة فقط، فتجاوز هذه الخطوة وابدأ بقاعدة فارغة، ثم انشر عبر مسار الاستيراد
  المراجَع في إدارة البيانات.

## 3. ضبط الخادم وتشغيله

```bash
cp deploy/.env.example deploy/.env    # على الخادم فقط؛ لا يُرفع أبدًا
# املأ:
#   POSTGRES_PASSWORD وOSRIP_CLIENT_HASH_KEY: 32 حرفًا عشوائيًا أو أكثر لكل منهما
#     (python3 -c "import secrets; print(secrets.token_urlsafe(48))")
#   OSRIP_DOMAIN وOSRIP_PUBLIC_BASE_URL=https://<النطاق> وOSRIP_CORS_ORIGINS=["https://<النطاق>"]
#   OSRIP_EMAIL_BACKEND=disabled (حسابات اسم مستخدم وكلمة مرور)
#   مزوّد الذكاء الاصطناعي: disabled، أو مزوّد واحد بمفتاحه ونموذجه (بموافقة المالك على الاستخدام المدفوع)
python3 deploy/predeploy_check.py                 # أصلح كل FAIL أولًا
sh deploy/remote_up.sh                            # أو: docker compose ... up -d --build
python3 deploy/predeploy_check.py --url https://<النطاق>
python3 tools/check_public_osrip.py https://<النطاق>
```

افتح للعامة المنفذين 80 و443 فقط، وSSH للمسؤولين (بمفتاح، ومقيدًا بعنوان المصدر متى أمكن). أنشئ المسؤول بالأمر
`compose run --rm api python -m app.cli ensure-admin --username <الاسم>`، وتُكتب كلمة المرور عند الطلب ولا تُحفظ.
هذه الخطوة للقاعدة الفارغة فقط: الحسابات المستعادة موجودة.

## 4. النسخ الاحتياطية على الخادم

خدمة `backup` تكتب نسخة ليلية في المجلد `backups` وتحتفظ بها 14 يومًا **على القرص نفسه**، وهذا لا ينجو من
فقدان الخادم.

انسخ الملفات خارج الخادم مشفرة إلى وجهة يختارها المالك ويأذن بها. لم يُضبط ذلك بعد لعدم تقديم وجهة. جرّب
الاستعادة كل شهر في قاعدة معزولة مع `compare_restore_counts.py`.

## 5. القبول قبل إعلان العنوان

1. ينجح `check_public_osrip.py https://<النطاق>`: الصفحة وHSTS وجاهزية الخادم.
2. من جهازين مختلفين خارج شبكة الخادم:
   - سجّل الدخول بحسابين، وتحقق أن المشاهد لا يصل إلى إدارة البيانات؛
   - الكهرباء والمياه تعرض بيانات معتمدة موسومة، لا بيانات مصطنعة؛
   - اختر محافظة ثم ولاياتها على الخريطة؛
   - يجيب الملهم فقط إذا ضُبط مزوّد ومفتاح، وإلا يقول إنه غير متاح.
3. أعد تشغيل الخادم وتأكد من بقاء البيانات، واستعد نسخة الليلة الماضية في قاعدة معزولة وقارنها.

بعد نجاح الثلاثة فقط: أعلن العنوان للفريق.
