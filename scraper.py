import os
import re
import time
import urllib.parse
import feedparser
import requests
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
# 2. قواعد الفلترة
# ==========================================
# كلمات مستبعدة (رياضة واقتصاد فقط)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

# دول ومناطق أجنبية (لمنع أخبار المغرب ومصر وغيرها)
FOREIGN_COUNTRIES = [
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين", 
    "عمان", "الأردن", "المغرب", "تونس", "ليبيا", "موريتانيا", "فرنسا",
    "زاكورة", "درعة", "الرباط", "الدار البيضاء", "مراكش"
]

# كلمات قوية تدل على الجزائر مباشرة
STRONG_LOCAL_KEYWORDS = [
    "غرداية", "وادي ميزاب", "بني يزقن", "بني مزاب", 
    "جمعية الشيخ أبي إسحاق", "جمعية التراث غرداية"
]

# كلمات ضعيفة تحتاج تأكيداً (لأنها قد توجد في دول أخرى)
WEAK_LOCAL_KEYWORDS = [
    "مزاب", "ميزاب", "بريان", "بونورة", "المنصورة"
]

def clean_text(text: str) -> str:
    if not text: return ""
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()

def determine_importance_and_category(title: str, summary: str):
    text = f"{title} {summary}".lower()
    if any(k in text for k in ["تعدي", "سرقة", "هدم", "ضرر", "خطر", "حريق", "اندثار"]):
        return "عالي", "أحداث خطيرة"
    elif any(k in text for k in ["مؤتمر", "ندوة", "افتتاح", "صدور", "كتاب", "مخطوط", "تراث"]):
        return "عالي", "نشاطات علمية وتراثية"
    return "عادي", "أخبار عامة"

# ==========================================
# 3. دالة الحفظ (مع الفلترة الدقيقة)
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    combined_text = f"{title} {summary}".lower()

    # 1. استبعاد الرياضة والاقتصاد
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. التحقق من كلمات البحث
    is_atfayyish = any(k in combined_text for k in ["أطفيش", "اطفيش", "إبراهيم أطفيش"])
    is_strong_local = any(k in combined_text for k in STRONG_LOCAL_KEYWORDS)
    is_weak_local = any(k in combined_text for k in WEAK_LOCAL_KEYWORDS)

    if not is_atfayyish:
        # إذا لم يكن عن الشيخ أطفيش، يجب أن يحتوي على كلمة محلية
        if not is_strong_local and not is_weak_local:
            return False

        mentions_foreign = any(country in combined_text for country in FOREIGN_COUNTRIES)
        mentions_algeria = "الجزائر" in combined_text or "جزائري" in combined_text or " dz" in combined_text

        # إذا ذكر دولة أجنبية ولم يذكر الجزائر، نرفضه
        if mentions_foreign and not mentions_algeria:
            print(f"   🚫 مستبعد (دولة أخرى): {title[:30]}...")
            return False

        # إذا كانت الكلمة المحلية ضعيفة (مثل بريان أو مزاب)، يجب أن يذكر الجزائر أو غرداية
        if is_weak_local and not is_strong_local:
            if not mentions_algeria and "غرداية" not in combined_text:
                print(f"   🚫 مستبعد (كلمة محلية ضعيفة بدون تأكيد): {title[:30]}...")
                return False

    # 3. الحفظ
    importance, category = determine_importance_and_category(title, summary)
    payload = {
        "title": title, "summary": summary, "link": link, "source": source,
        "published_date": pub_date, "importance": importance, "category": category
    }

    try:
        supabase.table("clippings").upsert(payload, on_conflict="link").execute()
        print(f"   ✅ تم الحفظ: {title[:40]}...")
        return True
    except Exception as e:
        print(f"   ❌ خطأ في قاعدة البيانات: {e}")
        return False

# ==========================================
# 4. دالة الكشط (باستخدام requests لتجنب الحظر)
# ==========================================
def scrape_google_news(query: str):
    encoded_query = urllib.parse.quote(query)
    url = f"https://news.google.com/rss/search?q={encoded_query}&hl=ar&gl=DZ&ceid=DZ:ar"
    
    # استخدام User-Agent لمحاكاة المتصفح وتجنب حظر جوجل
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
    }
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
        
        if response.status_code != 200:
            print(f"   ❌ فشل الاتصال بجوجل. كود الحالة: {response.status_code}")
            return 0
            
        feed = feedparser.parse(response.content)
        
        if not feed.entries:
            print(f"   ⚠️ 0 نتائج للبحث: {query}")
            return 0

        print(f"   📥 جوجل أعاد {len(feed.entries)} خبر. جاري الفلترة...")
        
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
                
        print(f"   📊 خلاصة البحث: تمت إضافة {added_count} قصاصة جديدة.")
        return added_count
                
    except Exception as e:
        print(f"   ❌ خطأ في الاتصال أو القراءة: {e}")
        return 0

# ==========================================
# 5. التنفيذ
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء عملية تمشيط الأرشيف...")
    
    # بحثنا هنا عن الكلمات المفتاحية الشاملة، لن نقيدها بالسنوات في هذه النسخة
    # لضمان جلب أحدث الأخبار أولاً
    queries = [
        '"غرداية" الجزائر',
        '"ولاية غرداية"',
        '"وادي ميزاب"',
        '"بني مزاب"',
        '"أطفيش"',
        '"جمعية التراث" غرداية',
        '"بريان" الجزائر',
        '"بونورة" الجزائر',
        '"المنصورة" غرداية',
        '"ميزاب" الجزائر'
    ]
    
    total_added = 0
    
    for q in queries:
        print(f"\n🔎 --- جاري البحث عن: {q} ---")
        added = scrape_google_news(q)
        total_added += added
        
        # الانتظار 5 ثوانٍ بين كل بحث وبحث لتجنب حظر جوجل نهائياً
        time.sleep(5)
            
    print("\n" + "="*50)
    print(f"🎉 انتهت العملية! تمت معالجة {total_added} قصاصة جديدة.")
    print("="*50)
