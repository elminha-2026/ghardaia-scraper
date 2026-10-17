import os
import re
import urllib.parse
import feedparser
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
# 2. قواعد الفلترة والتنظيف
# ==========================================
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات"
]

def clean_text(text: str) -> str:
    """تنظيف النص من وسوم HTML والمسافات الزائدة"""
    if not text:
        return ""
    # إزالة وسوم HTML مثل <a href...>
    text = re.sub(r'<[^>]+>', '', text)
    # إزالة المسافات المتكررة
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def determine_importance_and_category(title: str, summary: str):
    """تحديد الأهمية والتصنيف تلقائياً بناءً على الكلمات المفتاحية"""
    text = f"{title} {summary}".lower()
    
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار"]):
        return "عالي", "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط", "تراث"]):
        return "عالي", "نشاطات علمية وتراثية"
    
    return "عادي", "أخبار عامة"

# ==========================================
# 3. دالة الحفظ في قاعدة البيانات
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    combined_text = f"{title} {summary}".lower()

    # استبعاد الأخبار غير المرغوب فيها
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # تحديد الأهمية والتصنيف
    importance, category = determine_importance_and_category(title, summary)
    
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
        # استخدام upsert مع on_conflict="link" يمنع التكرار ويحدث الخبر إذا وجد
        supabase.table("clippings").upsert(payload, on_conflict="link").execute()
        print(f"   ✅ تم الحفظ: {title[:40]}...")
        return True
    except Exception as e:
        print(f"   ❌ خطأ أثناء الحفظ: {e}")
        return False

# ==========================================
# 4. دالة الكشط لجوجل نيوز
# ==========================================
def scrape_google_news(query: str):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    
    try:
        # استخدام feedparser لقراءة الـ RSS بذكاء
        feed = feedparser.parse(url)
        
        if not feed.entries:
            return 0

        added_count = 0
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            
            # استخراج المصدر
            source = "صحافة إلكترونية"
            if "source" in entry and isinstance(entry.source, dict):
                source = entry.source.get("title", "صحافة إلكترونية")

            # تحويل التاريخ إلى صيغة ISO
            pub_date = datetime.utcnow().isoformat() + "Z"
            if "published_parsed" in entry:
                try:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                except Exception:
                    pass

            if save_to_supabase(title, summary, link, source, pub_date):
                added_count += 1
                
        print(f"      🔎 {len(feed.entries)} خبر متاح، تمت معالجة {added_count} خبر.")
        return added_count
                
    except Exception as e:
        print(f"      ❌ خطأ أثناء الجلب: {e}")
        return 0

# ==========================================
# 5. نقطة انطلاق التنفيذ (البحث في الأرشيف سنة بسنة)
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء عملية تمشيط الأرشيف...")
    
    # الكلمات المفتاحية
    queries = [
        '"غرداية"',
        '"ولاية غرداية"',
        '"وادي ميزاب"',
        '"بني مزاب"',
        '"أطفيش"',
        '"جمعية التراث"'
    ]
    
    total_added = 0
    
    # البحث من سنة 2010 إلى 2026 لتجاوز حد الـ 100 خبر
    for year in range(2010, 2027):
        print(f"\n📅 --- جاري البحث في سنة {year} ---")
        
        for q in queries:
            # البحث عن الأخبار التي نُشرت في هذه السنة فقط
            search_query = f'{q} after:{year}-01-01 before:{year}-12-31'
            added = scrape_google_news(search_query)
            total_added += added
            
    print("\n" + "="*50)
    print(f"🎉 انتهت العملية! تمت معالجة {total_added} قصاصة جديدة.")
    print("="*50)
