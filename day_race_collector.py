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
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
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
# Race ID
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

    return (
        info["prefix"]
        + f"{race_number:02d}"
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

    if not match:
        return ""

    return (
        f"{int(match.group(1))}:"
        f"{match.group(2)}."
        f"{match.group(3)}"
    )


def race_time_to_seconds(value):
    text = normalize_race_time(value)

    if not text:
        return None

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
        r"\s*kg?"
        r"\s*"
        r"\("
        r"\s*"
        r"([+-]?\d+)"
        r"\s*"
        r"\)",
        text,
        re.IGNORECASE,
    )

    if not match:
        return None, None

    try:
        return (
            int(match.group(1)),
            int(match.group(2)),
        )
    except Exception:
        return None, None


# ============================================================
# 馬リンク
# ============================================================

def find_horse_link(row):
    selectors = [
        'a[href*="/horse/"]',
        'a[href*="horse.netkeiba.com/horse/"]',
        'a[href*="db.sp.netkeiba.com/horse/"]',
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

    href = clean_text(
        link.get("href", "")
    )

    patterns = [
        r"/horse/(?:result/)?(\d+)",
        r"horse_id=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(pattern, href)

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
# レース名
# ============================================================

def extract_race_name(soup):
    selectors = [
        ".RaceList_Item02",
        ".RaceList_NameBox",
        ".RaceName",
        ".RaceName_main",
        ".RaceName01",
        ".RaceTitle",
        "h1.RaceName",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if not element:
            continue

        # スマホ版ではレース名専用要素がある場合を優先
        candidates = [
            element.select_one(".RaceName"),
            element.select_one(".Race_Name"),
            element.select_one(".RaceName_main"),
        ]

        for candidate in candidates:
            if candidate:
                text = clean_text(
                    candidate.get_text(
                        " ",
                        strip=True,
                    )
                )

                if text:
                    return text

        text = clean_text(
            element.get_text(
                " ",
                strip=True,
            )
        )

        # 「12R 2勝クラス 嵯峨野特別 16:30 ...」
        match = re.search(
            r"\d{1,2}R\s+"
            r"(?:\S+\s+)?"
            r"(.+?)\s+"
            r"\d{1,2}:\d{2}\s+",
            text,
        )

        if match:
            name = clean_text(
                match.group(1)
            )

            # クラス名だけ残るケースを補正
            class_words = [
                "未勝利",
                "新馬",
                "1勝クラス",
                "2勝クラス",
                "3勝クラス",
                "オープン",
            ]

            for word in class_words:
                if name.startswith(
                    word + " "
                ):
                    name = clean_text(
                        name[len(word):]
                    )

            if name:
                return name

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
# レース基本情報
# ============================================================

def extract_race_data_text(soup):
    selectors = [
        ".Race_Data",
        ".RaceData",
        ".RaceList_Item02",
        ".RaceList_NameBox_inner",
    ]

    for selector in selectors:
        element = soup.select_one(selector)

        if element:
            text = clean_text(
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if text:
                return text

    return ""


def extract_surface_and_distance(text):
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
                int(match.group(1)),
            )

    return "", None


def extract_track_condition(
    race_data_text,
    surface,
):
    text = clean_text(
        race_data_text
    )

    # スマホ版例:
    # 16:30 ダ 1400m (右) 12頭 曇 重
    match = re.search(
        r"(?:芝|ダ(?:ート)?)"
        r"\s*"
        r"\d{3,4}"
        r"\s*m"
        r".*?"
        r"(良|稍重|重|不良)"
        r"(?:\s|$)",
        text,
    )

    if match:
        return match.group(1)

    if surface == "芝":
        patterns = [
            r"芝\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
        ]

    elif surface == "ダート":
        patterns = [
            r"ダ(?:ート)?\s*[:：]?\s*"
            r"(良|稍重|重|不良)",
        ]

    else:
        patterns = []

    patterns.append(
        r"馬場\s*[:：]?\s*"
        r"(良|稍重|重|不良)"
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
        )

        if match:
            return match.group(1)

    # Race_Dataの末尾付近
    tokens = text.split()

    for token in reversed(tokens):
        if token in [
            "良",
            "稍重",
            "重",
            "不良",
        ]:
            return token

    return ""


# ============================================================
# スマホ版結果表
# ============================================================

def find_result_table(soup):
    # 現行スマホ版
    for table in soup.find_all("table"):
        classes = set(
            table.get("class", [])
        )

        if {
            "RaceCommon_Table",
            "ResultRefund",
        }.issubset(classes):
            text = clean_text(
                table.get_text(
                    " ",
                    strip=True,
                )
            )

            if (
                "着" in text
                and "馬" in text
                and "タイム" in text
            ):
                return table

    # PC版・旧形式fallback
    selectors = [
        "table.RaceTable01",
        "table.race_table_01",
    ]

    for selector in selectors:
        table = soup.select_one(
            selector
        )

        if table:
            return table

    return None


def parse_finish(value):
    text = clean_text(value)

    match = re.match(
        r"^(\d+)\s*着?",
        text,
    )

    if not match:
        return None

    try:
        return int(
            match.group(1)
        )
    except Exception:
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

    # スマホ版 Timeセル:
    # 1:22.1 (35.4)
    matches = re.findall(
        r"\((\d{2}\.\d)\)",
        text,
    )

    if matches:
        try:
            value = float(
                matches[-1]
            )

            if 30.0 <= value <= 50.0:
                return value
        except Exception:
            pass

    match = re.search(
        r"(?<!\d)(\d{2}\.\d)(?!\d)",
        text,
    )

    if match:
        try:
            value = float(
                match.group(1)
            )

            if 30.0 <= value <= 50.0:
                return value
        except Exception:
            pass

    return None


def parse_popularity(value):
    text = clean_text(value)

    match = re.search(
        r"(\d+)\s*人気",
        text,
    )

    if not match:
        return None

    value = int(
        match.group(1)
    )

    if 1 <= value <= 30:
        return value

    return None


def parse_odds(value):
    text = clean_text(value)

    match = re.search(
        r"(\d+(?:\.\d+)?)\s*倍",
        text,
    )

    if not match:
        return None

    try:
        value = float(
            match.group(1)
        )

        if value > 0:
            return value
    except Exception:
        pass

    return None


def parse_mobile_horse_detail(cell):
    result = {
        "sex_age": "",
        "body_weight": None,
        "body_weight_change": None,
        "jockey": "",
        "carried_weight": None,
    }

    if not cell:
        return result

    text = clean_text(
        cell.get_text(
            " ",
            strip=True,
        )
    )

    sex_age_match = re.search(
        r"([牡牝セ騙]\d+)",
        text,
    )

    if sex_age_match:
        result["sex_age"] = (
            sex_age_match.group(1)
        )

    (
        body_weight,
        body_weight_change,
    ) = extract_body_weight(text)

    result["body_weight"] = (
        body_weight
    )

    result["body_weight_change"] = (
        body_weight_change
    )

    detail_right = cell.select_one(
        ".Detail_Right"
    )

    if detail_right:
        right_text = clean_text(
            detail_right.get_text(
                " ",
                strip=True,
            )
        )

        # 例:
        # 角田和 55.0 栗東・吉田
        match = re.match(
            r"(.+?)\s+"
            r"(\d{2}(?:\.\d)?)"
            r"(?:\s|$)",
            right_text,
        )

        if match:
            result["jockey"] = (
                clean_text(
                    match.group(1)
                )
            )

            try:
                weight = float(
                    match.group(2)
                )

                if 45.0 <= weight <= 65.0:
                    result[
                        "carried_weight"
                    ] = weight
            except Exception:
                pass

    return result


def parse_mobile_result_row(row):
    cells = row.find_all(
        "td",
        recursive=False,
    )

    if len(cells) < 6:
        return None

    finish_text = clean_text(
        cells[0].get_text(
            " ",
            strip=True,
        )
    )

    finish = parse_finish(
        finish_text
    )

    if finish is None:
        return None

    horse_number = (
        parse_horse_number(
            cells[2].get_text(
                " ",
                strip=True,
            )
        )
    )

    horse_cell = cells[3]
    time_cell = cells[4]
    odds_cell = cells[5]

    horse_name = extract_horse_name(
        row
    )

    horse_id = extract_horse_id(
        row
    )

    horse_detail = (
        parse_mobile_horse_detail(
            horse_cell
        )
    )

    time_text = clean_text(
        time_cell.get_text(
            " ",
            strip=True,
        )
    )

    race_time = normalize_race_time(
        time_text
    )

    race_time_seconds = (
        race_time_to_seconds(
            race_time
        )
    )

    last3f = parse_last3f(
        time_text
    )

    # スマホ版では着差もTimeセル内
    margin = ""

    time_dl = time_cell.find("dl")

    if time_dl:
        dds = time_dl.find_all(
            "dd",
            recursive=False,
        )

        for dd in dds:
            text = clean_text(
                dd.get_text(
                    " ",
                    strip=True,
                )
            )

            if not text:
                continue

            if re.fullmatch(
                r"\(\d{2}\.\d\)",
                text,
            ):
                continue

            margin = text
            break

    odds_text = clean_text(
        odds_cell.get_text(
            " ",
            strip=True,
        )
    )

    popularity = parse_popularity(
        odds_text
    )

    odds = parse_odds(
        odds_text
    )

    return {
        "finish": finish,
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": horse_detail[
            "sex_age"
        ],
        "race_time": race_time,
        "race_time_seconds":
            race_time_seconds,
        "margin": margin,

        # スマホ版結果表に個別通過順はない。
        # レース全体の通過順から推測しない。
        "corner_order": "",
        "final_corner": None,

        "last3f": last3f,
        "popularity": popularity,
        "odds": odds,
        "body_weight": horse_detail[
            "body_weight"
        ],
        "body_weight_change":
            horse_detail[
                "body_weight_change"
            ],
        "jockey": horse_detail[
            "jockey"
        ],
        "carried_weight":
            horse_detail[
                "carried_weight"
            ],
    }


def extract_finishers(soup):
    table = find_result_table(
        soup
    )

    if not table:
        return []

    finishers = []

    for row in table.find_all("tr"):
        result = (
            parse_mobile_result_row(
                row
            )
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
# コーナー通過順位
# ============================================================

def extract_corner_orders(soup):
    result = {}

    target_table = None

    for table in soup.find_all(
        "table"
    ):
        classes = set(
            table.get(
                "class",
                [],
            )
        )

        if (
            "RaceCommon_Table"
            in classes
            and "Corner_Num"
            in classes
        ):
            target_table = table
            break

    if not target_table:
        return result

    for row in target_table.find_all(
        "tr"
    ):
        cells = row.find_all(
            ["th", "td"],
            recursive=False,
        )

        if len(cells) < 2:
            continue

        label = clean_text(
            cells[0].get_text(
                " ",
                strip=True,
            )
        )

        order = clean_text(
            cells[1].get_text(
                " ",
                strip=True,
            )
        )

        match = re.search(
            r"([1-4])\s*コーナー",
            label,
        )

        if not match:
            continue

        corner_number = int(
            match.group(1)
        )

        result[
            f"{corner_number}_corner"
        ] = order

    return result


# ============================================================
# ラップ
# ============================================================

def extract_laps(soup):
    target_table = None

    for table in soup.find_all(
        "table"
    ):
        classes = set(
            table.get(
                "class",
                [],
            )
        )

        if (
            "RaceCommon_Table"
            in classes
            and "Race_HaronTime"
            in classes
        ):
            target_table = table
            break

    if not target_table:
        # 旧PC版fallback
        selectors = [
            ".Race_HaronTime",
            ".HaronTime",
            ".LapTime",
            ".RaceLap",
        ]

        for selector in selectors:
            target_table = (
                soup.select_one(
                    selector
                )
            )

            if target_table:
                break

    if not target_table:
        return []

    laps = []

    # スマホ版:
    #
    # header:
    # 200m 400m 600m 800m
    #
    # data:
    # 12.0 12.0
    # 22.8 10.8
    # 34.3 11.5
    # 46.0 11.7
    #
    # 各セルの最後の値だけが
    # その区間のラップ。
    for row in target_table.find_all(
        "tr"
    ):
        cells = row.find_all(
            ["td", "th"],
            recursive=False,
        )

        if not cells:
            continue

        row_texts = [
            clean_text(
                cell.get_text(
                    " ",
                    strip=True,
                )
            )
            for cell in cells
        ]

        # 距離見出し行は除外
        if all(
            (
                not text
                or re.fullmatch(
                    r"\d{3,4}m",
                    text,
                )
            )
            for text in row_texts
        ):
            continue

        for text in row_texts:
            if not text:
                continue

            values = re.findall(
                r"(?<!\d)"
                r"(\d{2}\.\d)"
                r"(?!\d)",
                text,
            )

            if not values:
                continue

            # 累計時計ではなく
            # セル内最後の値＝区間ラップ
            try:
                value = float(
                    values[-1]
                )
            except Exception:
                continue

            if 9.0 <= value <= 20.0:
                laps.append(
                    value
                )

    return laps


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

    # 前半の方が速い
    if difference <= -1.0:
        return "ハイ"

    # 後半の方が速い
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

    race_name = extract_race_name(
        soup
    )

    race_data_text = (
        extract_race_data_text(
            soup
        )
    )

    (
        surface,
        distance,
    ) = extract_surface_and_distance(
        race_data_text
    )

    # Race_Dataで取れない場合のみ
    # ページ全体をfallback
    if (
        not surface
        or distance is None
    ):
        page_text = clean_text(
            soup.get_text(
                " ",
                strip=True,
            )
        )

        (
            surface,
            distance,
        ) = extract_surface_and_distance(
            page_text
        )

    track_condition = (
        extract_track_condition(
            race_data_text,
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

    corner_orders = (
        extract_corner_orders(
            soup
        )
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
        "race_id": race_id,
        "race_number": race_number,
        "race_name": race_name,
        "surface": surface,
        "distance": distance,
        "track_condition":
            track_condition,
        "finished": finished,
        "finisher_count":
            len(finishers),
        "winner_time":
            winner_time,
        "winner_last3f":
            winner_last3f,
        "laps": laps,
        "pace": pace,
        "corner_orders":
            corner_orders,
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

        info["source"] = "netkeiba"
        info["source_url"] = url

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
            info["track_condition"],
            "finished:",
            info["finished"],
            "finishers:",
            info["finisher_count"],
            "laps:",
            len(info["laps"]),
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

            print(
                "  corners:",
                info.get(
                    "corner_orders"
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
        bool(args.include_target),

    "eligible_race_numbers":
        eligible_numbers,

    "future_race_usage":
        False,

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
