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

    return re.sub(
        r"\s+",
        " ",
        element.get_text(
            " ",
            strip=True
        )
    ).strip()


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


def to_float(value):

    try:
        return float(value)

    except (
        TypeError,
        ValueError
    ):
        return None


def to_int(value):

    try:
        return int(value)

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
    1
    <= target_race_number
    <= 12
):

    raise RuntimeError(
        f"対象R番号が不正です: {target_race_number}"
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
        "race_id": race_id,
        "race_date": race_date,
        "racecourse": racecourse,
        "surface": target_surface,
        "distance": target_distance,

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
        "saved:",
        OUTPUT_FILE
    )

    raise SystemExit(0)


# =========================================================
# race_id生成
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
# レース条件取得
# =========================================================

def parse_race_condition(
    soup
):

    surface = ""
    distance = 0
    track_condition = ""

    candidates = []

    for selector in [
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
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

    page_text = clean_text(
        soup
    )

    candidates.append(
        page_text
    )


    for text in candidates:

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


    for text in candidates:

        patterns = []

        if surface == "芝":

            patterns.extend(
                [
                    r"芝\s*[:：]\s*"
                    r"(良|稍重|重|不良)",

                    r"馬場\s*[:：]\s*"
                    r"(良|稍重|重|不良)",
                ]
            )

        elif surface == "ダート":

            patterns.extend(
                [
                    r"(?:ダート|ダ)\s*"
                    r"[:：]\s*"
                    r"(良|稍重|重|不良)",

                    r"馬場\s*[:：]\s*"
                    r"(良|稍重|重|不良)",
                ]
            )

        else:

            patterns.append(
                r"馬場\s*[:：]\s*"
                r"(良|稍重|重|不良)"
            )


        for pattern in patterns:

            match = re.search(
                pattern,
                text
            )

            if match:

                track_condition = (
                    match.group(1)
                )

                break

        if track_condition:
            break


    return (
        surface,
        distance,
        track_condition
    )


# =========================================================
# 正規の着順表取得
#
# Probeで確認済み：
#
# .Result_Num
# ↓
# 親tr
#
# Header行もResult_Numを持つので
# 「数字 + 着」のみ採用する。
# =========================================================

def parse_results(
    soup
):

    results = []

    seen_rows = set()


    for rank_element in soup.select(
        ".Result_Num"
    ):

        rank_text = clean_text(
            rank_element
        )

        rank_match = re.fullmatch(
            r"(\d+)\s*着",
            rank_text
        )

        if not rank_match:
            continue


        finish = int(
            rank_match.group(1)
        )


        row = rank_element.find_parent(
            "tr"
        )

        if row is None:
            continue


        row_key = id(
            row
        )

        if row_key in seen_rows:
            continue

        seen_rows.add(
            row_key
        )


        # -------------------------------------------------
        # 馬名・horse_id
        # -------------------------------------------------

        horse_link = (
            row.select_one(
                ".Horse_Info a"
            )
            or row.select_one(
                'a[href*="/horse/"]'
            )
        )


        if horse_link is None:
            continue


        horse_name = clean_text(
            horse_link
        )


        horse_id = ""

        href = str(
            horse_link.get(
                "href",
                ""
            )
        )


        horse_id_match = re.search(
            r"/horse/(\d+)",
            href
        )

        if horse_id_match:

            horse_id = (
                horse_id_match.group(1)
            )


        # -------------------------------------------------
        # 馬番
        # -------------------------------------------------

        horse_number = None


        number_element = (
            row.select_one(
                ".Umaban"
            )
            or row.select_one(
                ".Horse_Num"
            )
        )


        if number_element:

            number_match = re.search(
                r"\d+",
                clean_text(
                    number_element
                )
            )

            if number_match:

                horse_number = int(
                    number_match.group()
                )


        # 馬番専用classが取れない場合
        # Probeで確認した着順行の先頭構造から補完
        if horse_number is None:

            cells = row.find_all(
                "td",
                recursive=False
            )

            # Result_Numの次に枠番、
            # その次に馬番が置かれる構造を探索
            rank_cell_index = None

            for index, cell in enumerate(
                cells
            ):

                if rank_element in (
                    cell,
                    *cell.find_all(
                        True
                    )
                ):

                    rank_cell_index = index
                    break


            if rank_cell_index is not None:

                candidate_indexes = [
                    rank_cell_index + 2,
                    rank_cell_index + 1,
                ]

                for candidate_index in (
                    candidate_indexes
                ):

                    if (
                        0
                        <= candidate_index
                        < len(cells)
                    ):

                        candidate_text = clean_text(
                            cells[
                                candidate_index
                            ]
                        )

                        if re.fullmatch(
                            r"\d{1,2}",
                            candidate_text
                        ):

                            value = int(
                                candidate_text
                            )

                            if 1 <= value <= 18:

                                horse_number = value
                                break


        # -------------------------------------------------
        # 上がり3F
        #
        # Probe結果の行テキスト末尾にも
        # (33.3) のように存在する。
        # 専用class優先。
        # -------------------------------------------------

        last3f = None


        for selector in [
            ".Last3F",
            ".Last3f",
            ".Agari",
        ]:

            element = row.select_one(
                selector
            )

            if element:

                match = re.search(
                    r"(\d{2}\.\d)",
                    clean_text(
                        element
                    )
                )

                if match:

                    last3f = float(
                        match.group(1)
                    )

                    break


        if last3f is None:

            row_text = clean_text(
                row
            )

            matches = re.findall(
                r"\((\d{2}\.\d)\)",
                row_text
            )

            if matches:

                last3f = float(
                    matches[-1]
                )


        # -------------------------------------------------
        # 走破時計
        # -------------------------------------------------

        race_time = ""


        for selector in [
            ".Time",
            ".RaceTime",
        ]:

            element = row.select_one(
                selector
            )

            if element:

                text = clean_text(
                    element
                )

                match = re.search(
                    r"\d+:\d{2}\.\d",
                    text
                )

                if match:

                    race_time = (
                        match.group()
                    )

                    break


        if not race_time:

            row_text = clean_text(
                row
            )

            match = re.search(
                r"\d+:\d{2}\.\d",
                row_text
            )

            if match:

                race_time = (
                    match.group()
                )


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

                "last3f":
                    last3f,

                "race_time":
                    race_time,
            }
        )


    results.sort(
        key=lambda item:
            item.get(
                "finish",
                999
            )
    )


    return results


# =========================================================
# ラップ取得
#
# 重要：
# HorseListからは取得しない。
#
# data-laptimeを持つCellDataWrapを探し、
# PositionCellを含む「馬別ラップ」は除外。
#
# レース全体のラップ系列だけを候補にする。
# =========================================================

def parse_race_laps(
    soup,
    distance
):

    expected_count = 0

    if distance > 0:

        expected_count = (
            distance // 200
        )


    candidates = []


    # -----------------------------------------------------
    # ラップ系コンテナ候補
    # -----------------------------------------------------

    selectors = [
        ".Race_HaronTime",
        ".HaronTime",
        ".RaceData_Haron",
        "table.Race_HaronTime",
        "[class*='Haron']",
        "[class*='Lap']",
    ]


    containers = []

    seen_container = set()


    for selector in selectors:

        for container in soup.select(
            selector
        ):

            key = id(
                container
            )

            if key in seen_container:
                continue

            seen_container.add(
                key
            )

            containers.append(
                container
            )


    # -----------------------------------------------------
    # data-laptimeから取得
    # -----------------------------------------------------

    for container in containers:

        # 馬別ラップテーブルを除外
        if container.select_one(
            ".PositionCell"
        ):

            continue


        values = []


        for element in container.select(
            "[data-laptime]"
        ):

            raw = str(
                element.get(
                    "data-laptime",
                    ""
                )
            ).strip()


            if not re.fullmatch(
                r"\d{1,2}\.\d",
                raw
            ):

                continue


            value = float(
                raw
            )


            # 200m区間として異常値を除外
            if not (
                8.0
                <= value
                <= 20.0
            ):

                continue


            values.append(
                value
            )


        if values:

            candidates.append(
                values
            )


    # -----------------------------------------------------
    # data-laptime候補がない場合
    # テキストから取得
    # -----------------------------------------------------

    if not candidates:

        for container in containers:

            if container.select_one(
                ".PositionCell"
            ):

                continue


            text = clean_text(
                container
            )


            values = [
                float(value)
                for value in re.findall(
                    r"(?<!\d)"
                    r"(\d{1,2}\.\d)"
                    r"(?!\d)",
                    text
                )
            ]


            values = [
                value
                for value in values
                if (
                    8.0
                    <= value
                    <= 20.0
                )
            ]


            if values:

                candidates.append(
                    values
                )


    # -----------------------------------------------------
    # 距離から期待される区間数に
    # 最も近い候補を選ぶ
    # -----------------------------------------------------

    if not candidates:

        return []


    if expected_count > 0:

        exact = [
            values
            for values in candidates
            if len(values) == expected_count
        ]


        if exact:

            return exact[0]


        candidates.sort(
            key=lambda values:
                abs(
                    len(values)
                    - expected_count
                )
        )


    best = candidates[0]


    # 区間数より多い場合は
    # 推測で切り詰めず不明扱い
    if (
        expected_count > 0
        and len(best) != expected_count
    ):

        return []


    return best


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


    (
        surface,
        distance,
        track_condition
    ) = parse_race_condition(
        soup
    )


    results = parse_results(
        soup
    )


    race_laps = parse_race_laps(
        soup,
        distance
    )


    # -----------------------------------------------------
    # 状態
    # -----------------------------------------------------

    problems = []


    if not surface:

        problems.append(
            "surface"
        )


    if not distance:

        problems.append(
            "distance"
        )


    if not results:

        problems.append(
            "results"
        )


    if distance and not race_laps:

        problems.append(
            "race_laps"
        )


    if not problems:

        status = "ok"

    else:

        status = (
            "parse_incomplete"
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

        "race_laps":
            race_laps,

        "result_count":
            len(
                results
            ),

        "results":
            results,

        "parse_problems":
            problems,

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


    # 未来レース防止
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
        "race laps:",
        result.get(
            "race_laps",
            []
        )
    )

    print(
        "results:",
        result.get(
            "result_count",
            0
        )
    )

    print(
        "parse problems:",
        result.get(
            "parse_problems",
            []
        )
    )


    time.sleep(
        0.4
    )


# =========================================================
# 同馬場抽出
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
