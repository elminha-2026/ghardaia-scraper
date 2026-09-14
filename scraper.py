import os
import sys
import feedparser
import urllib.parse
from supabase import create_client, Client

# --- 1. التحقق من مفاتيح البيئة ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # مفتاح service_role

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في Secrets!")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
except Exception as e:
    print(f"❌ خطأ أثناء الاتصال بـ Supabase: {e}")
    sys.exit(1)

# --- 2. إعداد استعلام البحث عن أخبار 2026 ---
QUERY = '(غرداية OR "تراث غرداية" OR "الشيخ أبي إسحاق") "2026"'
ENCODED_QUERY = urllib.parse.quote(QUERY)
RSS_URL = f"https://news.google.com/rss/search?q={ENCODED_QUERY}&hl=ar&gl=DZ&ceid=DZ:ar"

def scrape_and_store():
    print("🚀 بدء تمشيط الأخبار لجلب القصاصات...")
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        print(f"❌ خطأ أثناء جلب تغذية RSS: {e}")
        return

    if not feed.entries:
        print("⚠️ لم يتم العثور على مقالات جديدة.")
        return

    new_articles_count = 0
    skipped_count = 0
    
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()
        
        # استخراج اسم المصدر
        source = "صحافة إلكترونية"
        if "source" in entry and isinstance(entry.source, dict):
            source = entry.source.get("title", "صحافة إلكترونية")

        summary = entry.get("summary", "")
        if not summary and "title_detail" in entry:
            summary = title

        if title and link:
            data = {
                "title": title,
                "source": source,
                "link": link,
                "published_date": published,
                "summary": summary,
                "category": "article_2026"
            }
            
            try:
                supabase.table("clippings").insert(data).execute()
                new_articles_count += 1
                print(f"✅ قصاصة جديدة: {title}")
            except Exception as e:
                # تجاوز المقالات المكررة أو الأخطاء الفردية دون إيقاف السكريبت
                skipped_count += 1

    print(f"\n📊 النتيجة: تم إدراج {new_articles_count} مقال جديد | تم تجاهل/تكرار {skipped_count} مقال.")

if __name__ == "__main__":
    scrape_and_store()
