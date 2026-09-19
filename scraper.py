import os
import sys
import feedparser
import urllib.parse
from datetime import datetime
from dateutil import parser as date_parser
from supabase import create_client, Client

# --- 1. الاتصال بـ Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY!")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. الاستعلامات المباشرة مع تقييد البحث بـ 2026 داخل Google ---
SEARCH_QUERIES = [
    # العربية
    {"q": 'غرداية after:2025-12-31', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"ولاية غرداية" after:2025-12-31', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"تراث غرداية" after:2025-12-31', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"الشيخ أبي إسحاق" after:2025-12-31', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": 'مزاب after:2025-12-31', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},

    # الفرنسية
    {"q": 'Ghardaïa after:2025-12-31', "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": '"patrimoine Ghardaia" after:2025-12-31', "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": 'Mzab after:2025-12-31', "params": "hl=fr&gl=DZ&ceid=DZ:fr"},

    # الإنجليزية
    {"q": 'Ghardaia after:2025-12-31', "params": "hl=en&gl=US&ceid=US:en"},
    {"q": '"Ghardaia heritage" after:2025-12-31', "params": "hl=en&gl=US&ceid=US:en"}
]

def determine_category_and_importance(title, summary):
    text = f"{title} {summary}".lower()
    
    category = "أخبار عامة"
    heritage_kw = ["تراث", "مخطوط", "تاريخ", "قصور", "ثقافة", "مزاب", "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history", "mzab"]
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

def get_valid_date(raw_date):
    """معالجة مرنة للتاريخ تمنع إسقاط المقالات المقبولة"""
    if raw_date:
        try:
            dt = date_parser.parse(raw_date)
            # إذا كان التاريخ ينتمي لـ 2026 أو أحدث
            if dt.year >= 2026:
                return dt.isoformat()
        except Exception:
            pass
    # في حال تعذر تحليل الصيغة مع كون البحث مقيد بـ 2026، يُعتمد التوقيت الحالي
    return datetime.utcnow().isoformat()

def run_scraper():
    print("🚀 بدء جلب القصاصات لعام 2026...")

    total_added = 0
    total_found = 0

    for item in SEARCH_QUERIES:
        query_text = item["q"]
        rss_params = item["params"]

        encoded_query = urllib.parse.quote(query_text)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{rss_params}"
        
        feed = feedparser.parse(rss_url)
        entries_count = len(feed.entries)
        total_found += entries_count

        print(f"🔍 الكلمة: [{query_text.split(' ')[0]}] | النتائج الملتقطة: {entries_count}")

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()

            if not title or not link:
                continue

            published_iso = get_valid_date(published_raw)

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
            except Exception as e:
                print(f"⚠️ خطأ أثناء الحفظ في Supabase: {e}")

    print("\n" + "="*50)
    print(f"🎉 إجمالي القصاصات المكتشفة: {total_found}")
    print(f"✅ إجمالي القصاصات المحفوظة/المحدثة بنجاح: {total_added}")
    print("="*50)

if __name__ == "__main__":
    run_scraper()
