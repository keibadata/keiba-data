import json
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


# =========================================================
# Race ID
# =========================================================

DEFAULT_RACE_ID = "202605040502"


def load_race_id():
    env_race_id = os.environ.get(
        "RACE_ID",
        ""
    ).strip()

    if env_race_id:
        if not re.fullmatch(
            r"\d{12}",
            env_race_id
        ):
            raise ValueError(
                "環境変数 RACE_ID は"
                "12桁の数字で指定してください。"
            )

        print(
            "race id source: environment"
        )

        return env_race_id

    if os.path.exists(
        "race_id.txt"
    ):
        with open(
            "race_id.txt",
            "r",
            encoding="utf-8"
        ) as f:
            file_race_id = (
                f.read().strip()
            )

        if file_race_id:
            if not re.fullmatch(
                r"\d{12}",
                file_race_id
            ):
                raise ValueError(
                    "race_id.txt は"
                    "12桁の数字で指定してください。"
                )

            print(
                "race id source: race_id.txt"
            )

            return file_race_id

    if not re.fullmatch(
        r"\d{12}",
        DEFAULT_RACE_ID
    ):
        raise ValueError(
            "DEFAULT_RACE_ID が不正です。"
        )

    print(
        "race id source: default"
    )

    return DEFAULT_RACE_ID


RACE_ID = load_race_id()

URL = (
    "https://race.netkeiba.com/"
    f"race/shutuba.html?race_id={RACE_ID}"
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


print(
    "========================================"
)
print(
    "RACE COLLECTOR"
)
print(
    "========================================"
)
print(
    "Target Race ID:",
    RACE_ID
)
print(
    "URL:",
    URL
)


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


# =========================================================
# 共通
# =========================================================

def clean_text(element):
    if element is None:
        return ""

    return element.get_text(
        " ",
        strip=True
    )


def first_text(
    row,
    selectors
):
    for selector in selectors:
        element = row.select_one(
            selector
        )

        if element:
            text = clean_text(
                element
            )

            if text:
                return text

    return ""


# =========================================================
# レース条件
# =========================================================

def extract_race_condition(
    soup,
    race_id
):
    page_text = clean_text(
        soup
    )

    # -----------------------------------------------------
    # 開催日
    # -----------------------------------------------------

    race_date = ""

    date_texts = []

    date_selectors = [
        ".RaceData02",
        ".RaceData01",
        ".RaceData",
        ".RaceList_Date",
        ".RaceList_Data",
        ".RaceList_Item01",
        ".RaceList_Item02",
    ]

    for selector in date_selectors:
        for element in soup.select(
            selector
        ):
            text = clean_text(
                element
            )

            if text:
                date_texts.append(
                    text
                )

    date_texts.append(
        page_text
    )

    date_patterns = [
        (
            r"(20\d{2})年\s*"
            r"(\d{1,2})月\s*"
            r"(\d{1,2})日"
        ),
        (
            r"(20\d{2})/"
            r"(\d{1,2})/"
            r"(\d{1,2})"
        ),
        (
            r"(20\d{2})-"
            r"(\d{1,2})-"
            r"(\d{1,2})"
        ),
        (
            r"(20\d{2})\."
            r"(\d{1,2})\."
            r"(\d{1,2})"
        ),
    ]

    for text in date_texts:
        for pattern in date_patterns:
            match = re.search(
                pattern,
                text
            )

            if not match:
                continue

            try:
                race_date = datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3))
                ).strftime(
                    "%Y-%m-%d"
                )

            except (
                TypeError,
                ValueError
            ):
                race_date = ""

            if race_date:
                break

        if race_date:
            break

    # -----------------------------------------------------
    # 競馬場
    #
    # race_id の場コードを正とする。
    # HTML全文から競馬場を上書きしない。
    # -----------------------------------------------------

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

    track = ""

    if len(race_id) == 12:
        track_code = race_id[
            4:6
        ]

        track = jra_tracks.get(
            track_code,
            ""
        )

    # -----------------------------------------------------
    # レース名
    # -----------------------------------------------------

    race_name = first_text(
        soup,
        [
            ".RaceName",
            "h1.RaceName",
            ".RaceName_main",
        ]
    )

    race_name = re.sub(
        r"\s+",
        " ",
        race_name
    ).strip()

    # -----------------------------------------------------
    # レース条件専用テキスト
    #
    # page_text 全体は新馬判定には使わない。
    # -----------------------------------------------------

    race_header_texts = []

    header_selectors = [
        ".RaceName",
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
    ]

    for selector in header_selectors:
        for element in soup.select(
            selector
        ):
            text = clean_text(
                element
            )

            if text:
                race_header_texts.append(
                    text
                )

    race_header_text = " ".join(
        race_header_texts
    )

    race_header_text = re.sub(
        r"\s+",
        " ",
        race_header_text
    ).strip()

    # -----------------------------------------------------
    # クラス
    # -----------------------------------------------------

    race_class = ""

    class_patterns = [
        (
            "新馬",
            r"(?:新馬|メイクデビュー)"
        ),
        (
            "未勝利",
            r"未勝利"
        ),
        (
            "1勝クラス",
            r"(?:1勝クラス|500万下)"
        ),
        (
            "2勝クラス",
            r"(?:2勝クラス|1000万下)"
        ),
        (
            "3勝クラス",
            r"(?:3勝クラス|1600万下)"
        ),
        (
            "オープン",
            r"(?:オープン|OP)"
        ),
        (
            "リステッド",
            r"(?:リステッド|Listed|\(L\))"
        ),
        (
            "G3",
            r"(?:GIII|GⅢ|G3)"
        ),
        (
            "G2",
            r"(?:GII|GⅡ|G2)"
        ),
        (
            "G1",
            r"(?:GI|GⅠ|G1)"
        ),
    ]

    class_source = (
        race_name
        + " "
        + race_header_text
    )

    for label, pattern in class_patterns:
        if re.search(
            pattern,
            class_source,
            re.IGNORECASE
        ):
            race_class = label
            break

    # -----------------------------------------------------
    # 年齢条件
    # -----------------------------------------------------

    age_condition = ""

    age_patterns = [
        (
            "2歳",
            r"2歳"
        ),
        (
            "3歳",
            r"3歳"
        ),
        (
            "3歳以上",
            r"3歳以上"
        ),
        (
            "4歳以上",
            r"4歳以上"
        ),
    ]

    # 長い文字列を先に判定する
    age_patterns = [
        (
            "3歳以上",
            r"3歳以上"
        ),
        (
            "4歳以上",
            r"4歳以上"
        ),
        (
            "2歳",
            r"2歳"
        ),
        (
            "3歳",
            r"3歳"
        ),
    ]

    for label, pattern in age_patterns:
        if re.search(
            pattern,
            race_header_text
        ):
            age_condition = label
            break

    # -----------------------------------------------------
    # 新馬戦判定
    #
    # 過去走0件では判定しない。
    # ページ全文でも判定しない。
    # レース名・レース条件欄に
    # 新馬 / メイクデビュー が明示された場合のみ true。
    # -----------------------------------------------------

    debut_pattern = (
        r"(?:新馬|メイクデビュー)"
    )

    is_debut = bool(
        re.search(
            debut_pattern,
            class_source,
            re.IGNORECASE
        )
    )

    if is_debut:
        race_class = "新馬"

    # -----------------------------------------------------
    # 芝 / ダート / 障害・距離
    # -----------------------------------------------------

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
        for element in soup.select(
            selector
        ):
            text = clean_text(
                element
            )

            if text:
                race_data_texts.append(
                    text
                )

    race_data_texts.append(
        page_text
    )

    for text in race_data_texts:
        match = re.search(
            (
                r"芝\s*"
                r"([0-9]{3,4})\s*"
                r"[mｍ]?"
            ),
            text,
            re.IGNORECASE
        )

        if match:
            surface = "芝"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            (
                r"(?:ダート|ダ)\s*"
                r"([0-9]{3,4})\s*"
                r"[mｍ]?"
            ),
            text,
            re.IGNORECASE
        )

        if match:
            surface = "ダート"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            (
                r"障(?:害)?\s*"
                r"([0-9]{3,4})\s*"
                r"[mｍ]?"
            ),
            text,
            re.IGNORECASE
        )

        if match:
            surface = "障害"
            distance = int(
                match.group(1)
            )
            break

    # -----------------------------------------------------
    # 馬場状態
    # -----------------------------------------------------

    track_condition = ""

    condition_patterns = [
        (
            r"馬場\s*[:：]\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"芝\s*[:：]\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"ダート?\s*[:：]\s*"
            r"(良|稍重|重|不良)"
        ),
    ]

    for pattern in condition_patterns:
        match = re.search(
            pattern,
            page_text
        )

        if match:
            track_condition = (
                match.group(1)
            )
            break

    return {
        "race_date":
            race_date,

        "track":
            track,

        "race_name":
            race_name,

        "race_class":
            race_class,

        "age_condition":
            age_condition,

        "is_debut":
            is_debut,

        "surface":
            surface,

        "distance":
            distance,

        "track_condition":
            track_condition,
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

    patterns = [
        r"/horse/(\d+)",
        r"horse_id=(\d+)",
    ]

    for pattern in patterns:
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
        [
            "td",
            "div",
        ]
    )

    for cell in cells[:6]:
        value = clean_text(
            cell
        )

        if re.fullmatch(
            r"\d{1,2}",
            value
        ):
            number = int(
                value
            )

            if 1 <= number <= 18:
                return str(
                    number
                )

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
                (
                    r"(?<!\d)"
                    r"(\d{2}(?:\.\d)?)"
                    r"(?!\d)"
                ),
                text
            )

            for value in numbers:
                weight = float(
                    value
                )

                if (
                    40.0
                    <= weight
                    <= 65.0
                ):
                    return (
                        f"{weight:.1f}"
                    )

    jockey_element = (
        row.select_one(
            ".Jockey"
        )
        or row.select_one(
            'a[href*="/jockey/"]'
        )
    )

    if jockey_element:
        parent = (
            jockey_element.parent
        )

        for _ in range(3):
            if parent is None:
                break

            text = clean_text(
                parent
            )

            numbers = re.findall(
                (
                    r"(?<!\d)"
                    r"(\d{2}(?:\.\d)?)"
                    r"(?!\d)"
                ),
                text
            )

            for value in numbers:
                weight = float(
                    value
                )

                if (
                    40.0
                    <= weight
                    <= 65.0
                ):
                    return (
                        f"{weight:.1f}"
                    )

            parent = (
                parent.parent
            )

    row_text = clean_text(
        row
    )

    numbers = re.findall(
        (
            r"(?<!\d)"
            r"(\d{2}(?:\.\d)?)"
            r"(?!\d)"
        ),
        row_text
    )

    for value in numbers:
        weight = float(
            value
        )

        if (
            40.0
            <= weight
            <= 65.0
        ):
            return (
                f"{weight:.1f}"
            )

    return ""


def extract_body_weight(row):
    row_text = clean_text(
        row
    )

    match = re.search(
        (
            r"(\d{3})\s*"
            r"\(([+\-−]?\d+)\)"
        ),
        row_text
    )

    if not match:
        return "", ""

    weight = match.group(1)

    change = (
        match.group(2)
        .replace(
            "−",
            "-"
        )
    )

    if not change.startswith(
        (
            "+",
            "-",
        )
    ):
        if change != "0":
            change = (
                "+"
                + change
            )

    return (
        weight,
        change
    )


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
        return int(
            number
        )

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
            missing.append(
                key
            )

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


# =========================================================
# 必須レース情報の安全確認
# =========================================================

if not race_condition[
    "race_date"
]:
    raise RuntimeError(
        "開催日を取得できませんでした。"
    )

if not race_condition[
    "track"
]:
    raise RuntimeError(
        "競馬場を取得できませんでした。"
    )

if not race_condition[
    "surface"
]:
    raise RuntimeError(
        "芝・ダートを取得できませんでした。"
    )

if (
    race_condition[
        "distance"
    ]
    <= 0
):
    raise RuntimeError(
        "距離を取得できませんでした。"
    )


JST = timezone(
    timedelta(
        hours=9
    )
)


# =========================================================
# race.json
# =========================================================

data = {
    "race_id":
        RACE_ID,

    "race_date":
        race_condition[
            "race_date"
        ],

    "updated_at":
        datetime.now(
            JST
        ).isoformat(),

    "source":
        "netkeiba",

    "source_url":
        URL,

    "track":
        race_condition[
            "track"
        ],

    "racecourse":
        race_condition[
            "track"
        ],

    "race_name":
        race_condition[
            "race_name"
        ],

    "race_class":
        race_condition[
            "race_class"
        ],

    "age_condition":
        race_condition[
            "age_condition"
        ],

    "is_debut":
        race_condition[
            "is_debut"
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


# =========================================================
# 最終 Race ID 整合性確認
# =========================================================

if data["race_id"] != RACE_ID:
    raise RuntimeError(
        "内部Race ID不整合: "
        f"requested={RACE_ID} "
        f"collected={data['race_id']}"
    )


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


# =========================================================
# ログ
# =========================================================

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
    "race_date:",
    data["race_date"]
)

print(
    "track:",
    data["track"]
)

print(
    "race_name:",
    data["race_name"]
)

print(
    "race_class:",
    data["race_class"]
)

print(
    "age_condition:",
    data["age_condition"]
)

print(
    "is_debut:",
    data["is_debut"]
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
    data["track_condition"]
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
        print(
            warning
        )


print(
    "\n========================================"
)

print(
    "RACE COLLECTION FINISHED"
)

print(
    "========================================"
)
