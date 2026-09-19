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
    print("❌ خطأ: لم يتم العثور على SUPABASE_URL أو SUPABASE_KEY!")
    sys.exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# تفكيك الكلمات المفتاحية إلى استعلامات منفردة للحصول على أقصى عدد من النتائج (100 لكل كلمة)
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
    """التحقق الدقيق من أن التاريخ يتبع لسنة 2026 حصراً"""
    if not raw_date:
        return None
    try:
        dt = date_parser.parse(raw_date)
        if dt.year == 2026:
            return dt.isoformat()
        return None
    except Exception:
        return None

def run_comprehensive_fetch():
    print("🚀 بدء الاستخراج الشامل والمكثف لقصاصات سبتمبر 2026 وكل السنة...")

    total_added = 0
    total_rejected = 0

    for item in SEARCH_QUERIES:
        query_text = item["q"]
        rss_params = item["params"]

        print(f"🔍 جلب النتائج للكلمة المفتاحية: [{query_text}]...")

        # جلب مباشر وبدون قيود معقدة لضمان التقاط أحدث المقالات (بما فيها 16 و17 سبتمبر)
        encoded_query = urllib.parse.quote(query_text)
        rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{rss_params}"
        feed = feedparser.parse(rss_url)

        for entry in feed.entries:
            title = entry.get("title", "").strip()
            link = entry.get("link", "").strip()
            published_raw = entry.get("published", "").strip()

            # الفلترة الحازمة للتأكد من أن المقال نشر في 2026
            published_iso = verify_and_parse_2026(published_raw)
            
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
                # الحفظ وتفادي التكرار بناء على رابط الخبر
                res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                if res.data:
                    total_added += 1
            except Exception:
                pass

    print("\n" + "="*50)
    print(f"🎉 تم الانتهاء بنجاح! إجمالي القصاصات المحفوظة والمحدثة لـ 2026: {total_added}")
    print(f"🛡️ المقالات المستبعدة (تواريخ غير مطابقة لـ 2026): {total_rejected}")
    print("="*50)

if __name__ == "__main__":
    run_comprehensive_fetch()
