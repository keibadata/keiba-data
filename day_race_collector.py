import argparse
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

JST = timezone(timedelta(hours=9))

NETKEIBA_BASE = "https://race.netkeiba.com"


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(JST).isoformat(timespec="seconds")


def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def clean_text(value):
    if value is None:
        return ""

    text = str(value)

    translation = str.maketrans(
        "０１２３４５６７８９：．－",
        "0123456789:.-",
    )

    text = text.translate(translation)
    text = text.replace("\u3000", " ")

    return re.sub(r"\s+", " ", text).strip()


def to_int(value):
    text = clean_text(value)

    match = re.search(r"\d+", text)

    if not match:
        return None

    try:
        return int(match.group())
    except Exception:
        return None


def to_float(value):
    text = clean_text(value)

    match = re.search(r"-?\d+(?:\.\d+)?", text)

    if not match:
        return None

    try:
        return float(match.group())
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
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in ["iso-8859-1", "ascii"]
    ):
        response.encoding = response.apparent_encoding

    return response.text


# ============================================================
# race_id
# ============================================================

def split_race_id(race_id):
    race_id = clean_text(race_id)

    if not re.fullmatch(r"\d{12}", race_id):
        return None

    return {
        "year": race_id[0:4],
        "track_code": race_id[4:6],
        "meeting": race_id[6:8],
        "day": race_id[8:10],
        "race_number": int(race_id[10:12]),
        "prefix": race_id[:10],
    }


def build_race_id(target_race_id, race_number):
    info = split_race_id(target_race_id)

    if not info:
        return ""

    return info["prefix"] + f"{race_number:02d}"


# ============================================================
# HTML補助
# ============================================================

def class_text(element):
    if not element:
        return ""

    return " ".join(
        element.get("class", [])
    ).lower()


def get_cell_by_class(cells, keywords):
    for cell in cells:
        classes = class_text(cell)

        if any(
            keyword.lower() in classes
            for keyword in keywords
        ):
            return cell

    return None


def cell_text_by_class(cells, keywords):
    cell = get_cell_by_class(cells, keywords)

    if not cell:
        return ""

    return clean_text(
        cell.get_text(" ", strip=True)
    )


def find_horse_link(row):
    selectors = [
        'a[href*="/horse/"]',
        'a[href*="horse.netkeiba.com/horse/"]',
    ]

    for selector in selectors:
        link = row.select_one(selector)

        if link:
            return link

    return None


def extract_horse_id(row):
    link = find_horse_link(row)

    if not link:
        return ""

    href = clean_text(link.get("href"))

    match = re.search(
        r"/horse/(?:result/)?(\d+)",
        href,
    )

    if match:
        return match.group(1)

    match = re.search(
        r"horse_id=(\d+)",
        href,
    )

    if match:
        return match.group(1)

    return ""


def extract_horse_name(row):
    link = find_horse_link(row)

    if link:
        name = clean_text(
            link.get_text(" ", strip=True)
        )

        if name:
            return name

    cells = row.find_all("td")

    value = cell_text_by_class(
        cells,
        [
            "horse",
            "umamei",
        ],
    )

    return value


# ============================================================
# 着順
# ============================================================

def extract_finish(cell):
    if not cell:
        return None

    text = clean_text(
        cell.get_text(" ", strip=True)
    )

    if re.fullmatch(r"\d+", text):
        return int(text)

    return None


def extract_horse_number(cells):
    value = cell_text_by_class(
        cells,
        [
            "umaban",
            "horse_num",
            "horse_number",
        ],
    )

    number = to_int(value)

    if number is not None:
        return number

    # netkeibaの結果表でclassが取得できない場合の補助
    for cell in cells[:5]:
        text = clean_text(
            cell.get_text(" ", strip=True)
        )

        if re.fullmatch(r"\d{1,2}", text):
            value = int(text)

            if 1 <= value <= 18:
                classes = class_text(cell)

                if "waku" not in classes:
                    return value

    return None


# ============================================================
# 走破時計
# ============================================================

def normalize_race_time(value):
    text = clean_text(value)

    match = re.search(
        r"(\d+):(\d{2})\.(\d)",
        text,
    )

    if match:
        return (
            f"{int(match.group(1))}:"
            f"{match.group(2)}."
            f"{match.group(3)}"
        )

    match = re.search(
        r"(\d+)\.(\d)",
        text,
    )

    if match:
        return match.group(0)

    return ""


def race_time_to_seconds(value):
    text = normalize_race_time(value)

    if not text:
        return None

    if ":" in text:
        match = re.fullmatch(
            r"(\d+):(\d{2})\.(\d)",
            text,
        )

        if not match:
            return None

        minutes = int(match.group(1))
        seconds = int(match.group(2))
        decimal = int(match.group(3)) / 10

        return round(
            minutes * 60 + seconds + decimal,
            1,
        )

    try:
        return float(text)
    except Exception:
        return None


# ============================================================
# 通過順位
# ============================================================

def normalize_corner_order(value):
    text = clean_text(value)

    if not text:
        return ""

    text = text.replace("→", "-")
    text = text.replace("－", "-")

    return text


def extract_final_corner(value):
    text = normalize_corner_order(value)

    if not text:
        return None

    numbers = re.findall(r"\d+", text)

    if not numbers:
        return None

    try:
        return int(numbers[-1])
    except Exception:
        return None


# ============================================================
# 上がり
# ============================================================

def normalize_last3f(value):
    text = clean_text(value)

    match = re.search(
        r"\d{2}\.\d",
        text,
    )

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


# ============================================================
# レースラップ
# ============================================================

def parse_lap_values(text):
    text = clean_text(text)

    values = re.findall(
        r"\d{2}\.\d",
        text,
    )

    result = []

    for value in values:
        try:
            number = float(value)

            if 9.0 <= number <= 20.0:
                result.append(number)
        except Exception:
            pass

    return result


def extract_laps(soup):
    candidates = []

    selectors = [
        ".Race_HaronTime",
        ".HaronTime",
        ".RaceData01",
        ".RaceData02",
        ".RaceData03",
        "table",
    ]

    for selector in selectors:
        for element in soup.select(selector):
            text = clean_text(
                element.get_text(" ", strip=True)
            )

            if (
                "ハロンタイム" in text
                or "ラップ" in text
            ):
                candidates.append(text)

    for text in candidates:
        values = parse_lap_values(text)

        if len(values) >= 4:
            return values

    return []


def classify_lap_pace(laps):
    if len(laps) < 6:
        return ""

    first3 = sum(laps[:3])
    last3 = sum(laps[-3:])

    difference = round(
        first3 - last3,
        1,
    )

    if difference <= -1.0:
        return "ハイ"

    if difference >= 1.0:
        return "スロー"

    return "ミドル"


# ============================================================
# レース情報
# ============================================================

def extract_race_name(soup):
    selectors = [
        ".RaceName",
        ".RaceName_main",
        "h1",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element:
            candidate = clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if candidate:
                return candidate

    return ""


def extract_surface_and_distance(text):
    surface = ""
    distance = None

    match = re.search(
        r"ダ(?:ート)?\s*(\d{3,4})m",
        text,
    )

    if match:
        surface = "ダート"
        distance = int(match.group(1))
        return surface, distance

    match = re.search(
        r"芝\s*(\d{3,4})m",
        text,
    )

    if match:
        surface = "芝"
        distance = int(match.group(1))
        return surface, distance

    return surface, distance


def extract_track_condition(text):
    patterns = [
        r"馬場\s*:\s*(良|稍重|重|不良)",
        r"馬場\s*(良|稍重|重|不良)",
        r"芝\s*:\s*(良|稍重|重|不良)",
        r"ダート\s*:\s*(良|稍重|重|不良)",
        r"ダ\s*:\s*(良|稍重|重|不良)",
    ]

    for pattern in patterns:
        match = re.search(pattern, text)

        if match:
            return match.group(1)

    return ""


# ============================================================
# 結果表
# ============================================================

def find_result_rows(soup):
    selectors = [
        "table.RaceTable01 tbody tr",
        "table.RaceTable01 tr",
        "table.race_table_01 tbody tr",
        "table.race_table_01 tr",
        ".RaceTable01 tbody tr",
        ".RaceTable01 tr",
    ]

    for selector in selectors:
        rows = soup.select(selector)

        valid_rows = []

        for row in rows:
            cells = row.find_all("td")

            if len(cells) >= 5:
                valid_rows.append(row)

        if valid_rows:
            return valid_rows

    return []


def extract_result_row(row):
    cells = row.find_all("td")

    if not cells:
        return None

    # --------------------------------------------------------
    # 着順
    # --------------------------------------------------------

    finish_cell = get_cell_by_class(
        cells,
        [
            "result_num",
            "rank",
            "order",
            "arrival",
        ],
    )

    finish = extract_finish(finish_cell)

    if finish is None:
        finish = extract_finish(cells[0])

    if finish is None:
        return None

    # --------------------------------------------------------
    # 馬
    # --------------------------------------------------------

    horse_number = extract_horse_number(cells)
    horse_id = extract_horse_id(row)
    horse_name = extract_horse_name(row)

    # --------------------------------------------------------
    # タイム
    # --------------------------------------------------------

    race_time_text = cell_text_by_class(
        cells,
        [
            "time",
        ],
    )

    race_time = normalize_race_time(
        race_time_text
    )

    race_time_seconds = race_time_to_seconds(
        race_time
    )

    # --------------------------------------------------------
    # 着差
    # --------------------------------------------------------

    margin = cell_text_by_class(
        cells,
        [
            "着差",
            "margin",
            "difference",
        ],
    )

    # --------------------------------------------------------
    # 通過
    # --------------------------------------------------------

    corner_order = cell_text_by_class(
        cells,
        [
            "corner",
            "passage",
        ],
    )

    corner_order = normalize_corner_order(
        corner_order
    )

    final_corner = extract_final_corner(
        corner_order
    )

    # --------------------------------------------------------
    # 上がり
    # --------------------------------------------------------

    last3f_text = cell_text_by_class(
        cells,
        [
            "agari",
            "last3",
            "last_3",
        ],
    )

    last3f = normalize_last3f(
        last3f_text
    )

    # --------------------------------------------------------
    # 人気
    # --------------------------------------------------------

    popularity_text = cell_text_by_class(
        cells,
        [
            "popular",
            "ninki",
        ],
    )

    popularity = to_int(
        popularity_text
    )

    # --------------------------------------------------------
    # 単勝
    # --------------------------------------------------------

    odds_text = cell_text_by_class(
        cells,
        [
            "odds",
        ],
    )

    odds = to_float(
        odds_text
    )

    # --------------------------------------------------------
    # 馬体重
    # --------------------------------------------------------

    body_weight_text = cell_text_by_class(
        cells,
        [
            "weight",
            "batai",
        ],
    )

    body_weight = None
    body_weight_change = None

    weight_match = re.search(
        r"(\d{3})\s*\(([+-]?\d+)\)",
        body_weight_text,
    )

    if weight_match:
        body_weight = int(
            weight_match.group(1)
        )

        body_weight_change = int(
            weight_match.group(2)
        )

    # --------------------------------------------------------
    # 騎手
    # --------------------------------------------------------

    jockey = cell_text_by_class(
        cells,
        [
            "jockey",
        ],
    )

    # --------------------------------------------------------
    # 斤量
    # --------------------------------------------------------

    carried_weight_text = cell_text_by_class(
        cells,
        [
            "weight",
            "burden",
            "kinryo",
        ],
    )

    carried_weight = None

    for cell in cells:
        classes = class_text(cell)

        if (
            "weight" in classes
            or "burden" in classes
            or "kinryo" in classes
        ):
            value = to_float(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                value is not None
                and 45 <= value <= 65
            ):
                carried_weight = value
                break

    return {
        "finish": finish,
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "race_time": race_time,
        "race_time_seconds": race_time_seconds,
        "margin": margin,
        "corner_order": corner_order,
        "final_corner": final_corner,
        "last3f": last3f,
        "popularity": popularity,
        "odds": odds,
        "body_weight": body_weight,
        "body_weight_change": body_weight_change,
        "jockey": jockey,
        "carried_weight": carried_weight,
    }


# ============================================================
# レース全体抽出
# ============================================================

def extract_race_info(
    html,
    target_id,
    race_number,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    text = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    race_name = extract_race_name(soup)

    surface, distance = (
        extract_surface_and_distance(text)
    )

    track_condition = (
        extract_track_condition(text)
    )

    result_rows = find_result_rows(soup)

    finishers = []

    for row in result_rows:
        result = extract_result_row(row)

        if result:
            finishers.append(result)

    finishers.sort(
        key=lambda item: item.get(
            "finish",
            999,
        )
    )

    finished = len(finishers) > 0

    laps = extract_laps(soup)

    pace = classify_lap_pace(laps)

    winner_time = None
    winner_last3f = None

    if finishers:
        winner_time = finishers[0].get(
            "race_time"
        )

        winner_last3f = finishers[0].get(
            "last3f"
        )

    return {
        "race_id": target_id,
        "race_number": race_number,
        "race_name": race_name,
        "surface": surface,
        "distance": distance,
        "track_condition": track_condition,
        "finished": finished,
        "finisher_count": len(finishers),
        "winner_time": winner_time,
        "winner_last3f": winner_last3f,
        "laps": laps,
        "pace": pace,
        "finishers": finishers,
    }


# ============================================================
# CLI
# ============================================================

parser = argparse.ArgumentParser()

parser.add_argument(
    "--include-target",
    action="store_true",
    help=(
        "結果照合用。対象レース自身も取得する。"
        "予想時には使用しない。"
    ),
)

parser.add_argument(
    "--output",
    default=OUTPUT_FILE,
)

args = parser.parse_args()


# ============================================================
# race.json
# ============================================================

race = load_json(RACE_FILE)

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


race_info = split_race_id(race_id)

if not race_info:
    raise SystemExit(
        "ERROR: race_id が12桁ではありません"
    )


target_race_number = (
    race_info["race_number"]
)


# ============================================================
# 取得対象
# ============================================================

if args.include_target:
    eligible_numbers = list(
        range(
            1,
            target_race_number + 1,
        )
    )
else:
    eligible_numbers = list(
        range(
            1,
            target_race_number,
        )
    )


print()
print(
    "===== DAY RACE COLLECTOR ====="
)

print(
    "target race id:",
    race_id,
)

print(
    "date:",
    race_date,
)

print(
    "racecourse:",
    racecourse,
)

print(
    "target surface:",
    target_surface,
)

print(
    "target distance:",
    target_distance,
)

print(
    "target race number:",
    target_race_number,
)

print(
    "include target:",
    args.include_target,
)

print(
    "eligible races:",
    eligible_numbers,
)

print()


# ============================================================
# 取得
# ============================================================

collected = []
errors = []


for race_number in eligible_numbers:

    current_race_id = build_race_id(
        race_id,
        race_number,
    )

    url = (
        NETKEIBA_BASE
        + "/race/result.html?race_id="
        + current_race_id
    )

    print(
        "collect:",
        race_number,
        "R",
        current_race_id,
    )

    try:
        html = get_html(url)

        info = extract_race_info(
            html,
            current_race_id,
            race_number,
        )

        info["source"] = "netkeiba"
        info["source_url"] = url

        collected.append(info)

        print(
            "  surface:",
            info["surface"],
            "distance:",
            info["distance"],
            "condition:",
            info["track_condition"],
            "finished:",
            info["finished"],
            "finishers:",
            info["finisher_count"],
            "laps:",
            len(info["laps"]),
        )

        if info["finished"]:
            print(
                "  winner:",
                (
                    info["finishers"][0]
                    .get("horse_number")
                ),
                (
                    info["finishers"][0]
                    .get("horse_name")
                ),
                (
                    info["finishers"][0]
                    .get("race_time")
                ),
            )

    except Exception as exc:

        error = {
            "race_id": current_race_id,
            "race_number": race_number,
            "error": str(exc),
        }

        errors.append(error)

        print(
            "  WARNING:",
            str(exc),
        )


# ============================================================
# 同馬場
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
# 安全性
# ============================================================

future_race_usage = any(
    (
        item.get(
            "race_number",
            99,
        )
        > target_race_number
    )
    for item in collected
)


if future_race_usage:
    raise SystemExit(
        "ERROR: 対象レースより後のデータが混入しました"
    )


target_race_included = any(
    (
        item.get("race_number")
        == target_race_number
    )
    for item in collected
)


if (
    not args.include_target
    and target_race_included
):
    raise SystemExit(
        "ERROR: 予想モードに対象レース結果が混入しました"
    )


# ============================================================
# 保存
# ============================================================

output = {
    "target_race_id": race_id,
    "race_date": race_date,
    "racecourse": racecourse,
    "target_surface": target_surface,
    "target_distance": target_distance,
    "target_race_number": target_race_number,

    "mode": (
        "result_verification"
        if args.include_target
        else "prediction"
    ),

    "include_target": bool(
        args.include_target
    ),

    "eligible_race_numbers":
        eligible_numbers,

    "future_race_usage": False,

    "target_race_included":
        target_race_included,

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
        now_jst(),
}


save_json(
    args.output,
    output,
)


# ============================================================
# ログ
# ============================================================

print()
print(
    "===== DAY RACE RESULT ====="
)

print(
    "mode:",
    output["mode"],
)

print(
    "target race:",
    target_race_number,
)

print(
    "collected:",
    len(collected),
)

print(
    "same surface finished:",
    len(same_surface_races),
)

print(
    "target included:",
    target_race_included,
)

print(
    "future race usage:",
    False,
)

print(
    "errors:",
    len(errors),
)

print(
    "saved:",
    args.output,
)

print(
    "==========================="
)
