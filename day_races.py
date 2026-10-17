import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

RACE_FILE = "race.json"
OUTPUT_FILE = "day_races.json"

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

JST = timezone(
    timedelta(hours=9)
)


# =========================================================
# 共通
# =========================================================

def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def text_of(element):
    if element is None:
        return ""

    return element.get_text(
        " ",
        strip=True
    )


def normalize_surface(value):
    value = str(
        value or ""
    ).strip()

    if value.startswith("芝"):
        return "芝"

    if (
        value.startswith("ダ")
        or "ダート" in value
    ):
        return "ダート"

    if value.startswith("障"):
        return "障害"

    return value


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# =========================================================
# race.json
# =========================================================

if not os.path.exists(
    RACE_FILE
):
    raise RuntimeError(
        "race.json がありません。"
    )


race = load_json(
    RACE_FILE
)

race_id = str(
    race.get(
        "race_id",
        ""
    )
).strip()

race_date = str(
    race.get(
        "race_date",
        ""
    )
).strip()

racecourse = str(
    race.get(
        "racecourse",
        race.get(
            "track",
            ""
        )
    )
).strip()

target_surface = normalize_surface(
    race.get(
        "surface",
        ""
    )
)

target_distance = safe_int(
    race.get(
        "distance"
    )
) or 0


# =========================================================
# race_id 検査
# =========================================================

if not re.fullmatch(
    r"\d{12}",
    race_id
):
    raise RuntimeError(
        "race.json の race_id が不正です。"
    )


if not race_date:
    raise RuntimeError(
        "race.json に race_date がありません。"
    )


if not racecourse:
    raise RuntimeError(
        "race.json に競馬場がありません。"
    )


if not target_surface:
    raise RuntimeError(
        "race.json にsurfaceがありません。"
    )


target_race_number = int(
    race_id[-2:]
)

if not (
    1 <= target_race_number <= 12
):
    raise RuntimeError(
        f"対象R番号が不正です: {target_race_number}"
    )


# =========================================================
# 対象より前のRだけ
# =========================================================

eligible_race_numbers = list(
    range(
        1,
        target_race_number
    )
)

race_id_prefix = race_id[:-2]


def build_race_id(race_number):
    return (
        race_id_prefix
        + f"{race_number:02d}"
    )


# =========================================================
# レース条件取得
# =========================================================

def extract_race_condition(soup):

    page_text = text_of(
        soup
    )

    surface = ""
    distance = 0
    track_condition = ""

    texts = []

    for selector in [
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
        ".RaceName",
    ]:

        for element in soup.select(
            selector
        ):
            value = text_of(
                element
            )

            if value:
                texts.append(
                    value
                )

    texts.append(
        page_text
    )

    for value in texts:

        match = re.search(
            r"芝\s*(\d{3,4})\s*[mｍ]?",
            value
        )

        if match:
            surface = "芝"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            r"(?:ダート|ダ)\s*"
            r"(\d{3,4})\s*[mｍ]?",
            value
        )

        if match:
            surface = "ダート"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            r"障(?:害)?\s*"
            r"(\d{3,4})\s*[mｍ]?",
            value
        )

        if match:
            surface = "障害"
            distance = int(
                match.group(1)
            )
            break

    for pattern in [
        r"馬場\s*[:：]\s*(良|稍重|重|不良)",
        r"芝\s*[:：]\s*(良|稍重|重|不良)",
        r"ダート?\s*[:：]\s*(良|稍重|重|不良)",
    ]:

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
        "surface":
            normalize_surface(
                surface
            ),

        "distance":
            distance,

        "track_condition":
            track_condition,
    }


# =========================================================
# 馬名取得
# =========================================================

def extract_horse_name(row):

    selectors = [
        ".Horse_Info.Horse_Link a",
        ".Horse_Info a",
        ".HorseName a",
        ".Horse_Name a",
        'a[href*="/horse/"]',
    ]

    for selector in selectors:

        element = row.select_one(
            selector
        )

        if element:

            name = text_of(
                element
            )

            if name:
                return name

    return ""


# =========================================================
# 着順取得
# =========================================================

def extract_finish(row):

    element = row.select_one(
        ".Result_Num"
    )

    if element is None:
        return None

    match = re.search(
        r"\d+",
        text_of(
            element
        )
    )

    if not match:
        return None

    return safe_int(
        match.group()
    )


# =========================================================
# 馬番取得
#
# Probeで確認した実HTML:
# <td class="Num Waku2 Sticky">2</td>
#
# このセルは今回のProbe上では馬を識別する番号として
# 使用可能だが、枠/馬番の構造差に備えて生値も保持する。
# =========================================================

def extract_number(row):

    element = row.select_one(
        "td.Num"
    )

    if element is None:
        return None

    match = re.search(
        r"\d+",
        text_of(
            element
        )
    )

    if not match:
        return None

    return safe_int(
        match.group()
    )


# =========================================================
# PositionCell取得
#
# Probeで実HTML確認済み:
#
# <td class="PositionCell"
#     data-position="2">2</td>
# =========================================================

def extract_positions(row):

    positions = []

    for cell in row.select(
        ".PositionCell[data-position]"
    ):

        raw = cell.get(
            "data-position",
            ""
        )

        position = safe_int(
            raw
        )

        if position is None:
            continue

        positions.append(
            position
        )

    return positions


# =========================================================
# 区間ラップ取得
#
# Probeで実HTML確認済み:
#
# <td class="CellDataWrap"
#     data-laptime="13.2">13.2</td>
# =========================================================

def extract_lap_times(row):

    laps = []

    for cell in row.select(
        ".CellDataWrap[data-laptime]"
    ):

        raw = cell.get(
            "data-laptime",
            ""
        )

        value = safe_float(
            raw
        )

        if value is None:
            continue

        laps.append(
            value
        )

    return laps


# =========================================================
# HorseListを用途別に分類
#
# 同じ馬が複数HorseListに存在するため、
# 全HorseListを結果馬として扱わない。
# =========================================================

def classify_horse_row(row):

    has_result = (
        row.select_one(
            ".Result_Num"
        )
        is not None
    )

    has_horse = bool(
        extract_horse_name(
            row
        )
    )

    has_lap = (
        row.select_one(
            ".CellDataWrap[data-laptime]"
        )
        is not None
    )

    has_position = (
        row.select_one(
            ".PositionCell[data-position]"
        )
        is not None
    )

    has_running_time = (
        row.select_one(
            ".RunningTimeCell"
        )
        is not None
    )

    has_mileage = (
        row.select_one(
            ".MilagesCell"
        )
        is not None
    )

    if not (
        has_result
        and has_horse
    ):
        return "other"

    if has_lap and has_position:
        return "lap_position"

    if (
        has_running_time
        or has_mileage
    ):
        return "running_time"

    return "other_result"


# =========================================================
# 位置取りから簡易脚質
#
# これは「能力評価」ではない。
# 当日バイアス判定用の観測分類。
# =========================================================

def classify_running_style(
    positions
):

    if not positions:
        return ""

    first_position = positions[0]

    if first_position == 1:
        return "逃げ"

    if first_position <= 4:
        return "先行"

    if first_position <= 9:
        return "中団"

    return "後方"


# =========================================================
# 1レース取得
# =========================================================

def fetch_race_result(
    previous_race_id,
    race_number
):

    url = (
        "https://race.netkeiba.com/"
        "race/result.html"
        f"?race_id={previous_race_id}"
    )

    try:

        response = requests.get(
            url,
            headers=HEADERS,
            timeout=30
        )

        response.raise_for_status()

        response.encoding = (
            response.apparent_encoding
        )

    except Exception as exc:

        return {
            "race_id":
                previous_race_id,

            "race_number":
                race_number,

            "source_url":
                url,

            "status":
                "fetch_error",

            "error":
                str(exc),

            "surface":
                "",

            "distance":
                0,

            "track_condition":
                "",

            "result_count":
                0,

            "results":
                [],
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    condition = extract_race_condition(
        soup
    )

    # -----------------------------------------------------
    # 同一馬を統合
    # -----------------------------------------------------

    horses = {}

    for row in soup.select(
        "tr.HorseList"
    ):

        row_type = classify_horse_row(
            row
        )

        if row_type == "other":
            continue

        finish = extract_finish(
            row
        )

        horse_name = extract_horse_name(
            row
        )

        if (
            finish is None
            or not horse_name
        ):
            continue

        number = extract_number(
            row
        )

        # 同一馬統合キー
        key = (
            finish,
            horse_name
        )

        if key not in horses:

            horses[key] = {
                "finish":
                    finish,

                "horse_number":
                    number,

                "horse_name":
                    horse_name,

                "positions":
                    [],

                "section_laps":
                    [],

                "running_style":
                    "",

                "source_row_types":
                    [],
            }

        item = horses[key]

        if (
            item["horse_number"]
            is None
            and number is not None
        ):
            item[
                "horse_number"
            ] = number

        if (
            row_type
            not in item[
                "source_row_types"
            ]
        ):
            item[
                "source_row_types"
            ].append(
                row_type
            )

        positions = extract_positions(
            row
        )

        laps = extract_lap_times(
            row
        )

        # PositionCellが最も多い行を採用
        if (
            len(positions)
            > len(
                item["positions"]
            )
        ):
            item[
                "positions"
            ] = positions

        # data-laptime付きだけ採用
        if (
            len(laps)
            > len(
                item["section_laps"]
            )
        ):
            item[
                "section_laps"
            ] = laps

    # -----------------------------------------------------
    # 最終整形
    # -----------------------------------------------------

    results = []

    for item in horses.values():

        item[
            "running_style"
        ] = classify_running_style(
            item[
                "positions"
            ]
        )

        results.append(
            item
        )

    results.sort(
        key=lambda x: (
            x.get(
                "finish"
            )
            if x.get(
                "finish"
            )
            is not None
            else 999
        )
    )

    status = "ok"

    if not condition[
        "surface"
    ]:
        status = (
            "condition_parse_incomplete"
        )

    if not results:
        status = (
            "result_parse_incomplete"
        )

    return {
        "race_id":
            previous_race_id,

        "race_number":
            race_number,

        "source_url":
            url,

        "surface":
            condition[
                "surface"
            ],

        "distance":
            condition[
                "distance"
            ],

        "track_condition":
            condition[
                "track_condition"
            ],

        "result_count":
            len(
                results
            ),

        "results":
            results,

        "status":
            status,
    }


# =========================================================
# 1R
# =========================================================

if not eligible_race_numbers:

    output = {
        "race_id":
            race_id,

        "race_date":
            race_date,

        "racecourse":
            racecourse,

        "surface":
            target_surface,

        "distance":
            target_distance,

        "target_race_number":
            target_race_number,

        "future_race_usage":
            False,

        "status":
            "no_previous_races",

        "eligible_race_numbers":
            [],

        "same_surface_race_numbers":
            [],

        "collected_race_count":
            0,

        "same_surface_race_count":
            0,

        "collected_races":
            [],

        "updated_at":
            datetime.now(
                JST
            ).isoformat(),
    }

    save_json(
        OUTPUT_FILE,
        output
    )

    print(
        "対象が1Rのため前レースなし"
    )

    print(
        "future race usage: False"
    )

    raise SystemExit(0)


# =========================================================
# 前レース収集
# =========================================================

collected_races = []

for race_number in (
    eligible_race_numbers
):

    previous_race_id = (
        build_race_id(
            race_number
        )
    )

    # 未来データ防止
    if (
        int(
            previous_race_id[-2:]
        )
        >= target_race_number
    ):
        raise RuntimeError(
            "未来レース混入防止チェック失敗"
        )

    print()
    print(
        "collect:",
        previous_race_id
    )

    result = fetch_race_result(
        previous_race_id,
        race_number
    )

    collected_races.append(
        result
    )

    print(
        "status:",
        result.get(
            "status"
        )
    )

    print(
        "surface:",
        result.get(
            "surface"
        )
    )

    print(
        "distance:",
        result.get(
            "distance"
        )
    )

    print(
        "result count:",
        result.get(
            "result_count"
        )
    )

    # 先頭3頭だけログ確認
    for horse in result.get(
        "results",
        []
    )[:3]:

        print(
            " ",
            horse.get(
                "finish"
            ),
            horse.get(
                "horse_name"
            ),
            "positions=",
            horse.get(
                "positions"
            ),
            "style=",
            horse.get(
                "running_style"
            ),
            "laps=",
            horse.get(
                "section_laps"
            ),
        )

    time.sleep(
        0.4
    )


# =========================================================
# 同馬場レース
# =========================================================

same_surface_races = []

for item in collected_races:

    if (
        item.get(
            "status"
        )
        != "ok"
    ):
        continue

    if (
        normalize_surface(
            item.get(
                "surface"
            )
        )
        == target_surface
    ):

        same_surface_races.append(
            item.get(
                "race_number"
            )
        )


# =========================================================
# 最終安全確認
# =========================================================

for item in collected_races:

    race_number = safe_int(
        item.get(
            "race_number"
        )
    )

    if race_number is None:
        continue

    if (
        race_number
        >= target_race_number
    ):
        raise RuntimeError(
            "対象レース以降のデータが"
            "混入しています。"
        )


# =========================================================
# 保存
# =========================================================

output = {
    "race_id":
        race_id,

    "race_date":
        race_date,

    "racecourse":
        racecourse,

    "surface":
        target_surface,

    "distance":
        target_distance,

    "target_race_number":
        target_race_number,

    "future_race_usage":
        False,

    "status":
        "collected",

    "eligible_race_numbers":
        eligible_race_numbers,

    "same_surface_race_numbers":
        same_surface_races,

    "collected_race_count":
        len(
            collected_races
        ),

    "same_surface_race_count":
        len(
            same_surface_races
        ),

    "collected_races":
        collected_races,

    "updated_at":
        datetime.now(
            JST
        ).isoformat(),
}


save_json(
    OUTPUT_FILE,
    output
)


# =========================================================
# ログ
# =========================================================

print()
print(
    "===== DAY RACES RESULT ====="
)

print(
    "target race:",
    target_race_number
)

print(
    "eligible:",
    eligible_race_numbers
)

print(
    "collected:",
    len(
        collected_races
    )
)

print(
    "same surface:",
    same_surface_races
)

print(
    "future race usage:",
    False
)

print(
    "saved:",
    OUTPUT_FILE
)
