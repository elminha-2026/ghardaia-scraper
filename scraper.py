"""
scraper.py — جلب وتصفية القصاصات الصحفية لولاية غرداية والشيخ إبراهيم أطفيش
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
    print("❌ خطأ: SUPABASE_URL أو SUPABASE_KEY غير موجودين في Secrets.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase بنجاح.")
except Exception as e:
    print(f"❌ فشل الاتصال بـ Supabase: {e}")
    sys.exit(1)


# ============================================================
# 2. أدوات معالجة وتنظيف النصوص
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
    # حذف وسوم تعريف الكاتب إذا وجدت في الـ RSS
    for tag in soup.select('.author, .author-bio, header, footer, script, style'):
        tag.decompose()
    clean = soup.get_text(separator=' ')
    return re.sub(r'\s+', ' ', clean).strip()


def norm(text: str) -> str:
    cleaned = clean_text(text).lower()
    return normalize_arabic(cleaned)


# ============================================================
# 3. قوائم الفلترة واستبعاد مزاب المغرب والرياضة
# ============================================================
TARGET_KEYWORDS_RAW = [
    # غرداية ومدنها
    "غرداية", "ميزاب", "مزاب", "بني يزقن", "القرارة", "بريان", 
    "متليلي", "العطف", "بونورة", "زلفانة", "سبسب", "المنصورة",
    # أطفيش
    "أطفيش", "اطفيش", "إبراهيم أطفيش", "أبو إسحاق", "أبي إسحاق",
    # باللغات الأجنبية
    "ghardaia", "ghardaïa", "mzab", "atfich", "ibrahim atfich", "guerrara", "berriane"
]

EXCLUDE_KEYWORDS_RAW = [
    # استبعاد أخبار الرياضة والأسهم
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "بورصة", "تداول الأسهم", "وظائف شاغرة", "عقارات للبيع", "football",
    # استبعاد أخبار منطقة مزاب بالمغرب (سطات/الشاوية)
    "سطات", "الشاوية", "settat", "chaouia"
]

TARGET_KEYWORDS  = [norm(k) for k in TARGET_KEYWORDS_RAW]
EXCLUDE_KEYWORDS = [norm(k) for k in EXCLUDE_KEYWORDS_RAW]


# ============================================================
# 4. دوال الفحص والتقييم
# ============================================================
def parse_date(date_str: str) -> str:
    if not date_str:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")
    try:
        return parsedate_to_datetime(date_str).strftime("%Y-%m-%d")
    except Exception:
        return datetime.now(timezone.utc).strftime("%Y-%m-%d")


def is_relevant_article(title: str, summary: str, is_google_source: bool = False) -> bool:
    text = norm(f"{title} {summary}")

    # 1. الاستبعاد الصريح (رياضة / مزاب المغرب)
    if any(exc in text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. المطابقة المباشرة في العنوان أو الملخص
    if any(kw in text for kw in TARGET_KEYWORDS):
        return True

    # 3. قبول نتائج Google News المباشرة طالما لم يتم استبعادها في الخطوة 1
    if is_google_source:
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
# 5. دالة الحفظ في Supabase
# ============================================================
def save_clipping_to_supabase(title: str, summary: str, link: str,
                              source: str, pub_date: str = None,
                              is_google_source: bool = False) -> bool:
    clean_title_str   = clean_text(title)
    clean_summary_str = clean_text(summary)

    if not clean_title_str or not link:
        return False

    if not is_relevant_article(clean_title_str, clean_summary_str, is_google_source):
        print(f"  ⏭️  [مستبعد]: {clean_title_str[:50]}...")
        return False

    # منع التكرار بناءً على الرابط والعنوان
    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data:
            print(f"  ⚠️  [مكرر بالرابط]: {clean_title_str[:50]}...")
            return False
        existing = supabase.table("clippings").select("id").eq("title", clean_title_str).execute()
        if existing.data:
            print(f"  ⚠️  [مكرر بالعنوان]: {clean_title_str[:50]}...")
            return False
    except Exception as e:
        print(f"  ⚠️  خطأ فحص التكرار: {e}")

    importance, category = determine_importance_and_category(clean_title_str, clean_summary_str)

    payload = {
        "title":          clean_title_str,
        "summary":        clean_summary_str if clean_summary_str else clean_title_str,
        "link":           link,
        "source":         source,
        "published_date": parse_date(pub_date),
        "importance":     importance,
        "category":       category,
    }

    try:
        supabase.table("clippings").insert(payload).execute()
        print(f"  ✅ [تم الحفظ بنجاح]: {clean_title_str[:50]}...")
        return True
    except Exception as e:
        print(f"  ❌ خطأ إدراج في Supabase: {e}")
        return False


# ============================================================
# 6. جلب RSS عبر شبكة الطلبات
# ============================================================
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8'
}


def scrape_rss_feed(feed_url: str, source_name: str, is_google_source: bool = False) -> int:
    print(f"\n🔍 {source_name}")
    try:
        response = requests.get(feed_url, headers=HEADERS, timeout=15)
        if response.status_code != 200:
            print(f"  ❌ فشل الجلب (كود الحالة: {response.status_code})")
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

        # جلب اسم المصدر الأصلي إذا كان موجهاً عبر Google News
        actual_source = source_name
        source_tag = item.find('source')
        if source_tag and source_tag.text:
            actual_source = source_tag.text.strip()

        if save_clipping_to_supabase(title, summary, link, actual_source, pub_date, is_google_source):
            saved += 1

    print(f"  📊 تم حفظ: {saved} قصاصات جديدة.")
    return saved


# ============================================================
# 7. التشغيل الرئيسي
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("بدء تشغيل السكرابر لجلب كافة القصاصات...")
    print("=" * 60)

    total_saved = 0

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

    print("\n📡 [1] جلب عبر Google News RSS")
    for q in SEARCH_QUERIES:
        encoded = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded}&hl=ar&gl=DZ&ceid=DZ:ar"
        total_saved += scrape_rss_feed(url, f"Google News: {q}", is_google_source=True)
        time.sleep(1)

    print("\n📡 [2] مصادر RSS جزائرية مباشرة")
    DIRECT_FEEDS = {
        "الشروق أونلاين": "https://www.echoroukonline.com/feed/",
        "جريدة اللقاء": "https://elikaaonline.com/feed/",
        "L'Expression": "https://lexpressiondz.com/feeds/index.rssi"
    }
    for name, url in DIRECT_FEEDS.items():
        total_saved += scrape_rss_feed(url, name, is_google_source=False)
        time.sleep(1)

    print("\n" + "=" * 60)
    print(f"🎉 اكتمل الرصد! إجمالي القصاصات المحفوظة: {total_saved}")
    print("=" * 60)
