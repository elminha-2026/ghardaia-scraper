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
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في Secrets!")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase بنجاح.")
except Exception as e:
    print(f"❌ خطأ أثناء الاتصال بـ Supabase: {e}")
    sys.exit(1)

# --- 2. إعداد البحث والتصنيف ---
BASE_KEYWORDS = '(غرداية OR "ولاية غرداية" OR "تراث غرداية" OR "الشيخ أبي إسحاق" OR "جمعية التراث") الجزائر'

def determine_category_and_importance(title, summary):
    """تحليل نص الخبر لتحديد التصنيف والأهمية تلقائياً"""
    text = f"{title} {summary}".lower()
    
    category = "أخبار عامة"
    if any(k in text for k in ["تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة"]):
        category = "تراث وثقافة"
    elif any(k in text for k in ["أبي إسحاق", "جمعية", "ملتقى", "محاضرة", "ندوة"]):
        category = "نشاطات الجمعية"

    importance = "عادي"
    if any(k in text for k in ["أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية", "وزير", "والي"]):
        importance = "عالي"

    return category, importance

def parse_to_iso_date(raw_date):
    """تحويل التاريخ المقروء من RSS إلى صيغة ISO المتوافقة مع Supabase"""
    try:
        dt = date_parser.parse(raw_date)
        return dt.isoformat()
    except Exception:
        return datetime.utcnow().isoformat()

def fetch_rss_for_query(query):
    """جلب وتحليل رابط RSS لطلب معين"""
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    return feedparser.parse(rss_url)

def scrape_and_store():
    print("🚀 بدء تمشيط أرشيف عام 2026 كاملاً وتجاوز عقبة الـ 100 خبر...")
    
    # تقسيم السحب على أشهُر سنة 2026 للحصول على كافة القصاصات (أكثر من 500+)
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
    total_skipped = 0

    # 1. البحث الشامل العام للتأكد من الأخبار الحديثة
    search_queries = [BASE_KEYWORDS]

    # 2. إضافة الاستعلامات الزمنية للحصول على التغطية الكاملة لكل شهر
    for start_d, end_d in months_2026:
        search_queries.append(f"{BASE_KEYWORDS} after:{start_d} before:{end_d}")

    for idx, query in enumerate(search_queries, 1):
        print(f"\n🔎 [جولة {idx}/{len(search_queries)}] تنفيذ الاستعلام...")
        feed = fetch_rss_for_query(query)

        if not feed.entries:
            continue

        print(f"   📥 تم العثور على {len(feed.entries)} عنصر في هذه الجولة.")

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()
            
            source = "صحافة إلكترونية"
            if "source" in entry and isinstance(entry.source, dict):
                source = entry.source.get("title", "صحافة إلكترونية")

            summary = entry.get("summary", "")
            if not summary and "title_detail" in entry:
                summary = title

            if title and link:
                category, importance = determine_category_and_importance(title, summary)
                published_iso = parse_to_iso_date(published_raw)

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
                    # تحديث أو إضافة دون تكرار
                    response = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                    if response.data:
                        total_added += 1
                except Exception as e:
                    total_skipped += 1

    print("\n" + "="*50)
    print(f"🎉 النتيجة النهائية: تم معالجة وتحديث {total_added} قصاصة لعام 2026 بنجاح!")
    print("="*50)

if __name__ == "__main__":
    scrape_and_store()
