import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from email.utils import parsedate_to_datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات قاعدة البيانات Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY")

if not SUPABASE_URL or not SUPABASE_KEY:
    print("❌ خطأ: لم يتم العثور على مفاتيح Supabase.")
    exit(1)

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. قواعد الفلترة والتحقق الدقيق
# ==========================================
MUST_MATCH_KEYWORDS = [
    "أبو إسحاق أطفيش", "ابو اسحاق اطفيش", "إبراهيم أطفيش", "ابراهيم اطفيش",
    "جمعية الشيخ أبي إسحاق", "جمعية الشيخ ابي اسحاق", "جمعية أطفيش",
    "تراث غرداية", "جمعية التراث غرداية"
]

CONTEXT_KEYWORDS = [
    "غرداية", "تراث", "بني يزقن", "ميزاب", "الجزائر", "مخطوطات", 
    "فقه", "تاريخ", "المكتبة", "المؤسس", "الشيخ"
]

EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الرياض",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

def clean_text(text: str) -> str:
    """تنظيف النص من المسافات الزائدة والأحرف الخاصة"""
    if not text:
        return ""
    # إزالة أي وسوم HTML إن وجدت
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_relevant_article(title: str, summary: str) -> bool:
    combined_text = f"{title} {summary}".lower()
    for exc in EXCLUDE_KEYWORDS:
        if exc in combined_text:
            return False

    has_exact_match = any(kw.lower() in combined_text for kw in MUST_MATCH_KEYWORDS)
    if has_exact_match:
        return True

    if "أطفيش" in combined_text or "اطفيش" in combined_text:
        has_context = any(ctx.lower() in combined_text for ctx in CONTEXT_KEYWORDS)
        if has_context:
            return True

    return False

def determine_importance_and_category(title: str, summary: str):
    text = f"{title} {summary}".lower()
    
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار"]):
        importance = "عالي"
        category = "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط"]):
        importance = "عالي"
        category = "نشاطات علمية وتراثية"
    else:
        importance = "عادي"
        category = "أخبار عامة"

    return importance, category

# ==========================================
# 3. دالة معالجة وحفظ القصاصة في Supabase
# ==========================================
def save_clipping_to_supabase(title: str, summary: str, link: str, source: str, pub_date: str = None):
    title = clean_text(title)
    summary = clean_text(summary)

    if not is_relevant_article(title, summary):
        print(f"❌ مستبعد (غير مرتبط): {title[:40]}...")
        return False

    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data and len(existing.data) > 0:
            print(f"⚠️ موجود مسبقاً: {title[:40]}...")
            return False
    except Exception as e:
        print(f"خطأ أثناء فحص التكرار: {e}")

    importance, category = determine_importance_and_category(title, summary)
    
    if not pub_date:
        pub_date = datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S")

    payload = {
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published_date": pub_date,
        "importance": importance,
        "category": category
    }

    try:
        res = supabase.table("clippings").insert(payload).execute()
        print(f"✅ تم الحفظ: {title[:40]}...")
        return True
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ: {e}")
        return False

# ==========================================
# 4. دالة الكشط الحقيقية (RSS)
# ==========================================
def scrape_rss_feed(feed_url: str, source_name: str):
    print(f"\n📡 جاري جلب الأخبار من: {source_name}...")
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(feed_url, headers=headers, timeout=15)
        response.raise_for_status() # التأكد من عدم وجود أخطاء في الرابط
        
        # نستخدم lxml لقراءة الـ XML بشكل صحيح
        soup = BeautifulSoup(response.content, 'xml') 
        
        items = soup.find_all('item')
        print(f"🔎 تم العثور على {len(items)} خبر في هذا المصدر.")
        
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            link = item.find('link').text if item.find('link') else ''
            summary = item.find('description').text if item.find('description') else ''
            pub_date_raw = item.find('pubDate').text if item.find('pubDate') else None
            
            # تحويل التاريخ من صيغة RSS إلى صيغة مقروءة
            pub_date_formatted = None
            if pub_date_raw:
                try:
                    dt = parsedate_to_datetime(pub_date_raw)
                    pub_date_formatted = dt.strftime("%Y-%m-%d %H:%M:%S")
                except Exception:
                    pass

            save_clipping_to_supabase(
                title=title,
                summary=summary,
                link=link,
                source=source_name,
                pub_date=pub_date_formatted
            )
    except Exception as e:
        print(f"❌ خطأ أثناء جلب المصدر {source_name}: {e}")

# ==========================================
# 5. التنفيذ الفعلي
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء عملية رصد القصاصات...")
    
    # روابط حقيقية من Google News للبحث عن الكلمات المفتاحية
    import urllib.parse
    queries = [
        "جمعية الشيخ أبي إسحاق غرداية",
        "تراث غرداية",
        "إبراهيم أطفيش"
    ]
    
    for q in queries:
        encoded_q = urllib.parse.quote(q)
        url = f"https://news.google.com/rss/search?q={encoded_q}&hl=ar&gl=DZ&ceid=DZ:ar"
        scrape_rss_feed(url, source_name="Google News")
        
    print("\n✅ انتهت العملية.")
