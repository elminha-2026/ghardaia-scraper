import feedparser
from supabase import create_client, Client

# --- استبدل هذه القيم ببيانات مشروعك من Supabase ---
SUPABASE_URL = "ضع_Project_URL_هنا"
SUPABASE_SERVICE_KEY = "ضع_service_role_key_هنا"

supabase: Client = create_client(SUPABASE_URL, sb_publishable_jx6mv6vokG8gydCt1Xzt5Q_1rP6xH5p)

# رابط تغذية الأخبار المباشر عن غرداية
RSS_URL = "https://news.google.com/rss/search?q=%D2%BA%D8%B1%D8%AF%D8%A7%D9%8A%D8%A9+%D8%A7%D9%84%D8%AC%D8%B2%D8%A7%D8%A6%D8%B1&hl=ar&gl=DZ&ceid=DZ:ar"

def run_scraper():
    print("🚀 بدء رصد الأخبار...")
    feed = feedparser.parse(RSS_URL)
    new_count = 0
    
    for entry in feed.entries:
        title = entry.title
        link = entry.link
        published = entry.get("published", "")
        summary = entry.get("summary", "").replace("<p>", "").replace("</p>", "")
        source = entry.get("source", {}).get("title", "جريدة جزائرية")

        try:
            data = {
                "title": title,
                "source": source,
                "link": link,
                "published_date": published,
                "summary": summary[:250] + "...",
                "category": "report"
            }
            # التخزين المباشر في قاعدة البيانات
            supabase.table("clippings").insert(data).execute()
            print(f"✅ تم إضافة: {title}")
            new_count += 1
        except Exception:
            # المقال مكرر أو موجود مسبقاً
            pass

    print(f"✨ اكتملت العملية! تم إدراج {new_count} مقال جديد.")

if __name__ == "__main__":
    run_scraper()
