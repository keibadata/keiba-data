import re
import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

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
# 共通
# =========================================================

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


def print_element(
    title,
    element,
    html_length=8000
):

    print()
    print(
        "=" * 60
    )
    print(
        title
    )
    print(
        "=" * 60
    )

    if element is None:

        print(
            "NOT FOUND"
        )

        return

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

    print()
    print(
        "TEXT:"
    )

    print(
        clean_text(
            element
        )[:4000]
    )

    print()
    print(
        "HTML:"
    )

    print(
        str(
            element
        )[:html_length]
    )


# =========================================================
# HTML取得
# =========================================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()

response.encoding = (
    response.apparent_encoding
)

html = response.text

soup = BeautifulSoup(
    html,
    "html.parser"
)


print(
    "========================================"
)

print(
    "NETKEIBA LAP PROBE"
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
# 1.
# ラップ関連キーワードの出現数
# =========================================================

print()
print(
    "===== KEYWORD COUNTS ====="
)

keywords = [
    "ハロンタイム",
    "ラップ",
    "Haron",
    "haron",
    "Lap",
    "lap",
    "Laptime",
    "laptime",
    "data-laptime",
    "Race_HaronTime",
    "HaronTime",
    "RaceData_Haron",
]


for keyword in keywords:

    print(
        keyword,
        "=>",
        html.count(
            keyword
        )
    )


# =========================================================
# 2.
# 「ハロンタイム」という文字を持つ要素
# =========================================================

print()
print(
    "===== HARON TEXT ELEMENTS ====="
)

haron_elements = []


for element in soup.find_all(
    string=re.compile(
        "ハロンタイム"
    )
):

    parent = element.parent

    if parent is None:
        continue

    haron_elements.append(
        parent
    )


print(
    "count:",
    len(
        haron_elements
    )
)


for index, element in enumerate(
    haron_elements,
    start=1
):

    print_element(
        f"HARON TEXT ELEMENT {index}",
        element
    )

    print_element(
        f"HARON PARENT {index}",
        element.parent,
        12000
    )

    if element.parent is not None:

        print_element(
            f"HARON GRANDPARENT {index}",
            element.parent.parent,
            16000
        )


# =========================================================
# 3.
# class名に Haron / Lap を含む要素
# =========================================================

print()
print(
    "===== CLASS SEARCH ====="
)

class_candidates = []

seen = set()


for element in soup.find_all(
    True
):

    classes = element.get(
        "class",
        []
    )

    class_text = " ".join(
        classes
    )

    lower = class_text.lower()

    if (
        "haron" not in lower
        and "lap" not in lower
    ):
        continue

    key = id(
        element
    )

    if key in seen:
        continue

    seen.add(
        key
    )

    class_candidates.append(
        element
    )


print(
    "count:",
    len(
        class_candidates
    )
)


for index, element in enumerate(
    class_candidates[:50],
    start=1
):

    print_element(
        f"CLASS CANDIDATE {index}",
        element,
        10000
    )


# =========================================================
# 4.
# data-laptime 全件
# =========================================================

print()
print(
    "===== DATA-LAPTIME ====="
)

data_laptime_elements = soup.select(
    "[data-laptime]"
)

print(
    "count:",
    len(
        data_laptime_elements
    )
)


for index, element in enumerate(
    data_laptime_elements[:100],
    start=1
):

    print()
    print(
        "DATA-LAPTIME",
        index
    )

    print(
        "TAG:",
        element.name
    )

    print(
        "CLASS:",
        element.get(
            "class"
        )
    )

    print(
        "VALUE:",
        element.get(
            "data-laptime"
        )
    )

    print(
        "TEXT:",
        clean_text(
            element
        )[:300]
    )


# =========================================================
# 5.
# data-laptimeを持つ親要素
# =========================================================

print()
print(
    "===== DATA-LAPTIME PARENTS ====="
)

parents = []

parent_seen = set()


for element in data_laptime_elements:

    parent = element.parent

    if parent is None:
        continue

    key = id(
        parent
    )

    if key in parent_seen:
        continue

    parent_seen.add(
        key
    )

    parents.append(
        parent
    )


print(
    "parent count:",
    len(
        parents
    )
)


for index, parent in enumerate(
    parents[:30],
    start=1
):

    print_element(
        f"LAPTIME PARENT {index}",
        parent,
        10000
    )


# =========================================================
# 6.
# 「12.4 - 11.1」のような
# ラップ列候補をHTML全体から探す
# =========================================================

print()
print(
    "===== LAP SEQUENCE SEARCH ====="
)

sequence_pattern = re.compile(
    r"(?:"
    r"\d{1,2}\.\d"
    r"\s*(?:-|－|–|—)\s*"
    r"){2,}"
    r"\d{1,2}\.\d"
)


sequence_matches = list(
    sequence_pattern.finditer(
        html
    )
)


print(
    "sequence count:",
    len(
        sequence_matches
    )
)


for index, match in enumerate(
    sequence_matches[:30],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "SEQUENCE",
        index
    )

    print(
        "VALUE:"
    )

    print(
        match.group()
    )

    start = max(
        0,
        match.start() - 1500
    )

    end = min(
        len(html),
        match.end() + 2500
    )

    print()
    print(
        "RAW HTML AROUND:"
    )

    print(
        html[start:end]
    )


# =========================================================
# 7.
# 10秒台～19秒台の数値が多数入る
# table / tr を探索
# =========================================================

print()
print(
    "===== NUMERIC TABLE SEARCH ====="
)

numeric_pattern = re.compile(
    r"(?<!\d)"
    r"(?:[89]|1\d)\.\d"
    r"(?!\d)"
)


tables = soup.find_all(
    "table"
)


for table_index, table in enumerate(
    tables,
    start=1
):

    text = clean_text(
        table
    )

    values = numeric_pattern.findall(
        text
    )

    if len(
        values
    ) < 4:
        continue

    print()
    print(
        "========================================"
    )

    print(
        "TABLE",
        table_index
    )

    print(
        "ID:",
        table.get(
            "id"
        )
    )

    print(
        "CLASS:",
        table.get(
            "class"
        )
    )

    print(
        "VALUES:",
        values[:50]
    )

    print(
        "TEXT:"
    )

    print(
        text[:4000]
    )

    print(
        "HTML:"
    )

    print(
        str(
            table
        )[:12000]
    )


# =========================================================
# 8.
# tbody単位でも同じ調査
# =========================================================

print()
print(
    "===== NUMERIC TBODY SEARCH ====="
)


tbodies = soup.find_all(
    "tbody"
)


for tbody_index, tbody in enumerate(
    tbodies,
    start=1
):

    text = clean_text(
        tbody
    )

    values = numeric_pattern.findall(
        text
    )

    if len(
        values
    ) < 4:
        continue

    print()
    print(
        "========================================"
    )

    print(
        "TBODY",
        tbody_index
    )

    print(
        "CLASS:",
        tbody.get(
            "class"
        )
    )

    print(
        "VALUES:",
        values[:50]
    )

    print(
        "TEXT:"
    )

    print(
        text[:4000]
    )


# =========================================================
# 9.
# 「ハロンタイム」周辺の生HTML
# =========================================================

print()
print(
    "===== RAW HTML AROUND ハロンタイム ====="
)


raw_matches = list(
    re.finditer(
        "ハロンタイム",
        html
    )
)


print(
    "match count:",
    len(
        raw_matches
    )
)


for index, match in enumerate(
    raw_matches[:10],
    start=1
):

    start = max(
        0,
        match.start() - 3000
    )

    end = min(
        len(html),
        match.end() + 12000
    )

    print()
    print(
        "========================================"
    )

    print(
        "RAW MATCH",
        index
    )

    print(
        "========================================"
    )

    print(
        html[start:end]
    )


# =========================================================
# 10.
# script内にラップデータがあるか確認
# =========================================================

print()
print(
    "===== SCRIPT SEARCH ====="
)


scripts = soup.find_all(
    "script"
)


for script_index, script in enumerate(
    scripts,
    start=1
):

    script_text = (
        script.string
        or script.get_text(
            "\n",
            strip=False
        )
        or ""
    )

    lower = (
        script_text.lower()
    )

    if (
        "laptime" not in lower
        and "haron" not in lower
        and "ハロン" not in script_text
    ):

        continue


    print()
    print(
        "========================================"
    )

    print(
        "SCRIPT",
        script_index
    )

    print(
        "========================================"
    )

    print(
        script_text[:20000]
    )


# =========================================================
# 完了
# =========================================================

print()
print(
    "========================================"
)

print(
    "LAP PROBE COMPLETE"
)

print(
    "========================================"
)
