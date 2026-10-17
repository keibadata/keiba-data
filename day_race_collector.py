import json
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
OUTPUT_FILE = "day_races.json"

TIMEOUT = 20

JST = timezone(
    timedelta(hours=9)
)

NETKEIBA_BASE = (
    "https://race.netkeiba.com"
)


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {}


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


def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def to_int(value):
    if value is None:
        return None

    match = re.search(
        r"\d+",
        str(value)
    )

    if not match:
        return None

    try:
        return int(
            match.group()
        )
    except Exception:
        return None


def get_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) "
            "Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language":
            "ja,en-US;q=0.8,en;q=0.6",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in [
            "iso-8859-1",
            "ascii"
        ]
    ):
        response.encoding = (
            response.apparent_encoding
        )

    return response.text


# ============================================================
# race_id
#
# JRA/netkeiba形式
#
# YYYY TT KK DD RR
#
# 2026 05 04 05 01
#       ↑東京
#                ↑1R
# ============================================================

def split_race_id(race_id):
    race_id = clean_text(
        race_id
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        return None

    return {
        "year": race_id[0:4],
        "track_code": race_id[4:6],
        "meeting": race_id[6:8],
        "day": race_id[8:10],
        "race_number": int(
            race_id[10:12]
        ),
        "prefix": race_id[:10]
    }


def build_race_id(
    target_race_id,
    race_number
):
    info = split_race_id(
        target_race_id
    )

    if not info:
        return ""

    return (
        info["prefix"]
        + f"{race_number:02d}"
    )


# ============================================================
# race.json
# ============================================================

race = load_json(
    RACE_FILE
)

if not race:
    raise SystemExit(
        "ERROR: race.json がありません"
    )


race_id = clean_text(
    race.get("race_id")
)

race_date = clean_text(
    race.get("race_date")
    or race.get("date")
)

racecourse = clean_text(
    race.get("racecourse")
    or race.get("track")
)

target_surface = clean_text(
    race.get("surface")
)

target_distance = race.get(
    "distance"
)


race_info = split_race_id(
    race_id
)

if not race_info:
    raise SystemExit(
        "ERROR: race_id が12桁ではありません"
    )


target_race_number = (
    race_info["race_number"]
)


# ============================================================
# 対象レースより前だけ
# ============================================================

eligible_numbers = list(
    range(
        1,
        target_race_number
    )
)


print()
print(
    "===== DAY RACE COLLECTOR ====="
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
    "target surface:",
    target_surface
)

print(
    "target distance:",
    target_distance
)

print(
    "target race number:",
    target_race_number
)

print(
    "eligible previous races:",
    eligible_numbers
)

print()


# ============================================================
# レース基本情報抽出
# ============================================================

def extract_race_info(
    html,
    previous_race_id,
    race_number
):
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

    # --------------------------------------------------------
    # レース名
    # --------------------------------------------------------

    race_name = ""

    selectors = [
        ".RaceName",
        ".RaceName_main",
        "h1",
    ]

    for selector in selectors:
        element = soup.select_one(
            selector
        )

        if element:
            candidate = clean_text(
                element.get_text(
                    " ",
                    strip=True
                )
            )

            if candidate:
                race_name = candidate
                break

    # --------------------------------------------------------
    # 芝 / ダート
    # --------------------------------------------------------

    surface = ""

    if re.search(
        r"ダ(?:ート)?\s*\d{3,4}m",
        text
    ):
        surface = "ダート"

    elif re.search(
        r"芝\s*\d{3,4}m",
        text
    ):
        surface = "芝"

    # --------------------------------------------------------
    # 距離
    # --------------------------------------------------------

    distance = None

    patterns = []

    if surface == "ダート":
        patterns = [
            r"ダ(?:ート)?\s*(\d{3,4})m"
        ]

    elif surface == "芝":
        patterns = [
            r"芝\s*(\d{3,4})m"
        ]

    else:
        patterns = [
            r"(?:芝|ダ(?:ート)?)\s*(\d{3,4})m"
        ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text
        )

        if match:
            distance = int(
                match.group(1)
            )
            break

    # --------------------------------------------------------
    # 馬場状態
    # --------------------------------------------------------

    track_condition = ""

    condition_patterns = [
        r"馬場\s*:\s*(良|稍重|重|不良)",
        r"馬場\s*(良|稍重|重|不良)",
        r"(?:芝|ダート)\s*:\s*(良|稍重|重|不良)",
    ]

    for pattern in condition_patterns:
        match = re.search(
            pattern,
            text
        )

        if match:
            track_condition = (
                match.group(1)
            )
            break

    # --------------------------------------------------------
    # 確定済み判定
    #
    # 着順表が存在することを優先
    # --------------------------------------------------------

    result_rows = []

    result_selectors = [
        "table.RaceTable01 tr",
        "table.race_table_01 tr",
        ".RaceTable01 tr",
    ]

    for selector in result_selectors:
        rows = soup.select(
            selector
        )

        if len(rows) > 1:
            result_rows = rows
            break

    finished = (
        len(result_rows) > 1
    )

    # --------------------------------------------------------
    # 着順・馬番
    # --------------------------------------------------------

    finishers = []

    if finished:
        for row in result_rows:
            cells = row.find_all(
                ["td", "th"]
            )

            if len(cells) < 2:
                continue

            values = [
                clean_text(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )
                for cell in cells
            ]

            if not values:
                continue

            finish = to_int(
                values[0]
            )

            if finish is None:
                continue

            horse_number = None

            # 馬番セル候補
            for cell in cells:
                classes = " ".join(
                    cell.get(
                        "class",
                        []
                    )
                ).lower()

                if (
                    "umaban" in classes
                    or "horse_num" in classes
                ):
                    horse_number = (
                        to_int(
                            cell.get_text(
                                " ",
                                strip=True
                            )
                        )
                    )
                    break

            finishers.append(
                {
                    "finish": finish,
                    "horse_number":
                        horse_number
                }
            )

    return {
        "race_id": previous_race_id,
        "race_number": race_number,
        "race_name": race_name,
        "surface": surface,
        "distance": distance,
        "track_condition":
            track_condition,
        "finished": finished,
        "finisher_count":
            len(finishers),
        "finishers": finishers,
    }


# ============================================================
# 前レース取得
# ============================================================

collected = []

errors = []


for race_number in eligible_numbers:

    previous_race_id = build_race_id(
        race_id,
        race_number
    )

    url = (
        NETKEIBA_BASE
        + "/race/result.html?race_id="
        + previous_race_id
    )

    print(
        "collect:",
        race_number,
        "R",
        previous_race_id
    )

    try:
        html = get_html(
            url
        )

        info = extract_race_info(
            html,
            previous_race_id,
            race_number
        )

        info["source"] = (
            "netkeiba"
        )

        info["source_url"] = url

        collected.append(
            info
        )

        print(
            "  surface:",
            info["surface"],
            "distance:",
            info["distance"],
            "finished:",
            info["finished"],
            "finishers:",
            info["finisher_count"]
        )

    except Exception as exc:

        error = {
            "race_id":
                previous_race_id,
            "race_number":
                race_number,
            "error":
                str(exc)
        }

        errors.append(
            error
        )

        print(
            "  WARNING:",
            str(exc)
        )


# ============================================================
# 対象馬場と同じレース
# ============================================================

same_surface_races = [
    item
    for item in collected
    if (
        item.get("surface")
        == target_surface
        and item.get("finished")
    )
]


# ============================================================
# 安全性確認
# ============================================================

future_race_usage = any(
    (
        item.get(
            "race_number",
            99
        )
        >= target_race_number
    )
    for item in collected
)


if future_race_usage:
    raise SystemExit(
        "ERROR: 対象レース以降のデータが混入しました"
    )


# ============================================================
# 保存
# ============================================================

output = {
    "target_race_id":
        race_id,

    "race_date":
        race_date,

    "racecourse":
        racecourse,

    "target_surface":
        target_surface,

    "target_distance":
        target_distance,

    "target_race_number":
        target_race_number,

    "eligible_previous_race_numbers":
        eligible_numbers,

    "future_race_usage":
        False,

    "collected_race_count":
        len(collected),

    "same_surface_finished_count":
        len(same_surface_races),

    "races":
        collected,

    "same_surface_races":
        same_surface_races,

    "errors":
        errors,

    "updated_at":
        now_jst()
}


save_json(
    OUTPUT_FILE,
    output
)


# ============================================================
# ログ
# ============================================================

print()
print(
    "===== DAY RACE RESULT ====="
)

print(
    "target race:",
    target_race_number
)

print(
    "collected:",
    len(collected)
)

print(
    "same surface finished:",
    len(same_surface_races)
)

print(
    "future race usage:",
    False
)

print(
    "errors:",
    len(errors)
)

print(
    "saved:",
    OUTPUT_FILE
)

print(
    "==========================="
)
