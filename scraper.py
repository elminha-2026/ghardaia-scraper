import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات قاعدة البيانات Supabase
# ==========================================
SUPABASE_URL = os.environ.get("SUPABASE_URL", "https://your-supabase-url.supabase.co")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "your-supabase-service-role-key")

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. قواعد الفلترة والتحقق الدقيق
# ==========================================

# الكلمات المفتاحية الأساسية (يجب وجود إحداها على الأقل)
MUST_MATCH_KEYWORDS = [
    "أبو إسحاق أطفيش",
    "ابو اسحاق اطفيش",
    "إبراهيم أطفيش",
    "ابراهيم اطفيش",
    "جمعية الشيخ أبي إسحاق",
    "جمعية الشيخ ابي اسحاق",
    "جمعية أطفيش",
    "تراث غرداية",
    "جمعية التراث غرداية"
]

# كلمات سياقية تأكيدية (إذا كانت الكلمة الأساسية عامة جداً)
CONTEXT_KEYWORDS = [
    "غرداية", "تراث", " بني يزقن", "ميزاب", "الجزائر", "مخطوطات", 
    "فقه", "تاريخ", "المكتبة", "المؤسس", "الشيخ"
]

# كلمات الاستبعاد (تستبعد القصاصة فوراً إذا وجدت في العنوان أو النص)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الرياض",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

def clean_text(text: str) -> str:
    """تنظيف النص من المسافات الزائدة والأحرف الخاصة"""
    if not text:
        return ""
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def is_relevant_article(title: str, summary: str) -> bool:
    """
    التحقق مما إذا كان الخبر متعلقاً بالجمعية وتراثها فعلياً.
    """
    combined_text = f"{title} {summary}".lower()

    # 1. الاستبعاد الفوري إذااحتوى النص على كلمات غير مرتبطة
    for exc in EXCLUDE_KEYWORDS:
        if exc in combined_text:
            return False

    # 2. مطابقة الكلمات الأساسية
    has_exact_match = any(kw.lower() in combined_text for kw in MUST_MATCH_KEYWORDS)
    if has_exact_match:
        return True

    # 3. شرط إضافي: إذا وجدت كلمة "أطفيش" أو "إبراهيم أطفيش" مع كلمة سياقية مثل "غرداية" أو "تراث"
    if "أطفيش" in combined_text or "اطفيش" in combined_text:
        has_context = any(ctx.lower() in combined_text for ctx in CONTEXT_KEYWORDS)
        if has_context:
            return True

    return False

def determine_importance_and_category(title: str, summary: str):
    """
    تحديد درجة الأهمية والموضوع تلقائياً بناءً على الكلمات المفتاحية
    """
    text = f"{title} {summary}".lower()
    
    # تحديد درجة الخطورة / الأهمية
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار"]):
        importance = "أحداث خطيرة"
        category = "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط"]):
        importance = "عالي"
        category = "نشاطات علمية وتراثية"
    else:
        importance = "عادي"
        category = "اخبار عامة"

    return importance, category

# ==========================================
# 3. دالة معالجة وحفظ القصاصة في Supabase
# ==========================================

def save_clipping_to_supabase(title: str, summary: str, link: str, source: str, pub_date: str = None):
    """
    التحقق من القصاصة ثم حفظها في قاعدة البيانات إذا لم تكن مكررة
    """
    title = clean_text(title)
    summary = clean_text(summary)

    # 1. الفحص الدقيق للمحتوى
    if not is_relevant_article(title, summary):
        print(f"❌ تم تجنب الخبر غير المباشر/الخاطئ: {title} ({source})")
        return False

    # 2. التأكد من عدم وجود الخبر سابقاً (تجنب التكرار عبر رابط الخبر)
    try:
        existing = supabase.table("clippings").select("id").eq("link", link).execute()
        if existing.data and len(existing.data) > 0:
            print(f"⚠️ الخبر موجود مسبقاً: {title}")
            return False
    except Exception as e:
        print(f"خطأ أثناء فحص التكرار: {e}")

    # 3. تحديد الأهمية والتصنيف
    importance, category = determine_importance_and_category(title, summary)
    
    # 4. تنسيق تاريخ النشر
    if not pub_date:
        pub_date = datetime.utcnow().strftime("%Y-%m-%d")

    # 5. تجهيز البيانات للحفظ
    payload = {
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published_date": pub_date,
        "importance": importance,
        "category": category
    }

    # 6. الحفظ في Supabase
    try:
        res = supabase.table("clippings").insert(payload).execute()
        print(f"✅ تم حفظ القصاصة بنجاح: {title}")
        return True
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ في Supabase: {e}")
        return False

# ==========================================
# 4. نموذج دالة الكشط (Scraping Example)
# ==========================================

def scrape_rss_feed(feed_url: str, source_name: str):
    """
    مثال لجلب البيانات عبر RSS Feed لموقع إخباري
    """
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    try:
        response = requests.get(feed_url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.content, 'xml') # أو 'html.parser' حسب المصدر
        
        items = soup.find_all('item')
        for item in items:
            title = item.find('title').text if item.find('title') else ''
            link = item.find('link').text if item.find('link') else ''
            summary = item.find('description').text if item.find('description') else ''
            pub_date_raw = item.find('pubDate').text if item.find('pubDate') else None
            
            # معالجة وحفظ الخبر
            save_clipping_to_supabase(
                title=title,
                summary=summary,
                link=link,
                source=source_name,
                pub_date=None # يمكن تحويل pub_date_raw لتنسيق YYYY-MM-DD
            )
    except Exception as e:
        print(f"خطأ أثناء جلب المصدر {source_name}: {e}")

if __name__ == "__main__":
    print("بدء عملية رصد القصاصات وإلغاء النتائج الخاطئة...")
    
    # تجربة اختبارية مع خبر خاطئ (مثل خبر جريدة الرياض):
    test_wrong_title = "افتتاح مشروع جديد في مدينة الرياض"
    test_wrong_summary = "تراث المنطقة الشرقية يشهد تطوراً كبيراً"
    save_clipping_to_supabase(test_wrong_title, test_wrong_summary, "https://www.alriyadh.com/2208237", "جريدة الرياض")

    # تجربة اختبارية مع خبر صحيح:
    test_right_title = "صدور كتاب جديد حول آثار الشيخ إبراهيم أطفيش"
    test_right_summary = "قامت جمعية الشيخ أبي إسحاق للتراث بفرع غرداية برعاية هذا العمل العلماني المميز."
    save_clipping_to_supabase(test_right_title, test_right_summary, "https://example.com/news/123", "جريدة التراث")
