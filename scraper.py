import os
import sys
import feedparser
import urllib.parse
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

# --- 2. استعلام البحث ---
QUERY = '(غرداية OR "ولاية غرداية" OR "تراث غرداية" OR "الشيخ أبي إسحاق" OR "جمعية التراث") الجزائر'
ENCODED_QUERY = urllib.parse.quote(QUERY)
RSS_URL = f"https://news.google.com/rss/search?q={ENCODED_QUERY}&hl=ar&gl=DZ&ceid=DZ:ar"

def determine_category_and_importance(title, summary):
    """تحليل نص الخبر لتحديد التصنيف والأهمية تلقائياً"""
    text = f"{title} {summary}".lower()
    
    # تحديد التصنيف
    category = "أخبار عامة"
    if any(k in text for k in ["تراث", "مخطوط", "تاريخ", "زايد", "قصور"]):
        category = "تراث وثقافة"
    elif any(k in text for k in ["أبي إسحاق", "جمعية", "ملتقى", "محاضرة"]):
        category = "نشاطات الجمعية"

    # تحديد الأهمية
    importance = "عادي"
    if any(k in text for k in ["أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية"]):
        importance = "عالي"

    return category, importance

def scrape_and_store():
    print("🚀 بدء تمشيط الأخبار لجلب القصاصات وتصنيفها...")
    feed = feedparser.parse(RSS_URL)

    if not feed.entries:
        print("⚠️ لم يتم العثور على أي مقالات.")
        return

    print(f"🔎 تم العثور على {len(feed.entries)} خبر. جاري الحفظ والتصنيف في Supabase...")

    new_articles_count = 0
    skipped_count = 0
    
    for entry in feed.entries:
        title = entry.get("title", "").strip()
        link = entry.get("link", "").strip()
        published = entry.get("published", "").strip()
        
        source = "صحافة إلكترونية"
        if "source" in entry and isinstance(entry.source, dict):
            source = entry.source.get("title", "صحافة إلكترونية")

        summary = entry.get("summary", "")
        if not summary and "title_detail" in entry:
            summary = title

        if title and link:
            # تحليل ذكي للتصنيف والأهمية
            category, importance = determine_category_and_importance(title, summary)

            data = {
                "title": title,
                "source": source,
                "link": link,
                "published_date": published,
                "summary": summary,
                "category": category,
                "importance": importance
            }
            
            try:
                # الحفظ والتحديث تلقائياً دون تكرار
                response = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                if response.data:
                    new_articles_count += 1
                    print(f"✅ [{category} | أهمية: {importance}] {title[:40]}...")
            except Exception as e:
                print(f"⚠️ تعذر إدراج الخبر: {e}")
                skipped_count += 1

    print("\n" + "="*50)
    print(f"📊 النتيجة: تم معالجة وتخزين {new_articles_count} مقال بنجاح!")
    print("="*50)

if __name__ == "__main__":
    scrape_and_store()
