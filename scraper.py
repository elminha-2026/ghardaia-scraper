import os
import sys
import feedparser
import urllib.parse
from supabase import create_client, Client

# --- 1. التحقق من مفاتيح الاتصال بـ Supabase ---
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")  # مفتاح service_role للتخزين الآمن

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY في Secrets!")
    sys.exit(1)

try:
    supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)
    print("✅ تم الاتصال بـ Supabase بنجاح.")
except Exception as e:
    print(f"❌ خطأ أثناء الاتصال بـ Supabase: {e}")
    sys.exit(1)

# --- 2. إعداد استعلام البحث الشامل (غرداية والجزائر والتراث) ---
QUERY = '(غرداية OR "ولاية غرداية" OR "تراث غرداية" OR "الشيخ أبي إسحاق" OR "جمعية التراث") الجزائر'
ENCODED_QUERY = urllib.parse.quote(QUERY)
RSS_URL = f"https://news.google.com/rss/search?q={ENCODED_QUERY}&hl=ar&gl=DZ&ceid=DZ:ar"

def scrape_and_store():
    print("🚀 بدء تمشيط الأخبار لجلب القصاصات...")
    
    try:
        feed = feedparser.parse(RSS_URL)
    except Exception as e:
        print(f"❌ خطأ أثناء جلب تغذية الأخبار RSS: {e}")
        return

    if not feed.entries:
        print("⚠️ لم يتم العثور على أي مقالات من Google News باستعلام البحث الحالي.")
        return

    print(f"🔎 تم العثور على {len(feed.entries)} خبر في RSS. جاري التخزين في قاعدة البيانات...\n")

    new_articles_count = 0
    skipped_count = 0
    
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()
        
        # استخراج اسم المصدر الصحفي
        source = "صحافة إلكترونية"
        if "source" in entry and isinstance(entry.source, dict):
            source = entry.source.get("title", "صحافة إلكترونية")

        # استخراج الملخص
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
                print(f"✅ تم حفظ القصاصة: {title}")
            except Exception as e:
                # يتجاهل المقالات المكررة (المرتبطة بـ UNIQUE constraint على رابط link)
                skipped_count += 1

    print("\n" + "="*40)
    print(f"📊 النتيجة النهائية:")
    print(f"   - قصاصات جديدة تم إدراجها: {new_articles_count}")
    print(f"   - قصاصات مكررة/متجاهلة: {skipped_count}")
    print("="*40)

if __name__ == "__main__":
    scrape_and_store()
