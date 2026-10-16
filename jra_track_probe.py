import re
import requests
from urllib.parse import urljoin

BABA_URL = "https://www.jra.go.jp/keiba/baba/index.html"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

KEYWORDS = [
    "moist_list",
    "btn_moist",
]


def get_text(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    r.raise_for_status()

    if not r.encoding or r.encoding.lower() in [
        "iso-8859-1",
        "ascii"
    ]:
        r.encoding = r.apparent_encoding or "utf-8"

    return r.text


def get_scripts(html):
    sources = re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']',
        html,
        re.I
    )

    return list(dict.fromkeys(
        urljoin(BABA_URL, src)
        for src in sources
    ))


def show_context(text, keyword, before=1500, after=3500):
    matches = list(
        re.finditer(
            re.escape(keyword),
            text,
            re.I
        )
    )

    if not matches:
        return False

    for i, match in enumerate(matches, 1):
        start = max(
            0,
            match.start() - before
        )
        end = min(
            len(text),
            match.end() + after
        )

        print()
        print("=" * 70)
        print(
            f"KEYWORD: {keyword} "
            f"MATCH: {i}/{len(matches)}"
        )
        print("=" * 70)
        print(text[start:end])

    return True


print("===== JRA MOISTURE SHORT PROBE =====")

html = get_text(BABA_URL)
scripts = get_scripts(html)

print("JS files:", len(scripts))

found = False

for url in scripts:
    try:
        js = get_text(url)
    except Exception:
        continue

    if not any(
        re.search(
            re.escape(keyword),
            js,
            re.I
        )
        for keyword in KEYWORDS
    ):
        continue

    found = True

    print()
    print("########################################")
    print("MATCHED JS")
    print(url)
    print("########################################")

    for keyword in KEYWORDS:
        show_context(
            js,
            keyword
        )


if not found:
    print()
    print("TARGET JAVASCRIPT NOT FOUND")

print()
print("===== PROBE FINISHED =====")
