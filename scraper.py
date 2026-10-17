import os
import re
import time
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
# كلمات غير مرغوب فيها نهائياً (رياضة، اقتصاد، ترفيه)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

# كلمات البحث المحلية (يجب أن يحتوي الخبر على واحدة منها على الأقل)
LOCAL_KEYWORDS = [
    "غرداية", "بريان", "بونورة", "المنصورة", 
    "ميزاب", "بني مزاب", "بني يزقن", "جمعية التراث", "جمعية الشيخ"
]

# أسماء دول أجنبية (لاستبعاد الأخبار التي تتحدث عنها)
FOREIGN_COUNTRIES = [
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين", 
    "عمان", "الأردن", "المغرب", "تونس", "ليبيا", "موريتانيا", "فرنسا"
]

def clean_text(text: str) -> str:
    """تنظيف النص من وسوم HTML والمسافات الزائدة"""
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
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
# 3. دالة الحفظ (مع الفلترة الصارمة)
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    combined_text = f"{title} {summary}".lower()

    # 1. استبعاد كلمات الرياضة والاقتصاد
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. هل الخبر عن الشيخ أطفيش؟ (هذا الاستثناء مسموح به دائماً)
    is_atfayyish = any(k in combined_text for k in ["أطفيش", "اطفيش", "إبراهيم أطفيش"])
    
    # 3. هل الخبر يخص المنطقة؟ (غرداية، بريان، إلخ)
    is_local = any(k in combined_text for k in LOCAL_KEYWORDS)

    # الشرط الأساسي: يجب أن يكون الخبر عن أطفيش أو عن المنطقة، وإلا نرفضه فوراً
    if not is_atfayyish and not is_local:
        # print(f"   🚫 مستبعد (غير مرتبط بالمنطقة): {title[:30]}...")
        return False

    # 4. الفلترة الجغرافية للأخبار المحلية (إذا لم يكن عن أطفيش)
    if not is_atfayyish:
        mentions_foreign = any(country in combined_text for country in FOREIGN_COUNTRIES)
        mentions_algeria = "الجزائر" in combined_text or "جزائري" in combined_text

        # إذا ذكر دولة أجنبية ولم يذكر الجزائر، نرفضه
        if mentions_foreign and not mentions_algeria:
            print(f"   🚫 مستبعد (يخص دولة أخرى): {title[:30]}...")
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
        # الحفظ أو التحديث في قاعدة البيانات
        supabase.table("clippings").upsert(payload, on_conflict="link").execute()
        print(f"   ✅ تم الحفظ: {title[:40]}...")
        return True
    except Exception as e:
        print(f"   ❌ خطأ في Supabase: {e}")
        return False

# ==========================================
# 4. دالة الكشط
# ==========================================
def scrape_google_news(query: str):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    
    try:
        feed = feedparser.parse(url)
        
        if not feed.entries:
            print(f"   ⚠️ 0 نتائج: {query}")
            return 0

        print(f"   📥 تم جلب {len(feed.entries)} خبر. جاري الفلترة...")
        
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
                
        print(f"   📊 تمت إضافة {added_count} قصاصة جديدة.")
        return added_count
                
    except Exception as e:
        print(f"   ❌ خطأ أثناء الجلب: {e}")
        return 0

# ==========================================
# 5. التنفيذ
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
        '"جمعية التراث" غرداية',
        '"بريان" الجزائر',
        '"بونورة" الجزائر',
        '"المنصورة" غرداية' 
    ]
    
    total_added = 0
    
    # البحث في الأرشيف من 2010 إلى 2026
    for year in range(2010, 2027):
        print(f"\n📅 --- جاري البحث في سنة {year} ---")
        
        for q in queries:
            search_query = f'{q} after:{year}-01-01 before:{year}-12-31'
            added = scrape_google_news(search_query)
            total_added += added
            
            # 🔴 الانتظار 3 ثوانٍ بين كل طلب لتجنب حظر جوجل (Rate Limiting)
            time.sleep(3)
            
    print("\n" + "="*50)
    print(f"🎉 انتهت العملية! تمت إضافة {total_added} قصاصة جديدة.")
    print("="*50)
