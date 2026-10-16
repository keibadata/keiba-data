import re
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# =========================================================
# JRA クッション値 通信先/API診断
# =========================================================

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


def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


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


def contains_target(text):
    text_lower = text.lower()

    keywords = [
        "cushion_list",
        "btn_cushion",
        "cushion_data",
        "cushion",
        "クッション",
    ]

    return any(
        keyword.lower() in text_lower
        for keyword in keywords
    )


def print_context(
    text,
    keyword,
    width=500
):
    lower_text = text.lower()
    lower_keyword = keyword.lower()

    start = 0
    count = 0

    while True:

        index = lower_text.find(
            lower_keyword,
            start
        )

        if index < 0:
            break

        count += 1

        left = max(
            0,
            index - width
        )

        right = min(
            len(text),
            index + len(keyword) + width
        )

        print()
        print(
            f"[{keyword} #{count}]"
        )

        print(
            text[left:right]
        )

        start = (
            index
            + len(keyword)
        )

        if count >= 10:
            break

    return count


# =========================================================
# 1. 馬場情報ページ取得
# =========================================================

print(
    "===== FETCH JRA TRACK PAGE ====="
)

html = fetch(
    PAGE_URL
)

print(
    "PAGE:",
    PAGE_URL
)

print(
    "HTML BYTES:",
    len(html.encode("utf-8"))
)

soup = BeautifulSoup(
    html,
    "html.parser"
)


# =========================================================
# 2. scriptタグ一覧
# =========================================================

scripts = []

for script in soup.find_all(
    "script"
):

    src = script.get(
        "src"
    )

    if src:

        url = urljoin(
            PAGE_URL,
            src
        )

        if url not in scripts:
            scripts.append(
                url
            )


print()
print(
    "===== JAVASCRIPT FILES ====="
)

print(
    "COUNT:",
    len(scripts)
)

for index, url in enumerate(
    scripts,
    start=1
):

    print(
        f"{index}:",
        url
    )


# =========================================================
# 3. HTML内の関連文字を確認
# =========================================================

print()
print(
    "===== HTML TARGET CONTEXT ====="
)

for keyword in [
    "cushion_list",
    "btn_cushion",
    "cushion_data",
]:

    count = print_context(
        html,
        keyword,
        width=350
    )

    if count == 0:
        print(
            keyword,
            ": NONE"
        )


# =========================================================
# 4. JSファイルを順番に取得
# =========================================================

matched_scripts = []

for index, url in enumerate(
    scripts,
    start=1
):

    print()
    print(
        "=" * 70
    )

    print(
        "CHECK SCRIPT:",
        index
    )

    print(
        "URL:",
        url
    )

    try:

        js = fetch(
            url
        )

    except Exception as error:

        print(
            "FETCH ERROR:",
            repr(error)
        )

        continue

    print(
        "SIZE:",
        len(js)
    )

    if not contains_target(
        js
    ):

        print(
            "TARGET: NONE"
        )

        continue

    print(
        "TARGET: FOUND"
    )

    matched_scripts.append(
        {
            "url": url,
            "text": js,
        }
    )

    for keyword in [
        "cushion_list",
        "btn_cushion",
        "cushion_data",
        "cushion",
    ]:

        print_context(
            js,
            keyword,
            width=700
        )


# =========================================================
# 5. 通信URL候補を抽出
# =========================================================

print()
print(
    "=" * 70
)

print(
    "===== NETWORK URL CANDIDATES ====="
)

network_candidates = []


def add_candidate(value):

    value = clean_text(
        value
    )

    if not value:
        return

    if value not in network_candidates:
        network_candidates.append(
            value
        )


for item in matched_scripts:

    js = item[
        "text"
    ]

    # -----------------------------------------------------
    # 絶対URL
    # -----------------------------------------------------

    for match in re.finditer(
        r"""https?://[^\s"'<>]+""",
        js
    ):

        add_candidate(
            match.group(0)
        )

    # -----------------------------------------------------
    # 相対URL・JSON・APIらしい文字列
    # -----------------------------------------------------

    patterns = [
        r"""["']([^"']+\.json(?:\?[^"']*)?)["']""",
        r"""["']([^"']+\.php(?:\?[^"']*)?)["']""",
        r"""["']([^"']+\.cgi(?:\?[^"']*)?)["']""",
        r"""["']([^"']+/api/[^"']*)["']""",
        r"""["']([^"']*cushion[^"']*)["']""",
        r"""["']([^"']*baba[^"']*\.json[^"']*)["']""",
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            js,
            flags=re.I
        ):

            add_candidate(
                match.group(1)
            )


if not network_candidates:

    print(
        "NONE"
    )

else:

    for index, value in enumerate(
        network_candidates,
        start=1
    ):

        print(
            f"{index}:",
            value
        )


# =========================================================
# 6. $.ajax / fetch / XMLHttpRequest 周辺
# =========================================================

print()
print(
    "=" * 70
)

print(
    "===== REQUEST CODE CONTEXT ====="
)

request_keywords = [
    "$.ajax",
    "$.get",
    "$.getJSON",
    "fetch(",
    "XMLHttpRequest",
    "ajax(",
    "url:",
]

found_request_code = False

for item in matched_scripts:

    js = item[
        "text"
    ]

    print()
    print(
        "SCRIPT:",
        item["url"]
    )

    for keyword in request_keywords:

        count = print_context(
            js,
            keyword,
            width=900
        )

        if count > 0:
            found_request_code = True


if not found_request_code:

    print(
        "NO REQUEST CODE FOUND"
    )


# =========================================================
# 完了
# =========================================================

print()
print(
    "=" * 70
)

print(
    "MATCHED SCRIPT COUNT:",
    len(matched_scripts)
)

print(
    "JRA CUSHION NETWORK PROBE FINISHED"
)

print(
    "=" * 70
)
