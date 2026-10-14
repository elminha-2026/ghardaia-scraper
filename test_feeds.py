"""
test_feeds.py — اختبار صلاحية روابط RSS الجزائرية
"""
import requests

HEADERS = {
    'User-Agent': ('Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                   'AppleWebKit/537.36 (KHTML, like Gecko) '
                   'Chrome/122.0.0.0 Safari/537.36'),
    'Accept': 'application/rss+xml, application/xml, text/xml, */*;q=0.8',
}

TEST_FEEDS = {
    # Google News بالفرنسية
    "Google News: Ghardaia": "https://news.google.com/rss/search?q=Ghardaia+when:30d&hl=fr&gl=DZ&ceid=DZ:fr",
    "Google News: Mzab":     "https://news.google.com/rss/search?q=Mzab+when:30d&hl=fr&gl=DZ&ceid=DZ:fr",
    "Google News: أطفيش":     "https://news.google.com/rss/search?q=%D8%A3%D8%B7%D9%81%D9%8A%D8%B4+when:30d&hl=fr&gl=DZ&ceid=DZ:fr",
    # صحف جزائرية
    "الشروق أونلاين":       "https://www.echoroukonline.com/feed/",
    "جريدة اللقاء":         "https://elikaaonline.com/feed/",
    "L'Expression":         "https://lexpressiondz.com/feeds/index.rssi",
    "Radio Algérie":        "http://www.radioalgerie.dz/news/fr/rss.xml",
    "Algérie Eco":          "https://www.algerie-eco.com/feed/",
    "Alg24":                "https://www.alg24.net/feed/",
    "Dzair Daily":          "https://www.dzairdaily.com/feed/",
    "El Watan":             "https://elwatan-dz.com/feed",
    "APS":                  "https://www.aps.dz/ar/rss",
}

print("=" * 70)
print("اختبار المصادر — يرجى الانتظار...")
print("=" * 70)

working = []
failed  = []

for name, url in TEST_FEEDS.items():
    try:
        r = requests.get(url, headers=HEADERS, timeout=15)
        size = len(r.content)
        status = r.status_code

        # فحص المحتوى
        if status == 200 and size > 500:
            has_items = b'<item' in r.content or b'<entry' in r.content
            marker = "✅" if has_items else "⚠️ (لا يحتوي عناصر)"
            print(f"{marker} {name:30} | {status} | {size} bytes")
            if has_items:
                working.append((name, url))
            else:
                failed.append((name, url, "لا يحتوي <item>"))
        else:
            print(f"❌ {name:30} | {status} | {size} bytes")
            failed.append((name, url, f"HTTP {status}"))
    except requests.RequestException as e:
        print(f"❌ {name:30} | خطأ: {e}")
        failed.append((name, url, str(e)))

print("\n" + "=" * 70)
print(f"✅ تعمل: {len(working)}")
print(f"❌ لا تعمل: {len(failed)}")
print("=" * 70)

if working:
    print("\nالمصادر التي تعمل — انسخها إلى scraper.py:")
    for name, url in working:
        print(f'    "{name}": "{url}",')

if failed:
    print("\nالمصادر التي لا تعمل — احذفها أو استبدلها:")
    for name, url, err in failed:
        print(f"    ❌ {name} — {err}")
