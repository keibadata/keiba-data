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
        "０１２３４５６７８９：．－＋",
        "0123456789:.-+",
    )

    text = text.translate(translation)
    text = text.replace("\u3000", " ")

    return re.sub(r"\s+", " ", text).strip()


def to_int(value):
    text = clean_text(value)

    match = re.search(r"-?\d+", text)

    if not match:
        return None

    try:
        return int(match.group())
    except Exception:
        return None


def to_float(value):
    text = clean_text(value)

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text,
    )

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
        "Accept-Language":
            "ja,en-US;q=0.8,en;q=0.6",
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT,
        allow_redirects=True,
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

    if not re.fullmatch(
        r"\d{12}",
        race_id,
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
        "prefix": race_id[:10],
    }


def build_race_id(
    target_race_id,
    race_number,
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
# HTML補助
# ============================================================

def class_text(element):
    if not element:
        return ""

    return " ".join(
        element.get(
            "class",
            [],
        )
    ).lower()


def find_horse_link(row):
    selectors = [
        'a[href*="/horse/"]',
        'a[href*="horse.netkeiba.com/horse/"]',
    ]

    for selector in selectors:
        link = row.select_one(
            selector
        )

        if link:
            return link

    return None


def extract_horse_id(row):
    link = find_horse_link(row)

    if not link:
        return ""

    href = clean_text(
        link.get(
            "href",
            "",
        )
    )

    patterns = [
        r"/horse/(?:result/)?(\d+)",
        r"horse_id=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            href,
        )

        if match:
            return match.group(1)

    return ""


def extract_horse_name(row):
    link = find_horse_link(row)

    if not link:
        return ""

    return clean_text(
        link.get_text(
            " ",
            strip=True,
        )
    )


# ============================================================
# 時計
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

    return ""


def race_time_to_seconds(value):
    text = normalize_race_time(
        value
    )

    if not text:
        return None

    match = re.fullmatch(
        r"(\d+):(\d{2})\.(\d)",
        text,
    )

    if not match:
        return None

    minutes = int(
        match.group(1)
    )

    seconds = int(
        match.group(2)
    )

    decimal = (
        int(match.group(3))
        / 10
    )

    return round(
        minutes * 60
        + seconds
        + decimal,
        1,
    )


# ============================================================
# 馬体重
# ============================================================

def extract_body_weight(value):
    text = clean_text(value)

    match = re.search(
        r"(\d{3})"
        r"\s*"
        r"\("
        r"\s*"
        r"([+-]?\d+)"
        r"\s*"
        r"\)",
        text,
    )

    if not match:
        return None, None

    try:
        weight = int(
            match.group(1)
        )

        change = int(
            match.group(2)
        )

        return weight, change

    except Exception:
        return None, None


# ============================================================
# 結果表検出
# ============================================================

def find_result_table(soup):
    selectors = [
        "table.RaceCommon_Table.ResultRefund",
        "table.ResultRefund",
        ".RaceCommon_Table.ResultRefund",
        "table.RaceTable01",
        "table.race_table_01",
    ]

    for selector in selectors:
        table = soup.select_one(
            selector
        )

        if not table:
            continue

        text = clean_text(
            table.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "着順" in text
            and "馬名" in text
        ):
            return table

    return None


def get_result_headers(table):
    if not table:
        return []

    rows = table.find_all("tr")

    for row in rows:
        ths = row.find_all("th")

        if not ths:
            continue

        headers = [
            clean_text(
                th.get_text(
                    " ",
                    strip=True,
                )
            )
            for th in ths
        ]

        if (
            "着順" in headers
            or "馬名" in headers
        ):
            return headers

    return []


def normalize_header(value):
    text = clean_text(value)

    replacements = {
        "着 順": "着順",
        "馬 番": "馬番",
        "人 気": "人気",
        "馬体 重": "馬体重",
        "上 り": "上り",
        "上がり": "上り",
        "通過": "通過",
        "単勝": "オッズ",
    }

    for before, after in (
        replacements.items()
    ):
        text = text.replace(
            before,
            after,
        )

    return text


def header_index(
    headers,
    candidates,
):
    normalized = [
        normalize_header(
            value
        )
        for value in headers
    ]

    for candidate in candidates:
        target = normalize_header(
            candidate
        )

        for index, value in enumerate(
            normalized
        ):
            if value == target:
                return index

    for candidate in candidates:
        target = normalize_header(
            candidate
        )

        for index, value in enumerate(
            normalized
        ):
            if target in value:
                return index

    return None


def get_cell(
    cells,
    index,
):
    if index is None:
        return None

    if index < 0:
        return None

    if index >= len(cells):
        return None

    return cells[index]


def get_cell_text(
    cells,
    index,
):
    cell = get_cell(
        cells,
        index,
    )

    if not cell:
        return ""

    return clean_text(
        cell.get_text(
            " ",
            strip=True,
        )
    )


# ============================================================
# 結果行
# ============================================================

def parse_finish(value):
    text = clean_text(value)

    if re.fullmatch(
        r"\d+",
        text,
    ):
        return int(text)

    return None


def parse_horse_number(value):
    number = to_int(value)

    if (
        number is not None
        and 1 <= number <= 18
    ):
        return number

    return None


def parse_last3f(value):
    text = clean_text(value)

    match = re.search(
        r"\d{2}\.\d",
        text,
    )

    if not match:
        return None

    try:
        value = float(
            match.group()
        )

        if (
            30.0
            <= value
            <= 50.0
        ):
            return value

    except Exception:
        pass

    return None


def parse_popularity(value):
    value = to_int(value)

    if (
        value is not None
        and 1 <= value <= 30
    ):
        return value

    return None


def parse_odds(value):
    value = to_float(value)

    if (
        value is not None
        and value > 0
    ):
        return value

    return None


def parse_carried_weight(value):
    value = to_float(value)

    if (
        value is not None
        and 45.0 <= value <= 65.0
    ):
        return value

    return None


def parse_corner_order(value):
    text = clean_text(value)

    if not text:
        return ""

    text = text.replace(
        "→",
        "-",
    )

    return text


def parse_final_corner(value):
    text = parse_corner_order(
        value
    )

    numbers = re.findall(
        r"\d+",
        text,
    )

    if not numbers:
        return None

    try:
        return int(
            numbers[-1]
        )
    except Exception:
        return None


def parse_result_row(
    row,
    headers,
):
    cells = row.find_all("td")

    if not cells:
        return None

    indexes = {
        "finish": header_index(
            headers,
            ["着順"],
        ),
        "horse_number": header_index(
            headers,
            ["馬番"],
        ),
        "horse_name": header_index(
            headers,
            ["馬名"],
        ),
        "sex_age": header_index(
            headers,
            ["性齢"],
        ),
        "carried_weight": header_index(
            headers,
            ["斤量"],
        ),
        "jockey": header_index(
            headers,
            ["騎手"],
        ),
        "race_time": header_index(
            headers,
            ["タイム"],
        ),
        "margin": header_index(
            headers,
            ["着差"],
        ),
        "popularity": header_index(
            headers,
            ["人気"],
        ),
        "odds": header_index(
            headers,
            ["単勝", "オッズ"],
        ),
        "last3f": header_index(
            headers,
            ["上り", "上がり"],
        ),
        "corner_order": header_index(
            headers,
            ["通過"],
        ),
        "body_weight": header_index(
            headers,
            ["馬体重"],
        ),
    }

    finish_text = get_cell_text(
        cells,
        indexes["finish"],
    )

    if not finish_text:
        finish_text = get_cell_text(
            cells,
            0,
        )

    finish = parse_finish(
        finish_text
    )

    if finish is None:
        return None

    horse_number = (
        parse_horse_number(
            get_cell_text(
                cells,
                indexes[
                    "horse_number"
                ],
            )
        )
    )

    horse_id = extract_horse_id(
        row
    )

    horse_name = extract_horse_name(
        row
    )

    if not horse_name:
        horse_name = get_cell_text(
            cells,
            indexes[
                "horse_name"
            ],
        )

    sex_age = get_cell_text(
        cells,
        indexes["sex_age"],
    )

    carried_weight = (
        parse_carried_weight(
            get_cell_text(
                cells,
                indexes[
                    "carried_weight"
                ],
            )
        )
    )

    jockey = get_cell_text(
        cells,
        indexes["jockey"],
    )

    race_time_text = get_cell_text(
        cells,
        indexes["race_time"],
    )

    race_time = normalize_race_time(
        race_time_text
    )

    race_time_seconds = (
        race_time_to_seconds(
            race_time
        )
    )

    margin = get_cell_text(
        cells,
        indexes["margin"],
    )

    popularity = (
        parse_popularity(
            get_cell_text(
                cells,
                indexes[
                    "popularity"
                ],
            )
        )
    )

    odds = parse_odds(
        get_cell_text(
            cells,
            indexes["odds"],
        )
    )

    last3f = parse_last3f(
        get_cell_text(
            cells,
            indexes["last3f"],
        )
    )

    corner_order = (
        parse_corner_order(
            get_cell_text(
                cells,
                indexes[
                    "corner_order"
                ],
            )
        )
    )

    final_corner = (
        parse_final_corner(
            corner_order
        )
    )

    body_weight_text = (
        get_cell_text(
            cells,
            indexes[
                "body_weight"
            ],
        )
    )

    (
        body_weight,
        body_weight_change,
    ) = extract_body_weight(
        body_weight_text
    )

    return {
        "finish": finish,
        "horse_number":
            horse_number,
        "horse_id":
            horse_id,
        "horse_name":
            horse_name,
        "sex_age":
            sex_age,
        "race_time":
            race_time,
        "race_time_seconds":
            race_time_seconds,
        "margin":
            margin,
        "corner_order":
            corner_order,
        "final_corner":
            final_corner,
        "last3f":
            last3f,
        "popularity":
            popularity,
        "odds":
            odds,
        "body_weight":
            body_weight,
        "body_weight_change":
            body_weight_change,
        "jockey":
            jockey,
        "carried_weight":
            carried_weight,
    }


def extract_finishers(soup):
    table = find_result_table(
        soup
    )

    if not table:
        return []

    headers = get_result_headers(
        table
    )

    if not headers:
        return []

    finishers = []

    for row in table.find_all("tr"):
        result = parse_result_row(
            row,
            headers,
        )

        if result:
            finishers.append(
                result
            )

    finishers.sort(
        key=lambda item:
            item.get(
                "finish",
                999,
            )
    )

    return finishers


# ============================================================
# レース名
# ============================================================

def extract_race_name(soup):
    selectors = [
        ".RaceName",
        ".RaceName_main",
        ".RaceName01",
        ".RaceTitle",
        "h1.RaceName",
        "h1",
    ]

    for selector in selectors:
        elements = soup.select(
            selector
        )

        for element in elements:
            text = clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                text
                and text.lower()
                != "netkeiba"
            ):
                return text

    title = ""

    if soup.title:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True,
            )
        )

    if title:
        parts = re.split(
            r"[|｜]",
            title,
        )

        for part in parts:
            part = clean_text(part)

            if (
                part
                and "netkeiba"
                not in part.lower()
                and "結果" not in part
            ):
                return part

    return ""


# ============================================================
# コース情報
# ============================================================

def extract_surface_and_distance(
    text,
):
    text = clean_text(text)

    patterns = [
        (
            "ダート",
            r"ダ(?:ート)?"
            r"\s*"
            r"(\d{3,4})"
            r"\s*m",
        ),
        (
            "芝",
            r"芝"
            r"\s*"
            r"(\d{3,4})"
            r"\s*m",
        ),
    ]

    for surface, pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            return (
                surface,
                int(
                    match.group(1)
                ),
            )

    return "", None


def extract_track_condition(
    text,
    surface,
):
    text = clean_text(text)

    if surface == "芝":
        patterns = [
            r"芝\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
            r"馬場\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
        ]

    elif surface == "ダート":
        patterns = [
            r"ダ(?:ート)?\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
            r"馬場\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
        ]

    else:
        patterns = [
            r"馬場\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
        ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            return match.group(1)

    return ""


# ============================================================
# ラップ
# ============================================================

def parse_lap_values(value):
    text = clean_text(value)

    matches = re.findall(
        r"(?<!\d)"
        r"(\d{2}\.\d)"
        r"(?!\d)",
        text,
    )

    values = []

    for match in matches:
        try:
            value = float(match)

            if (
                9.0
                <= value
                <= 20.0
            ):
                values.append(
                    value
                )

        except Exception:
            continue

    return values


def extract_laps(soup):
    # --------------------------------------------------------
    # まず「ハロンタイム」ラベル周辺を探す
    # --------------------------------------------------------

    label_candidates = (
        soup.find_all(
            string=re.compile(
                r"ハロンタイム|ラップ"
            )
        )
    )

    for string_node in label_candidates:
        parent = string_node.parent

        if not parent:
            continue

        candidates = [
            parent,
            parent.parent
            if parent.parent
            else None,
        ]

        if (
            parent.parent
            and parent.parent.parent
        ):
            candidates.append(
                parent.parent.parent
            )

        for element in candidates:
            if not element:
                continue

            text = clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            values = parse_lap_values(
                text
            )

            if len(values) >= 4:
                return values

    # --------------------------------------------------------
    # 専用class候補
    # --------------------------------------------------------

    selectors = [
        ".Race_HaronTime",
        ".HaronTime",
        ".Haron",
        ".LapTime",
        ".RaceLap",
        ".RaceData01",
        ".RaceData02",
        ".RaceData03",
    ]

    for selector in selectors:
        for element in soup.select(
            selector
        ):
            text = clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            values = parse_lap_values(
                text
            )

            if len(values) >= 4:
                return values

    # --------------------------------------------------------
    # table行単位
    # --------------------------------------------------------

    for row in soup.find_all("tr"):
        text = clean_text(
            row.get_text(
                " ",
                strip=True,
            )
        )

        if (
            "ハロンタイム"
            not in text
            and "ラップ"
            not in text
        ):
            continue

        values = parse_lap_values(
            text
        )

        if len(values) >= 4:
            return values

    return []


def classify_lap_pace(laps):
    if len(laps) < 6:
        return ""

    first3 = round(
        sum(laps[:3]),
        1,
    )

    last3 = round(
        sum(laps[-3:]),
        1,
    )

    difference = round(
        first3 - last3,
        1,
    )

    # 前半3Fの方が速い
    if difference <= -1.0:
        return "ハイ"

    # 後半3Fの方が速い
    if difference >= 1.0:
        return "スロー"

    return "ミドル"


# ============================================================
# レース全体
# ============================================================

def extract_race_info(
    html,
    race_id,
    race_number,
):
    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True,
        )
    )

    race_name = extract_race_name(
        soup
    )

    (
        surface,
        distance,
    ) = extract_surface_and_distance(
        page_text
    )

    track_condition = (
        extract_track_condition(
            page_text,
            surface,
        )
    )

    finishers = extract_finishers(
        soup
    )

    finished = (
        len(finishers) > 0
    )

    laps = extract_laps(
        soup
    )

    pace = classify_lap_pace(
        laps
    )

    winner_time = None
    winner_last3f = None

    if finishers:
        winner_time = (
            finishers[0].get(
                "race_time"
            )
        )

        winner_last3f = (
            finishers[0].get(
                "last3f"
            )
        )

    return {
        "race_id":
            race_id,
        "race_number":
            race_number,
        "race_name":
            race_name,
        "surface":
            surface,
        "distance":
            distance,
        "track_condition":
            track_condition,
        "finished":
            finished,
        "finisher_count":
            len(finishers),
        "winner_time":
            winner_time,
        "winner_last3f":
            winner_last3f,
        "laps":
            laps,
        "pace":
            pace,
        "finishers":
            finishers,
    }


# ============================================================
# CLI
# ============================================================

parser = argparse.ArgumentParser()

parser.add_argument(
    "--include-target",
    action="store_true",
    help=(
        "結果照合専用。"
        "対象レース自身も取得する。"
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

race = load_json(
    RACE_FILE
)

if not race:
    raise SystemExit(
        "ERROR: race.json がありません"
    )


race_id = clean_text(
    race.get(
        "race_id"
    )
)

race_date = clean_text(
    race.get(
        "race_date"
    )
    or race.get(
        "date"
    )
)

racecourse = clean_text(
    race.get(
        "racecourse"
    )
    or race.get(
        "track"
    )
)

target_surface = clean_text(
    race.get(
        "surface"
    )
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
    race_info[
        "race_number"
    ]
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

    current_race_id = (
        build_race_id(
            race_id,
            race_number,
        )
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
        html = get_html(
            url
        )

        info = extract_race_info(
            html,
            current_race_id,
            race_number,
        )

        info["source"] = (
            "netkeiba"
        )

        info["source_url"] = (
            url
        )

        collected.append(
            info
        )

        print(
            "  name:",
            info["race_name"],
        )

        print(
            "  surface:",
            info["surface"],
            "distance:",
            info["distance"],
            "condition:",
            info[
                "track_condition"
            ],
            "finished:",
            info["finished"],
            "finishers:",
            info[
                "finisher_count"
            ],
            "laps:",
            len(
                info["laps"]
            ),
            "pace:",
            info["pace"],
        )

        if info["finished"]:
            winner = (
                info["finishers"][0]
            )

            print(
                "  winner:",
                winner.get(
                    "horse_number"
                ),
                winner.get(
                    "horse_name"
                ),
                winner.get(
                    "race_time"
                ),
                "last3f:",
                winner.get(
                    "last3f"
                ),
            )

    except Exception as exc:

        error = {
            "race_id":
                current_race_id,
            "race_number":
                race_number,
            "error":
                str(exc),
        }

        errors.append(
            error
        )

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
        item.get(
            "surface"
        )
        == target_surface
        and item.get(
            "finished"
        )
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
        item.get(
            "race_number"
        )
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

    "mode": (
        "result_verification"
        if args.include_target
        else "prediction"
    ),

    "include_target":
        bool(
            args.include_target
        ),

    "eligible_race_numbers":
        eligible_numbers,

    "future_race_usage":
        False,

    "target_race_included":
        target_race_included,

    "collected_race_count":
        len(collected),

    "same_surface_finished_count":
        len(
            same_surface_races
        ),

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
    len(
        same_surface_races
    ),
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
