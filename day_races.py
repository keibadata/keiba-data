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


def safe_int(value):
    try:
        return int(value)
    except (
        TypeError,
        ValueError
    ):
        return None


def safe_float(value):
    try:
        return float(value)
    except (
        TypeError,
        ValueError
    ):
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


target_race_number = int(
    race_id[-2:]
)

if not (
    1 <= target_race_number <= 12
):
    raise RuntimeError(
        f"対象R番号が不正です: "
        f"{target_race_number}"
    )


# =========================================================
# 対象レースより前だけ
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

    raise SystemExit(0)


# =========================================================
# race_id生成
# =========================================================

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

    page_text = clean_text(
        soup
    )

    surface = ""
    distance = 0

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

            text = clean_text(
                element
            )

            if text:
                texts.append(
                    text
                )

    texts.append(
        page_text
    )

    for text in texts:

        match = re.search(
            r"芝\s*(\d{3,4})\s*[mｍ]?",
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

    return (
        surface,
        distance,
        track_condition
    )


# =========================================================
# 着順結果テーブルを特定
# =========================================================

def is_real_result_row(row):
    """
    通常の着順結果行だけを通す。

    netkeibaには同じHorseListクラスを使った
    ラップ解析・走行位置解析等の別テーブルがあるため、
    Result_Num + Horse_Info + horseリンクの存在を必須にする。
    """

    result_cell = row.select_one(
        "td.Result_Num"
    )

    horse_cell = row.select_one(
        "td.Horse_Info"
    )

    horse_link = row.select_one(
        'td.Horse_Info a[href*="/horse/"]'
    )

    if result_cell is None:
        return False

    if horse_cell is None:
        return False

    if horse_link is None:
        return False

    result_text = clean_text(
        result_cell
    )

    if not re.fullmatch(
        r"\d+",
        result_text
    ):
        return False

    return True


# =========================================================
# コーナー通過順位
# =========================================================

def extract_corner_positions(row):
    """
    馬ごとの「通過」欄を取得する。

    例:
      2-2
      5-4
      10-9
      1-1-1-1

    数字だけの配列に変換する。
    """

    selectors = [
        ".PassageRate",
        ".Passage",
        ".Corner",
    ]

    for selector in selectors:

        element = row.select_one(
            selector
        )

        if element is None:
            continue

        text = clean_text(
            element
        )

        numbers = re.findall(
            r"\d+",
            text
        )

        if numbers:
            return [
                int(value)
                for value in numbers
            ]

    return []


# =========================================================
# 上がり3F
# =========================================================

def extract_last3f(row):

    selectors = [
        ".Last3F",
        "td.Last3F",
    ]

    for selector in selectors:

        element = row.select_one(
            selector
        )

        if element is None:
            continue

        text = clean_text(
            element
        )

        match = re.search(
            r"\d{2}\.\d",
            text
        )

        if match:
            return safe_float(
                match.group()
            )

    return None


# =========================================================
# レース全体ラップ
# =========================================================

def extract_race_laps(soup):

    candidates = []

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
                candidates.append(
                    text
                )

    for text in candidates:

        values = re.findall(
            r"(?<!\d)"
            r"(\d{1,2}\.\d)"
            r"(?!\d)",
            text
        )

        if len(values) >= 3:

            return [
                float(value)
                for value in values
            ]

    return []


# =========================================================
# 結果取得
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

            "results":
                [],
        }

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    (
        surface,
        distance,
        track_condition
    ) = extract_race_condition(
        soup
    )

    race_laps = extract_race_laps(
        soup
    )

    results = []

    # HorseListは複数テーブルに存在するので
    # 後段で厳密に通常結果行だけを選別
    rows = soup.select(
        "tr.HorseList"
    )

    for row in rows:

        if not is_real_result_row(
            row
        ):
            continue

        # -------------------------------------------------
        # 着順
        # -------------------------------------------------

        result_cell = row.select_one(
            "td.Result_Num"
        )

        finish_text = clean_text(
            result_cell
        )

        finish = safe_int(
            finish_text
        )

        if finish is None:
            continue

        # -------------------------------------------------
        # 馬番
        # -------------------------------------------------

        horse_number = None

        number_cell = (
            row.select_one(
                "td.Num"
            )
            or row.select_one(
                "td.Umaban"
            )
            or row.select_one(
                ".Umaban"
            )
        )

        if number_cell:

            match = re.search(
                r"\d+",
                clean_text(
                    number_cell
                )
            )

            if match:
                horse_number = (
                    int(
                        match.group()
                    )
                )

        # -------------------------------------------------
        # 馬名・horse_id
        # -------------------------------------------------

        horse_link = row.select_one(
            'td.Horse_Info '
            'a[href*="/horse/"]'
        )

        horse_name = clean_text(
            horse_link
        )

        horse_id = ""

        if horse_link:

            href = horse_link.get(
                "href",
                ""
            )

            match = re.search(
                r"/horse/(\d+)",
                href
            )

            if match:
                horse_id = (
                    match.group(1)
                )

        if not horse_name:
            continue

        # -------------------------------------------------
        # 通過順位
        # -------------------------------------------------

        corner_positions = (
            extract_corner_positions(
                row
            )
        )

        # -------------------------------------------------
        # 上がり
        # -------------------------------------------------

        last3f = extract_last3f(
            row
        )

        # -------------------------------------------------
        # 保存
        # -------------------------------------------------

        results.append(
            {
                "finish":
                    finish,

                "horse_number":
                    horse_number,

                "horse_id":
                    horse_id,

                "horse_name":
                    horse_name,

                "corner_positions":
                    corner_positions,

                "last3f":
                    last3f,
            }
        )

    # -----------------------------------------------------
    # 重複除去
    # -----------------------------------------------------

    unique_results = []
    seen = set()

    for item in results:

        key = (
            item.get(
                "finish"
            ),
            item.get(
                "horse_id"
            ),
            item.get(
                "horse_name"
            ),
        )

        if key in seen:
            continue

        seen.add(
            key
        )

        unique_results.append(
            item
        )

    results = unique_results

    # -----------------------------------------------------
    # 着順順
    # -----------------------------------------------------

    results.sort(
        key=lambda item:
            item.get(
                "finish",
                999
            )
    )

    # -----------------------------------------------------
    # 取得品質
    # -----------------------------------------------------

    if not surface:

        status = (
            "condition_parse_incomplete"
        )

    elif len(results) < 3:

        status = (
            "result_parse_incomplete"
        )

    else:

        status = "ok"

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

        "race_laps":
            race_laps,

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
        "result count:",
        result.get(
            "result_count",
            0
        )
    )

    print(
        "race laps:",
        result.get(
            "race_laps",
            []
        )
    )

    time.sleep(
        0.4
    )


# =========================================================
# 同一馬場
# =========================================================

same_surface_races = []

for item in collected_races:

    if (
        normalize_surface(
            item.get(
                "surface"
            )
        )
        != target_surface
    ):
        continue

    # 結果取得が壊れているレースは
    # バイアス判定対象にしない
    if item.get(
        "status"
    ) != "ok":
        continue

    same_surface_races.append(
        item.get(
            "race_number"
        )
    )


# =========================================================
# 最終安全確認
# =========================================================

for item in collected_races:

    item_race_number = int(
        item.get(
            "race_number",
            0
        )
        or 0
    )

    if (
        item_race_number
        >= target_race_number
    ):

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
    "same surface usable:",
    same_surface_races
)

print(
    "future race usage:",
    False
)

for item in collected_races:

    print()
    print(
        "R:",
        item.get(
            "race_number"
        )
    )

    print(
        "surface:",
        item.get(
            "surface"
        )
    )

    print(
        "status:",
        item.get(
            "status"
        )
    )

    print(
        "result_count:",
        item.get(
            "result_count",
            0
        )
    )

print()
print(
    "saved:",
    OUTPUT_FILE
)
