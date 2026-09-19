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
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY!")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# --- 2. الكلمات المفتاحية مقسمة لضمان جلب أكبر عدد من التحديثات اليومية ---
SEARCH_QUERIES = [
    # العربية
    {"q": "غرداية", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"ولاية غرداية"', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"تراث غرداية"', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"الشيخ أبي إسحاق"', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": '"جمعية التراث"', "params": "hl=ar&gl=DZ&ceid=DZ:ar"},
    {"q": "مزاب", "params": "hl=ar&gl=DZ&ceid=DZ:ar"},

    # الفرنسية
    {"q": "Ghardaïa", "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": '"patrimoine Ghardaia"', "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": '"Abou Issaq"', "params": "hl=fr&gl=DZ&ceid=DZ:fr"},
    {"q": "M'zab", "params": "hl=fr&gl=DZ&ceid=DZ:fr"},

    # الإنجليزية
    {"q": "Ghardaia", "params": "hl=en&gl=US&ceid=US:en"},
    {"q": '"Ghardaia heritage"', "params": "hl=en&gl=US&ceid=US:en"},
    {"q": '"Mzab valley"', "params": "hl=en&gl=US&ceid=US:en"}
]

def determine_category_and_importance(title, summary):
    text = f"{title} {summary}".lower()
    
    category = "أخبار عامة"
    heritage_kw = ["تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة", "مزاب", "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history", "mzab"]
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

def verify_and_parse_2026(raw_date):
    """التحقق الصارم من أن الخبر حديث ويخص عام 2026 فقط"""
    if not raw_date:
        return None
    try:
        dt = date_parser.parse(raw_date)
        if dt.year == 2026:
            return dt.isoformat()
        return None
    except Exception:
        return None

def scrape_daily():
    print("🔄 بدء المسح اليومي المكثف لكافة الأخبار والقصاصات الجديدة لعام 2026...")

    total_added = 0
    total_rejected = 0

    for item in SEARCH_QUERIES:
        query_text = item["q"]
        rss_params = item["params"]

        encoded_query = urllib.parse.quote(query_text)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{rss_params}"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()

            published_iso = verify_and_parse_2026(published_raw)
            
            # تجاهل أي قصاصة ليست من عام 2026
            if not published_iso:
                total_rejected += 1
                continue

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
                res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                if res.data:
                    total_added += 1
            except Exception:
                pass

    print(f"✅ اكتمل المسح اليومي: تم حفظ/تحديث {total_added} قصاصة بنجاح، واستبعاد {total_rejected} عنصر غير مطابق.")

if __name__ == "__main__":
    scrape_daily()
