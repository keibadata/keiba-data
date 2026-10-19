import json
import os
import re
import time
import statistics
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
DAY_RACES_FILE = "day_races.json"
OUTPUT_FILE = "day_time_history.json"

MAX_HISTORY_PER_CONDITION = 15
MIN_HISTORY_PER_CONDITION = 5
LOOKBACK_DAYS = 365

REQUEST_WAIT = 0.35
DATE_WAIT = 0.45

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}

JST = timezone(
    timedelta(hours=9)
)


# =========================================================
# JSON
# =========================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default

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
            indent=2,
        )


# =========================================================
# normalize
# =========================================================

def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "")
    ).strip()


def normalize_surface(value):
    value = clean_text(value)

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    if "障" in value:
        return "障害"

    return value


def normalize_track(value):
    return clean_text(value)


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
            "%Y-%m-%d"
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
        value
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
        1
    )


# =========================================================
# HTTP
# =========================================================

def get_html(url, params=None):
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


# =========================================================
# race id
# =========================================================

def extract_race_ids(html):
    ids = re.findall(
        r"race_id=(\d{12})",
        html
    )

    ids += re.findall(
        r"/race/(?:result/)?(\d{12})",
        html
    )

    output = []
    seen = set()

    for race_id in ids:
        if race_id in seen:
            continue

        seen.add(race_id)
        output.append(race_id)

    return output


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
        text
    ).upper()


def grade_from_text(value):
    text = normalize_grade_text(
        value
    )

    if not text:
        return ""

    # 長い表記から先に判定
    if re.search(
        r"(^|[^A-Z0-9])G(?:3|III)([^A-Z0-9]|$)",
        text
    ):
        return "G3"

    if re.search(
        r"(^|[^A-Z0-9])G(?:2|II)([^A-Z0-9]|$)",
        text
    ):
        return "G2"

    if re.search(
        r"(^|[^A-Z0-9])G(?:1|I)([^A-Z0-9]|$)",
        text
    ):
        return "G1"

    if text in {
        "GIII",
        "G3",
    }:
        return "G3"

    if text in {
        "GII",
        "G2",
    }:
        return "G2"

    if text in {
        "GI",
        "G1",
    }:
        return "G1"

    if text in {
        "L",
        "LISTED",
    }:
        return "L"

    return ""


def extract_grade(soup):
    candidates = []

    for tag in soup.find_all(True):
        classes = " ".join(
            tag.get(
                "class",
                []
            )
        )

        if (
            "grade" not in classes.lower()
            and "icon" not in classes.lower()
            and not tag.has_attr(
                "data-grade"
            )
        ):
            continue

        text = tag.get_text(
            " ",
            strip=True
        )

        if text:
            candidates.append(text)

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
# class / age
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
        " "
    )

    normalized = (
        normalize_grade_text(
            text
        )
    )

    if re.search(
        r"\bGIII\b|\bG3\b",
        normalized
    ):
        return "G3"

    if re.search(
        r"\bGII\b|\bG2\b",
        normalized
    ):
        return "G2"

    if re.search(
        r"\bGI\b|\bG1\b",
        normalized
    ):
        return "G1"

    if (
        "リステッド" in text
        or re.search(
            r"\bL\b",
            normalized
        )
    ):
        return "L"

    if (
        "オープン" in text
        or re.search(
            r"\bOP\b",
            text.upper()
        )
    ):
        return "OP"

    if re.search(
        r"3\s*勝|３\s*勝",
        text
    ):
        return "3勝クラス"

    if re.search(
        r"2\s*勝|２\s*勝",
        text
    ):
        return "2勝クラス"

    if re.search(
        r"1\s*勝|１\s*勝",
        text
    ):
        return "1勝クラス"

    if "未勝利" in text:
        return "未勝利"

    if "新馬" in text:
        return "新馬"

    return ""


def extract_age_condition(
    race_name,
    race_info_text,
):
    text = (
        f"{race_name} "
        f"{race_info_text}"
    ).replace(
        "　",
        " "
    )

    patterns = [
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

    for pattern, label in patterns:
        if re.search(
            pattern,
            text
        ):
            return label

    return ""


# =========================================================
# race page
# =========================================================

def parse_race_page(race_id):
    html = get_html(
        "https://race.sp.netkeiba.com/",
        {
            "pid": "race_result",
            "race_id": race_id,
        },
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    page_text = soup.get_text(
        " ",
        strip=True
    )

    # -----------------------------------------------------
    # name
    # -----------------------------------------------------

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
            race_name = element.get_text(
                " ",
                strip=True
            )

            if race_name:
                break

    # -----------------------------------------------------
    # info
    # -----------------------------------------------------

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
                    strip=True
                )
            )

            if race_info_text:
                break

    # -----------------------------------------------------
    # track
    # -----------------------------------------------------

    racecourse = ""

    for name in [
        "札幌",
        "函館",
        "福島",
        "新潟",
        "東京",
        "中山",
        "中京",
        "京都",
        "阪神",
        "小倉",
    ]:
        if name in page_text:
            racecourse = name
            break

    # -----------------------------------------------------
    # surface / distance
    # -----------------------------------------------------

    surface = ""
    distance = 0

    patterns = [
        r"(芝|ダート|ダ)\s*(\d{3,4})\s*[mｍ]",
        r"(芝|ダート|ダ)\s*(\d{3,4})",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            page_text
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

    # -----------------------------------------------------
    # track condition
    # -----------------------------------------------------

    track_condition = ""

    patterns = [
        r"芝\s*[:：]?\s*(良|稍重|重|不良)",
        r"ダート\s*[:：]?\s*(良|稍重|重|不良)",
        r"馬場(?:状態)?\s*[:：]?\s*(良|稍重|重|不良)",
    ]

    for pattern in patterns:
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
    # class / age
    # -----------------------------------------------------

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

    # -----------------------------------------------------
    # winner time
    # -----------------------------------------------------

    winner_time = ""

    rank_elements = (
        soup.select(
            ".Result_Num"
        )
    )

    for rank_element in rank_elements:
        rank_text = (
            rank_element.get_text(
                " ",
                strip=True
            )
        )

        if not re.fullmatch(
            r"1\s*着",
            rank_text
        ):
            continue

        row = rank_element.find_parent(
            "tr"
        )

        if row is None:
            continue

        for selector in [
            ".Time",
            ".RaceTime",
        ]:
            element = row.select_one(
                selector
            )

            if element:
                match = re.search(
                    r"\d+:\d{2}\.\d",
                    element.get_text(
                        " ",
                        strip=True
                    )
                )

                if match:
                    winner_time = (
                        match.group()
                    )
                    break

        if not winner_time:
            match = re.search(
                r"\d+:\d{2}\.\d",
                row.get_text(
                    " ",
                    strip=True
                )
            )

            if match:
                winner_time = (
                    match.group()
                )

        break

    return {
        "race_id": race_id,
        "racecourse": racecourse,
        "surface": surface,
        "distance": distance,
        "track_condition": (
            track_condition
        ),
        "race_name": race_name,
        "race_info_text": (
            race_info_text
        ),
        "race_class": race_class,
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
# date list
# =========================================================

def find_races_from_date(
    date_string
):
    html = get_html(
        (
            "https://race.netkeiba.com/"
            "top/race_list.html"
        ),
        {
            "kaisai_date": (
                date_string
            )
        },
    )

    return extract_race_ids(
        html
    )


# =========================================================
# target
# =========================================================

race = load_json(
    RACE_FILE
)

day_races = load_json(
    DAY_RACES_FILE
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
)

target_date = parse_date(
    target_date_text
)

racecourse = normalize_track(
    race.get(
        "racecourse"
    )
    or race.get(
        "track"
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

if not re.fullmatch(
    r"\d{12}",
    target_race_id
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
# 当日参考レース抽出
# =========================================================

reference_races = []

for item in (
    day_races.get(
        "collected_races",
        []
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

    # 未来情報禁止
    if race_number >= target_race_number:
        continue

    surface = normalize_surface(
        item.get(
            "surface"
        )
    )

    if surface != target_surface:
        continue

    distance = safe_int(
        item.get(
            "distance"
        )
    )

    if distance <= 0:
        continue

    results = (
        item.get(
            "results",
            []
        )
        or []
    )

    winner = None

    for result in results:
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

    winner_time_seconds = (
        race_time_to_seconds(
            winner_time
        )
    )

    if winner_time_seconds is None:
        continue

    reference_races.append({
        "race_id": clean_text(
            item.get(
                "race_id"
            )
        ),
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
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
            winner_time_seconds
        ),
    })


# =========================================================
# 当日参考レース metadata
# =========================================================

print(
    "=============================="
)
print(
    "DAY TIME HISTORY"
)
print(
    "target:",
    target_race_id
)
print(
    "reference races:",
    len(reference_races)
)
print(
    "=============================="
)


for reference in reference_races:
    race_id = reference[
        "race_id"
    ]

    try:
        info = parse_race_page(
            race_id
        )

        reference[
            "race_name"
        ] = info.get(
            "race_name",
            ""
        )

        reference[
            "race_info_text"
        ] = info.get(
            "race_info_text",
            ""
        )

        reference[
            "race_class"
        ] = info.get(
            "race_class",
            ""
        )

        reference[
            "age_condition"
        ] = info.get(
            "age_condition",
            ""
        )

        if not reference.get(
            "track_condition"
        ):
            reference[
                "track_condition"
            ] = info.get(
                "track_condition",
                ""
            )

        print(
            "REF:",
            reference[
                "race_number"
            ],
            "R",
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

    except Exception as e:
        reference[
            "metadata_error"
        ] = str(e)

        reference[
            "race_class"
        ] = ""

        reference[
            "age_condition"
        ] = ""


# =========================================================
# condition key
# =========================================================

conditions = []

seen_condition_keys = set()

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

    distance = safe_int(
        reference.get(
            "distance"
        )
    )

    # クラス/年齢が取れない場合は
    # 無理に時計基準を作らない
    if (
        not race_class
        or not age_condition
        or distance <= 0
    ):
        continue

    key = (
        racecourse,
        target_surface,
        distance,
        race_class,
        age_condition,
    )

    if key in seen_condition_keys:
        continue

    seen_condition_keys.add(
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
            distance
        ),
        "race_class": (
            race_class
        ),
        "age_condition": (
            age_condition
        ),
    })


# =========================================================
# 既存キャッシュ
# =========================================================

old_output = load_json(
    OUTPUT_FILE,
    {}
)

old_histories = (
    old_output.get(
        "histories",
        []
    )
    or []
)

cache_map = {}

for history in old_histories:
    key = (
        clean_text(
            history.get(
                "racecourse"
            )
        ),
        normalize_surface(
            history.get(
                "surface"
            )
        ),
        safe_int(
            history.get(
                "distance"
            )
        ),
        clean_text(
            history.get(
                "race_class"
            )
        ),
        clean_text(
            history.get(
                "age_condition"
            )
        ),
    )

    races = (
        history.get(
            "races",
            []
        )
        or []
    )

    if races:
        cache_map[key] = races


# =========================================================
# 過去時計収集
# =========================================================

histories = []

errors = []

for condition in conditions:
    key = (
        condition[
            "racecourse"
        ],
        condition[
            "surface"
        ],
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

    cached = (
        cache_map.get(
            key,
            []
        )
        or []
    )

    valid_cached = []

    for row in cached:
        race_date = parse_date(
            row.get(
                "race_date"
            )
        )

        if race_date is None:
            continue

        if race_date >= target_date:
            continue

        if (
            race_time_to_seconds(
                row.get(
                    "winner_time"
                )
            )
            is None
        ):
            continue

        valid_cached.append(
            row
        )

    if (
        len(valid_cached)
        >= MIN_HISTORY_PER_CONDITION
    ):
        selected = (
            valid_cached[
                :MAX_HISTORY_PER_CONDITION
            ]
        )

        times = [
            race_time_to_seconds(
                row[
                    "winner_time"
                ]
            )
            for row in selected
        ]

        times = [
            value
            for value in times
            if value is not None
        ]

        histories.append({
            **condition,
            "cache_used": True,
            "sample_count": (
                len(times)
            ),
            "median_winner_time_seconds": (
                round(
                    statistics.median(
                        times
                    ),
                    2
                )
                if times
                else None
            ),
            "races": selected,
        })

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
            len(times),
        )

        continue

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

    matched = []
    checked_ids = set()

    for days_back in range(
        1,
        LOOKBACK_DAYS + 1
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

        except Exception as e:
            errors.append({
                "date": (
                    date_string
                ),
                "condition": (
                    condition
                ),
                "error": str(e),
            })

            continue

        if not race_ids:
            continue

        for race_id in race_ids:
            if (
                len(matched)
                >= MAX_HISTORY_PER_CONDITION
            ):
                break

            if race_id in checked_ids:
                continue

            if race_id == target_race_id:
                continue

            checked_ids.add(
                race_id
            )

            try:
                info = (
                    parse_race_page(
                        race_id
                    )
                )

                if (
                    info[
                        "racecourse"
                    ]
                    != condition[
                        "racecourse"
                    ]
                ):
                    continue

                if (
                    info[
                        "surface"
                    ]
                    != condition[
                        "surface"
                    ]
                ):
                    continue

                if (
                    info[
                        "distance"
                    ]
                    != condition[
                        "distance"
                    ]
                ):
                    continue

                if (
                    info[
                        "race_class"
                    ]
                    != condition[
                        "race_class"
                    ]
                ):
                    continue

                if (
                    info[
                        "age_condition"
                    ]
                    != condition[
                        "age_condition"
                    ]
                ):
                    continue

                winner_seconds = (
                    info.get(
                        "winner_time_seconds"
                    )
                )

                if winner_seconds is None:
                    continue

                matched.append({
                    "race_id": (
                        race_id
                    ),
                    "race_date": (
                        search_date.isoformat()
                    ),
                    "race_name": (
                        info.get(
                            "race_name",
                            ""
                        )
                    ),
                    "race_class": (
                        info[
                            "race_class"
                        ]
                    ),
                    "age_condition": (
                        info[
                            "age_condition"
                        ]
                    ),
                    "track_condition": (
                        info.get(
                            "track_condition",
                            ""
                        )
                    ),
                    "winner_time": (
                        info[
                            "winner_time"
                        ]
                    ),
                    "winner_time_seconds": (
                        winner_seconds
                    ),
                })

                print(
                    "  MATCH:",
                    race_id,
                    search_date,
                    info[
                        "winner_time"
                    ],
                )

                time.sleep(
                    REQUEST_WAIT
                )

            except Exception as e:
                errors.append({
                    "race_id": (
                        race_id
                    ),
                    "condition": (
                        condition
                    ),
                    "error": str(e),
                })

        time.sleep(
            DATE_WAIT
        )

    matched.sort(
        key=lambda row: (
            row.get(
                "race_date",
                ""
            ),
            row.get(
                "race_id",
                ""
            ),
        ),
        reverse=True,
    )

    times = [
        row[
            "winner_time_seconds"
        ]
        for row in matched
        if row.get(
            "winner_time_seconds"
        )
        is not None
    ]

    histories.append({
        **condition,
        "cache_used": False,
        "sample_count": (
            len(times)
        ),
        "median_winner_time_seconds": (
            round(
                statistics.median(
                    times
                ),
                2
            )
            if times
            else None
        ),
        "races": matched,
    })


# =========================================================
# reference -> baseline 接続
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

        sample_count = (
            history.get(
                "sample_count",
                0
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
            continue

        reference[
            "baseline_connected"
        ] = True

        reference[
            "baseline_sample_count"
        ] = sample_count

        reference[
            "baseline_median_seconds"
        ] = median_seconds

        reference[
            "time_delta_seconds"
        ] = round(
            reference[
                "winner_time_seconds"
            ]
            - median_seconds,
            2
        )

        break


# =========================================================
# output
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
    "future_race_usage": False,
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
    "histories": histories,
    "error_count": (
        len(errors)
    ),
    "errors": errors,
}

save_json(
    OUTPUT_FILE,
    output
)

print(
    "=============================="
)
print(
    "saved:",
    OUTPUT_FILE
)
print(
    "reference:",
    len(reference_races)
)
print(
    "baseline connected:",
    connected_count,
    "/",
    len(reference_races)
)
print(
    "errors:",
    len(errors)
)
print(
    "=============================="
)
