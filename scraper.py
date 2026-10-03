import requests
from bs4 import BeautifulSoup
from datetime import datetime
from supabase import create_client, Client

# ==========================================
# 1. إعدادات الاتصال بـ Supabase
# ==========================================
SUPABASE_URL = "https://*************.supabase.co"
SUPABASE_KEY = "sb_publishable_***************"

supabase: Client = create_client(SUPABASE_URL, SUPABASE_KEY)

# ==========================================
# 2. الكلمات المفتاحية الخاصة بالأحداث الخطيرة
# ==========================================
CRITICAL_KEYWORDS = [
    "حادث", "كارثة", "حريق", "فيضان", "وفاة", "ضحايا", "خطير", 
    "طوارئ", "انهيار", "اعتداء", "انفجار", "مصابين", "جريمة"
]

# ==========================================
# 3. دوال المعالجة والفلترة الدقيقة
# ==========================================
def extract_main_article_text(html_content: str) -> str:
    """
    استخراج النص الأساسي للخبر واستبعاد الهوامش والشريط الجانبي 
    والتعريف بالكاتب لتفادي الإيجابيات الكاذبة.
    """
    if not html_content:
        return ""
        
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # حذف العناصر غير التابعة لصلب الموضوع
    unwanted_selectors = [
        'header', 'footer', 'nav', 'aside', 'script', 'style',
        '.sidebar', '.related-posts', '.author-bio', '.footer-widgets', 
        '.comments', '.tags', '.share-buttons', '#sidebar'
    ]
    for tag in soup.select(','.join(unwanted_selectors)):
        tag.decompose()
        
    # البحث عن حاوية النص الرئيسية للمقال
    article_body = (
        soup.find('article') or 
        soup.find('div', class_=['entry-content', 'article-body', 'post-content', 'main-content', 'content-inner'])
    )
    
    if article_body:
        return article_body.get_text(separator=' ', strip=True)
        
    return soup.get_text(separator=' ', strip=True)


def determine_event_importance(title: str, html_content: str = "") -> str:
    """
    تقييم الأهمية:
    1. يفحص العنوان أولاً (إذا وُجدت الكلمة فإنه حدث خطير).
    2. يفحص صلب النص المصفى ويشترط تكرار الكلمة مرتين على الأقل.
    """
    clean_title = (title or "").lower()
    
    # المعيار الأول: وجود الكلمة في العنوان الرئيسي
    for keyword in CRITICAL_KEYWORDS:
        if keyword in clean_title:
            return "أحداث خطيرة"
            
    # المعيار الثاني: تكرار الكلمة مرتين أو أكثر في صلب الخبر المصفي
    if html_content:
        clean_text = extract_main_article_text(html_content).lower()
        for keyword in CRITICAL_KEYWORDS:
            if clean_text.count(keyword) >= 2:
                return "أحداث خطيرة"
                
    return "عادي"

# ==========================================
# 4. دالة معالجة وحفظ القصاصة إلى Supabase
# ==========================================
def process_and_save_clipping(title, summary, source, link, pub_date, category, html_content=""):
    """
    تستقبل بيانات الخبر وتحدد درجة الخطورة بدقة ثم تحفظ القصاصة في Supabase.
    """
    importance_level = determine_event_importance(title=title, html_content=html_content)
    
    payload = {
        "title": title,
        "summary": summary,
        "source": source,
        "link": link,
        "published_date": pub_date,  # صيغة ISO 8601 مثل: '2026-10-03T12:00:00Z'
        "category": category,
        "importance": importance_level
    }
    
    try:
        response = supabase.table("clippings").insert(payload).execute()
        print(f"✅ تم الحفظ بنجاح: [{importance_level}] - {title}")
        return response
    except Exception as e:
        print(f"❌ خطأ أثناء الحفظ في قاعدة البيانات: {e}")
        return None

# ==========================================
# 5. نقطة التشغيل الرئيسية (مثال على حلقة التجميع)
# ==========================================
if __name__ == "__main__":
    # مثال لتجربة سحب صفحة خبر وتخزينها
    test_url = "https://example.com/news/article-123"
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    try:
        response = requests.get(test_url, headers=headers, timeout=10)
        if response.status_code == 200:
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # استخراج عنوان الخبر وملخصه حسب هيكل الموقع
            article_title = soup.find('h1').get_text(strip=True) if soup.find('h1') else "عنوان افتراضي"
            article_summary = soup.find('meta', {'name': 'description'})['content'] if soup.find('meta', {'name': 'description'}) else ""
            
            # حفظ وتحليل القصاصة
            process_and_save_clipping(
                title=article_title,
                summary=article_summary,
                source="اسم الجريدة/الموقع",
                link=test_url,
                pub_date=datetime.utcnow().isoformat() + "Z",
                category="أخبار عامة",
                html_content=response.text
            )
    except Exception as e:
        print(f"حدث خطأ أثناء الاتصال بالموقع: {e}")
