import json
import os
import re
import statistics
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup


# =========================================================
# 設定
# =========================================================

RACE_FILE = "race.json"
DAY_RACES_FILE = "day_races.json"
HISTORY_DB_FILE = "history_db.json"
OUTPUT_FILE = "day_time_history.json"

MAX_HISTORY_PER_CONDITION = 15
MIN_HISTORY_PER_CONDITION = 5
LOOKBACK_DAYS = 365

REQUEST_WAIT = 0.20
DATE_WAIT = 0.15

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

JST = timezone(timedelta(hours=9))

# JRA race_id
# YYYY + 場コード2桁 + 回 + 日 + R
VENUE_CODE_MAP = {
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


# =========================================================
# JSON
# =========================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default

    try:
        with open(
            path,
            "r",
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception:
        return {} if default is None else default


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 基本
# =========================================================

def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def normalize_surface(value):
    text = clean_text(value)

    if "芝" in text:
        return "芝"

    if "ダ" in text:
        return "ダート"

    if "障" in text:
        return "障害"

    return text


def safe_int(value):
    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return 0


def parse_date(value):
    try:
        return datetime.strptime(
            str(value),
            "%Y-%m-%d",
        ).date()

    except (
        TypeError,
        ValueError,
    ):
        return None


def race_time_to_seconds(value):
    value = clean_text(value)

    match = re.fullmatch(
        r"(\d+):(\d{2})\.(\d)",
        value,
    )

    if not match:
        return None

    minute = int(
        match.group(1)
    )

    second = int(
        match.group(2)
    )

    tenth = int(
        match.group(3)
    )

    return round(
        minute * 60
        + second
        + tenth / 10,
        1,
    )


# =========================================================
# race_id
# =========================================================

def venue_from_race_id(race_id):
    race_id = clean_text(
        race_id
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id,
    ):
        return ""

    venue_code = race_id[
        4:6
    ]

    return VENUE_CODE_MAP.get(
        venue_code,
        "",
    )


def meeting_key(race_id):
    """
    race_idのR番号2桁を除いた10桁。
    同一開催日をまとめて除外するために使用。
    """

    race_id = clean_text(
        race_id
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id,
    ):
        return ""

    return race_id[:10]


# =========================================================
# HTTP
# =========================================================

def get_html(
    url,
    params=None,
):
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
    )

    return response.text


def extract_race_ids(html):
    ids = re.findall(
        r"race_id=(\d{12})",
        html,
    )

    ids += re.findall(
        r"/race/(?:result/)?(\d{12})",
        html,
    )

    output = []
    seen = set()

    for race_id in ids:
        if race_id in seen:
            continue

        seen.add(
            race_id
        )

        output.append(
            race_id
        )

    return output


def find_races_from_date(
    date_string,
):
    html = get_html(
        (
            "https://race.netkeiba.com/"
            "top/race_list.html"
        ),
        {
            "kaisai_date": (
                date_string
            ),
        },
    )

    return extract_race_ids(
        html
    )


# =========================================================
# grade
# =========================================================

def normalize_grade_text(value):
    text = str(
        value or ""
    )

    text = (
        text
        .replace("Ｇ", "G")
        .replace("Ⅰ", "I")
        .replace("Ⅱ", "II")
        .replace("Ⅲ", "III")
        .replace("１", "1")
        .replace("２", "2")
        .replace("３", "3")
    )

    return re.sub(
        r"\s+",
        "",
        text,
    ).upper()


def grade_from_text(value):
    text = normalize_grade_text(
        value
    )

    if not text:
        return ""

    checks = [
        (
            r"(^|[^A-Z0-9])G(?:3|III)([^A-Z0-9]|$)",
            "G3",
        ),
        (
            r"(^|[^A-Z0-9])G(?:2|II)([^A-Z0-9]|$)",
            "G2",
        ),
        (
            r"(^|[^A-Z0-9])G(?:1|I)([^A-Z0-9]|$)",
            "G1",
        ),
    ]

    for pattern, label in checks:
        if re.search(
            pattern,
            text,
        ):
            return label

    if text in {
        "L",
        "LISTED",
    }:
        return "L"

    return ""


def extract_grade(soup):
    candidates = []

    for tag in soup.find_all(
        True
    ):
        classes = " ".join(
            tag.get(
                "class",
                [],
            )
        )

        if (
            "grade"
            not in classes.lower()
            and "icon"
            not in classes.lower()
            and not tag.has_attr(
                "data-grade"
            )
        ):
            continue

        text = tag.get_text(
            " ",
            strip=True,
        )

        if text:
            candidates.append(
                text
            )

        if classes:
            candidates.append(
                classes
            )

        for attr in [
            "title",
            "alt",
            "aria-label",
            "data-grade",
        ]:
            value = tag.get(
                attr
            )

            if value:
                candidates.append(
                    value
                )

    for value in candidates:
        grade = grade_from_text(
            value
        )

        if grade:
            return grade

    return ""


# =========================================================
# クラス
# =========================================================

def normalize_race_class(
    race_name,
    race_info_text,
    grade="",
):
    if grade in {
        "G1",
        "G2",
        "G3",
        "L",
    }:
        return grade

    text = (
        f"{race_name} "
        f"{race_info_text}"
    ).replace(
        "　",
        " ",
    )

    normalized = (
        normalize_grade_text(
            text
        )
    )

    checks = [
        (
            r"GIII|G3",
            "G3",
        ),
        (
            r"GII|G2",
            "G2",
        ),
        (
            r"GI|G1",
            "G1",
        ),
    ]

    for pattern, label in checks:
        if re.search(
            pattern,
            normalized,
        ):
            return label

    if "リステッド" in text:
        return "L"

    if (
        "オープン" in text
        or re.search(
            r"\bOP\b",
            text.upper(),
        )
    ):
        return "OP"

    checks = [
        (
            r"3\s*勝|３\s*勝",
            "3勝クラス",
        ),
        (
            r"2\s*勝|２\s*勝",
            "2勝クラス",
        ),
        (
            r"1\s*勝|１\s*勝",
            "1勝クラス",
        ),
    ]

    for pattern, label in checks:
        if re.search(
            pattern,
            text,
        ):
            return label

    if "未勝利" in text:
        return "未勝利"

    if "新馬" in text:
        return "新馬"

    return ""


# =========================================================
# 年齢
# =========================================================

def extract_age_condition(
    race_name,
    race_info_text,
):
    text = (
        f"{race_name} "
        f"{race_info_text}"
    ).replace(
        "　",
        " ",
    )

    checks = [
        (
            r"(?:2|２)\s*歳以上",
            "2歳以上",
        ),
        (
            r"(?:3|３)\s*歳以上",
            "3歳以上",
        ),
        (
            r"(?:4|４)\s*歳以上",
            "4歳以上",
        ),
        (
            r"(?:2|２)\s*歳",
            "2歳",
        ),
        (
            r"(?:3|３)\s*歳",
            "3歳",
        ),
        (
            r"(?:4|４)\s*歳",
            "4歳",
        ),
    ]

    for pattern, label in checks:
        if re.search(
            pattern,
            text,
        ):
            return label

    return ""


# =========================================================
# レースページ
# =========================================================

def parse_race_page(
    race_id,
):
    html = get_html(
        "https://race.sp.netkeiba.com/",
        {
            "pid": "race_result",
            "race_id": race_id,
        },
    )

    soup = BeautifulSoup(
        html,
        "html.parser",
    )

    page_text = soup.get_text(
        " ",
        strip=True,
    )

    race_name = ""

    for selector in [
        "h1.Race_Name",
        ".Race_Name",
        ".RaceName",
    ]:
        element = soup.select_one(
            selector
        )

        if element:
            race_name = (
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if race_name:
                break

    race_info_text = ""

    for selector in [
        "p.Race_Info",
        ".Race_Info",
        ".RaceInfo",
    ]:
        element = soup.select_one(
            selector
        )

        if element:
            race_info_text = (
                element.get_text(
                    " ",
                    strip=True,
                )
            )

            if race_info_text:
                break

    surface = ""
    distance = 0

    for pattern in [
        r"(芝|ダート|ダ)\s*(\d{3,4})\s*[mｍ]",
        r"(芝|ダート|ダ)\s*(\d{3,4})",
    ]:
        match = re.search(
            pattern,
            page_text,
        )

        if match:
            surface = (
                normalize_surface(
                    match.group(1)
                )
            )

            distance = int(
                match.group(2)
            )

            break

    track_condition = ""

    for pattern in [
        r"芝\s*[:：]?\s*(良|稍重|重|不良)",
        r"ダート\s*[:：]?\s*(良|稍重|重|不良)",
        r"馬場(?:状態)?\s*[:：]?\s*(良|稍重|重|不良)",
    ]:
        match = re.search(
            pattern,
            page_text,
        )

        if match:
            track_condition = (
                match.group(1)
            )

            break

    grade = extract_grade(
        soup
    )

    race_class = (
        normalize_race_class(
            race_name,
            race_info_text,
            grade,
        )
    )

    age_condition = (
        extract_age_condition(
            race_name,
            race_info_text,
        )
    )

    winner_time = ""

    for rank_element in soup.select(
        ".Result_Num"
    ):
        rank_text = (
            rank_element.get_text(
                " ",
                strip=True,
            )
        )

        if not re.fullmatch(
            r"1\s*着",
            rank_text,
        ):
            continue

        row = rank_element.find_parent(
            "tr"
        )

        if row:
            match = re.search(
                r"\d+:\d{2}\.\d",
                row.get_text(
                    " ",
                    strip=True,
                ),
            )

            if match:
                winner_time = (
                    match.group()
                )

        break

    return {
        "race_id": race_id,

        # ページ本文から競馬場名を拾わず、
        # race_idのJRA場コードから確定
        "racecourse": (
            venue_from_race_id(
                race_id
            )
        ),

        "surface": surface,
        "distance": distance,

        "track_condition": (
            track_condition
        ),

        "race_name": race_name,

        "race_info_text": (
            race_info_text
        ),

        "race_class": (
            race_class
        ),

        "age_condition": (
            age_condition
        ),

        "winner_time": (
            winner_time
        ),

        "winner_time_seconds": (
            race_time_to_seconds(
                winner_time
            )
        ),
    }


# =========================================================
# history_db
# =========================================================

def iter_history_db_rows(data):
    if isinstance(
        data,
        list,
    ):
        for row in data:
            if isinstance(
                row,
                dict,
            ):
                yield row

        return

    if not isinstance(
        data,
        dict,
    ):
        return

    for key in [
        "races",
        "history",
        "histories",
        "data",
        "records",
    ]:
        value = data.get(
            key
        )

        if not isinstance(
            value,
            list,
        ):
            continue

        for row in value:
            if isinstance(
                row,
                dict,
            ):
                yield row


def extract_winner_from_db(
    row,
):
    winner_time = clean_text(
        row.get(
            "winner_time"
        )
    )

    if winner_time:
        return winner_time

    for result in (
        row.get(
            "results",
            [],
        )
        or []
    ):
        finish = safe_int(
            result.get(
                "finish"
            )
            or result.get(
                "rank"
            )
        )

        if finish != 1:
            continue

        return clean_text(
            result.get(
                "race_time"
            )
            or result.get(
                "time"
            )
        )

    return ""


def normalize_history_row(
    row,
):
    race_id = clean_text(
        row.get(
            "race_id"
        )
    )

    return {
        "race_id": race_id,

        "race_date": clean_text(
            row.get(
                "race_date"
            )
            or row.get(
                "date"
            )
        ),

        "racecourse": clean_text(
            row.get(
                "racecourse"
            )
            or row.get(
                "track"
            )
            or venue_from_race_id(
                race_id
            )
        ),

        "surface": (
            normalize_surface(
                row.get(
                    "surface"
                )
            )
        ),

        "distance": safe_int(
            row.get(
                "distance"
            )
        ),

        "race_class": clean_text(
            row.get(
                "race_class"
            )
        ),

        "age_condition": clean_text(
            row.get(
                "age_condition"
            )
        ),

        "race_name": clean_text(
            row.get(
                "race_name"
            )
        ),

        "track_condition": clean_text(
            row.get(
                "track_condition"
            )
        ),

        "winner_time": (
            extract_winner_from_db(
                row
            )
        ),
    }


def same_condition(
    row,
    condition,
):
    return (
        row.get(
            "racecourse"
        )
        == condition[
            "racecourse"
        ]
        and row.get(
            "surface"
        )
        == condition[
            "surface"
        ]
        and row.get(
            "distance"
        )
        == condition[
            "distance"
        ]
        and row.get(
            "race_class"
        )
        == condition[
            "race_class"
        ]
        and row.get(
            "age_condition"
        )
        == condition[
            "age_condition"
        ]
    )


# =========================================================
# 入力
# =========================================================

race = load_json(
    RACE_FILE
)

day_races = load_json(
    DAY_RACES_FILE
)

history_db = load_json(
    HISTORY_DB_FILE,
    {},
)

old_output = load_json(
    OUTPUT_FILE,
    {},
)

if not race:
    raise RuntimeError(
        "race.json がありません"
    )

if not day_races:
    raise RuntimeError(
        "day_races.json がありません"
    )


target_race_id = clean_text(
    race.get(
        "race_id"
    )
)

target_date_text = clean_text(
    race.get(
        "race_date"
    )
    or race.get(
        "date"
    )
)

target_date = parse_date(
    target_date_text
)

racecourse = clean_text(
    race.get(
        "racecourse"
    )
    or race.get(
        "track"
    )
    or venue_from_race_id(
        target_race_id
    )
)

target_surface = (
    normalize_surface(
        race.get(
            "surface"
        )
    )
)

target_race_number = (
    safe_int(
        target_race_id[-2:]
    )
)

target_meeting_key = (
    meeting_key(
        target_race_id
    )
)

if not re.fullmatch(
    r"\d{12}",
    target_race_id,
):
    raise RuntimeError(
        "race_id が不正です"
    )

if target_date is None:
    raise RuntimeError(
        "race_date が不正です"
    )

if not racecourse:
    raise RuntimeError(
        "競馬場を取得できません"
    )


# =========================================================
# 当日レースID
# =========================================================

same_day_ids = {
    target_race_id
}

for item in (
    day_races.get(
        "collected_races",
        [],
    )
    or []
):
    race_id = clean_text(
        item.get(
            "race_id"
        )
    )

    if race_id:
        same_day_ids.add(
            race_id
        )


# =========================================================
# 当日参考レース
# =========================================================

reference_races = []

for item in (
    day_races.get(
        "collected_races",
        [],
    )
    or []
):
    race_number = safe_int(
        item.get(
            "race_number"
        )
    )

    if race_number <= 0:
        continue

    # 対象R以降は使用禁止
    if (
        race_number
        >= target_race_number
    ):
        continue

    surface = normalize_surface(
        item.get(
            "surface"
        )
    )

    if (
        surface
        != target_surface
    ):
        continue

    distance = safe_int(
        item.get(
            "distance"
        )
    )

    if distance <= 0:
        continue

    winner = None

    for result in (
        item.get(
            "results",
            [],
        )
        or []
    ):
        if safe_int(
            result.get(
                "finish"
            )
        ) == 1:
            winner = result
            break

    if winner is None:
        continue

    winner_time = clean_text(
        winner.get(
            "race_time"
        )
    )

    winner_seconds = (
        race_time_to_seconds(
            winner_time
        )
    )

    if winner_seconds is None:
        continue

    reference_races.append({
        "race_id": clean_text(
            item.get(
                "race_id"
            )
        ),

        "race_number": (
            race_number
        ),

        "surface": (
            surface
        ),

        "distance": (
            distance
        ),

        "track_condition": (
            clean_text(
                item.get(
                    "track_condition"
                )
            )
        ),

        "winner_time": (
            winner_time
        ),

        "winner_time_seconds": (
            winner_seconds
        ),
    })


print(
    "=============================="
)

print(
    "DAY TIME HISTORY SAFE"
)

print(
    "target:",
    target_race_id,
)

print(
    "target date:",
    target_date_text,
)

print(
    "meeting exclusion:",
    target_meeting_key,
)

print(
    "reference races:",
    len(reference_races),
)

print(
    "=============================="
)


# =========================================================
# 当日参考レース metadata
# =========================================================

for reference in reference_races:
    try:
        info = parse_race_page(
            reference[
                "race_id"
            ]
        )

        reference[
            "race_name"
        ] = info.get(
            "race_name",
            "",
        )

        reference[
            "race_info_text"
        ] = info.get(
            "race_info_text",
            "",
        )

        reference[
            "race_class"
        ] = info.get(
            "race_class",
            "",
        )

        reference[
            "age_condition"
        ] = info.get(
            "age_condition",
            "",
        )

        if not reference[
            "track_condition"
        ]:
            reference[
                "track_condition"
            ] = info.get(
                "track_condition",
                "",
            )

        print(
            "REF:",
            f'{reference["race_number"]}R',
            reference[
                "distance"
            ],
            reference.get(
                "race_class"
            )
            or "class不明",
            reference.get(
                "age_condition"
            )
            or "age不明",
            reference[
                "winner_time"
            ],
        )

        time.sleep(
            REQUEST_WAIT
        )

    except Exception as exc:
        reference[
            "metadata_error"
        ] = str(
            exc
        )

        reference[
            "race_class"
        ] = ""

        reference[
            "age_condition"
        ] = ""


# =========================================================
# 必要な基準条件
# =========================================================

conditions = []
seen_conditions = set()

for reference in reference_races:
    race_class = clean_text(
        reference.get(
            "race_class"
        )
    )

    age_condition = clean_text(
        reference.get(
            "age_condition"
        )
    )

    if (
        not race_class
        or not age_condition
    ):
        continue

    key = (
        racecourse,
        target_surface,
        reference[
            "distance"
        ],
        race_class,
        age_condition,
    )

    if key in seen_conditions:
        continue

    seen_conditions.add(
        key
    )

    conditions.append({
        "racecourse": (
            racecourse
        ),

        "surface": (
            target_surface
        ),

        "distance": (
            reference[
                "distance"
            ]
        ),

        "race_class": (
            race_class
        ),

        "age_condition": (
            age_condition
        ),
    })


# =========================================================
# キャッシュ母集団
# =========================================================

cache_pool = []

# history_dbを最優先
for row in iter_history_db_rows(
    history_db
):
    cache_pool.append(
        normalize_history_row(
            row
        )
    )


# 既存day_time_historyも再利用
for history in (
    old_output.get(
        "histories",
        [],
    )
    or []
):
    for row in (
        history.get(
            "races",
            [],
        )
        or []
    ):
        merged = dict(
            row
        )

        merged[
            "racecourse"
        ] = history.get(
            "racecourse"
        )

        merged[
            "surface"
        ] = history.get(
            "surface"
        )

        merged[
            "distance"
        ] = history.get(
            "distance"
        )

        merged[
            "race_class"
        ] = history.get(
            "race_class"
        )

        merged[
            "age_condition"
        ] = history.get(
            "age_condition"
        )

        cache_pool.append(
            normalize_history_row(
                merged
            )
        )


# =========================================================
# 過去基準作成
# =========================================================

histories = []
errors = []

for condition in conditions:
    matched = []
    seen_ids = set()

    # -----------------------------------------------------
    # 共通追加処理
    # -----------------------------------------------------

    def add_candidate(
        row,
    ):
        race_id = clean_text(
            row.get(
                "race_id"
            )
        )

        if not race_id:
            return False

        if race_id in seen_ids:
            return False

        # 当日レース完全除外
        if race_id in same_day_ids:
            return False

        # 同一開催キー完全除外
        if (
            meeting_key(
                race_id
            )
            == target_meeting_key
        ):
            return False

        # race_idの場コードで競馬場を確認
        if (
            venue_from_race_id(
                race_id
            )
            != condition[
                "racecourse"
            ]
        ):
            return False

        if not same_condition(
            row,
            condition,
        ):
            return False

        winner_seconds = (
            race_time_to_seconds(
                row.get(
                    "winner_time"
                )
            )
        )

        if winner_seconds is None:
            return False

        row_date = parse_date(
            row.get(
                "race_date"
            )
        )

        # 日付が取れている場合は
        # 対象日以降を完全除外
        if (
            row_date is not None
            and row_date
            >= target_date
        ):
            return False

        seen_ids.add(
            race_id
        )

        matched.append({
            "race_id": (
                race_id
            ),

            "race_date": (
                clean_text(
                    row.get(
                        "race_date"
                    )
                )
            ),

            "race_name": (
                clean_text(
                    row.get(
                        "race_name"
                    )
                )
            ),

            "race_class": (
                condition[
                    "race_class"
                ]
            ),

            "age_condition": (
                condition[
                    "age_condition"
                ]
            ),

            "track_condition": (
                clean_text(
                    row.get(
                        "track_condition"
                    )
                )
            ),

            "winner_time": (
                clean_text(
                    row.get(
                        "winner_time"
                    )
                )
            ),

            "winner_time_seconds": (
                winner_seconds
            ),
        })

        return True

    # -----------------------------------------------------
    # キャッシュ
    # -----------------------------------------------------

    for row in cache_pool:
        add_candidate(
            row
        )

    matched.sort(
        key=lambda row: (
            row.get(
                "race_date",
                "",
            ),
            row.get(
                "race_id",
                "",
            ),
        ),
        reverse=True,
    )

    matched = matched[
        :MAX_HISTORY_PER_CONDITION
    ]

    cache_count = len(
        matched
    )

    print(
        "CACHE:",
        condition[
            "distance"
        ],
        condition[
            "race_class"
        ],
        condition[
            "age_condition"
        ],
        cache_count,
    )

    # -----------------------------------------------------
    # キャッシュ5件以上なら検索しない
    # -----------------------------------------------------

    if (
        len(matched)
        < MIN_HISTORY_PER_CONDITION
    ):
        print(
            "SEARCH:",
            condition[
                "distance"
            ],
            condition[
                "race_class"
            ],
            condition[
                "age_condition"
            ],
        )

        for days_back in range(
            1,
            LOOKBACK_DAYS + 1,
        ):
            if (
                len(matched)
                >= MAX_HISTORY_PER_CONDITION
            ):
                break

            search_date = (
                target_date
                - timedelta(
                    days=days_back
                )
            )

            # search_dateは必ずtarget_date未満
            if (
                search_date
                >= target_date
            ):
                continue

            date_string = (
                search_date.strftime(
                    "%Y%m%d"
                )
            )

            try:
                race_ids = (
                    find_races_from_date(
                        date_string
                    )
                )

            except Exception as exc:
                errors.append({
                    "date": (
                        search_date.isoformat()
                    ),

                    "condition": (
                        condition
                    ),

                    "error": (
                        str(exc)
                    ),
                })

                continue

            # -------------------------------------------------
            # race_id場コードで先に対象競馬場だけ残す
            # ここで他場のページ取得を防ぐ
            # -------------------------------------------------

            race_ids = [
                race_id
                for race_id in race_ids
                if (
                    venue_from_race_id(
                        race_id
                    )
                    == condition[
                        "racecourse"
                    ]
                )
            ]

            for history_race_id in race_ids:
                if (
                    len(matched)
                    >= MAX_HISTORY_PER_CONDITION
                ):
                    break

                if (
                    history_race_id
                    in seen_ids
                ):
                    continue

                if (
                    history_race_id
                    in same_day_ids
                ):
                    continue

                if (
                    meeting_key(
                        history_race_id
                    )
                    == target_meeting_key
                ):
                    continue

                try:
                    info = (
                        parse_race_page(
                            history_race_id
                        )
                    )

                    row = {
                        **info,

                        "race_date": (
                            search_date.isoformat()
                        ),
                    }

                    added = add_candidate(
                        row
                    )

                    if added:
                        print(
                            " MATCH:",
                            history_race_id,
                            search_date.isoformat(),
                            info.get(
                                "winner_time"
                            ),
                        )

                    time.sleep(
                        REQUEST_WAIT
                    )

                except Exception as exc:
                    errors.append({
                        "race_id": (
                            history_race_id
                        ),

                        "condition": (
                            condition
                        ),

                        "error": (
                            str(exc)
                        ),
                    })

            time.sleep(
                DATE_WAIT
            )

    # -----------------------------------------------------
    # 最終整列
    # -----------------------------------------------------

    matched.sort(
        key=lambda row: (
            row.get(
                "race_date",
                "",
            ),
            row.get(
                "race_id",
                "",
            ),
        ),
        reverse=True,
    )

    matched = matched[
        :MAX_HISTORY_PER_CONDITION
    ]

    times = [
        row[
            "winner_time_seconds"
        ]
        for row in matched
    ]

    median_seconds = (
        round(
            statistics.median(
                times
            ),
            2,
        )
        if times
        else None
    )

    histories.append({
        **condition,

        "cache_used": (
            cache_count
            >= MIN_HISTORY_PER_CONDITION
        ),

        "cache_sample_count": (
            cache_count
        ),

        "sample_count": (
            len(times)
        ),

        "median_winner_time_seconds": (
            median_seconds
        ),

        "races": (
            matched
        ),
    })

    print(
        "BASELINE:",
        condition[
            "distance"
        ],
        condition[
            "race_class"
        ],
        condition[
            "age_condition"
        ],
        "n=",
        len(times),
        "median=",
        median_seconds,
    )


# =========================================================
# 当日参考レースと基準を接続
# =========================================================

for reference in reference_races:
    reference[
        "baseline_connected"
    ] = False

    reference[
        "baseline_sample_count"
    ] = 0

    reference[
        "baseline_median_seconds"
    ] = None

    reference[
        "time_delta_seconds"
    ] = None

    for history in histories:
        if (
            history[
                "racecourse"
            ]
            != racecourse
        ):
            continue

        if (
            history[
                "surface"
            ]
            != reference[
                "surface"
            ]
        ):
            continue

        if (
            history[
                "distance"
            ]
            != reference[
                "distance"
            ]
        ):
            continue

        if (
            history[
                "race_class"
            ]
            != reference.get(
                "race_class"
            )
        ):
            continue

        if (
            history[
                "age_condition"
            ]
            != reference.get(
                "age_condition"
            )
        ):
            continue

        sample_count = safe_int(
            history.get(
                "sample_count"
            )
        )

        median_seconds = (
            history.get(
                "median_winner_time_seconds"
            )
        )

        if (
            sample_count
            < MIN_HISTORY_PER_CONDITION
            or median_seconds is None
        ):
            break

        reference[
            "baseline_connected"
        ] = True

        reference[
            "baseline_sample_count"
        ] = sample_count

        reference[
            "baseline_median_seconds"
        ] = median_seconds

        # マイナス = 基準より速い
        # プラス   = 基準より遅い
        reference[
            "time_delta_seconds"
        ] = round(
            reference[
                "winner_time_seconds"
            ]
            - median_seconds,
            2,
        )

        break


# =========================================================
# 最終安全確認
# =========================================================

leak_race_ids = []

for history in histories:
    for row in (
        history.get(
            "races",
            [],
        )
        or []
    ):
        race_id = clean_text(
            row.get(
                "race_id"
            )
        )

        row_date = parse_date(
            row.get(
                "race_date"
            )
        )

        if (
            race_id
            in same_day_ids
        ):
            leak_race_ids.append(
                race_id
            )

        elif (
            meeting_key(
                race_id
            )
            == target_meeting_key
        ):
            leak_race_ids.append(
                race_id
            )

        elif (
            row_date is not None
            and row_date
            >= target_date
        ):
            leak_race_ids.append(
                race_id
            )


leak_race_ids = sorted(
    set(
        leak_race_ids
    )
)

if leak_race_ids:
    raise RuntimeError(
        "時計基準に対象日以降または"
        "同一開催レースが混入: "
        + ",".join(
            leak_race_ids
        )
    )


# =========================================================
# 保存
# =========================================================

connected_count = sum(
    1
    for row in reference_races
    if row.get(
        "baseline_connected"
    )
)

output = {
    "updated_at": (
        datetime.now(
            JST
        ).isoformat()
    ),

    "target_race_id": (
        target_race_id
    ),

    "race_date": (
        target_date_text
    ),

    "racecourse": (
        racecourse
    ),

    "surface": (
        target_surface
    ),

    "future_race_usage": (
        False
    ),

    "same_day_excluded": (
        True
    ),

    "same_meeting_excluded": (
        True
    ),

    "excluded_meeting_key": (
        target_meeting_key
    ),

    "venue_validation_by_race_id": (
        True
    ),

    "minimum_history_sample": (
        MIN_HISTORY_PER_CONDITION
    ),

    "reference_race_count": (
        len(reference_races)
    ),

    "baseline_connected_count": (
        connected_count
    ),

    "reference_races": (
        reference_races
    ),

    "histories": (
        histories
    ),

    "leak_check_passed": (
        True
    ),

    "leak_race_ids": (
        []
    ),

    "error_count": (
        len(errors)
    ),

    "errors": (
        errors
    ),
}

save_json(
    OUTPUT_FILE,
    output,
)


# =========================================================
# ログ
# =========================================================

print(
    "=============================="
)

print(
    "DAY TIME HISTORY RESULT"
)

print(
    "saved:",
    OUTPUT_FILE,
)

print(
    "reference:",
    len(reference_races),
)

print(
    "baseline connected:",
    f"{connected_count}/{len(reference_races)}",
)

print(
    "same day excluded:",
    True,
)

print(
    "same meeting excluded:",
    True,
)

print(
    "leak check:",
    "PASS",
)

for reference in reference_races:
    print(
        (
            f'{reference["race_number"]}R '
            f'{reference["distance"]}m '
            f'{reference.get("race_class") or "class不明"} '
            f'{reference.get("age_condition") or "age不明"} '
            f'actual={reference["winner_time"]} '
            f'baseline={reference.get("baseline_median_seconds")} '
            f'delta={reference.get("time_delta_seconds")} '
            f'n={reference.get("baseline_sample_count")}'
        )
    )

print(
    "errors:",
    len(errors),
)

print(
    "=============================="
)
