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

# --- 2. إعدادات البحث الدقيقة (تخصيص الجزائر وتفادي مزاب المغرب) ---
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
            '"مزاب غرداية"'
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
            '"Mzab Ghardaia"'
        ],
        "params": "hl=fr&gl=DZ&ceid=DZ:fr"
    },
    {
        "lang": "en",
        "queries": [
            "Ghardaia",
            '"Ghardaia heritage"',
            '"Mzab valley Ghardaia"'
        ],
        "params": "hl=en&gl=US&ceid=US:en"
    }
]

# الكلمات المرفوضة الخاصة بمزاب المغرب لضمان عدم إدخال أخبار المملكة المغربية
MOROCCO_EXCLUDE_KEYWORDS = ["سطات", "الشاوية", "المغرب", "maroc", "settat", "chaouia"]

def clean_summary_text(raw_html):
    """تنظيف نص الملخص وحذف الأجزاء الخاصة بتوقيع الصحفيين والـ Author Bio"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    
    # حذف أي عناصر تعبيرية عن الكاتب
    for tag in soup.select('header, footer, nav, aside, script, style, .sidebar, .author-bio, .author'):
        tag.decompose()
        
    text = soup.get_text(separator=' ', strip=True)

    # حذف أنماط تعريف الصحفي الشائعة (مثل حالة Djamel Kachemad)
    bio_patterns = [
        r"Djamel Kachemad.*?(?=wilaya de Ghardaïa|Ghardaïa|\.|$)",
        r"journaliste au sein de la rédaction de.*?Ghardaïa\.?",
        r"spécialisé dans l'actualité locale.*?Ghardaïa\.?",
        r"صحفي متخصص في أخبار.*?غرداية\.?"
    ]
    for pattern in bio_patterns:
        text = re.sub(pattern, "", text, flags=re.IGNORECASE)

    return text.strip()

def is_valid_ghardaia_article(title, clean_summary):
    """
    التحقق من أن الخبر يخص غرداية/مزاب الجزائر وليس إيجابية كاذبة أو يخص المغرب
    """
    full_text = f"{title} {clean_summary}".lower()

    # 1. استبعاد الأخبار الخاصة بمزاب المغرب
    if any(m_kw in full_text for m_kw in MOROCCO_EXCLUDE_KEYWORDS):
        # إلا إذا وُجد ذكر صريح لغرداية أو الجزائر في العنوان
        if "غرداية" not in title.lower() and "ghardaïa" not in title.lower() and "ghardaia" not in title.lower():
            return False

    # 2. التأكد من وجود إشارة حقيقية لغرداية أو مزاب الجزائر
    valid_keywords = ["غرداية", "ghardaïa", "ghardaia", "مزاب", "mzab", "أبي إسحاق", "abou issaq"]
    
    # إذا كانت الكلمة في العنوان فالمقال مؤكد 100%
    if any(kw in title.lower() for kw in valid_keywords):
        return True

    # إذا لم تكن في العنوان، يجب أن تظهر في الملخص النظيف (بعد حذف بيو الكاتب)
    if any(kw in clean_summary.lower() for kw in valid_keywords):
        return True

    return False

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

    is_critical = False
    if any(k in clean_title for k in critical_kw):
        is_critical = True
    else:
        for k in critical_kw:
            if clean_summary.count(k) >= 2:
                is_critical = True
                break

    if is_critical:
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

def validate_and_parse_2026_date(raw_date):
    if not raw_date:
        return None
    try:
        dt = date_parser.parse(raw_date)
        if dt.year == 2026:
            return dt.isoformat()
    except Exception:
        pass
    return None

def fetch_rss(query, params):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{params}"
    return feedparser.parse(rss_url)

def scrape_and_store():
    print("🚀 بدء التمشيط المفلتر والدقيق لعام 2026...")
    
    months_2026 = [
        ("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30"),
        ("2026-05-01", "2026-05-31"), ("2026-06-01", "2026-06-30"),
        ("2026-07-01", "2026-07-31"), ("2026-08-01", "2026-08-31"),
        ("2026-09-01", "2026-09-30"), ("2026-10-01", "2026-10-31"),
        ("2026-11-01", "2026-11-30"), ("2026-12-01", "2026-12-31"),
    ]

    total_added = 0
    total_rejected = 0

    for config in SEARCH_CONFIGS:
        lang = config["lang"]
        queries = config["queries"]
        params = config["params"]

        print(f"\n🌐 --- بدء المعالجة باللغة [{lang.upper()}] ---")

        for q in queries:
            all_target_queries = [q]
            for start_d, end_d in months_2026:
                all_target_queries.append(f"{q} after:{start_d} before:{end_d}")

            for target_q in all_target_queries:
                feed = fetch_rss(target_q, params)

                for entry in feed.entries:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    published_raw = entry.get("published", "").strip()

                    # 1. التحقق من السنة (2026 حصراً)
                    published_iso = validate_and_parse_2026_date(published_raw)
                    if not published_iso:
                        total_rejected += 1
                        continue

                    # 2. تنظيف الملخص وحذف توقيع الكاتب
                    raw_summary = entry.get("summary", "")
                    clean_summary = clean_summary_text(raw_summary)

                    # 3. الفحص الدقيق للمقال (استبعاد مزاب المغرب وإيجابيات الكاتب الكاذبة)
                    if not is_valid_ghardaia_article(title, clean_summary):
                        total_rejected += 1
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
                        except Exception:
                            pass

    print("\n" + "="*60)
    print(f"🎉 النتيجة النهائية: تم حفظ وتحديث {total_added} قصاصة دقيقة ومؤكدة لعام 2026!")
    print(f"🛡️ تم استبعاد {total_rejected} مقال (تاريخ غير متوافق، أخبار مزاب المغرب، أو توقيع الصحفي الكاذب).")
    print("="*60)

if __name__ == "__main__":
    scrape_and_store()
