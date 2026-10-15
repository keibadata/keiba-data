import json
import os
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime, timezone, timedelta

DEFAULT_RACE_ID = "202605040502"
RACE_ID = os.environ.get("RACE_ID", DEFAULT_RACE_ID).strip()

if not re.fullmatch(r"\d{12}", RACE_ID):
    raise ValueError("RACE_IDは12桁の数字で指定してください。")

URL = f"https://race.netkeiba.com/race/shutuba.html?race_id={RACE_ID}"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)
response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


def clean_text(element):
    if element is None:
        return ""
    return element.get_text(" ", strip=True)


def first_text(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)

        if element:
            text = clean_text(element)

            if text:
                return text

    return ""


# =========================================================
# レース条件
# =========================================================

def extract_race_condition(soup, race_id):
    """
    出馬表ページから
    競馬場・芝/ダート・距離・馬場状態を取得。

    HTMLだけで取れない場合でも、
    JRAのrace_id構造から競馬場を補完する。
    """

    page_text = clean_text(soup)

    # -------------------------
    # 競馬場
    # -------------------------

    track = ""

    jra_tracks = {
        "01": "札幌",
        "02": "函館",
        "03": "福島",
        "04": "新潟",
        "05": "東京",
        "06": "中山",
        "07": "中京",
        "08": "京都",
        "09": "阪神",
        "10": "小倉",
    }

    # JRA race_id:
    # YYYY + 場コード2桁 + 開催回 + 開催日 + R
    if len(race_id) == 12:
        track_code = race_id[4:6]
        track = jra_tracks.get(
            track_code,
            ""
        )

    # HTML側に明確な競馬場名があれば確認
    for name in jra_tracks.values():
        if name in page_text:
            track = name
            break

    # -------------------------
    # 芝 / ダート / 障害
    # 距離
    # -------------------------

    surface = ""
    distance = 0

    race_data_texts = []

    selectors = [
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
        ".RaceName",
        ".RaceList_Item02",
    ]

    for selector in selectors:
        for element in soup.select(selector):
            text = clean_text(element)

            if text:
                race_data_texts.append(text)

    race_data_texts.append(page_text)

    for text in race_data_texts:

        # 芝1400m
        match = re.search(
            r"芝\s*([0-9]{3,4})\s*m?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "芝"
            distance = int(match.group(1))
            break

        # ダ1400m / ダート1400m
        match = re.search(
            r"(?:ダート|ダ)\s*([0-9]{3,4})\s*m?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "ダート"
            distance = int(match.group(1))
            break

        # 障害
        match = re.search(
            r"障(?:害)?\s*([0-9]{3,4})\s*m?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "障害"
            distance = int(match.group(1))
            break

    # -------------------------
    # 馬場状態
    # -------------------------

    track_condition = ""

    condition_patterns = [
        r"馬場\s*[:：]\s*(良|稍重|重|不良)",
        r"芝\s*[:：]\s*(良|稍重|重|不良)",
        r"ダート?\s*[:：]\s*(良|稍重|重|不良)",
    ]

    for pattern in condition_patterns:

        match = re.search(
            pattern,
            page_text
        )

        if match:
            track_condition = match.group(1)
            break

    return {
        "track": track,
        "surface": surface,
        "distance": distance,
        "track_condition": track_condition,
    }


race_condition = extract_race_condition(
    soup,
    RACE_ID
)


# =========================================================
# 出走馬
# =========================================================

def extract_horse_id(row):
    link = row.select_one(
        'a[href*="/horse/"]'
    )

    if not link:
        return ""

    href = link.get(
        "href",
        ""
    )

    for pattern in [
        r"/horse/(\d+)",
        r"horse_id=(\d+)",
    ]:
        match = re.search(
            pattern,
            href
        )

        if match:
            return match.group(1)

    return ""


def extract_horse_name(row):
    name = first_text(
        row,
        [
            ".HorseName a",
            ".HorseInfo .HorseName a",
            'a[href*="/horse/"]',
        ],
    )

    return re.sub(
        r"のデータベース$",
        "",
        name
    ).strip()


def extract_number(row):
    text = first_text(
        row,
        [
            ".Umaban",
            ".Horse_Num",
            "td.Umaban",
        ],
    )

    match = re.search(
        r"\d+",
        text
    )

    if match:
        return match.group()

    cells = row.find_all(
        ["td", "div"]
    )

    for cell in cells[:6]:

        value = clean_text(cell)

        if re.fullmatch(
            r"\d{1,2}",
            value
        ):
            number = int(value)

            if 1 <= number <= 18:
                return str(number)

    return ""


def extract_sex_age(row):
    text = first_text(
        row,
        [
            ".Barei",
            ".HorseInfo .Barei",
            ".SexAge",
        ],
    )

    match = re.search(
        r"[牡牝セ騸]\s*\d+",
        text
    )

    if not match:
        match = re.search(
            r"[牡牝セ騸]\s*\d+",
            clean_text(row)
        )

    if match:
        return re.sub(
            r"\s+",
            "",
            match.group()
        )

    return ""


def extract_jockey(row):
    text = first_text(
        row,
        [
            ".Jockey a",
            'a[href*="/jockey/"]',
            ".Jockey",
        ],
    )

    text = re.sub(
        r"\s+\d{2}(?:\.\d)?\s*$",
        "",
        text
    )

    return text.strip()


def extract_carried_weight(row):
    selectors = [
        ".Weight",
        ".BurdenWeight",
        ".Kinryo",
        ".JockeyWeight",
        "td.Weight",
    ]

    for selector in selectors:

        for element in row.select(
            selector
        ):

            text = clean_text(
                element
            )

            numbers = re.findall(
                r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)",
                text
            )

            for value in numbers:

                weight = float(value)

                if 40.0 <= weight <= 65.0:
                    return f"{weight:.1f}"

    jockey_element = (
        row.select_one(".Jockey")
        or row.select_one(
            'a[href*="/jockey/"]'
        )
    )

    if jockey_element:

        parent = jockey_element.parent

        for _ in range(3):

            if parent is None:
                break

            text = clean_text(
                parent
            )

            numbers = re.findall(
                r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)",
                text
            )

            for value in numbers:

                weight = float(value)

                if 40.0 <= weight <= 65.0:
                    return f"{weight:.1f}"

            parent = parent.parent

    row_text = clean_text(row)

    numbers = re.findall(
        r"(?<!\d)(\d{2}(?:\.\d)?)(?!\d)",
        row_text
    )

    for value in numbers:

        weight = float(value)

        if 40.0 <= weight <= 65.0:
            return f"{weight:.1f}"

    return ""


def extract_body_weight(row):
    row_text = clean_text(row)

    match = re.search(
        r"(\d{3})\s*\(([+\-−]?\d+)\)",
        row_text
    )

    if not match:
        return "", ""

    weight = match.group(1)

    change = (
        match.group(2)
        .replace("−", "-")
    )

    if not change.startswith(
        ("+", "-")
    ):
        if change != "0":
            change = "+" + change

    return weight, change


horses = []

for row in soup.select(
    ".HorseList"
):

    horse_name = extract_horse_name(
        row
    )

    if not horse_name:
        continue

    horse_number = extract_number(
        row
    )

    horse_id = extract_horse_id(
        row
    )

    sex_age = extract_sex_age(
        row
    )

    carried_weight = (
        extract_carried_weight(
            row
        )
    )

    jockey = extract_jockey(
        row
    )

    (
        body_weight,
        body_weight_change
    ) = extract_body_weight(
        row
    )

    horses.append(
        {
            "horse_number":
                horse_number,

            "horse_id":
                horse_id,

            "horse_name":
                horse_name,

            "sex_age":
                sex_age,

            "carried_weight":
                carried_weight,

            "jockey":
                jockey,

            "body_weight":
                body_weight,

            "body_weight_change":
                body_weight_change,
        }
    )


if not horses:
    raise RuntimeError(
        "出走馬を取得できませんでした。"
        "HTML構造またはレースIDを確認してください。"
    )


def horse_sort_key(horse):
    number = horse[
        "horse_number"
    ]

    if number.isdigit():
        return int(number)

    return 999


horses.sort(
    key=horse_sort_key
)


# =========================================================
# 検査
# =========================================================

warnings = []

for horse in horses:

    missing = []

    for key in [
        "horse_number",
        "horse_name",
        "sex_age",
        "carried_weight",
        "jockey",
        "body_weight",
    ]:

        if not horse[key]:
            missing.append(key)

    if missing:

        warnings.append(
            {
                "horse_number":
                    horse[
                        "horse_number"
                    ],

                "horse_name":
                    horse[
                        "horse_name"
                    ],

                "missing":
                    missing,
            }
        )


# レース条件は後続解析に必須
if not race_condition["track"]:
    raise RuntimeError(
        "競馬場を取得できませんでした。"
    )

if not race_condition["surface"]:
    raise RuntimeError(
        "芝・ダートを取得できませんでした。"
    )

if race_condition["distance"] <= 0:
    raise RuntimeError(
        "距離を取得できませんでした。"
    )


JST = timezone(
    timedelta(hours=9)
)


data = {
    "race_id":
        RACE_ID,

    "updated_at":
        datetime.now(
            JST
        ).isoformat(),

    "source":
        "netkeiba",

    "source_url":
        URL,

    # 後続処理で使用するレース条件
    "track":
        race_condition[
            "track"
        ],

    "surface":
        race_condition[
            "surface"
        ],

    "distance":
        race_condition[
            "distance"
        ],

    "track_condition":
        race_condition[
            "track_condition"
        ],

    "horse_count":
        len(horses),

    "warnings":
        warnings,

    "horses":
        horses,
}


with open(
    "race.json",
    "w",
    encoding="utf-8"
) as f:

    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )


print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)

print(
    "\n--- RACE CONDITION ---"
)

print(
    "race_id:",
    RACE_ID
)

print(
    "track:",
    data["track"]
)

print(
    "surface:",
    data["surface"]
)

print(
    "distance:",
    data["distance"]
)

print(
    "track_condition:",
    data[
        "track_condition"
    ]
)

print(
    "\n--- HORSES ---"
)

print(
    "horse_count:",
    len(horses)
)

for horse in horses:

    print(
        horse[
            "horse_number"
        ],
        horse[
            "horse_name"
        ],
        horse[
            "sex_age"
        ],
        horse[
            "carried_weight"
        ],
        horse[
            "jockey"
        ],
        horse[
            "body_weight"
        ],
        horse[
            "body_weight_change"
        ],
    )


if warnings:

    print(
        "\n--- WARNINGS ---"
    )

    for warning in warnings:
        print(warning)
