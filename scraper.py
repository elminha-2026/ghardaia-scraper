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
# 1. الاتصال بـ Supabase والتحقق من البيئة
# ============================================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ حرج: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY.")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بقاعدة بيانات Supabase بنجاح.")
except Exception as e:
    print(f"❌ فشل الاتصال بـ Supabase: {e}")
    sys.exit(1)


# ============================================================
# 2. أدوات تطبيع النص العربي
# ============================================================
_DIACRITICS_RE = re.compile(r'[\u064B-\u065F\u0670\u06D6-\u06ED]')
_TATWEEL_RE    = re.compile(r'\u0640')
_ALEF_RE       = re.compile(r'[إأآٱا]')
_YAA_RE        = re.compile(r'[يى]')
_TAA_RE        = re.compile(r'ة')
_WS_RE         = re.compile(r'\s+')


def normalize_arabic(text: str) -> str:
    """تطبيع النص العربي: إزالة التشكيل وتوحيد الحروف المتشابهة."""
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
    """إزالة وسوم HTML والمسافات الزائدة."""
    if not text:
        return ""
    soup = BeautifulSoup(text, "html.parser")
    return re.sub(r'\s+', ' ', soup.get_text(separator=' ')).strip()


def norm(text: str) -> str:
    """نص جاهز للمطابقة (منظَّف + مُطبَّع + lowercase)."""
    return normalize_arabic(clean_text(text)).lower()


# ============================================================
# 3. قوائم الفلترة (تُطبَّع تلقائياً عند التحميل)
# ============================================================

# --- كلمات محدّدة → قبول فوري ---
SPECIFIC_KEYWORDS_RAW = [
    # الجغرافيا: ولاية غرداية ووادي ميزاب
    "غرداية", "ولاية غرداية", "ميزاب", "وادي ميزاب", "وادي مزاب",
    "بني يزقن", "بني يسجن", "بني مزاب",
    "القرارة", "بريان", "متليلي", "العطف", "بونورة", "زلفانة",
    "ضاية بن ضحوة", "حاسي الفحل", "سبسب",
    # الشيخ إبراهيم أطفيش — كل الصيغ الإملائية والشهرة
    "أطفيش", "اطفيش", "أطفايش", "اطفايش", "أطفوي", "الأطفيشي",
    "إبراهيم أطفيش", "أبو إسحاق أطفيش", "أبي إسحاق أطفيش",
    "الشيخ أطفيش", "إبراهيم بن الحاج موسى",
    # نسبة إلى المنطقة
    "مزابي", "ميزابي",
]

# --- كلمات عامة → تحتاج دليل جزائري مرافق ---
GENERIC_KEYWORDS_RAW = [
    "تراث", "مخطوط", "تراثي", "أرشيف", "مخطوطات",
]

# --- مؤشرات قوية على الجزائر ---
ALGERIA_INDICATORS_RAW = [
    "الجزائر", "الجزائري", "الجزائرية", "جزائري", "جزائرية",
    "ولاية غرداية", "الدولة الجزائرية",
    "الجيش الوطني الشعبي", "الدرك الوطني", "الحماية المدنية",
]

# --- نطاقات الصحافة الجزائرية (قائمة بيضاء) ---
ALGERIAN_DOMAINS = [
    "aps.dz", "elkhabar.com", "ennahar.dz", "echoroukonline.com",
    "elwatan.com", "elwatan-dz.com", "liberte-algerie.com",
    "lexpressiondz.com", "tsa-algerie.com", "algerie360.com",
    "ennaharonline.com", "elbilad.net", "ennas.dz", "en-nas.dz",
    "elhayat.net", "al-fadjr.com", "essahafa.com", "alkhaleej.dz",
    "dzayerinfo.com", "lequotidienalgerie.com", "radioalgerie.dz",
    "el-massa.com", "algerie-focus.com", "elain.info",
    "annasronline.com", "sawt-alahrar.net", "el-mouradia.dz",
    "el-moudjahid.com", "horizons.dz", "reflexiondz.net",
    "lapatrienews.dz", "lejeune-independant.net", "reporters.dz",
    "fibladi.com", "dzairdaily.com", "lagazettedufennec.com",
    "elikaaonline.com", "lenational.dz", "alg24.net",
    # نطاقات جهوية/محلية (غرداية، وادي ميزاب، الجنوب)
    "ghardaia.com", "elghardaia.com", "mzab-info.com",
    "atfich.net", "el-attef.com", "ouargla.org",
]

# --- دول ومناطق عربية أخرى (للاستبعاد عند اقترانها بكلمة عامة) ---
OTHER_ARAB_COUNTRIES_RAW = [
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين",
    "سلطنة عمان", "الأردن", "لبنان", "سوريا", "العراق",
    "فلسطين", "تونس", "المغرب", "ليبيا", "موريتانيا",
    "السودان", "اليمن", "تركيا", "إيران",
]

# --- كلمات الاستبعاد (رياضة، اقتصاد، إعلانات) ---
EXCLUDE_KEYWORDS_RAW = [
    "كرة القدم", "مباراة كرة",
    "الدوري الإنجليزي", "الدوري الإسباني", "الدوري الإيطالي",
    "الدوري الجزائري", "الأهلي المصري", "الهلال السعودي",
    "النصر السعودي", "الزمالك",
    "بورصة", "تداول الأسهم", "أسهم", "وظائف شاغرة", "عقارات للبيع",
]

# --- تطبيع كل القوائم مرة واحدة ---
SPECIFIC_KEYWORDS    = [normalize_arabic(k).lower() for k in SPECIFIC_KEYWORDS_RAW]
GENERIC_KEYWORDS     = [normalize_arabic(k).lower() for k in GENERIC_KEYWORDS_RAW]
ALGERIA_INDICATORS   = [normalize_arabic(k).lower() for k in ALGERIA_INDICATORS_RAW]
OTHER_ARAB_COUNTRIES = [normalize_arabic(k).lower() for k in OTHER_ARAB_COUNTRIES_RAW]
EXCLUDE_KEYWORDS     = [normalize_arabic(k).lower() for k in EXCLUDE_KEYWORDS_RAW]

# مفاتيح خاصة بالشيخ أطفيش (لتصنيف الأهمية)
SCHOLAR_KEYS_NORM = [normalize_arabic(k).lower() for k in
                     ["أطفيش", "اطفيش", "أطفايش", "اطفايش",
                      "أطفوي", "الأطفيشي", "أبو إسحاق أطفيش"]]

DANGER_KEYS_NORM = [normalize_arabic(k).lower() for k in
                    ["تعدي", "سرقة", "هدم", "ضرر", "خطر",
                     "حريق", "اندثار", "انهيار", "احتجاج", "جريمة"]]

ACTIVITY_KEYS_NORM = [normalize_arabic(k).lower() for k in
                      ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب",
                       "مخطوط", "محاضرة", "معرض", "مهرجان",
                       "ترميم", "توثيق"]]


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


def extract_domain(url: str) -> str:
    if not url:
        return ""
    try:
        parsed = urllib.parse.urlparse(url)
        domain = parsed.netloc.lower()
        if domain.startswith("www."):
            domain = domain[4:]
        return domain
    except Exception:
        return ""


def is_algerian_domain(source_url: str) -> bool:
    domain = extract_domain(source_url)
    return bool(domain) and any(alg in domain for alg in ALGERIAN_DOMAINS)


# ============================================================
# 5. منطق الفلترة والتصنيف
# ============================================================
def is_relevant_article(title: str, summary: str, source_url: str = "") -> bool:
    """
    ثلاث طبقات للقبول:
      1) لا يحتوي على كلمات الاستبعاد.
      2) يحتوي على كلمة محدّدة (غرداية/ميزاب/أطفيش...) → قبول مباشر.
      3) يحتوي على كلمة عامة (تراث) → يُشترط ذكر الجزائر صراحة
         أو أن يكون المصدر ضمن القائمة البيضاء الجزائرية.
    """
    text = norm(f"{title} {summary}")

    # (1) استبعاد
    if any(exc in text for exc in EXCLUDE_KEYWORDS):
        return False

    # (2) مطابقة محدّدة → قبول مباشر
    if any(kw in text for kw in SPECIFIC_KEYWORDS):
        return True

    # (3) مطابقة عامة → تحتاج دليل جزائري
    if not any(kw in text for kw in GENERIC_KEYWORDS):
        return False

    has_algeria    = any(ind in text for ind in ALGERIA_INDICATORS)
    has_alg_domain = is_algerian_domain(source_url)

    # إذا ذُكرت دولة عربية أخرى بلا الجزائر ولا نطاق جزائري → رفض
    has_other = any(c in text for c in OTHER_ARAB_COUNTRIES)
    if has_other and not has_algeria and not has_alg_domain:
        return False

    return has_algeria or has_alg_domain


def determine_importance_and_category(title: str, summary: str):
    text = norm(f"{title} {summary}")

    # أولوية قصوى: أخبار الشيخ أطفيش دائماً "عالي"
    if any(k in text for k in SCHOLAR_KEYS_NORM):
        return "عالي", "الشيخ إبراهيم أطفيش"

    if any(k in text for k in DANGER_KEYS_NORM):
        return "أحداث خطيرة", "أحداث خطيرة"

    if any(k in text for k in ACTIVITY_KEYS_NORM):
        return "عالي", "نشاطات علمية وتراثية"

    return "عادي", "أخبار عامة"


# ============================================================
# 6. حفظ القصاصة في Supabase
# ============================================================
def save_clipping_to_supabase(title: str, summary: str, link: str,
                              source: str, pub_date: str = None,
                              source_url: str = "") -> bool:
    clean_title   = clean_text(title)
    clean_summary = clean_text(summary)

    if not clean_title or not link:
        return False

    if not is_relevant_article(clean_title, clean_summary, source_url):
        print(f"  ⏭️  [مستبعد]: {clean_title[:50]}...")
        return False

    # --- فحص التكرار (بالرابط أو بالعنوان) ---
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
        print(f"  ❌ خطأ إدراج في Supabase: {e}")
        return False


# ============================================================
# 7. جلب RSS مع إعادة المحاولة
# ============================================================
HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/122.0.0.0 Safari/537.36'),
    'Accept': 'application/rss+xml, application/xml, text/xml, */*;q=0.8',
    'Accept-Language': 'ar,fr;q=0.9,en;q=0.8',
}


def fetch_with_retry(url: str, max_retries: int = 3, timeout: int = 20):
    for attempt in range(max_retries):
        try:
            r = requests.get(url, headers=HEADERS, timeout=timeout)
            if r.status_code == 200:
                return r
            print(f"  ⚠️  رمز الحالة {r.status_code} (محاولة {attempt + 1})")
        except requests.RequestException as e:
            print(f"  ⚠️  فشل الطلب (محاولة {attempt + 1}): {e}")
        if attempt < max_retries - 1:
            time.sleep(2 ** attempt)
    return None


def scrape_rss_feed(feed_url: str, source_name: str) -> int:
    print(f"\n🔍 المصدر: {source_name}")
    response = fetch_with_retry(feed_url)
    if response is None:
        print("  ❌ فشل جلب المصدر بعد كل المحاولات.")
        return 0

    # ضبط الترميز لتفادي تشويه العربية
    if not response.encoding or response.encoding.lower() == 'iso-8859-1':
        response.encoding = response.apparent_encoding or 'utf-8'

    soup = BeautifulSoup(response.content, 'xml')
    items = soup.find_all('item')
    if not items:
        soup = BeautifulSoup(response.content, 'html.parser')
        items = soup.find_all('item')

    print(f"  📦 عدد العناصر المكتشفة: {len(items)}")

    saved = 0
    for item in items:
        title    = item.find('title').text       if item.find('title')       else ''
        link     = item.find('link').text        if item.find('link')        else ''
        summary  = item.find('description').text if item.find('description') else ''
        pub_date = item.find('pubDate').text     if item.find('pubDate')     else None

        # استخراج رابط المصدر الحقيقي من وسم <source url="...">
        source_tag = item.find('source')
        source_url = source_tag.get('url', '') if source_tag is not None else ''

        if save_clipping_to_supabase(title, summary, link, source_name,
                                     pub_date, source_url):
            saved += 1

    print(f"  📊 محفوظ جديد من هذا المصدر: {saved}")
    return saved


# ============================================================
# 8. التشغيل الرئيسي
# ============================================================
if __name__ == "__main__":
    print("=" * 60)
    print("بدء تشغيل scraper.py — متابعة ولاية غرداية والشيخ أطفيش")
    print("=" * 60)

    total_saved = 0

    # ============================================================
    # المصدر 1: Google News — باقة الجزائر بالفرنسية (مدعومة رسمياً)
    # ============================================================
    print("\n📡 [المصدر 1] Google News — باقة الجزائر (fr)")
    GOOGLE_QUERIES = [
        "Ghardaia", "Ghardaïa", "Mzab", "Vallee du Mzab",
        "Atfich", "Atfayech", "Ibrahim Atfich",
        "غرداية", "وادي ميزاب", "أطفيش",
    ]
    for q in GOOGLE_QUERIES:
        encoded = urllib.parse.quote(f"{q} when:30d")
        url = (f"https://news.google.com/rss/search?"
               f"q={encoded}&hl=fr&gl=DZ&ceid=DZ:fr")
        total_saved += scrape_rss_feed(url, f"Google News: {q}")
        time.sleep(1.5)

    # ============================================================
    # المصدر 2: مصادر RSS جزائرية مباشرة
    # ============================================================
    print("\n📡 [المصدر 2] مصادر RSS جزائرية مباشرة")
    ALGERIAN_RSS_FEEDS = {
        # صحف وطنية عربية
        "الشروق أونلاين":          "https://www.echoroukonline.com/feed/",
        "جريدة اللقاء":            "https://elikaaonline.com/feed/",
        "وكالة الأنباء الجزائرية": "https://www.aps.dz/ar/rss",
        # صحف وطنية فرنسية (تغطي أخبار الجزائر)
        "L'Expression":            "https://lexpressiondz.com/feeds/info-en-continu.rssi",
        "Le National":             "https://lenational.dz/?feed=rss2",
        "Alg24":                   "https://www.alg24.net/feed/",
        # إذاعة الجزائر
        "Radio Algérie":           "http://www.radioalgerie.dz/news/fr/rss.xml",
    }
    for name, url in ALGERIAN_RSS_FEEDS.items():
        total_saved += scrape_rss_feed(url, name)
        time.sleep(1.5)

    print("\n" + "=" * 60)
    print(f"انتهى التشغيل. إجمالي القصاصات الجديدة: {total_saved}")
    print("=" * 60)
