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


def clean_text(element):
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

target_distance = int(
    race.get(
        "distance",
        0
    )
    or 0
)


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


# JRA race_id 最後2桁 = R番号
target_race_number = int(
    race_id[-2:]
)

if not (
    1
    <= target_race_number
    <= 12
):
    raise RuntimeError(
        f"対象R番号が不正です: {target_race_number}"
    )


# =========================================================
# 重要
#
# 対象レースより前だけを使用する。
#
# 例：
# 対象1R → []
# 対象5R → [1,2,3,4]
# 対象11R → [1..10]
#
# 対象レース自身・未来レースは絶対に使用しない。
# =========================================================

eligible_race_numbers = list(
    range(
        1,
        target_race_number
    )
)


print(
    "===== DAY RACES ====="
)

print(
    "target race id:",
    race_id
)

print(
    "date:",
    race_date
)

print(
    "racecourse:",
    racecourse
)

print(
    "surface:",
    target_surface
)

print(
    "distance:",
    target_distance
)

print(
    "target race number:",
    target_race_number
)

print(
    "eligible previous races:",
    eligible_race_numbers
)


# =========================================================
# 1Rなら前レースなし
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

        "collected_race_count":
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
        "対象が1Rのため、"
        "同日前レースはありません。"
    )

    print(
        "future race usage: False"
    )

    print(
        "saved:",
        OUTPUT_FILE
    )

    raise SystemExit(0)


# =========================================================
# race_id を組み立てる
#
# 最後2桁だけR番号を変更する。
# =========================================================

race_id_prefix = race_id[:-2]


def build_race_id(
    race_number
):
    return (
        race_id_prefix
        + f"{race_number:02d}"
    )


# =========================================================
# レースページ取得
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

            "status":
                "fetch_error",

            "error":
                str(exc),

            "source_url":
                url,
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    page_text = clean_text(
        soup
    )

    # -----------------------------------------------------
    # レース条件
    # -----------------------------------------------------

    surface = ""
    distance = 0

    condition_texts = []

    for selector in [
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
        ".RaceName",
    ]:

        for element in soup.select(
            selector
        ):

            text = clean_text(
                element
            )

            if text:
                condition_texts.append(
                    text
                )

    condition_texts.append(
        page_text
    )

    for text in condition_texts:

        match = re.search(
            r"芝\s*"
            r"(\d{3,4})\s*[mｍ]?",
            text
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
            text
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
            text
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

    for pattern in [
        r"馬場\s*[:：]\s*"
        r"(良|稍重|重|不良)",

        r"芝\s*[:：]\s*"
        r"(良|稍重|重|不良)",

        r"ダート?\s*[:：]\s*"
        r"(良|稍重|重|不良)",
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

    # -----------------------------------------------------
    # ラップ
    # -----------------------------------------------------

    lap_times = []

    lap_candidates = []

    for selector in [
        ".Race_HaronTime",
        ".HaronTime",
        ".RaceData_Haron",
        "table.Race_HaronTime",
    ]:

        for element in soup.select(
            selector
        ):

            text = clean_text(
                element
            )

            if text:
                lap_candidates.append(
                    text
                )

    for text in lap_candidates:

        values = re.findall(
            r"\d{1,2}\.\d",
            text
        )

        if len(values) >= 3:
            lap_times = [
                float(value)
                for value in values
            ]
            break

    # -----------------------------------------------------
    # 結果馬
    # -----------------------------------------------------

    results = []

    result_rows = soup.select(
        "tr.HorseList"
    )

    if not result_rows:
        result_rows = soup.select(
            ".RaceTable01 tr"
        )

    for row in result_rows:

        text = clean_text(
            row
        )

        if not text:
            continue

        # 着順
        finish = ""

        finish_element = (
            row.select_one(
                ".Rank"
            )
            or row.select_one(
                ".Result_Num"
            )
        )

        if finish_element:

            match = re.search(
                r"\d+",
                clean_text(
                    finish_element
                )
            )

            if match:
                finish = match.group()

        # 馬番
        horse_number = ""

        number_element = (
            row.select_one(
                ".Umaban"
            )
            or row.select_one(
                ".Horse_Num"
            )
        )

        if number_element:

            match = re.search(
                r"\d+",
                clean_text(
                    number_element
                )
            )

            if match:
                horse_number = (
                    match.group()
                )

        # 馬名
        horse_name = ""

        horse_element = (
            row.select_one(
                ".Horse_Name a"
            )
            or row.select_one(
                ".HorseName a"
            )
            or row.select_one(
                'a[href*="/horse/"]'
            )
        )

        if horse_element:
            horse_name = clean_text(
                horse_element
            )

        if not horse_name:
            continue

        # 通過順位
        corner = ""

        corner_element = (
            row.select_one(
                ".PassageRate"
            )
            or row.select_one(
                ".Passage"
            )
        )

        if corner_element:
            corner = clean_text(
                corner_element
            )

        # 上がり
        last3f = None

        last_element = (
            row.select_one(
                ".Last3F"
            )
            or row.select_one(
                ".Time"
            )
        )

        if last_element:

            values = re.findall(
                r"\d{2}\.\d",
                clean_text(
                    last_element
                )
            )

            if values:

                try:
                    last3f = float(
                        values[-1]
                    )
                except ValueError:
                    last3f = None

        results.append(
            {
                "finish":
                    finish,

                "horse_number":
                    horse_number,

                "horse_name":
                    horse_name,

                "corner":
                    corner,

                "last3f":
                    last3f,
            }
        )

    # -----------------------------------------------------
    # 取得判定
    # -----------------------------------------------------

    status = "ok"

    if not surface:
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
            surface,

        "distance":
            distance,

        "track_condition":
            track_condition,

        "lap_times":
            lap_times,

        "result_count":
            len(results),

        "results":
            results,

        "status":
            status,
    }


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

    # 安全確認
    if (
        int(
            previous_race_id[-2:]
        )
        >= target_race_number
    ):
        raise RuntimeError(
            "未来レース混入防止チェックに失敗しました。"
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
        "results:",
        result.get(
            "result_count",
            0
        )
    )

    # サーバー負荷回避
    time.sleep(
        0.4
    )


# =========================================================
# 同じ馬場のみを識別
#
# 芝対象 → 芝だけ
# ダート対象 → ダートだけ
#
# ただし収集データ自体は全前レースを保存する。
# =========================================================

same_surface_races = []

for item in collected_races:

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

    race_number = int(
        item.get(
            "race_number",
            0
        )
        or 0
    )

    if race_number >= target_race_number:

        raise RuntimeError(
            "対象レース以降のデータが"
            "day_races.json に混入しています。"
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
        (
            "collected"
            if collected_races
            else "no_previous_races"
        ),

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
