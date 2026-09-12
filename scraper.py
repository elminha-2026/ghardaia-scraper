import feedparser
from supabase import create_client, Client

# --- بيانات الاتصال بقواعد بيانات Supabase (الخاصة بك من الخطوة 1) ---
SUPABASE_URL = "أدخل_Project_URL_هنا"
SUPABASE_SERVICE_KEY = "أدخل_service_role_key_هنا"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_SERVICE_KEY)

# --- روابط تغذية RSS لرصد مقالات غرداية ---
RSS_FEEDS = [
    {
        "source_default": "أرشيف الصحف الجزائرية",
        "url": "https://news.google.com/rss/search?q=%D2%BA%D8%B1%D8%AF%D8%A7%D9%8A%D8%A9+%D8%A7%D9%84%D8%AC%D8%B2%D8%A7%D8%A6%D8%B1&hl=ar&gl=DZ&ceid=DZ:ar"
    }
]

def run_scraper():
    print("🚀 بدء رصد الصحف عن غرداية...")
    new_count = 0
    
    for feed_info in RSS_FEEDS:
        feed = feedparser.parse(feed_info["url"])
        for entry in feed.entries:
            title = entry.title
            link = entry.link
            published = entry.get("published", "غير محدد")
            summary = entry.get("summary", "").replace("<p>", "").replace("</p>", "")
            source = entry.get("source", {}).get("title", feed_info["source_default"])

            try:
                data = {
                    "title": title,
                    "source": source,
                    "link": link,
                    "published_date": published,
                    "summary": summary[:250] + "...",
                    "category": "report"
                }
                # التخزين في خادم Supabase مباشرة
                supabase.table("clippings").insert(data).execute()
                print(f"✅ تم إضافة: {title} | {source}")
                new_count += 1
            except Exception as e:
                # المقال مخزن سابقاً (يتم تجاهله تلقائياً)
                pass

    print(f"✨ اكتملت العملية! تم إضافة {new_count} قصاصة جديدة.")

if __name__ == "__main__":
    run_scraper()