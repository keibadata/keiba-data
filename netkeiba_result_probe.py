import re
import requests
from bs4 import BeautifulSoup


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


def clean_text(element):

    if element is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        element.get_text(
            " ",
            strip=True
        )
    ).strip()


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


print("=" * 50)
print("NETKEIBA CORNER PROBE")
print("=" * 50)

print("RACE_ID:", RACE_ID)
print("URL:", URL)
print("HTML SIZE:", len(html))


# =========================================================
# 1. キーワード確認
# =========================================================

print()
print("===== KEYWORD CHECK =====")

keywords = [
    "コーナー通過順位",
    "1コーナー",
    "2コーナー",
    "3コーナー",
    "4コーナー",
    "通過順位",
]

for keyword in keywords:

    print(
        keyword,
        "=>",
        html.count(keyword)
    )


# =========================================================
# 2. キーワードを直接含む要素
# =========================================================

print()
print("===== DIRECT TEXT ELEMENTS =====")

for keyword in keywords:

    print()
    print("########", keyword, "########")

    found = []

    for node in soup.find_all(
        string=re.compile(
            re.escape(keyword)
        )
    ):

        parent = node.parent

        if parent is None:
            continue

        key = id(parent)

        if key in found:
            continue

        found.append(key)

        print()
        print("TAG:", parent.name)
        print("ID:", parent.get("id"))
        print("CLASS:", parent.get("class"))
        print("TEXT:", clean_text(parent))

        print("PARENT HTML:")

        parent2 = parent.parent

        if parent2 is not None:
            print(str(parent2)[:6000])
        else:
            print(str(parent)[:6000])


# =========================================================
# 3. 「コーナー」を含む要素
# =========================================================

print()
print("===== CORNER ELEMENTS =====")

corner_elements = []

seen = set()

for element in soup.find_all(True):

    text = clean_text(element)

    if not text:
        continue

    if (
        "コーナー通過順位" not in text
        and "1コーナー" not in text
        and "2コーナー" not in text
        and "3コーナー" not in text
        and "4コーナー" not in text
    ):
        continue

    key = id(element)

    if key in seen:
        continue

    seen.add(key)

    # ページ全体の巨大要素は除外
    if len(text) > 3000:
        continue

    corner_elements.append(element)


print(
    "CORNER ELEMENT COUNT:",
    len(corner_elements)
)


for index, element in enumerate(
    corner_elements[:30],
    start=1
):

    print()
    print("-" * 50)
    print("CORNER ELEMENT", index)

    print(
        "TAG:",
        element.name
    )

    print(
        "ID:",
        element.get("id")
    )

    print(
        "CLASS:",
        element.get("class")
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
        str(element)[:8000]
    )


# =========================================================
# 4. class / id に corner/pass を含むもの
# =========================================================

print()
print("===== CLASS ID SEARCH =====")

patterns = [
    "corner",
    "pass",
    "passage",
    "position",
]

matched = set()

for element in soup.find_all(True):

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

    if not any(
        pattern in target
        for pattern in patterns
    ):
        continue

    key = (
        element.name,
        element_id,
        classes,
    )

    if key in matched:
        continue

    matched.add(key)

    print()
    print("TAG:", element.name)
    print("ID:", element_id)
    print("CLASS:", classes)

    print(
        "TEXT:",
        clean_text(element)[:1500]
    )

    print(
        "HTML:",
        str(element)[:5000]
    )


# =========================================================
# 5. 生HTMLでキーワード前後を表示
# =========================================================

print()
print("===== RAW HTML AROUND CORNERS =====")

for keyword in [
    "コーナー通過順位",
    "1コーナー",
    "2コーナー",
    "3コーナー",
    "4コーナー",
]:

    print()
    print("#" * 50)
    print(keyword)
    print("#" * 50)

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
        matches[:10],
        start=1
    ):

        start = max(
            0,
            match.start() - 2500
        )

        end = min(
            len(html),
            match.end() + 6000
        )

        print()
        print(
            "----- MATCH",
            index,
            "-----"
        )

        print(
            html[start:end]
        )


print()
print("=" * 50)
print("CORNER PROBE COMPLETE")
print("=" * 50)
