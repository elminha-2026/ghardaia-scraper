import os
import sys
import feedparser
import urllib.parse
from datetime import datetime
from dateutil import parser as date_parser
from supabase import create_client, Client

SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

SEARCH_CONFIGS = [
    {"lang": "ar", "query": '(غرداية OR "ولاية غرداية" OR "تراث غرداية" OR "الشيخ أبي إسحاق") الجزائر', "rss_params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"lang": "fr", "query": '(Ghardaïa OR "wilaya de Ghardaïa" OR "patrimoine de Ghardaïa") Algérie', "rss_params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"lang": "en", "query": '(Ghardaia OR "Ghardaia heritage") Algeria', "rss_params": "hl=en&gl=US&ceid=US:en"}
]

def determine_category_and_importance(title, summary):
    text = f"{title} {summary}".lower()
    category = "أخبار عامة"
    if any(k in text for k in ["تراث", "مخطوط", "تاريخ", "ثقافة", "patrimoine", "manuscrit", "heritage"]):
        category = "تراث وثقافة"
    elif any(k in text for k in ["أبي إسحاق", "جمعية", "ملتقى", "association", "abou issaq"]):
        category = "نشاطات الجمعية"

    importance = "عادي"
    if any(k in text for k in ["أبي إسحاق", "افتتاح", "رسمي", "اتفاقية", "وزير", "wali", "minister"]):
        importance = "عالي"

    return category, importance

def scrape_daily():
    print("🔄 بدء المسح اليومي الخفيف للأخبار الجديدة...")
    total_added = 0

    for config in SEARCH_CONFIGS:
        query = config["query"]
        params = config["rss_params"]
        
        encoded_query = urllib.parse.quote(query)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{params}"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()

            try:
                published_iso = date_parser.parse(published_raw).isoformat()
            except Exception:
                published_iso = datetime.utcnow().isoformat()

            source = entry.source.get("title", "صحافة إلكترونية") if "source" in entry and isinstance(entry.source, dict) else "صحافة إلكترونية"
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
            except Exception:
                pass

    print(f"✅ اكتمل المسح اليومي: تم إضافة/تحديث {total_added} قصاصة جديدة.")

if __name__ == "__main__":
    scrape_daily()
