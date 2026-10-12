# ==========================================
# 2. قوائم الفلترة مع تساهل في المطابقة
# ==========================================

# كلمات مفتاحية خاصة بغرداية/ميزاب — جزائرية بطبيعتها ولا تظهر في أخبار دول أخرى
SPECIFIC_KEYWORDS = [
    "غرداية", "أطفيش", "اطفيش", "ميزاب", "بني يزقن",
    "القرارة", "بريان", "متليلي", "العطف", "بونورة", "زلفانة",
    "بني يسجن", "مزابي", "ورقلة", "المنيعة", "الجلفة"
]

# كلمات عامة تحتاج دليل جزائري مرافق (لأنها قد تظهر في تراث مصر/السعودية/المغرب...)
GENERIC_KEYWORDS = [
    "تراث", "مخطوط", "تراثي", "أرشيف"
]

# مؤشرات قوية على أن الخبر يخص الجزائر
ALGERIA_INDICATORS = [
    "الجزائر", "الجزائري", "الجزائرية", "جزائري", "جزائرية",
    "ولاية غرداية", "ولاية", "بلدية", "الدولة الجزائرية",
    "الجيش الوطني الشعبي", "الدرك الوطني", "الحماية المدنية"
]

# قائمة بيضاء لنطاقات الصحافة الجزائرية (يُضاف إليها ما يكتشفه المستخدم لاحقاً)
ALGERIAN_DOMAINS = [
    "aps.dz", "elkhabar.com", "ennahar.dz", "echoroukonline.com",
    "elwatan.com", "elwatan-dz.com", "liberte-algerie.com",
    "lexpressiondz.com", "tsa-algerie.com", "algerie360.com",
    "ennaharonline.com", "elbilad.net", "ennas.dz", "en-nas.dz",
    "elhayat.net", "al-fadjr.com", "essahafa.com", "alkhaleej.dz",
    "dzayerinfo.com", "lequotidienalgerie.com", "radioalgerie.dz",
    "el-massa.com", "algerie-focus.com", "elain.info",
    "annasronline.com", "sawt-alahrar.net", "el-mouradia.dz",
    "el-moudjahid.com", "horizons.dz", "reflexiondz.net",
    "lapatrienews.dz", "lejeune-independant.net", "reporters.dz",
    "fibladi.com", "dzairdaily.com", "lagazettedufennec.com",
    # نطاقات محلية/جهوية (غرداية، ورقلة، الجنوب)
    "ghardaia.com", "elghardaia.com", "mzab-info.com",
    "atfich.net", "el-attef.com", "ouargla.org"
]

# دول ومناطق قد تتسرب من مصادر عربية أخرى (تُستخدم كتحذير فقط عند المطابقة العامة)
OTHER_ARAB_COUNTRIES = [
    "مصر", "السعودية", "الإمارات", "الكويت", "قطر", "البحرين",
    "سلطنة عمان", "الأردن", "لبنان", "سوريا", "العراق",
    "فلسطين", "تونس", "المغرب", "ليبيا", "موريتانيا",
    "السودان", "اليمن", "تركيا", "إيران"
]

EXCLUDE_KEYWORDS = [
    "كرة القدم", "الدوري", "مباراة", "الأهلي", "الهلال", "النصر", "الزمالك",
    "سهم", "أسهم", "بورصة", "تداول", "وظائف", "عقارات للبيع"
]
