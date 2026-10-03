import os
import sys
import feedparser
import urllib.parse
import requests
from datetime import datetime
from dateutil import parser as date_parser
from bs4 import BeautifulSoup
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

# --- 2. إعدادات البحث ---
SEARCH_CONFIGS = [
    {
        "lang": "ar",
        "queries": ["غرداية", '"ولاية غرداية"', '"تراث غرداية"', '"الشيخ أبي إسحاق"', '"جمعية التراث"', "مزاب"],
        "params": "hl=ar&gl=DZ&ceid=DZ:ar"
    },
    {
        "lang": "fr",
        "queries": ["Ghardaïa", '"wilaya de Ghardaia"', '"patrimoine Ghardaia"', '"Abou Issaq"', "Mzab"],
        "params": "hl=fr&gl=DZ&ceid=DZ:fr"
    },
    {
        "lang": "en",
        "queries": ["Ghardaia", '"Ghardaia heritage"', '"Mzab valley"'],
        "params": "hl=en&gl=US&ceid=US:en"
    }
]

CORE_LOCATION_KEYWORDS = ["ghardaïa", "ghardaia", "غرداية", "مزاب", "mzab", "abou issaq", "أبي إسحاق"]

def verify_and_clean_real_article(url):
    """
    تفتح هذه الدالة الرابط الأصلي، وتحذف بيو الكاتب والهوامش كلياً،
    ثم تتحقق هل الكلمة المفتاحية موجودة فعلاً في صلب المقال أم كانت مجرد توقيع للكاتب.
    """
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
    }
    try:
        res = requests.get(url, headers=headers, timeout=8, allow_redirects=True)
        if res.status_code != 200:
            return None, False

        soup = BeautifulSoup(res.text, 'html.parser')

        # 1. حذف كامل للحاويات الجانبية وتوقيع الكاتب والهوامش
        unwanted_selectors = [
            'header', 'footer', 'nav', 'aside', 'script', 'style',
            '.sidebar', '.author-bio', '.author', '.author-box', '.profile', 
            '.journaliste', '.related-posts', '.footer-widgets', '#sidebar',
            'div[class*="author"]', 'div[class*="bio"]'
        ]
        for tag in soup.select(','.join(unwanted_selectors)):
            tag.decompose()

        # 2. استخراج صلب المقال فقط
        article_body = (
            soup.find('article') or 
            soup.find('div', class_=['entry-content', 'article-body', 'post-content', 'main-content'])
        )

        clean_text = ""
        if article_body:
            clean_text = article_body.get_text(separator=' ', strip=True)
        else:
            # استخراج الفقرات الأساسية فقط
            paragraphs = soup.find_all('p')
            clean_text = ' '.join([p.get_text(strip=True) for p in paragraphs])

        clean_text_lower = clean_text.lower()

        # 3. التحقق الجذري: هل الكلمة البحثية موجودة في صلب المقال النظيف؟
        has_core_keyword = any(kw in clean_text_lower for kw in CORE_LOCATION_KEYWORDS)

        return clean_text[:300], has_core_keyword

    except Exception:
        # في حال تعذر جلب الصفحة الأصيلة، نكتفي بعدم المجازفة إذا لم تكن في العنوان
        return None, False


def determine_category_and_importance(title, summary_text):
    clean_title = (title or "").lower()
    clean_summary = (summary_text or "").lower()
    full_text = f"{clean_title} {clean_summary}"

    critical_kw = [
        "حادث", "كارثة", "حريق", "فيضان", "وفاة", "ضحايا", "خطير", 
        "طوارئ", "انهيار", "اعتداء", "انفجار", "مصابين", "جريمة", "غرق",
        "accident", "incendie", "inondation", "décès", "victimes", "explosion", "drame", "crash",
        "disaster", "fire", "flood", "death", "fatalities", "emergency", "collapse"
    ]

    is_critical = False
    if any(k in clean_title for k in critical_kw):
        is_critical = True
    else:
        for k in critical_kw:
            if clean_summary.count(k) >= 2:
                is_critical = True
                break

    if is_critical:
        return "أحداث خطيرة", "أحداث خطيرة"

    heritage_kw = ["تراث", "مخطوط", "تاريخ", "زايد", "قصور", "ثقافة", "مزاب", "patrimoine", "manuscrit", "histoire", "culture", "heritage", "history", "mzab"]
    activity_kw = ["أبي إسحاق", "جمعية", "ملتقى", "محاضرة", "ندوة", "association", "séminaire", "conférence", "abou issaq"]
    economy_kw = ["اقتصاد", "سوق", "تجارة", "استثمار", "تنمية", "ميزانية", "أسعار", "بورصة", "فلاحة", "زراعة", "صناعة", "économie", "commerce", "investissement", "market", "economy", "trade", "business"]

    category = "أخبار عامة"
    if any(k in full_text for k in heritage_kw):
        category = "تراث وثقافة"
    elif any(k in full_text for k in activity_kw):
        category = "نشاطات الجمعية"
    elif any(k in full_text for k in economy_kw):
        category = "اقتصاد"

    importance = "عادي"
    high_kw = ["أبي إسحاق", "افتتاح", "رسمي", "هام", "اتفاقية", "وزير", "والي", "abou issaq", "ministre", "wali", "officiel", "minister"]
    if any(k in full_text for k in high_kw):
        importance = "عالي"

    return category, importance


def validate_and_parse_2026_date(raw_date):
    if not raw_date:
        return None
    try:
        dt = date_parser.parse(raw_date)
        if dt.year == 2026:
            return dt.isoformat()
    except Exception:
        pass
    return None


def fetch_rss(query, params):
    encoded_query = urllib.parse.quote(query)
    rss_url = f"https://news.google.com/rss/search?q={encoded_query}&{params}"
    return feedparser.parse(rss_url)


def scrape_and_store():
    print("🚀 بدء التمشيط المتقدم والمفلتر لعام 2026...")
    
    months_2026 = [
        ("2026-01-01", "2026-01-31"), ("2026-02-01", "2026-02-28"),
        ("2026-03-01", "2026-03-31"), ("2026-04-01", "2026-04-30"),
        ("2026-05-01", "2026-05-31"), ("2026-06-01", "2026-06-30"),
        ("2026-07-01", "2026-07-31"), ("2026-08-01", "2026-08-31"),
        ("2026-09-01", "2026-09-30"), ("2026-10-01", "2026-10-31"),
        ("2026-11-01", "2026-11-30"), ("2026-12-01", "2026-12-31"),
    ]

    total_added = 0
    total_rejected = 0

    for config in SEARCH_CONFIGS:
        lang = config["lang"]
        queries = config["queries"]
        params = config["params"]

        print(f"\n🌐 --- بدء المعالجة باللغة [{lang.upper()}] ---")

        for q in queries:
            all_target_queries = [q]
            for start_d, end_d in months_2026:
                all_target_queries.append(f"{q} after:{start_d} before:{end_d}")

            for target_q in all_target_queries:
                feed = fetch_rss(target_q, params)

                for entry in feed.entries:
                    title = entry.get("title", "").strip()
                    link = entry.get("link", "").strip()
                    published_raw = entry.get("published", "").strip()

                    published_iso = validate_and_parse_2026_date(published_raw)
                    if not published_iso:
                        total_rejected += 1
                        continue

                    title_lower = title.lower()
                    has_in_title = any(kw in title_lower for kw in CORE_LOCATION_KEYWORDS)

                    final_summary = ""
                    
                    # إذا لم تكن الكلمة في العنوان الرئيسي، نفحص صلب المقال الأصلي بعد حذف بيو الكاتب
                    if not has_in_title:
                        real_summary, is_valid = verify_and_clean_real_article(link)
                        if not is_valid:
                            total_rejected += 1
                            print(f"🛡️ تم استبعاد خبر خاطئ (بسبب بيو الكاتب): {title}")
                            continue
                        final_summary = real_summary
                    else:
                        # إذا كانت في العنوان فالمقال مؤكد
                        raw_summary = entry.get("summary", "")
                        soup = BeautifulSoup(raw_summary, "html.parser")
                        final_summary = soup.get_text(separator=' ', strip=True)

                    source = "صحافة إلكترونية"
                    if "source" in entry and isinstance(entry.source, dict):
                        source = entry.source.get("title", "صحافة إلكترونية")

                    if title and link:
                        category, importance = determine_category_and_importance(title, final_summary)

                        data = {
                            "title": title,
                            "source": source,
                            "link": link,
                            "published_date": published_iso,
                            "summary": final_summary,
                            "category": category,
                            "importance": importance
                        }

                        try:
                            res = supabase.table("clippings").upsert(data, on_conflict="link").execute()
                            if res.data:
                                total_added += 1
                        except Exception:
                            pass

    print("\n" + "="*60)
    print(f"🎉 النتيجة النهائية: تم حفظ وتحديث {total_added} قصاصة حقيقية ومؤكدة لعام 2026!")
    print(f"🛡️ تم استبعاد {total_rejected} مقال غير متوافق أو إيجابية كاذبة (بسبب تعريف الكاتب).")
    print("="*60)

if __name__ == "__main__":
    scrape_and_store()
