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
# 2. الكلمات المفتاحية والفلترة
# ==========================================
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

def clean_text(text: str) -> str:
    """تنظيف النص من وسوم HTML والمسافات الزائدة"""
    if not text:
        return ""
    # إزالة أي وسوم HTML (مثل <a href...>)
    text = re.sub(r'<[^>]+>', '', text)
    # إزالة المسافات المتكررة
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def determine_importance_and_category(title: str, summary: str):
    """تحديد الأهمية والتصنيف تلقائياً"""
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
    # تنظيف النصوص
    title = clean_text(title)
    summary = clean_text(summary)

    # استبعاد الأخبار غير المرغوب فيها
    combined_text = f"{title} {summary}".lower()
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # تجهيز البيانات
    importance, category = determine_importance_and_category(title, summary)
    
    payload = {
        "title": title,
        "summary": summary,
        "link": link,
        "source": source,
        "published_date": pub_date, # بصيغة ISO
        "importance": importance,
        "category": category
    }

    try:
        # استخدام upsert لتحديث الخبر إذا كان الرابط موجوداً، أو إضافته إذا كان جديداً
        response = supabase.table("clippings").upsert(payload, on_conflict="link").execute()
        # التحقق مما إذا كان السجل جديداً حقاً (Supabase يعيد البيانات في كل مرة)
        # للتبسيط، سنعتمد على طباعة النجاح
        print(f"✅ تم المعالجة: [{category}] {title[:40]}...")
        return True
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ: {e}")
        return False

# ==========================================
# 4. دالة الكشط من Google News
# ==========================================
def scrape_google_news(query: str):
    encoded_query = urllib.parse.quote(query)
    # البحث في النسخة الجزائرية من جوجل نيوز
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    
    print(f"\n📡 جاري جلب الأخبار لـ: [{query}]...")
    
    try:
        # استخدام feedparser بدلاً من BeautifulSoup لسهولة قراءة RSS
        feed = feedparser.parse(url)
        
        if not feed.entries:
            print("   ⚠️ لم يتم العثور على أخبار لهذا الاستعلام.")
            return

        print(f"   🔎 تم العثور على {len(feed.entries)} خبر.")
        added_count = 0
        
        for entry in feed.entries:
            title = entry.get("title", "")
            link = entry.get("link", "")
            summary = entry.get("summary", "")
            
            # استخراج اسم المصدر
            source = "صحافة إلكترونية"
            if "source" in entry and isinstance(entry.source, dict):
                source = entry.source.get("title", "صحافة إلكترونية")

            # تحويل التاريخ إلى صيغة ISO التي تفهمها قاعدة البيانات والواجهة
            pub_date = datetime.utcnow().isoformat() + "Z"
            if "published_parsed" in entry:
                try:
                    pub_date = datetime(*entry.published_parsed[:6]).isoformat() + "Z"
                except Exception:
                    pass

            # الحفظ
            if save_to_supabase(title, summary, link, source, pub_date):
                added_count += 1
                
    except Exception as e:
        print(f"❌ خطأ أثناء جلب المصدر: {e}")

# ==========================================
# 5. نقطة انطلاق التنفيذ
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء عملية تمشيط الأخبار الشاملة...")
    
    # قائمة استعلامات بحث واسعة جداً لتجاوز حد الـ 100 خبر لكل استعلام
    SEARCH_QUERIES = [
        '"غرداية"',
        '"ولاية غرداية"',
        '"وادي ميزاب"',
        '"بني مزاب"',
        '"بني يزقن"',
        '"الشيخ أبي إسحاق"',
        '"إبراهيم أطفيش"',
        '"جمعية التراث" غرداية',
        '"تراث غرداية"',
        '"قصور غرداية"'
    ]
    
    for q in SEARCH_QUERIES:
        scrape_google_news(q)
        
    print("\n" + "="*50)
    print("🎉 انتهت العملية بنجاح! اذهب إلى Supabase أو الواجهة لترى النتائج.")
    print("="*50)
