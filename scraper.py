import os
import sys
import feedparser
import urllib.parse
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

# --- 2. استعلامات متكاملة وموسعة للغات الثلاث ---
SEARCH_CONFIGS = [
    {
        "lang": "ar",
        "queries": [
            "غرداية",
            '"ولاية غرداية"',
            '"تراث غرداية"',
            '"الشيخ أبي إسحاق"',
            '"جمعية التراث"',
            "مزاب"
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
            "Mzab"
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

def clean_html_text(raw_html):
    """تنظيف نص الملخص من وسم الـ HTML والتنقلات الجانبية"""
    if not raw_html:
        return ""
    soup = BeautifulSoup(raw_html, "html.parser")
    # استبعاد العناصر الهامشية إن وجدت
    for tag in soup.select('header, footer, nav, aside, script, style, .sidebar, .author-bio'):
        tag.decompose()
    return soup.get_text(separator=' ', strip=True)

def determine_category_and_importance(title, summary_text):
    """
    تحليل دقيق لمنع الإيجابيات الكاذبة وتحديد التصنيف والأهمية باللغات الثلاث
    """
    clean_title = (title or "").lower()
    clean_summary = (summary_text or "").lower()
    full_text = f"{clean_title} {clean_summary}"

    # 1. كلمات الأحداث الخطيرة بلغات متعددة
    critical_kw = [
        "حادث", "كارثة", "حريق", "فيضان", "وفاة", "ضحايا", "خطير", 
        "طوارئ", "انهيار", "اعتداء", "انفجار", "مصابين", "جريمة", "غرق",
        "accident", "incendie", "inondation", "décès", "victimes", "explosion", "drame", "crash",
        "disaster", "fire", "flood", "death", "fatalities", "emergency", "collapse"
    ]

    # --- فحص الأحداث الخطيرة (آلية منع الإيجابيات الكاذبة) ---
    is_critical = False
    
    # المعيار الأول: وجود كلمة خطيرة مباشرة في العنوان (مؤشر قطعي)
    if any(k in clean_title for k in critical_kw):
        is_critical = True
    else:
        # المعيار الثاني: تكرار الكلمة مرتين على الأقل في نص المقال/الملخص لمنع التقاط الهوامش العابرة
        for k in critical_kw:
            if clean_summary.count(k) >= 2:
                is_critical = True
                break

    if is_critical:
        return "أحداث خطيرة", "أحداث خطيرة"

    # 2. بقية التصنيفات والمفاهيم
    heritage_kw = [
        "تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة", "مزاب",
        "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history", "mzab"
    ]
    activity_kw = [
        "أبي إسحاق", "جمعية", "ملتقى", "محاضرة", "ندوة",
        "association", "séminaire", "conférence", "abou issaq"
    ]
    economy_kw = [
        "اقتصاد", "سوق", "تجارة", "استثمار", "تنمية", "ميزانية", "أسعار", "بورصة", "فلاحة", "زراعة", "أسواق", "صناعة",
        "économie", "commerce", "investissement", "market", "economy", "trade", "business"
    ]

    category = "أخبار عامة"
    if any(k in full_text for k in heritage_kw):
        category = "تراث وثقافة"
    elif any(k in full_text for k in activity_kw):
        category = "نشاطات الجمعية"
    elif any(k in full_text for k in economy_kw):
        category = "اقتصاد"

    # 3. تحديد الأهمية لبقية الأخبار
    importance = "عادي"
    high_kw = [
        "أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية", "وزير", "والي",
        "abou issaq", "ministre", "wali", "officiel", "minister"
    ]

    if any(k in full_text for k in high_kw):
        importance = "عالي"

    return category, importance

def validate_and_parse_2026_date(raw_date):
    """التحقق الجازم من أن القصاصة تنتمي لعام 2026 حصراً وترجيع صيغة ISO"""
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
    print("🚀 بدء التمشيط العميق لعام 2026 باللغات الثلاث (العربية، الفرنسية، الإنجليزية)...")
    
    months_2026 = [
        ("2026-01-01", "2026-01-31"),
        ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"),
        ("2026-04-01", "2026-04-30"),
        ("2026-05-01", "2026-05-31"),
        ("2026-06-01", "2026-06-30"),
        ("2026-07-01", "2026-07-31"),
        ("2026-08-01", "2026-08-31"),
        ("2026-09-01", "2026-09-30"),
        ("2026-10-01", "2026-10-31"),
        ("2026-11-01", "2026-11-30"),
        ("2026-12-01", "2026-12-31"),
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

                    published_iso = validate_and_parse_2026_date(published_raw)
                    if not published_iso:
                        total_rejected += 1
                        continue

                    source = "صحافة إلكترونية"
                    if "source" in entry and isinstance(entry.source, dict):
                        source = entry.source.get("title", "صحافة إلكترونية")

                    raw_summary = entry.get("summary", "")
                    if not raw_summary and "title_detail" in entry:
                        raw_summary = title

                    # تنظيف الملخص من وسوم الـ HTML والملاحظات الجانبية
                    summary_clean = clean_html_text(raw_summary)

                    if title and link:
                        category, importance = determine_category_and_importance(title, summary_clean)

                        data = {
                            "title": title,
                            "source": source,
                            "link": link,
                            "published_date": published_iso,
                            "summary": summary_clean,
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
    print(f"🎉 النتيجة النهائية: تم حفظ وتحديث {total_added} قصاصة مؤكدة لعام 2026 بنجاح!")
    print(f"🛡️ تم استبعاد {total_rejected} مقال لعدم توافق تاريخها مع سنة 2026.")
    print("="*60)

if __name__ == "__main__":
    scrape_and_store()
