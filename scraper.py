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
# 2. قواعد الفلترة والتنظيف الصارمة
# ==========================================
# 1. كلمات مستبعدة نهائياً (رياضة، اقتصاد، دول ومناطق أجنبية)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع",
    # دول ومناطق قد تتشابه مع اسم "مزاب"
    "المغرب", "زاكورة", "درعة", "الدار البيضاء", "الرباط", "مراكش",
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين", 
    "عمان", "الأردن", "تونس", "ليبيا", "موريتانيا", "فرنسا"
]

# 2. كلمات محلية قوية (تكفي وحدها لقبول الخبر)
STRONG_LOCAL_KEYWORDS = [
    "غرداية", "بريان", "بونورة", "المنصورة", "بني يزقن", "وادي ميزاب", 
    "بني مزاب", "جمعية الشيخ أبي إسحاق", "جمعية التراث غرداية"
]

# 3. كلمات محلية ضعيفة (تحتاج تأكيداً بكلمة الجزائر أو غرداية)
WEAK_LOCAL_KEYWORDS = [
    "مزاب", "ميزاب"
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
# 3. دالة الحفظ (مع الفلترة الذكية)
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    combined_text = f"{title} {summary}".lower()

    # 1. استبعاد الكلمات الرياضية أو الدول/المناطق الأجنبية
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. هل الخبر عن الشيخ أطفيش؟ (استثناء مقبول دائماً)
    is_atfayyish = any(k in combined_text for k in ["أطفيش", "اطفيش", "إبراهيم أطفيش"])
    if is_atfayyish:
        pass # نقبله مباشرة

    else:
        # 3. هل يحتوي على كلمات محلية قوية؟ (غرداية، وادي ميزاب...)
        is_strong_local = any(k in combined_text for k in STRONG_LOCAL_KEYWORDS)
        
        # 4. هل يحتوي فقط على كلمات محلية ضعيفة؟ (مزاب فقط)
        is_weak_local = any(k in combined_text for k in WEAK_LOCAL_KEYWORDS)
        
        # إذا لم يكن أطفيش ولا يحتوي على أي كلمة محلية قوية أو ضعيفة، نرفضه
        if not is_strong_local and not is_weak_local:
            return False

        # إذا كان يعتمد فقط على كلمة "مزاب" الضعيفة، يجب أن يذكر الجزائر أو غرداية
        if is_weak_local and not is_strong_local:
            mentions_algeria = "الجزائر" in combined_text or "جزائري" in combined_text
            if not mentions_algeria:
                print(f"   🚫 مستبعد (مزاب لكن ليس بالجزائر): {title[:30]}...")
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
    
    # تحديث الاستعلامات لضمان جلب أخبار الجزائر فقط
    queries = [
        '"غرداية"',
        '"ولاية غرداية"',
        '"وادي ميزاب"',
        '"بني مزاب"',
        '"أطفيش"',
        '"جمعية التراث" غرداية',
        '"بريان" غرداية',
        '"بونورة" غرداية',
        '"المنصورة" غرداية',
        '"ميزاب" الجزائر' # لضمان جلب ميزاب الجزائرية
    ]
    
    total_added = 0
    
    # البحث في الأرشيف من 2010 إلى 2026
    for year in range(2010, 2027):
        print(f"\n📅 --- جاري البحث في سنة {year} ---")
        
        for q in queries:
            search_query = f'{q} after:{year}-01-01 before:{year}-12-31'
            added = scrape_google_news(search_query)
            total_added += added
            
            # الانتظار 3 ثوانٍ لتجنب حظر جوجل
            time.sleep(3)
            
    print("\n" + "="*50)
    print(f"🎉 انتهت العملية! تمت إضافة {total_added} قصاصة جديدة.")
    print("="*50)
