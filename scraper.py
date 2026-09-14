import os
import feedparser
import urllib.parse
from supabase import create_client, Client

# --- 1. إعدادات الاتصال بـ Supabase ---
SUPABASE_URL = os.environ.get("https://sixvgxtoizjxprkpkjki.supabase.co")
SUPABASE_KEY = os.environ.get("sb_publishable_jx6mv6vokG8gydCt1Xzt5Q_1rP6xH5p")  # مفتاح service_role

if not SUPABASE_URL or not SUPABASE_KEY:
    raise ValueError("بيانات الاتصال بـ Supabase غير مكتملة في Secrets!")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. إعداد استعلام البحث عن أخبار 2026 ---
# البحث يتضمن الكلمات المفتاحية مع تخصيص سنة 2026
QUERY = '(غرداية OR "تراث غرداية" OR "الشيخ أبي إسحاق") "2026"'
ENCODED_QUERY = urllib.parse.quote(QUERY)

# رابط RSS الخاص بأخبار جوجل
RSS_URL = f"https://news.google.com/rss/search?q={ENCODED_QUERY}&hl=ar&gl=DZ&ceid=DZ:ar"

def scrape_and_store():
    print("🚀 بدء تمشيط الأخبار لجلب القصاصات...")
    feed = feedparser.parse(RSS_URL)
    
    if not feed.entries:
        print("⚠️ لم يتم العثور على مقالات جديدة.")
        return

    new_articles_count = 0
    skipped_count = 0
    
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()
        source = entry.get("source", {}).get("title", "صحافة إلكترونية")
        
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
                # إدراج المقال في قاعدة البيانات
                supabase.table("clippings").insert(data).execute()
                new_articles_count += 1
                print(f"✅ قصاصة جديدة: {title}")
            except Exception:
                # المقال موجود مسبقاً في الأرشيف فتتجاهله قاعدة البيانات
                skipped_count += 1

    print(f"\n📊 النتيجة: تم إدراج {new_articles_count} مقال جديد | تم تجاهل {skipped_count} مقال مكرر.")

if __name__ == "__main__":
    scrape_and_store()
