import os
import re
import sys
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات وتأكيد متغيرات البيئة لـ Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ حرج: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في متغيرات البيئة.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بقاعدة بيانات Supabase بنجاح.")
except Exception as e:
    print(f"❌ فشل الاتصال بقاعدة البيانات Supabase: {e}")
    sys.exit(1)

# ==========================================
# 2. قوائم الفلترة والكلمات المفتاحية
# ==========================================

GHARDAIA_MUNICIPALITIES = [
    "غرداية", "بني يزقن", "العطف", "بونورة", "القرارة", 
    "بريان", "متليلي", "سبسب", "المنصورة", "زلفانة"
]

MUST_MATCH_KEYWORDS = [
    "أطفيش", "اطفيش", "غرداية", "ميزاب", "تراث"
]

EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع", "شقة للبيع"
]

# ==========================================
# 3. الدوال المساعدة لمعالجة النصوص
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
    """فحص صلة الخبر بالفكرة المطلوب رصدها"""
    combined_text = clean_text(f"{title} {summary}").lower()

    # 1. الاستبعاد الفوري عند وجود كلمات غير مرتبطة
    for exc in EXCLUDE_KEYWORDS:
        if exc in combined_text:
            return False

    # 2. فحص وجود أي كلمة من الكلمات المفتاحية أو بلديات غرداية
    if any(kw.lower() in combined_text for kw in MUST_MATCH_KEYWORDS + GHARDAIA_MUNICIPALITIES):
        return True

    return False

def determine_importance_and_category(title: str, summary: str):
    """تحديد الأهمية والتصنيف"""
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
# 4. دالة الحفظ في Supabase مع Logging مفصل
# ==========================================

def save_clipping_to_supabase(title: str, summary: str, link: str, source: str, pub_date: str = None) -> bool:
    clean_title_str = clean_text(title)
    clean_summary_str = clean_text(summary)

    if not clean_title_str or not link:
        return False

    # 1. الفلترة
    if not is_relevant_article(clean_title_str, clean_summary_str):
        print(f"  ⏭️ [مستبعد بالفلترة]: {clean_title_str[:40]}...")
        return False

    # 2. منع التكرار
    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data and len(existing.data) > 0:
            print(f"  ⚠️ [موجود مسبقاً]: {clean_title_str[:40]}...")
            return False
    except Exception as e:
        print(f"  ⚠️ خطأ أثناء فحص التكرار: {e}")

    # 3. تجهيز البيانات
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

    # 4. الإدراج الحقيقي في قاعدة البيانات
    try:
        response = supabase.table("clippings").insert(payload).execute()
        print(f"  ✅ [تم الحفظ بنجاح]: {clean_title_str[:40]}...")
        return True
    except Exception as e:
        print(f"  ❌ خطأ إدراج في Supabase (تأكد من أسماء الأعمدة): {e}")
        return False

# ==========================================
# 5. دوال جلب الأخبار RSS
# ==========================================

def build_google_news_url(query: str) -> str:
    encoded_query = urllib.parse.quote(query)
    return f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"

def scrape_rss_feed(feed_url: str, source_name: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept-Language': 'ar,en-US;q=0.9,en;q=0.8'
    }
    try:
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status()
        
        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        if not items:
            soup = BeautifulSoup(response.content, 'html.parser')
            items = soup.find_all('item')

        print(f"\n🔍 المصدر: {source_name} | عدد العناصر المسترجعة: {len(items)}")

        saved_count = 0
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            link = item.find('link').text if item.find('link') else ''
            summary = item.find('description').text if item.find('description') else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') else None

            if save_clipping_to_supabase(title, summary, link, source_name, pub_date):
                saved_count += 1

        print(f"📊 النتيجة: تم إضافة {saved_count} قصاصات جديدة من أصل {len(items)}")

    except Exception as e:
        print(f"❌ خطأ أثناء الاتصال بالمصدر {source_name}: {e}")

# ==========================================
# 6. التشغيل الرئيسي
# ==========================================

if __name__ == "__main__":
    print("=" * 60)
    print("بدء تشغيل scraper.py وتتبع عمليات الرصد...")
    print("=" * 60)

    # مصادر استعلامات واسعة النطاق للتحقق من العمل
    SEARCH_QUERIES = [
        "غرداية",
        "ولاية غرداية",
        "تراث غرداية",
        "أطفيش"
    ]

    for q in SEARCH_QUERIES:
        rss_url = build_google_news_url(q)
        scrape_rss_feed(rss_url, f"Google News: {q}")

    print("\n" + "=" * 60)
    print("إنتهاء عملية الرصد والتصفية.")
    print("=" * 60)
