import os
import sys
import feedparser
import urllib.parse
import re
from datetime import datetime
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
from supabase import create_client, Client

# --- 1. التحقق من مفاتيح الاتصال ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في Secrets!")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase بنجاح.")
except Exception as e:
    print(f"❌ خطأ أثناء الاتصال بـ Supabase: {e}")
    sys.exit(1)

# --- 2. إعدادات البحث المرنة والواسعة ---
SEARCH_CONFIGS = [
    {
        "lang": "ar",
        "queries": [
            "غرداية",
            '"ولاية غرداية"',
            '"تراث غرداية"',
            '"الشيخ أبي إسحاق"',
            '"جمعية التراث"',
            '"وادي مزاب"',
            '"مزاب غرداية"',
            "مزاب الجزائر"
        ],
        "params": "hl=ar&gl=DZ&ceid=DZ:ar"
    },
    {
        "lang": "fr",
        "queries": [
            "Ghardaïa",
            '"wilaya de Ghardaia"',
            '"patrimoine Ghardaia"',
            '"Abou Issaq"',
            '"vallée du Mzab"',
            "Mzab Ghardaia"
        ],
        "params": "hl=fr&gl=DZ&ceid=DZ:fr"
    },
    {
        "lang": "en",
        "queries": [
            "Ghardaia",
            '"Ghardaia heritage"',
            '"Mzab valley"'
        ],
        "params": "hl=en&gl=US&ceid=US:en"
    }
]

# كلمات حصرية لاستبعاد مزاب المغرب فقط
MOROCCO_EXCLUDE_KEYWORDS = ["سطات", "الشاوية", "settat", "chaouia"]

def clean_summary_text(raw_html):
    """تنظيف النص وإزالة وسوم HTML ونصوص بيو الصحفيين"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    
    for tag in soup.select('header, footer, nav, aside, script, style, .sidebar, .author-bio, .author'):
        tag.decompose()
        
    text = soup.get_text(separator=' ', strip=True)

    # تنظيف بيو الصحفيين الشائع
    bio_patterns = [
        r"Djamel Kachemad.*?(?=Ghardaïa|Ghardaia|غرداية|\.|$)",
        r"journaliste au sein de la rédaction de.*?(?=\.|$)",
        r"spécialisé dans l'actualité locale.*?(?=\.|$)"
    ]
    for pattern in bio_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text.strip()

def parse_date_to_iso(raw_date):
    """تحويل التاريخ إلى ISO بشكل آمن دون إلقاء المقالات"""
    if not raw_date:
        return datetime.utcnow().isoformat()
    try:
        dt = date_parser.parse(raw_date)
        return dt.isoformat()
    except Exception:
        return datetime.utcnow().isoformat()

def is_valid_article(title, summary, raw_summary):
    """تحديد ما إذا كان الخبر يتحدث فعلياً عن غرداية/مزاب الجزائر"""
    full_text = f"{title} {summary} {raw_summary}".lower()

    # 1. استبعاد مزاب المغرب
    if any(m_kw in full_text for m_kw in MOROCCO_EXCLUDE_KEYWORDS):
        return False

    # 2. إذا كانت الكلمة في العنوان -> القبول فوراً
    valid_kw = ["غرداية", "ghardaïa", "ghardaia", "مزاب", "mzab", "أبي إسحاق", "abou issaq"]
    if any(kw in title.lower() for kw in valid_kw):
        return True

    # 3. إذا كان البيو هو المسبب الوحيد لذكر غرداية والعنوان يتحدث عن ولاية أخرى -> استبعاد
    if "djamel kachemad" in raw_summary.lower() or "journaliste au sein de la rédaction" in raw_summary.lower():
        # إذا لم يذكر اسم غرداية في الملخص النظيف بعد حذف البيو -> استبعاد
        if not any(kw in summary.lower() for kw in valid_kw):
            return False

    return True

def determine_category_and_importance(title, summary_text):
    clean_title = (title or "").lower()
    clean_summary = (summary_text or "").lower()
    full_text = f"{clean_title} {clean_summary}"

    critical_kw = [
        "حادث", "كارثة", "حريق", "فيضان", "وفاة", "ضحايا", "خطير", 
        "طوارئ", "انهيار", "اعتداء", "انفجار", "مصابين", "جريمة", "غرق",
        "accident", "incendie", "inondation", "décès", "victimes", "explosion", "drame", "crash",
        "disaster", "fire", "flood", "death", "fatalities", "emergency", "collapse"
    ]

    if any(k in clean_title for k in critical_kw) or any(clean_summary.count(k) >= 2 for k in critical_kw):
        return "أحداث خطيرة", "أحداث خطيرة"

    heritage_kw = ["تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة", "مزاب", "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history", "mzab"]
    activity_kw = ["أبي إسحاق", "جمعية", "ملتقى", "محاضرة", "ندوة", "association", "séminaire", "conférence", "abou issaq"]
    economy_kw = ["اقتصاد", "سوق", "تجارة", "استثمار", "تنمية", "ميزانية", "أسعار", "بورصة", "فلاحة", "زراعة", "صناعة", "économie", "commerce", "investissement", "market", "economy", "trade", "business"]

    category = "أخبار عامة"
    if any(k in full_text for k in heritage_kw):
        category = "تراث وثقافة"
    elif any(k in full_text for k in activity_kw):
        category = "نشاطات الجمعية"
    elif any(k in full_text for k in economy_kw):
        category = "اقتصاد"

    importance = "عادي"
    high_kw = ["أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية", "وزير", "والي", "abou issaq", "ministre", "wali", "officiel", "minister"]
    if any(k in full_text for k in high_kw):
        importance = "عالي"

    return category, importance

def fetch_rss(query, params):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{params}"
    return feedparser.parse(rss_url)

def scrape_and_store():
    print("🚀 بدء التمشيط الشامل والمباشر لاستخراج جميع القصاصات...")

    total_added = 0
    total_skipped = 0

    for config in SEARCH_CONFIGS:
        lang = config["lang"]
        queries = config["queries"]
        params = config["params"]

        print(f"\n🌐 --- معالجة الاستعلامات باللغة [{lang.upper()}] ---")

        for q in queries:
            feed = fetch_rss(q, params)

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                published_raw = entry.get("published", "").strip()

                published_iso = parse_date_to_iso(published_raw)

                raw_summary = entry.get("summary", "")
                clean_summary = clean_summary_text(raw_summary)

                # التثبت من صحة المقال
                if not is_valid_article(title, clean_summary, raw_summary):
                    total_skipped += 1
                    continue

                source = "صحافة إلكترونية"
                if "source" in entry and isinstance(entry.source, dict):
                    source = entry.source.get("title", "صحافة إلكترونية")

                if title and link:
                    category, importance = determine_category_and_importance(title, clean_summary)

                    data = {
                        "title": title,
                        "source": source,
                        "link": link,
                        "published_date": published_iso,
                        "summary": clean_summary,
                        "category": category,
                        "importance": importance
                    }

                    try:
                        res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                        if res.data:
                            total_added += 1
                    except Exception as e:
                        print(f"⚠️ خطأ أثناء الإدراج: {e}")

    print("\n" + "="*60)
    print(f"🎉 تم استخراج وحفظ {total_added} قصاصة بنجاح!")
    print(f"🛡️ تم تخطي {total_skipped} عنصر (إيجابيات كاذبة أو تخص مناطق أخرى).")
    print("="*60)

if __name__ == "__main__":
    scrape_and_store()
