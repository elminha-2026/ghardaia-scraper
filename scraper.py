import os
import sys
import feedparser
import urllib.parse
from datetime import datetime
from dateutil import parser as date_parser
from supabase import create_client, Client

# --- 1. التحقق من مفاتيح الاتصال بـ Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

print("🔍 [اختبار الاتصال] جاري التحقق من متغيرات البيئة...")
if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ قاطع: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في Secrets!")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase بنجاح.")
except Exception as e:
    print(f"❌ خطأ أثناء الاتصال بـ Supabase: {e}")
    sys.exit(1)

# --- 2. الاستعلامات الكلاسيكية البسيطة والمستقرة (بدون after/before لمنع منع النتائج) ---
SEARCH_QUERIES = [
    # العربية
    {"q": "غرداية", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": "ولاية غرداية", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": "تراث غرداية", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": "الشيخ أبي إسحاق", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": "مزاب", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},

    # الفرنسية
    {"q": "Ghardaia", "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": "patrimoine Ghardaia", "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": "Mzab", "params": "hl=fr&gl=DZ&ceid=DZ:fr"},

    # الإنجليزية
    {"q": "Ghardaia", "params": "hl=en&gl=US&ceid=US:en"},
    {"q": "Ghardaia heritage", "params": "hl=en&gl=US&ceid=US:en"}
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

def process_date(raw_date):
    """تحليل التاريخ بطريقة آمنة تضمن الحفظ ولا تسقط المقالات"""
    if raw_date:
        try:
            dt = date_parser.parse(raw_date)
            return dt.isoformat()
        except Exception:
            pass
    return datetime.utcnow().isoformat()

def run_scraper():
    print("\n🚀 بدء جلب وتحديث كافة القصاصات المتاحة...")

    total_added = 0
    total_found_overall = 0

    for item in SEARCH_QUERIES:
        query_text = item["q"]
        rss_params = item["params"]

        encoded_query = urllib.parse.quote(query_text)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{rss_params}"
        
        feed = feedparser.parse(rss_url)
        entries_count = len(feed.entries)
        total_found_overall += entries_count

        print(f"📡 البحث عن: [{query_text}] ---> تم العثور على ({entries_count}) خبر")

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()

            if not title or not link:
                continue

            published_iso = process_date(published_raw)

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
                # حفظ القصاصة في جدول clippings مع تجنب التكرار بفضل رابط الخبر Unique Link
                res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                if res.data:
                    total_added += 1
            except Exception as e:
                print(f"   ⚠️ خطأ Supabase أثناء حفظ [{title[:20]}...]: {e}")

    print("\n" + "="*60)
    print(f"📊 إجمالي المقالات الملتقطة من Google News: {total_found_overall}")
    print(f"🎉 إجمالي القصاصات المحفوظة/المحدثة بـ Supabase: {total_added}")
    print("="*60)

if __name__ == "__main__":
    run_scraper()
