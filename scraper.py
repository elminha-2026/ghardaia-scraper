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
# 1. الاتصال بـ Supabase والتحقق من البيئة
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
    print(f"❌ فشل الاتصال بـ Supabase: {e}")
    sys.exit(1)

# ==========================================
# 2. قوائم الفلترة مع تساهل في المطابقة
# ==========================================

KEYWORDS = [
    "غرداية", "أطفيش", "اطفيش", "ميزاب", "تراث", "بني يزقن", 
    "القرارة", "بريان", "متليلي", "العطف", "بونورة", "زلفانة"
]

EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

# ==========================================
# 3. المعالجة والدوال المساعدة
# ==========================================

def clean_text(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    clean = soup.get_text(separator=' ')
    clean = re.sub(r'\s+', ' ', clean)
    return clean.strip()

def parse_date(date_str: str) -> str:
    if not date_str:
        return datetime.utcnow().strftime("%Y-%m-%d")
    try:
        dt = parsedate_to_datetime(date_str)
        return dt.strftime("%Y-%m-%d")
    except Exception:
        return datetime.utcnow().strftime("%Y-%m-%d")

def is_relevant_article(title: str, summary: str) -> bool:
    combined_text = clean_text(f"{title} {summary}").lower()

    # استبعاد الأخبار غير التراثية/الرياضية
    for exc in EXCLUDE_KEYWORDS:
        if exc in combined_text:
            return False

    # قبول أي خبر يحتوي على إحدى الكلمات المفتاحية
    for kw in KEYWORDS:
        if kw.lower() in combined_text:
            return True

    return False

def determine_importance_and_category(title: str, summary: str):
    text = clean_text(f"{title} {summary}").lower()
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار"]):
        return "أحداث خطيرة", "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط", "محاضرة"]):
        return "عالي", "نشاطات علمية وتراثية"
    return "عادي", "أخبار عامة"

# ==========================================
# 4. دالة الحفظ
# ==========================================

def save_clipping_to_supabase(title: str, summary: str, link: str, source: str, pub_date: str = None) -> bool:
    clean_title_str = clean_text(title)
    clean_summary_str = clean_text(summary)

    if not clean_title_str or not link:
        return False

    if not is_relevant_article(clean_title_str, clean_summary_str):
        print(f"  ⏭️ [مستبعد بالفلترة]: {clean_title_str[:40]}...")
        return False

    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data and len(existing.data) > 0:
            print(f"  ⚠️ [موجود مسبقاً]: {clean_title_str[:40]}...")
            return False
    except Exception as e:
        print(f"  ⚠️ خطأ فحص التكرار: {e}")

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

    try:
        supabase.table("clippings").insert(payload).execute()
        print(f"  ✅ [تم الحفظ بنجاح]: {clean_title_str[:40]}...")
        return True
    except Exception as e:
        print(f"  ❌ خطأ إدراج في Supabase: {e}")
        return False

# ==========================================
# 5. دوال جلب الأخبار واختبار الاستجابة
# ==========================================

def scrape_rss_feed(feed_url: str, source_name: str):
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
    }
    try:
        response = requests.get(feed_url, headers=headers, timeout=15)
        print(f"\n🔍 المصدر: {source_name} | كود الاستجابة: {response.status_code}")

        if response.status_code != 200:
            print(f"❌ فشل جلب الرابط، رمز الحالة: {response.status_code}")
            return

        soup = BeautifulSoup(response.content, 'xml')
        items = soup.find_all('item')
        
        if not items:
            soup = BeautifulSoup(response.content, 'html.parser')
            items = soup.find_all('item')

        print(f"📦 عدد العناصر المكتشفة في XML: {len(items)}")

        saved_count = 0
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            link = item.find('link').text if item.find('link') else ''
            summary = item.find('description').text if item.find('description') else ''
            pub_date = item.find('pubDate').text if item.find('pubDate') else None

            if save_clipping_to_supabase(title, summary, link, source_name, pub_date):
                saved_count += 1

        print(f"📊 نتيجة المصدر: تم حفظ {saved_count} قصاصات جديدة.")

    except Exception as e:
        print(f"❌ خطأ غير متوقع أثناء جلب {source_name}: {e}")

# ==========================================
# 6. التشغيل الرئيسي
# ==========================================

if __name__ == "__main__":
    print("=" * 60)
    print("بدء تشغيل scraper.py ومراقبة النتائج...")
    print("=" * 60)

    # قائمة استعلامات متدرجة
    queries = [
        "غرداية",
        "ولاية غرداية",
        "تراث غرداية",
        "أطفيش"
    ]

    for q in queries:
        encoded_query = urllib.parse.quote(q)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
        scrape_rss_feed(rss_url, f"Google News: {q}")

    print("\n" + "=" * 60)
    print("إنتهاء عملية التشغيل.")
    print("=" * 60)
