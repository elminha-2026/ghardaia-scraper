import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات قاعدة البيانات Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("❌ لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في متغيرات البيئة (Environment Variables).")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. قوائم بلديات ولاية غرداية والفلترة
# ==========================================

# بلديات ولاية غرداية الـ 10
GHARDAIA_MUNICIPALITIES = [
    "غرداية",
    "بني يزقن",
    "العطف",
    "بونورة",
    "ضواحي غرداية",
    "القرارة",
    "بريان",
    "متليلي",
    "سبسب",
    "المنصورة",
    "زلفانة"
]

# الكلمات المفتاحية الأساسية الصريحة
MUST_MATCH_KEYWORDS = [
    "أبو إسحاق أطفيش",
    "ابو اسحاق اطفيش",
    "إبراهيم أطفيش",
    "ابراهيم اطفيش",
    "جمعية الشيخ أبي إسحاق",
    "جمعية الشيخ ابي اسحاق",
    "جمعية أطفيش",
    "تراث غرداية",
    "جمعية التراث غرداية"
]

# كلمات سياقية مساندة تشمل بلديات غرداية والمعالم التراثية
CONTEXT_KEYWORDS = GHARDAIA_MUNICIPALITIES + [
    "تراث", "ميزاب", "وادي ميزاب", "الجزائر", "مخطوطات", 
    "فقه", "تاريخ", "المكتبة", "المؤسس", "الشيخ", 
    "الإباضية", "مكتبة القطب", "قصر غرداية", "قصر بني يزقن",
    "قصر العطف", "قصر بونورة", "قصر القرارة", "قصر بريان"
]

# كلمات الاستبعاد (تستبعد الخبر فوراً لمنع القصاصات الخاطئة)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع", "شقة للبيع",
    "دوري روشن", "أبطال أوروبا", "أسعار الذهب", "سعر الدولار"
]

# ==========================================
# 3. الدوال المساعدة ومعالجة النصوص
# ==========================================

def clean_text(text: str) -> str:
    """تنظيف النص من وسوم HTML والمسافات الزائدة"""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def parse_date(date_str: str) -> str:
    """تحويل تواريخ RSS إلى صيغة YYYY-MM-DD"""
    if not date_str:
        return datetime.utcnow().strftime("%Y-%m-%d")
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")

def is_relevant_article(title: str, summary: str) -> bool:
    """
    الدالة المحورية للفلترة: تفحص العنوان والملخص لضمان الصلة بالتراث وببلديات غرداية
    """
    combined_text = clean_text(f"{title} {summary}").lower()

    # 1. الاستبعاد الفوري عند وجود كلمات مستبعدة
    for exc in EXCLUDE_KEYWORDS:
        if exc in combined_text:
            return False

    # 2. المطابقة التامة مع الكلمات المفتاحية الأساسية
    if any(kw.lower() in combined_text for kw in MUST_MATCH_KEYWORDS):
        return True

    # 3. المطابقة عند ذكر اسم "أطفيش" بشرط وجود بلدية من بلديات غرداية أو كلمة سياقية
    if "أطفيش" in combined_text or "اطفيش" in combined_text:
        if any(ctx.lower() in combined_text for ctx in CONTEXT_KEYWORDS):
            return True

    # 4. قبول الأخبار التراثية أو العلمية المباشرة المسجلة في إحدى بلديات غرداية
    has_municipality = any(muni.lower() in combined_text for muni in GHARDAIA_MUNICIPALITIES)
    has_heritage = any(h in combined_text for h in ["تراث", "مخطوط", "جمعية", "تاريخ", "ميزاب", "معلم"])
    
    if has_municipality and has_heritage:
        return True

    return False

def determine_importance_and_category(title: str, summary: str):
    """
    تحديد درجة الأهمية والتصنيف التلقائي للقصاصة
    """
    text = clean_text(f"{title} {summary}").lower()
    
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار", "تهديد"]):
        importance = "أحداث خطيرة"
        category = "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط", "محاضرة", "معرض"]):
        importance = "عالي"
        category = "نشاطات علمية وتراثية"
    else:
        importance = "عادي"
        category = "أخبار عامة"

    return importance, category

# ==========================================
# 4. دالة الحفظ في Supabase
# ==========================================

def save_clipping_to_supabase(title: str, summary: str, link: str, source: str, pub_date: str = None) -> bool:
    """
    فحص وتصفية القصاصة ثم رفعها لقاعدة البيانات إذا لم تكن مكررة
    """
    clean_title_str = clean_text(title)
    clean_summary_str = clean_text(summary)

    # 1. فلترة المحتوى الخاطئ/غير المرتبط
    if not is_relevant_article(clean_title_str, clean_summary_str):
        print(f"❌ تم تجاوز خبر غير مرتبط: {clean_title_str[:50]}... ({source})")
        return False

    # 2. منع التكرار بناءً على رابط المقال
    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data and len(existing.data) > 0:
            print(f"⚠️ الخبر موجود مسبقاً في قاعدة البيانات: {clean_title_str[:50]}...")
            return False
    except Exception as e:
        print(f"⚠️ خطأ أثناء فحص التكرار: {e}")

    # 3. معالجة التواريخ والتصنيفات
    importance, category = determine_importance_and_category(clean_title_str, clean_summary_str)
    formatted_date = parse_date(pub_date)

    payload = {
        "title": clean_title_str,
        "summary": clean_summary_str,
        "link": link,
        "source": source,
        "published_date": formatted_date,
        "importance": importance,
        "category": category
    }

    # 4. الحفظ في Supabase
    try:
        supabase.table("clippings").insert(payload).execute()
        print(f"✅ تم حفظ القصاصة بنجاح: {clean_title_str[:50]}...")
        return True
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ في Supabase: {e}")
        return False

# ==========================================
# 5. دوال جلب البيانات من المصادر (Scrapers)
# ==========================================

def scrape_rss_feed(feed_url: str, source_name: str):
    """
    جلب القصاصات من خلاصة RSS معينة
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        if not items:
            soup = BeautifulSoup(response.content, 'html.parser')
            items = soup.find_all('item')

        print(f"\n🔍 تم العثور على {len(items)} عنصر في مصدر: {source_name}")

        saved_count = 0
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            link = item.find('link').text if item.find('link') else ''
            summary = item.find('description').text if item.find('description') else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') else None

            if save_clipping_to_supabase(title, summary, link, source_name, pub_date):
                saved_count += 1

        print(f"✨ تم إضافة {saved_count} قصاصات جديدة من {source_name}")

    except Exception as e:
        print(f"❌ خطأ أثناء جلب المصدر {source_name} ({feed_url}): {e}")

# ==========================================
# 6. التشغيل الرئيسي
# ==========================================

if __name__ == "__main__":
    print("=" * 60)
    print("بدء تشغيل scraper.py بالاعتماد على بلديات ولاية غرداية...")
    print("=" * 60)

    # قائمة بمصادر الأخبار (RSS Feeds) التي سيتم فحصها
    RSS_SOURCES = [
        # {"url": "https://example.com/rss", "name": "اسم المصدر"}
    ]

    for source in RSS_SOURCES:
        scrape_rss_feed(source["url"], source["name"])

    print("\n=" * 60)
    print("إنتهاء عملية
