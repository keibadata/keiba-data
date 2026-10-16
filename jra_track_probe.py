import re
import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

MOIST_URL = (
    "https://www.jra.go.jp/"
    "keiba/baba/_data_moist.html"
)

BABA_URL = (
    "https://www.jra.go.jp/"
    "keiba/baba/index.html"
)

TARGET_TRACK = "東京"
TARGET_DATE = "2026-10-12"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
    "Referer": BABA_URL,
}

TIMEOUT = 30


# ============================================================
# HTTP
# ============================================================

def get_html():

    response = requests.get(
        MOIST_URL,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in ["iso-8859-1", "ascii"]
    ):
        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


# ============================================================
# 日付候補
# ============================================================

def date_variants():

    year, month, day = TARGET_DATE.split("-")

    month_i = int(month)
    day_i = int(day)

    return [
        TARGET_DATE,
        TARGET_DATE.replace("-", "/"),
        f"{year}年{month_i}月{day_i}日",
        f"{month_i}月{day_i}日",
        f"{month_i}/{day_i}",
        f"{month_i:02d}/{day_i:02d}",
    ]


# ============================================================
# HTML取得
# ============================================================

print()
print("========================================")
print("JRA MOIST HTML PROBE")
print("========================================")

print("URL:", MOIST_URL)
print("TARGET TRACK:", TARGET_TRACK)
print("TARGET DATE:", TARGET_DATE)


try:

    html = get_html()

except Exception as exc:

    raise SystemExit(
        "ERROR: "
        + str(exc)
    )


print("HTML SIZE:", len(html))


# ============================================================
# HTML全体に何があるか
# ============================================================

soup = BeautifulSoup(
    html,
    "html.parser"
)


text = soup.get_text(
    " ",
    strip=True
)


print()
print("===== BASIC CHECK =====")

print(
    "東京 exists:",
    TARGET_TRACK in text
)


for value in date_variants():

    if value in text:

        print(
            "DATE MATCH:",
            value
        )


# ============================================================
# 東京を含む要素
# ============================================================

print()
print("===== TOKYO ELEMENTS =====")


tokyo_elements = []


for tag in soup.find_all(True):

    tag_text = tag.get_text(
        " ",
        strip=True
    )

    if TARGET_TRACK not in tag_text:
        continue

    # 巨大な親要素は除外
    if len(tag_text) > 5000:
        continue

    tokyo_elements.append(
        tag
    )


print(
    "TOKYO ELEMENT COUNT:",
    len(tokyo_elements)
)


for number, tag in enumerate(
    tokyo_elements[:10],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "TOKYO ELEMENT",
        number
    )

    print(
        "TAG:",
        tag.name
    )

    print(
        "ID:",
        tag.get("id")
    )

    print(
        "CLASS:",
        tag.get("class")
    )

    print(
        "TEXT:",
        tag.get_text(
            " ",
            strip=True
        )
    )

    print(
        "HTML:"
    )

    print(
        str(tag)[:5000]
    )


# ============================================================
# 10/12を含む要素
# ============================================================

print()
print("===== TARGET DATE ELEMENTS =====")


date_elements = []


for tag in soup.find_all(True):

    tag_text = tag.get_text(
        " ",
        strip=True
    )

    matched = False

    for value in date_variants():

        if value in tag_text:
            matched = True
            break

    if not matched:
        continue

    if len(tag_text) > 5000:
        continue

    date_elements.append(
        tag
    )


print(
    "DATE ELEMENT COUNT:",
    len(date_elements)
)


for number, tag in enumerate(
    date_elements[:10],
    start=1
):

    print()
    print(
        "----------------------------------------"
    )

    print(
        "DATE ELEMENT",
        number
    )

    print(
        "TAG:",
        tag.name
    )

    print(
        "ID:",
        tag.get("id")
    )

    print(
        "CLASS:",
        tag.get("class")
    )

    print(
        "TEXT:",
        tag.get_text(
            " ",
            strip=True
        )
    )

    print(
        "HTML:"
    )

    print(
        str(tag)[:5000]
    )


# ============================================================
# JSが利用している可能性の高いクラス・属性
# ============================================================

print()
print("===== STRUCTURE CANDIDATES =====")


keywords = [
    "moist",
    "turf",
    "dirt",
    "time",
    "gm",
    "c4",
]


found = 0


for tag in soup.find_all(True):

    attrs = str(
        tag.attrs
    ).lower()

    tag_html = str(
        tag
    ).lower()


    if not any(
        keyword in attrs
        or keyword in tag_html
        for keyword in keywords
    ):
        continue


    tag_text = tag.get_text(
        " ",
        strip=True
    )


    # 巨大ブロックを除外
    if len(tag_text) > 2500:
        continue


    found += 1


    print()
    print(
        "----------------------------------------"
    )

    print(
        "STRUCTURE",
        found
    )

    print(
        "TAG:",
        tag.name
    )

    print(
        "ID:",
        tag.get("id")
    )

    print(
        "CLASS:",
        tag.get("class")
    )

    print(
        "TEXT:",
        tag_text
    )

    print(
        "HTML:"
    )

    print(
        str(tag)[:3500]
    )


    if found >= 20:
        break


# ============================================================
# 生HTMLから東京周辺を直接抽出
# ============================================================

print()
print("===== RAW TOKYO CONTEXT =====")


positions = [
    match.start()
    for match in re.finditer(
        TARGET_TRACK,
        html
    )
]


print(
    "RAW TOKYO MATCH COUNT:",
    len(positions)
)


for number, position in enumerate(
    positions[:5],
    start=1
):

    start = max(
        0,
        position - 1500
    )

    end = min(
        len(html),
        position + 5000
    )


    print()
    print(
        "----------------------------------------"
    )

    print(
        "RAW TOKYO",
        number
    )

    print(
        html[start:end]
    )


# ============================================================
# 生HTMLから10/12周辺を直接抽出
# ============================================================

print()
print("===== RAW DATE CONTEXT =====")


raw_date_found = 0


for value in date_variants():

    positions = [
        match.start()
        for match in re.finditer(
            re.escape(value),
            html
        )
    ]


    for position in positions[:3]:

        raw_date_found += 1

        start = max(
            0,
            position - 1500
        )

        end = min(
            len(html),
            position + 5000
        )


        print()
        print(
            "----------------------------------------"
        )

        print(
            "DATE FORMAT:",
            value
        )

        print(
            html[start:end]
        )


if raw_date_found == 0:

    print(
        "RAW TARGET DATE NOT FOUND"
    )


print()
print("========================================")
print("PROBE FINISHED")
print("========================================")
