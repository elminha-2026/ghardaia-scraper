import os
import sys
import feedparser
import urllib.parse
from datetime import datetime
from dateutil import parser as date_parser
from supabase import create_client, Client

# --- 1. التحقق من مفاتيح الاتصال ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY!")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. إعدادات البحث بكلمات موسعة لزيادة النتائج ---
SEARCH_CONFIGS = [
    {
        "lang": "ar",
        "query": '(غرداية OR "ولاية غرداية" OR "تراث غرداية" OR "الشيخ أبي إسحاق" OR "جمعية التراث") الجزائر',
        "rss_params": "hl=ar&gl=DZ&ceid=DZ:ar"
    },
    {
        "lang": "fr",
        "query": '(Ghardaïa OR "wilaya de Ghardaïa" OR "patrimoine de Ghardaïa" OR "Abou Issaq") Algérie',
        "rss_params": "hl=fr&gl=DZ&ceid=DZ:fr"
    },
    {
        "lang": "en",
        "query": '(Ghardaia OR "Ghardaia heritage" OR "Ghardaia province") Algeria',
        "rss_params": "hl=en&gl=US&ceid=US:en"
    }
]

def determine_category_and_importance(title, summary):
    text = f"{title} {summary}".lower()
    
    category = "أخبار عامة"
    heritage_kw = ["تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة", "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history"]
    activity_kw = ["أبي إسحاق", "جمعية", "ملتقى", "محاضرة", "ندوة", "association", "séminaire", "conférence", "abou issaq"]

    if any(k in text for k in heritage_kw):
        category = "تراث وثقافة"
    elif any(k in text for k in activity_kw):
        category = "نشاطات الجمعية"

    importance = "عادي"
    high_kw = ["أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية", "وزير", "والي", "abou issaq", "ministre", "wali", "officiel", "minister"]

    if any(k in text for k in high_kw):
        importance = "عالي"

    return category, importance

def parse_and_verify_2026(raw_date):
    """
    تحليل التاريخ والتحقق الجازم من أن المقال نشر في سنة 2026 حصراً.
    يُرجع None في حال كان التاريخ قديماً أو تعذر التحقق منه لتعزيز الدقة.
    """
    if not raw_date:
        return None
    try:
        dt = date_parser.parse(raw_date)
        # التحقق من أن السنة هي 2026 فقط
        if dt.year == 2026:
            return dt.isoformat()
        return None
    except Exception:
        return None

def run_backfill_2026():
    print("🚀 بدء استخراج كافة قصاصات عام 2026 باللغات الثلاث مع التحقق الدقيق من التاريخ...")
    
    # تقسيم سنة 2026 إلى أشهر لجلب أكبر قدر ممكن من النتائج دون أن يتجاوز حد Google RSS
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
    total_ignored = 0

    for config in SEARCH_CONFIGS:
        lang = config["lang"]
        base_query = config["query"]
        rss_params = config["rss_params"]

        print(f"\n🌐 جلب أرشيف 2026 للغة [{lang.upper()}]...")

        for start_d, end_d in months_2026:
            # استخدام بعد وقبل مع تواريخ المدى المحدد
            query = f"{base_query} after:{start_d} before:{end_d}"
            encoded_query = urllib.parse.quote(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{rss_params}"
            
            feed = feedparser.parse(rss_url)

            for entry in feed.entries:
                title = entry.get("title", "").strip()
                link = entry.get("link", "").strip()
                published_raw = entry.get("published", "").strip()

                # التحقق الصارم: هل المقال من سنة 2026 فعلاً؟
                published_iso = parse_and_verify_2026(published_raw)
                
                if not published_iso:
                    total_ignored += 1
                    continue  # استبعاد التواريخ القديمة (مثل 1990) أو غير المعروفة

                source = "صحافة إلكترونية"
                if "source" in entry and isinstance(entry.source, dict):
                    source = entry.source.get("title", "صحافة إلكترونية")

                summary = entry.get("summary", title)
                category, importance = determine_category_and_importance(title, summary)

                data = {
                    "title": title,
                    "source": source,
                    "link": link,
                    "published_date": published_iso,
                    "summary": summary,
                    "category": category,
                    "importance": importance
                }

                try:
                    res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                    if res.data:
                        total_added += 1
                except Exception:
                    pass

    print("\n" + "="*50)
    print(f"🎉 تم الانتهاء بنجاح! القصاصات المقبولة والمحققة لعام 2026: {total_added}")
    print(f"🛡️ القصاصات المستبعدة (تواريخ قديمة/غير مطابقة لـ 2026): {total_ignored}")
    print("="*50)

if __name__ == "__main__":
    run_backfill_2026()
