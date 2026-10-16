import re
import requests
from bs4 import BeautifulSoup


# =========================================================
# JRA馬場情報ページ
# 現在の開催場候補を診断
# =========================================================

PAGES = {
    "page1": (
        "https://www.jra.go.jp/"
        "keiba/baba/index.html"
    ),
    "page2": (
        "https://www.jra.go.jp/"
        "keiba/baba/index2.html"
    ),
    "page3": (
        "https://www.jra.go.jp/"
        "keiba/baba/index3.html"
    ),
}


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


KEYWORDS = [
    "東京",
    "京都",
    "新潟",
    "クッション値",
    "含水率",
    "ゴール前",
    "4コーナー",
    "ダート",
    "芝",
    "良",
    "稍重",
    "重",
    "不良",
]


def clean_text(text):
    return re.sub(
        r"\s+",
        " ",
        text
    ).strip()


def print_keyword_context(
    text,
    keyword,
    width=150
):
    start = 0
    found = 0

    while True:

        index = text.find(
            keyword,
            start
        )

        if index < 0:
            break

        found += 1

        left = max(
            0,
            index - width
        )

        right = min(
            len(text),
            index + len(keyword) + width
        )

        context = text[
            left:right
        ]

        print(
            f"\n[{keyword} #{found}]"
        )

        print(
            clean_text(
                context
            )
        )

        start = (
            index
            + len(keyword)
        )

        # ログ肥大化防止
        if found >= 5:
            break

    return found


for page_name, url in PAGES.items():

    print()
    print(
        "=" * 70
    )

    print(
        "PAGE:",
        page_name
    )

    print(
        "URL:",
        url
    )

    print(
        "=" * 70
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        print(
            "status:",
            response.status_code
        )

        print(
            "content-type:",
            response.headers.get(
                "content-type",
                ""
            )
        )

        print(
            "bytes:",
            len(response.content)
        )

        response.raise_for_status()

    except Exception as e:

        print(
            "FETCH ERROR:",
            repr(e)
        )

        continue

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    print()
    print(
        "--- TITLE ---"
    )

    if soup.title:

        print(
            clean_text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )
        )

    else:
        print(
            "NO TITLE"
        )

    print()
    print(
        "--- TEXT LENGTH ---"
    )

    print(
        len(page_text)
    )

    print()
    print(
        "--- KEYWORD COUNTS ---"
    )

    for keyword in KEYWORDS:

        count = page_text.count(
            keyword
        )

        print(
            keyword,
            ":",
            count
        )

    print()
    print(
        "--- KEYWORD CONTEXT ---"
    )

    for keyword in KEYWORDS:

        if keyword not in page_text:
            continue

        print_keyword_context(
            page_text,
            keyword
        )

    print()
    print(
        "--- TABLES ---"
    )

    tables = soup.find_all(
        "table"
    )

    print(
        "table count:",
        len(tables)
    )

    for index, table in enumerate(
        tables[:20],
        start=1
    ):

        table_text = clean_text(
            table.get_text(
                " ",
                strip=True
            )
        )

        print()
        print(
            f"[TABLE {index}]"
        )

        print(
            table_text[:2000]
        )

    print()
    print(
        "--- SCRIPT SOURCES ---"
    )

    scripts = soup.find_all(
        "script"
    )

    script_sources = []

    for script in scripts:

        src = script.get(
            "src"
        )

        if src:
            script_sources.append(
                src
            )

    if script_sources:

        for src in script_sources:
            print(
                src
            )

    else:

        print(
            "NO EXTERNAL SCRIPT"
        )

    print()
    print(
        "--- LINKS CONTAINING BABA ---"
    )

    found_links = set()

    for link in soup.find_all(
        "a",
        href=True
    ):

        href = link.get(
            "href",
            ""
        )

        label = clean_text(
            link.get_text(
                " ",
                strip=True
            )
        )

        combined = (
            href
            + " "
            + label
        )

        if (
            "baba" in combined.lower()
            or "馬場" in combined
            or "含水" in combined
            or "クッション" in combined
        ):

            item = (
                label,
                href
            )

            if item in found_links:
                continue

            found_links.add(
                item
            )

            print(
                label,
                "=>",
                href
            )

print()
print(
    "=" * 70
)

print(
    "JRA TRACK PROBE FINISHED"
)

print(
    "=" * 70
)
