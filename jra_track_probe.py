import re
import requests
from bs4 import BeautifulSoup


# =========================================================
# JRA 馬場情報ページ診断
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
    return re.sub(
        r"\s+",
        " ",
        value
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


def find_track_name(soup):
    title = ""

    if soup.title:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

    for track in [
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
    ]:
        if track in title:
            return track

    return ""


def find_dates(text):
    results = []

    patterns = [
        (
            r"(20\d{2})年"
            r"\s*(\d{1,2})月"
            r"\s*(\d{1,2})日"
        ),
        (
            r"(20\d{2})/"
            r"(\d{1,2})/"
            r"(\d{1,2})"
        ),
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text
        ):

            value = (
                f"{int(match.group(1)):04d}-"
                f"{int(match.group(2)):02d}-"
                f"{int(match.group(3)):02d}"
            )

            if value not in results:
                results.append(
                    value
                )

    return results


def contexts(
    text,
    keyword,
    width=220,
    limit=10
):
    results = []

    start = 0

    while True:

        index = text.find(
            keyword,
            start
        )

        if index < 0:
            break

        left = max(
            0,
            index - width
        )

        right = min(
            len(text),
            index + len(keyword) + width
        )

        value = clean_text(
            text[left:right]
        )

        if value not in results:
            results.append(
                value
            )

        if len(results) >= limit:
            break

        start = (
            index
            + len(keyword)
        )

    return results


def find_cushion_candidates(text):
    results = []

    for context in contexts(
        text,
        "クッション値",
        width=250,
        limit=15
    ):

        # -------------------------------------------------
        # 小数値だけを候補化
        #
        # 12 / 10 / 8 / 7 などの
        # 基準説明整数を除外する
        # -------------------------------------------------

        numbers = re.findall(
            r"(?<!\d)"
            r"(\d{1,2}\.\d)"
            r"(?!\d)",
            context
        )

        candidates = []

        for value in numbers:

            try:
                number = float(
                    value
                )
            except ValueError:
                continue

            # JRAクッション値として
            # 明らかに不自然な値を除外
            if not (
                5.0
                <= number
                <= 15.0
            ):
                continue

            if number not in candidates:
                candidates.append(
                    number
                )

        if candidates:

            results.append(
                {
                    "values":
                        candidates,

                    "context":
                        context,
                }
            )

    return results


def find_moisture_candidates(text):
    results = []

    # -----------------------------------------------------
    # HTMLテキストで確認できた実際の並び
    #
    # ゴール前 4コーナー
    # 芝 14.0 12.7
    # ダート 2.1 2.2
    # -----------------------------------------------------

    patterns = [
        (
            r"ゴール前"
            r"\s*4コーナー"
            r".{0,100}?"
            r"芝\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"ダート\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"(\d{1,2}(?:\.\d+)?)"
        ),

        (
            r"ゴール前と4コーナーの含水率"
            r".{0,150}?"
            r"ゴール前"
            r"\s*4コーナー"
            r".{0,100}?"
            r"芝\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"ダート\s*"
            r"(\d{1,2}(?:\.\d+)?)"
            r"\s*"
            r"(\d{1,2}(?:\.\d+)?)"
        ),
    ]

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.I
        ):

            candidate = {
                "turf_finish":
                    float(
                        match.group(1)
                    ),

                "turf_4corner":
                    float(
                        match.group(2)
                    ),

                "dirt_finish":
                    float(
                        match.group(3)
                    ),

                "dirt_4corner":
                    float(
                        match.group(4)
                    ),
            }

            if candidate not in results:
                results.append(
                    candidate
                )

    return results


def print_contexts(
    title,
    items
):
    print()
    print(
        "---",
        title,
        "---"
    )

    if not items:
        print(
            "NONE"
        )
        return

    for index, value in enumerate(
        items,
        start=1
    ):

        print()
        print(
            f"[{index}]"
        )

        print(
            value
        )


# =========================================================
# 実行
# =========================================================

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

    text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    track_name = find_track_name(
        soup
    )

    dates = find_dates(
        text
    )

    cushion_candidates = (
        find_cushion_candidates(
            text
        )
    )

    moisture_candidates = (
        find_moisture_candidates(
            text
        )
    )

    print(
        "TRACK:",
        track_name
    )

    print(
        "DATES:",
        dates[:10]
    )

    print()
    print(
        "--- CUSHION CANDIDATES ---"
    )

    if not cushion_candidates:

        print(
            "NONE"
        )

    else:

        for index, item in enumerate(
            cushion_candidates,
            start=1
        ):

            print()
            print(
                f"CANDIDATE {index}"
            )

            print(
                "VALUES:",
                item["values"]
            )

            print(
                "CONTEXT:",
                item["context"]
            )

    print()
    print(
        "--- MOISTURE CANDIDATES ---"
    )

    if not moisture_candidates:

        print(
            "NONE"
        )

    else:

        for index, item in enumerate(
            moisture_candidates,
            start=1
        ):

            print(
                f"CANDIDATE {index}:",
                item
            )

    # -----------------------------------------------------
    # 測定時刻周辺
    # -----------------------------------------------------

    measurement_contexts = contexts(
        text,
        "測定時刻",
        width=180,
        limit=5
    )

    print_contexts(
        "MEASUREMENT CONTEXT",
        measurement_contexts
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
