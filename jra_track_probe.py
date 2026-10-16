import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


PAGE_URL = (
    "https://www.jra.go.jp/"
    "keiba/baba/index.html"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language":
        "ja,en-US;q=0.9,en;q=0.8",
}


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    return response.text


def compact(value):
    return re.sub(
        r"[ \t]+",
        " ",
        value
    )


def contexts(
    text,
    keyword,
    width=1200,
    limit=5
):
    results = []

    lower_text = text.lower()
    lower_keyword = keyword.lower()

    start = 0

    while len(results) < limit:

        pos = lower_text.find(
            lower_keyword,
            start
        )

        if pos < 0:
            break

        left = max(
            0,
            pos - width
        )

        right = min(
            len(text),
            pos + len(keyword) + width
        )

        value = text[
            left:right
        ]

        if value not in results:
            results.append(
                value
            )

        start = (
            pos
            + len(keyword)
        )

    return results


# =========================================================
# JRA馬場ページ
# =========================================================

html = fetch(
    PAGE_URL
)

soup = BeautifulSoup(
    html,
    "html.parser"
)


# =========================================================
# JS一覧取得
# =========================================================

script_urls = []

for script in soup.find_all(
    "script"
):
    src = script.get(
        "src"
    )

    if not src:
        continue

    url = urljoin(
        PAGE_URL,
        src
    )

    if url not in script_urls:
        script_urls.append(
            url
        )


# =========================================================
# cushion関連JSだけ抽出
# =========================================================

matched = []

for url in script_urls:

    try:
        js = fetch(
            url
        )

    except Exception:
        continue

    lower = js.lower()

    if (
        "cushion_list" in lower
        or "btn_cushion" in lower
        or "cushion_data" in lower
    ):
        matched.append(
            (
                url,
                js
            )
        )


print(
    "===== MATCHED JAVASCRIPT ====="
)

print(
    "COUNT:",
    len(matched)
)


for index, (
    url,
    js
) in enumerate(
    matched,
    start=1
):

    print()
    print(
        f"JS #{index}"
    )

    print(
        "URL:",
        url
    )

    print(
        "SIZE:",
        len(js)
    )


# =========================================================
# cushion_list周辺
# =========================================================

print()
print(
    "===== CUSHION_LIST CODE ====="
)

for url, js in matched:

    items = contexts(
        js,
        "cushion_list",
        width=1600,
        limit=3
    )

    for index, item in enumerate(
        items,
        start=1
    ):

        print()
        print(
            "SCRIPT:",
            url
        )

        print(
            f"CUSHION_LIST #{index}"
        )

        print(
            compact(
                item
            )
        )


# =========================================================
# btn_cushion周辺
# =========================================================

print()
print(
    "===== BTN_CUSHION CODE ====="
)

for url, js in matched:

    items = contexts(
        js,
        "btn_cushion",
        width=1600,
        limit=3
    )

    for index, item in enumerate(
        items,
        start=1
    ):

        print()
        print(
            f"BTN_CUSHION #{index}"
        )

        print(
            compact(
                item
            )
        )


# =========================================================
# AJAX / GET / POST / JSON 周辺
# =========================================================

print()
print(
    "===== REQUEST CODE ====="
)

request_words = [
    "$.ajax",
    "$.get(",
    "$.post(",
    "$.getjson",
    "fetch(",
    "xmlhttprequest",
    ".json",
]

request_found = False

for url, js in matched:

    for keyword in request_words:

        items = contexts(
            js,
            keyword,
            width=1300,
            limit=3
        )

        for item in items:

            request_found = True

            print()
            print(
                "KEYWORD:",
                keyword
            )

            print(
                compact(
                    item
                )
            )


if not request_found:
    print(
        "NONE"
    )


# =========================================================
# URL文字列候補
# =========================================================

print()
print(
    "===== URL STRINGS ====="
)

url_strings = []

for url, js in matched:

    patterns = [
        r"""["']([^"']*cushion[^"']*)["']""",
        r"""["']([^"']*baba[^"']*)["']""",
        r"""["']([^"']+\.json[^"']*)["']""",
        r"""["']([^"']+\.php[^"']*)["']""",
        r"""["']([^"']+\.cgi[^"']*)["']""",
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            js,
            flags=re.I
        ):

            value = (
                match.group(1)
                .strip()
            )

            if (
                value
                and value
                not in url_strings
            ):
                url_strings.append(
                    value
                )


if url_strings:

    for index, value in enumerate(
        url_strings,
        start=1
    ):

        print(
            f"{index}:",
            value
        )

else:

    print(
        "NONE"
    )


print()
print(
    "===== FINISHED ====="
)
