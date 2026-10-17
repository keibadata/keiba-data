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
    "Accept-Language":
        "ja,en-US;q=0.9,en;q=0.8",
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


def short_html(
    element,
    length=3000
):

    if element is None:
        return ""

    return str(
        element
    )[:length]


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
    "NETKEIBA RESULT TABLE PROBE"
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
# HorseList の全数
# =========================================================

print()
print(
    "===== HORSELIST CHECK ====="
)

horse_list_rows = soup.select(
    "tr.HorseList"
)

print(
    "tr.HorseList count:",
    len(horse_list_rows)
)


for index, row in enumerate(
    horse_list_rows,
    start=1
):

    print()
    print(
        "HORSELIST",
        index
    )

    print(
        "classes:",
        row.get(
            "class"
        )
    )

    print(
        "text:",
        clean_text(
            row
        )[:500]
    )


# =========================================================
# 2.
# Result_Num の全数
# =========================================================

print()
print(
    "===== RESULT_NUM CHECK ====="
)

result_num_elements = soup.select(
    ".Result_Num"
)

print(
    ".Result_Num count:",
    len(result_num_elements)
)


for index, element in enumerate(
    result_num_elements[:30],
    start=1
):

    row = element.find_parent(
        "tr"
    )

    print()
    print(
        "RESULT_NUM",
        index
    )

    print(
        "value:",
        clean_text(
            element
        )
    )

    if row is not None:

        print(
            "row class:",
            row.get(
                "class"
            )
        )

        print(
            "row text:",
            clean_text(
                row
            )[:800]
        )


# =========================================================
# 3.
# Horse_Info の全数
# =========================================================

print()
print(
    "===== HORSE_INFO CHECK ====="
)

horse_info_elements = soup.select(
    ".Horse_Info"
)

print(
    ".Horse_Info count:",
    len(horse_info_elements)
)


for index, element in enumerate(
    horse_info_elements[:30],
    start=1
):

    row = element.find_parent(
        "tr"
    )

    print()
    print(
        "HORSE_INFO",
        index
    )

    print(
        "text:",
        clean_text(
            element
        )
    )

    if row is not None:

        print(
            "row class:",
            row.get(
                "class"
            )
        )


# =========================================================
# 4.
# 馬リンクを持つTRを全部探す
# =========================================================

print()
print(
    "===== HORSE LINK ROWS ====="
)

horse_rows = []

seen = set()


for link in soup.select(
    'a[href*="/horse/"]'
):

    row = link.find_parent(
        "tr"
    )

    if row is None:
        continue

    row_id = id(
        row
    )

    if row_id in seen:
        continue

    seen.add(
        row_id
    )

    horse_rows.append(
        row
    )


print(
    "horse link row count:",
    len(horse_rows)
)


for index, row in enumerate(
    horse_rows[:30],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "HORSE ROW",
        index
    )

    print(
        "class:",
        row.get(
            "class"
        )
    )

    print(
        "text:"
    )

    print(
        clean_text(
            row
        )[:1200]
    )


# =========================================================
# 5.
# 全TABLE調査
# =========================================================

print()
print(
    "===== ALL TABLES ====="
)

tables = soup.find_all(
    "table"
)

print(
    "table count:",
    len(tables)
)


for index, table in enumerate(
    tables,
    start=1
):

    rows = table.find_all(
        "tr"
    )

    horse_links = table.select(
        'a[href*="/horse/"]'
    )

    result_nums = table.select(
        ".Result_Num"
    )

    print()
    print(
        "TABLE",
        index
    )

    print(
        "id:",
        table.get(
            "id"
        )
    )

    print(
        "class:",
        table.get(
            "class"
        )
    )

    print(
        "tr count:",
        len(rows)
    )

    print(
        "horse links:",
        len(horse_links)
    )

    print(
        "Result_Num:",
        len(result_nums)
    )

    print(
        "text:",
        clean_text(
            table
        )[:800]
    )


# =========================================================
# 6.
# Result_Numを含む親TABLE
# =========================================================

print()
print(
    "===== RESULT TABLE CANDIDATES ====="
)

candidate_tables = []

candidate_seen = set()


for element in result_num_elements:

    table = element.find_parent(
        "table"
    )

    if table is None:
        continue

    table_id = id(
        table
    )

    if table_id in candidate_seen:
        continue

    candidate_seen.add(
        table_id
    )

    candidate_tables.append(
        table
    )


print(
    "candidate table count:",
    len(candidate_tables)
)


for index, table in enumerate(
    candidate_tables,
    start=1
):

    print()
    print(
        "========================================"
    )

    print(
        "CANDIDATE TABLE",
        index
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

    rows = table.find_all(
        "tr"
    )

    print(
        "ROW COUNT:",
        len(rows)
    )

    print(
        "HORSE LINKS:",
        len(
            table.select(
                'a[href*="/horse/"]'
            )
        )
    )

    print(
        "RESULT NUM:",
        len(
            table.select(
                ".Result_Num"
            )
        )
    )

    print(
        "HTML:"
    )

    print(
        short_html(
            table,
            12000
        )
    )


# =========================================================
# 7.
# tbody単位でも調査
# =========================================================

print()
print(
    "===== TBODY CHECK ====="
)

tbodies = soup.find_all(
    "tbody"
)

print(
    "tbody count:",
    len(tbodies)
)


for index, tbody in enumerate(
    tbodies,
    start=1
):

    horse_links = tbody.select(
        'a[href*="/horse/"]'
    )

    result_nums = tbody.select(
        ".Result_Num"
    )

    if (
        not horse_links
        and not result_nums
    ):
        continue

    print()
    print(
        "TBODY",
        index
    )

    print(
        "class:",
        tbody.get(
            "class"
        )
    )

    print(
        "tr count:",
        len(
            tbody.find_all(
                "tr"
            )
        )
    )

    print(
        "horse links:",
        len(
            horse_links
        )
    )

    print(
        "Result_Num:",
        len(
            result_nums
        )
    )

    print(
        "text:",
        clean_text(
            tbody
        )[:1500]
    )


# =========================================================
# 8.
# 1着〜着順セル候補
# =========================================================

print()
print(
    "===== RANK CELL CLASS CHECK ====="
)

rank_patterns = [
    "Result_Num",
    "Rank",
    "Result",
    "Order",
    "Arrival",
]


for pattern in rank_patterns:

    elements = soup.select(
        f".{pattern}"
    )

    print(
        pattern,
        "=>",
        len(elements)
    )


# =========================================================
# 9.
# class名にResult/Horseを含むTR
# =========================================================

print()
print(
    "===== TR CLASS SEARCH ====="
)

for row in soup.find_all(
    "tr"
):

    classes = " ".join(
        row.get(
            "class",
            []
        )
    )

    lower = classes.lower()

    if (
        "horse" in lower
        or "result" in lower
    ):

        print()
        print(
            "class:",
            classes
        )

        print(
            "text:",
            clean_text(
                row
            )[:1000]
        )


# =========================================================
# 10.
# JavaScript / HTML内に結果データが
# 別形式で入っていないか確認
# =========================================================

print()
print(
    "===== RAW KEYWORD COUNTS ====="
)

raw_keywords = [
    "HorseList",
    "Result_Num",
    "Horse_Info",
    "RaceTable01",
    "HorseName",
    "Umaban",
    "Last3F",
    "PassageRate",
]


for keyword in raw_keywords:

    print(
        keyword,
        "=>",
        html.count(
            keyword
        )
    )


# =========================================================
# 11.
# RaceTable01 周辺のHTML
# =========================================================

print()
print(
    "===== RAW HTML AROUND RaceTable01 ====="
)

matches = list(
    re.finditer(
        "RaceTable01",
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
        match.start() - 1000
    )

    end = min(
        len(html),
        match.end() + 10000
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
print(
    "========================================"
)

print(
    "PROBE COMPLETE"
)

print(
    "========================================"
)
