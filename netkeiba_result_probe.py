import re
import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

# 東京2RでHTML構造を調査
RACE_ID = "202605040502"

URL = (
    "https://race.netkeiba.com/"
    "race/result.html"
    f"?race_id={RACE_ID}"
)

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


# =========================================================
# 取得
# =========================================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()
response.encoding = response.apparent_encoding

html = response.text

soup = BeautifulSoup(
    html,
    "html.parser"
)


def clean_text(element):
    if element is None:
        return ""

    return element.get_text(
        " ",
        strip=True
    )


print(
    "========================================"
)

print(
    "NETKEIBA RESULT PROBE"
)

print(
    "========================================"
)

print(
    "RACE_ID:",
    RACE_ID
)

print(
    "URL:",
    URL
)

print(
    "HTML SIZE:",
    len(html)
)


# =========================================================
# キーワード存在確認
# =========================================================

print()
print(
    "===== KEYWORD CHECK ====="
)

keywords = [
    "コーナー通過順位",
    "通過順位",
    "3コーナー",
    "4コーナー",
    "上り",
    "上がり",
    "ハロンタイム",
]

for keyword in keywords:

    print(
        keyword,
        "=>",
        keyword in html
    )


# =========================================================
# 結果表
# =========================================================

print()
print(
    "===== RESULT ROWS ====="
)

result_rows = soup.select(
    "tr.HorseList"
)

if not result_rows:

    result_rows = soup.select(
        ".RaceTable01 tr"
    )

print(
    "RESULT ROW COUNT:",
    len(result_rows)
)


for index, row in enumerate(
    result_rows[:5],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "RESULT ROW",
        index
    )

    print(
        "TEXT:"
    )

    print(
        clean_text(row)
    )

    print(
        "HTML:"
    )

    print(
        str(row)[:5000]
    )


# =========================================================
# 「コーナー」を含むHTML要素
# =========================================================

print()
print(
    "===== CORNER TEXT ELEMENTS ====="
)

corner_elements = []

for element in soup.find_all(
    [
        "div",
        "table",
        "tr",
        "td",
        "th",
        "span",
        "ul",
        "li",
        "dl",
        "dt",
        "dd",
    ]
):

    text = clean_text(
        element
    )

    if (
        "コーナー通過順位" in text
        or "3コーナー" in text
        or "4コーナー" in text
    ):

        corner_elements.append(
            element
        )


print(
    "CORNER ELEMENT COUNT:",
    len(corner_elements)
)


for index, element in enumerate(
    corner_elements[:20],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "CORNER ELEMENT",
        index
    )

    print(
        "TAG:",
        element.name
    )

    print(
        "ID:",
        element.get(
            "id"
        )
    )

    print(
        "CLASS:",
        element.get(
            "class"
        )
    )

    print(
        "TEXT:"
    )

    print(
        clean_text(element)
    )

    print(
        "HTML:"
    )

    print(
        str(element)[:7000]
    )


# =========================================================
# 通過順位らしいclass/idを探索
# =========================================================

print()
print(
    "===== CLASS / ID SEARCH ====="
)

patterns = [
    "corner",
    "pass",
    "passage",
    "position",
    "rank",
    "result",
    "haron",
    "lap",
]

found = []


for element in soup.find_all(
    True
):

    element_id = str(
        element.get(
            "id",
            ""
        )
    )

    classes = " ".join(
        element.get(
            "class",
            []
        )
    )

    target = (
        element_id
        + " "
        + classes
    ).lower()

    if any(
        pattern in target
        for pattern in patterns
    ):

        key = (
            element.name,
            element_id,
            classes,
        )

        if key not in found:

            found.append(
                key
            )

            print()
            print(
                "TAG:",
                element.name
            )

            print(
                "ID:",
                element_id
            )

            print(
                "CLASS:",
                classes
            )

            print(
                "TEXT:",
                clean_text(element)[:1000]
            )


# =========================================================
# 「3コーナー」「4コーナー」周辺の生HTML
# =========================================================

print()
print(
    "===== RAW HTML AROUND CORNER KEYWORDS ====="
)


for keyword in [
    "コーナー通過順位",
    "3コーナー",
    "4コーナー",
]:

    print()
    print(
        "########",
        keyword,
        "########"
    )

    matches = list(
        re.finditer(
            re.escape(keyword),
            html
        )
    )

    print(
        "MATCH COUNT:",
        len(matches)
    )

    for index, match in enumerate(
        matches[:5],
        start=1
    ):

        start = max(
            0,
            match.start() - 1500
        )

        end = min(
            len(html),
            match.end() + 4000
        )

        print()
        print(
            "--- MATCH",
            index,
            "---"
        )

        print(
            html[start:end]
        )


print()
print(
    "========================================"
)

print(
    "PROBE COMPLETE"
)

print(
    "========================================"
)
