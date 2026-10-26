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
# 2. قواعد الفلترة الصارمة
# ==========================================
# كلمات مستبعدة دائماً (رياضة واقتصاد)
EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", 
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]

# دول ومناطق أجنبية (يُرفض الخبر فوراً إذا ذكرها ولم يذكر الجزائر)
FOREIGN_KEYWORDS = [
    "المغرب", "زاكورة", "درعة", "الرباط", "الدار البيضاء", "مراكش", 
    "أكادير", "فاس", "مكناس", "طنجة", "وجدة", "تطوان",
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين", 
    "عمان", "الأردن", "تونس", "ليبيا", "موريتانيا", "فرنسا"
]

# كلمات تدل على الجزائر والمنطقة (مطلوبة لقبول الخبر)
ALGERIA_KEYWORDS = [
    "الجزائر", "جزائري", "غرداية", "وادي ميزاب", "بني يزقن", 
    "بريان", "بونورة", "المنصورة", "القرارة", "زلفانة", "العطف"
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
# 3. دالة الحفظ (الفلترة القاتلة للمغرب)
# ==========================================
def save_to_supabase(title, summary, link, source, pub_date):
    title = clean_text(title)
    summary = clean_text(summary)
    combined_text = f"{title} {summary}".lower()

    # 1. استبعاد الرياضة والاقتصاد
    if any(exc in combined_text for exc in EXCLUDE_KEYWORDS):
        return False

    # 2. هل الخبر عن الشيخ أطفيش؟ (استثناء مقبول دائماً)
    is_atfayyish = any(k in combined_text for k in ["أطفيش", "اطفيش", "إبراهيم أطفيش"])

    # 3. الفحص الجغرافي الصارم
    if not is_atfayyish:
        mentions_foreign = any(country in combined_text for country in FOREIGN_KEYWORDS)
        mentions_algeria = any(k in combined_text for k in ALGERIA_KEYWORDS)

        # إذا ذكر المغرب أو أي دولة أجنبية، ولم يذكر الجزائر -> نرفضه فوراً
        if mentions_foreign and not mentions_algeria:
            print(f"   🚫 مستبعد (دولة أجنبية): {title[:40]}...")
            return False
        
        # إذا كان الخبر عن "مزاب" أو "بني مزاب" ولم يذكر الجزائر أو غرداية -> نرفضه
        if ("مزاب" in combined_text or "بني مزاب" in combined_text) and not mentions_algeria:
            print(f"   🚫 مستبعد (مزاب بدون ذكر الجزائر): {title[:40]}...")
            return False

        # إذا لم يكن أطفيش، ولا يحتوي على أي كلمة جزائرية -> نرفضه
        if not mentions_algeria:
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
    
    # إرسال User-Agent لمحاكاة المتصفح وتجنب حظر جوجل
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'}
    
    try:
        response = requests.get(url, headers=headers, timeout=15)
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
        print(f"   ❌ خطأ أثناء الاتصال بجوجل: {e}")
        return 0

# ==========================================
# 5. التنفيذ
# ==========================================
if __name__ == "__main__":
    print("🚀 بدء عملية تمشيط الأرشيف (نسخة استبعاد المغرب)...")
    
    # 💡 السر هنا: الكلمات المفتاحية مقترنة بكلمة الجزائر أو غرداية
    queries = [
        '"غرداية" الجزائر',
        '"ولاية غرداية"',
        '"وادي ميزاب"',
        '"بني مزاب" الجزائر',     # منع جوجل من جلب بني مزاب المغربية
        '"بني مزاب" غرداية',
        '"أطفيش"',
        '"جمعية التراث" غرداية',
        '"بريان" غرداية',
        '"بونورة" غرداية',
        '"المنصورة" غرداية'
    ]
    
    total_added = 0
    
    # البحث في الأرشيف سنة بسنة من 2010 إلى 2026
    for year in range(2010, 2027):
        print(f"\n📅 --- جاري البحث في سنة {year} ---")
        
        for q in queries:
            # دمج الكلمة مع التاريخ
            search_query = f'{q} after:{year}-01-01 before:{year}-12-31'
            added = scrape_google_news(search_query)
            total_added += added
            
            # الانتظار 5 ثوانٍ بين كل طلب لتجنب حظر جوجل (Rate Limiting)
            time.sleep(5)
            
    print("\n" + "="*50)
    print(f"🎉 انتهت العملية! تمت معالجة {total_added} قصاصة جديدة.")
    print("="*50)
