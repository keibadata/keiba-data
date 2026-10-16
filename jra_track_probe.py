import re
import requests
from bs4 import BeautifulSoup


# =========================================================
# JRA クッション値 HTML構造診断
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


def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def fetch_page(url):
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


def detect_track(soup):
    title = ""

    if soup.title:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

    tracks = [
        "東京",
        "京都",
        "新潟",
        "中山",
        "阪神",
        "中京",
        "札幌",
        "函館",
        "福島",
        "小倉",
    ]

    for track in tracks:
        if track in title:
            return track

    return ""


def print_tag_info(
    label,
    element
):
    print()
    print(
        "-----",
        label,
        "-----"
    )

    if element is None:
        print(
            "NONE"
        )
        return

    print(
        "TAG:",
        element.name
    )

    print(
        "CLASS:",
        element.get(
            "class",
            []
        )
    )

    print(
        "ID:",
        element.get(
            "id",
            ""
        )
    )

    print(
        "TEXT:"
    )

    print(
        clean_text(
            element.get_text(
                " ",
                strip=True
            )
        )[:3000]
    )

    print(
        "HTML:"
    )

    print(
        str(element)[:5000]
    )


def relevant_cushion_elements(
    soup
):
    results = []

    for element in soup.find_all(
        string=re.compile(
            "クッション値"
        )
    ):

        parent = element.parent

        if parent is None:
            continue

        text = clean_text(
            parent.get_text(
                " ",
                strip=True
            )
        )

        # -------------------------------------------------
        # 基礎知識・説明リンクをなるべく除外
        # -------------------------------------------------

        if (
            "基礎知識"
            in text
            and len(text) < 100
        ):
            continue

        results.append(
            parent
        )

    return results


# =========================================================
# 実行
# =========================================================

for page_name, url in PAGES.items():

    print()
    print(
        "=" * 80
    )

    print(
        "PAGE:",
        page_name
    )

    print(
        "URL:",
        url
    )

    try:

        html = fetch_page(
            url
        )

    except Exception as e:

        print(
            "FETCH ERROR:",
            repr(e)
        )

        continue

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    track = detect_track(
        soup
    )

    print(
        "TRACK:",
        track
    )

    matches = (
        relevant_cushion_elements(
            soup
        )
    )

    print(
        "CUSHION TEXT MATCHES:",
        len(matches)
    )

    if not matches:

        print(
            "NO CUSHION ELEMENT"
        )

        continue

    for index, element in enumerate(
        matches[:10],
        start=1
    ):

        print()
        print(
            "#" * 80
        )

        print(
            "MATCH:",
            index
        )

        print_tag_info(
            "MATCH ELEMENT",
            element
        )

        # ================================================
        # 親を最大5階層確認
        # ================================================

        parent = element

        for level in range(
            1,
            6
        ):

            parent = (
                parent.parent
                if parent
                else None
            )

            if parent is None:
                break

            print_tag_info(
                f"PARENT LEVEL {level}",
                parent
            )

        # ================================================
        # 直近の前後兄弟
        # ================================================

        previous_element = (
            element.find_previous_sibling()
        )

        next_element = (
            element.find_next_sibling()
        )

        print_tag_info(
            "PREVIOUS SIBLING",
            previous_element
        )

        print_tag_info(
            "NEXT SIBLING",
            next_element
        )

        # ================================================
        # 近くのtable
        # ================================================

        table = element.find_parent(
            "table"
        )

        print_tag_info(
            "PARENT TABLE",
            table
        )

        # ================================================
        # 近くのsection/div
        # ================================================

        container = (
            element.find_parent(
                "section"
            )
            or element.find_parent(
                "div"
            )
        )

        print_tag_info(
            "NEAREST CONTAINER",
            container
        )


print()
print(
    "=" * 80
)

print(
    "JRA CUSHION HTML PROBE FINISHED"
)

print(
    "=" * 80
)
