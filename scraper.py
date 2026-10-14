"""
scraper.py — جلب القصاصات الصحفية حول ولاية غرداية والشيخ إبراهيم أطفيش
"""
import os
import re
import sys
import time
import requests
import urllib.parse
from bs4 import BeautifulSoup
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from supabase import create_client, Client


# ============================================================
# 1. الاتصال بـ Supabase
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: SUPABASE_URL أو SUPABASE_KEY غير موجودين.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase.")
except Exception as e:
    print(f"❌ فشل الاتصال بـ Supabase: {e}")
    sys.exit(1)


# ============================================================
# 2. أدوات تطبيع النص
# ============================================================
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED]')
_TATWEEL_RE    = re.compile(r'\u0640')
_ALEF_RE       = re.compile(r'[إأآٱا]')
_YAA_RE        = re.compile(r'[يى]')
_TAA_RE        = re.compile(r'ة')
_WS_RE         = re.compile(r'\s+')


def normalize_arabic(text: str) -> str:
    if not text:
        return ""
    text = str(text)
    text = _DIACRITICS_RE.sub('', text)
    text = _TATWEEL_RE.sub('', text)
    text = _ALEF_RE.sub('ا', text)
    text = _YAA_RE.sub('ي', text)
    text = _TAA_RE.sub('ه', text)
    return _WS_RE.sub(' ', text).strip()


def clean_text(text: str) -> str:
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return re.sub(r'\s+', ' ', soup.get_text(separator=' ')).strip()


def norm(text: str) -> str:
    cleaned = clean_text(text).lower()
    return normalize_arabic(cleaned)


# ============================================================
# 3. الكلمات المفتاحية
# ============================================================
TARGET_KEYWORDS_RAW = [
    # غرداية ومدنها
    "غرداية", "ميزاب", "مزاب", "بني يزقن", "القرارة", "بريان", 
    "متليلي", "العطف", "بونورة", "زلفانة", "سبسب", "المنصورة",
    # أطفيش
    "أطفيش", "اطفيش", "إبراهيم أطفيش", "أبو إسحاق", "أبي إسحاق",
    # بالفرنسية
    "ghardaia", "ghardaïa", "mzab", "atfich", "ibrahim atfich", "guerrara", "berriane"
]

EXCLUDE_KEYWORDS_RAW = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "بورصة", "تداول الأسهم", "وظائف شاغرة", "عقارات للبيع", "football"
]

TARGET_KEYWORDS  = [norm(k) for k in TARGET_KEYWORDS_RAW]
EXCLUDE_KEYWORDS = [norm(k) for k in EXCLUDE_KEYWORDS_RAW]


# ============================================================
# 4. دوال مساعدة
# ============================================================
def parse_date(date_str: str) -> str:
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_relevant_article(title: str, summary: str, query_context: str = "") -> bool:
    text = norm(f"{title} {summary} {query_context}")

    # 1. استبعاد الرياضة والعقارات
    if any(exc in text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. القبول الفوري إذا تطابق أي جزء من العنوان أو الاستعلام مع الكلمات المطلوبة
    if any(kw in text for kw in TARGET_KEYWORDS):
        return True

    # 3. قبول نصوص Google News المباشرة لأنها مجلوبة بطلب خاص للكلمة
    if query_context and any(kw in norm(query_context) for kw in TARGET_KEYWORDS):
        return True

    return False


def determine_importance_and_category(title: str, summary: str):
    text = norm(f"{title} {summary}")

    if any(k in text for k in ["أطفيش", "اطفيش", "أبو إسحاق", "atfich"]):
        return "عالي", "الشيخ إبراهيم أطفيش"

    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار", "انهيار"]):
        return "أحداث خطيرة", "أحداث خطيرة"

    if any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط", "محاضرة", "ترميم"]):
        return "عالي", "نشاطات علمية وتراثية"

    return "عادي", "أخبار عامة"


# ============================================================
# 5. حفظ في Supabase
# ============================================================
def save_clipping_to_supabase(title: str, summary: str, link: str,
                              source: str, pub_date: str = None,
                              query_context: str = "") -> bool:
    clean_title   = clean_text(title)
    clean_summary = clean_text(summary)

    if not clean_title or not link:
        return False

    if not is_relevant_article(clean_title, clean_summary, query_context):
        print(f"  ⏭️  [مستبعد]: {clean_title[:50]}...")
        return False

    # فحص التكرار
    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data:
            print(f"  ⚠️  [مكرر بالرابط]: {clean_title[:50]}...")
            return False
        existing = supabase.table("clippings").select("id").eq("title", clean_title).execute()
        if existing.data:
            print(f"  ⚠️  [مكرر بالعنوان]: {clean_title[:50]}...")
            return False
    except Exception as e:
        print(f"  ⚠️  خطأ فحص التكرار: {e}")

    importance, category = determine_importance_and_category(clean_title, clean_summary)

    payload = {
        "title":          clean_title,
        "summary":        clean_summary,
        "link":           link,
        "source":         source,
        "published_date": parse_date(pub_date),
        "importance":     importance,
        "category":       category,
    }

    try:
        supabase.table("clippings").insert(payload).execute()
        print(f"  ✅ [محفوظ]: {clean_title[:50]}...")
        return True
    except Exception as e:
        print(f"  ❌ خطأ إدراج: {e}")
        return False


# ============================================================
# 6. جلب RSS
# ============================================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}


def scrape_rss_feed(feed_url: str, source_name: str, query_context: str = "") -> int:
    print(f"\n🔍 {source_name}")
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  ❌ فشل الجلب (رمز الحالة: {response.status_code})")
            return 0
    except Exception as e:
        print(f"  ❌ خطأ اتصال: {e}")
        return 0

    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')
    if not items:
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('item')

    print(f"  📦 عناصر مكتشفة: {len(items)}")
    if not items:
        return 0

    saved = 0
    for item in items:
        title    = item.find('title').text        if item.find('title')        else ''
        link     = item.find('link').text         if item.find('link')         else ''
        summary  = item.find('description').text if item.find('description') else ''
        pub_date = item.find('pubDate').text      if item.find('pubDate')      else None

        if save_clipping_to_supabase(title, summary, link, source_name, pub_date, query_context):
            saved += 1

    print(f"  📊 تم حفظ: {saved}")
    return saved


# ============================================================
# 7. التشغيل الرئيسي
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("بدء التشغيل — غرداية + الشيخ إبراهيم أطفيش")
    print("=" * 60)

    total_saved = 0

    # استعلامات مباشرة بدون قيود زمنية معقدة
    SEARCH_QUERIES = [
        "غرداية",
        "ولاية غرداية",
        "تراث غرداية",
        "وادي ميزاب",
        "أطفيش",
        "إبراهيم أطفيش",
        "Ghardaia",
        "Mzab"
    ]

    print("\n📡 [1] Google News RSS")
    for q in SEARCH_QUERIES:
        encoded = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ar&gl=DZ&ceid=DZ:ar"
        total_saved += scrape_rss_feed(url, f"Google News: {q}", query_context=q)
        time.sleep(1)

    print("\n📡 [2] مصادر RSS جزائرية مباشرة")
    DIRECT_FEEDS = {
        "الشروق أونلاين": "https://www.echoroukonline.com/feed/",
        "جريدة اللقاء": "https://elikaaonline.com/feed/",
        "L'Expression": "https://lexpressiondz.com/feeds/index.rssi"
    }
    for name, url in DIRECT_FEEDS.items():
        total_saved += scrape_rss_feed(url, name)
        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"🎉 انتهى التشغيل بنجاح! إجمالي القصاصات الجديدة الحقيقية: {total_saved}")
    print("=" * 60)
