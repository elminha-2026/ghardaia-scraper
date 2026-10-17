import os
import re
import time
import urllib.parse
import feedparser
import requests
from datetime import datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات قاعدة البيانات Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على مفاتيح SUPABASE_URL أو SUPABASE_KEY.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. دالة التنظيف
# ==========================================
def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

# ==========================================
# 3. دالة الحفظ (نسخة التشخيص المبدئي)
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    
    # نطبع كل ما يجلبه جوجل للتأكد
    print(f"   📄 محاولة حفظ: {title[:40]}...")

    payload = {
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published_date": pub_date,
        "importance": "عادي",
        "category": "أخبار عامة"
    }

    try:
        supabase.table("clippings").upsert(payload, on_conflict="link").execute()
        print(f"   ✅ تم الحفظ في Supabase بنجاح!")
        return True
    except Exception as e:
        print(f"   ❌ خطأ في Supabase (تأكد من إعدادات الجدول): {e}")
        return False

# ==========================================
# 4. دالة الكشط
# ==========================================
def scrape_google_news(query: str):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        feed = feedparser.parse(response.content)
        
        print(f"\n🔎 بحث: {query}")
        print(f"   📥 جوجل أعاد: {len(feed.entries)} خبر.")
        
        added_count = 0
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            
            source = "صحافة إلكترونية"
            if "source" in entry and isinstance(entry.source, dict):
                source = entry.source.get("title", "صحافة إلكترونية")

            pub_date = datetime.utcnow().isoformat() + "Z"
            if "published_parsed" in entry:
                try:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                except Exception:
                    pass

            if save_to_supabase(title, summary, link, source, pub_date):
                added_count += 1
                
        return added_count
                
    except Exception as e:
        print(f"   ❌ خطأ أثناء الاتصال بجوجل: {e}")
        return 0

# ==========================================
# 5. التنفيذ
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء التشخيص...")
    
    # نبحث عن كلمة واحدة فقط للتجربة
    queries = ['"غرداية"', '"بريان" الجزائر']
    
    for q in queries:
        scrape_google_news(q)
        time.sleep(2)
