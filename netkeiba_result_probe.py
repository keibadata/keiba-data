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

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


print(
    "========================================"
)

print(
    "NETKEIBA HARON TABLE PROBE"
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


# =========================================================
# Race_HaronTime
# =========================================================

tables = soup.select(
    "table.Race_HaronTime"
)

print()
print(
    "Race_HaronTime table count:",
    len(tables)
)


# =========================================================
# TABLEごとに完全調査
# =========================================================

for table_index, table in enumerate(
    tables,
    start=1
):

    print()
    print(
        "========================================"
    )

    print(
        "TABLE",
        table_index
    )

    print(
        "========================================"
    )

    print(
        "class:",
        table.get(
            "class"
        )
    )

    print(
        "summary:",
        table.get(
            "summary"
        )
    )


    rows = table.find_all(
        "tr",
        recursive=False
    )


    print(
        "row count:",
        len(rows)
    )


    # =====================================================
    # 各TR
    # =====================================================

    for row_index, row in enumerate(
        rows,
        start=1
    ):

        print()
        print(
            "----------------------------------------"
        )

        print(
            "ROW",
            row_index
        )

        print(
            "----------------------------------------"
        )

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
            )
        )


        # -------------------------------------------------
        # 直下セル
        # -------------------------------------------------

        cells = row.find_all(
            [
                "th",
                "td",
            ],
            recursive=False
        )


        print(
            "cell count:",
            len(cells)
        )


        for cell_index, cell in enumerate(
            cells,
            start=1
        ):

            print()
            print(
                "CELL",
                cell_index
            )

            print(
                "tag:",
                cell.name
            )

            print(
                "class:",
                cell.get(
                    "class"
                )
            )

            print(
                "text:",
                clean_text(
                    cell
                )
            )

            print(
                "data-laptime:",
                cell.get(
                    "data-laptime"
                )
            )

            print(
                "data-time:",
                cell.get(
                    "data-time"
                )
            )

            print(
                "colspan:",
                cell.get(
                    "colspan"
                )
            )

            print(
                "rowspan:",
                cell.get(
                    "rowspan"
                )
            )

            print(
                "html:",
                str(
                    cell
                )[:1500]
            )


# =========================================================
# data-laptimeをページ全体でも確認
# =========================================================

print()
print(
    "========================================"
)

print(
    "ALL DATA-LAPTIME ELEMENTS"
)

print(
    "========================================"
)

lap_elements = soup.select(
    "[data-laptime]"
)

print(
    "count:",
    len(lap_elements)
)


for index, element in enumerate(
    lap_elements,
    start=1
):

    print()
    print(
        "DATA-LAPTIME",
        index
    )

    print(
        "tag:",
        element.name
    )

    print(
        "class:",
        element.get(
            "class"
        )
    )

    print(
        "value:",
        element.get(
            "data-laptime"
        )
    )

    print(
        "text:",
        clean_text(
            element
        )
    )

    parent = element.parent

    if parent is not None:

        print(
            "parent tag:",
            parent.name
        )

        print(
            "parent class:",
            parent.get(
                "class"
            )
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
