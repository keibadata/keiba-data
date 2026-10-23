import json
import os
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
OUTPUT_FILE = "runner_history.json"

BASE_URL = "https://db.netkeiba.com/horse/result/{horse_id}/"

REQUEST_INTERVAL = 1.5
TIMEOUT = 25
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
}


def now_jst():
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).isoformat()


def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def load_json(path, default=None):
    if default is None:
        default = {}

    if not os.path.exists(path):
        return default

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return default


def parse_date(value):
    text = clean_text(value)

    if not text:
        return None

    text = (
        text
        .replace("年", "/")
        .replace("月", "/")
        .replace("日", "")
        .replace("-", "/")
        .replace(".", "/")
    )

    match = re.search(
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        text
    )

    if not match:
        return None

    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3))
        ).date()

    except Exception:
        return None


def extract_target_date(data):
    if not isinstance(data, dict):
        return None

    for key in [
        "race_date",
        "date",
        "target_date",
    ]:
        parsed = parse_date(
            data.get(key)
        )

        if parsed is not None:
            return parsed

    race_info = data.get(
        "race_info"
    )

    if isinstance(race_info, dict):
        for key in [
            "race_date",
            "date",
            "target_date",
        ]:
            parsed = parse_date(
                race_info.get(key)
            )

            if parsed is not None:
                return parsed

    return None


def get_html(url):
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT
            )

            if response.status_code == 200:
                response.encoding = (
                    response.apparent_encoding
                )

                return response.text

            last_error = (
                f"HTTP {response.status_code}"
            )

        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(
                2 + attempt
            )

    raise RuntimeError(
        last_error or "取得失敗"
    )


def load_race_and_runners():
    with open(
        RACE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    target_date = extract_target_date(
        data
    )

    if target_date is None:
        raise RuntimeError(
            "race.jsonから対象日を取得できません。"
            "リーク防止のため停止します。"
        )

    candidates = []

    if isinstance(data, dict):
        for key in [
            "horses",
            "runners",
            "entries",
            "race_entries",
            "results",
        ]:
            value = data.get(key)

            if isinstance(value, list):
                candidates = value
                break

    runners = []

    for item in candidates:
        if not isinstance(item, dict):
            continue

        horse_id = clean_text(
            item.get("horse_id")
            or item.get("horseId")
            or item.get("id")
        )

        horse_name = clean_text(
            item.get("horse_name")
            or item.get("horseName")
            or item.get("name")
        )

        horse_number = clean_text(
            item.get("horse_number")
            or item.get("horseNumber")
            or item.get("number")
            or item.get("umaban")
        )

        if not horse_id:
            continue

        runners.append({
            "horse_id": horse_id,
            "horse_name": horse_name,
            "horse_number": horse_number,
        })

    if not runners:
        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    return (
        data,
        target_date,
        runners
    )


def normalize_header(value):
    text = clean_text(value)

    replacements = {
        "着 順": "着順",
        "レース": "レース名",
        "上り": "上がり",
        "上り3F": "上がり",
        "上がり3F": "上がり",
        "馬場": "馬場状態",
    }

    return replacements.get(
        text,
        text
    )


def get_value(
    record,
    names
):
    for name in names:
        value = clean_text(
            record.get(name)
        )

        if value:
            return value

    return ""


def parse_distance_surface(value):
    text = clean_text(value)

    surface = ""
    distance = ""

    if "芝" in text:
        surface = "芝"

    elif "ダ" in text:
        surface = "ダート"

    elif "障" in text:
        surface = "障害"

    match = re.search(
        r"(\d{3,4})",
        text
    )

    if match:
        distance = match.group(1)

    return (
        surface,
        distance
    )


def table_score(table):
    text = clean_text(
        table.get_text(
            " ",
            strip=True
        )
    )

    score = 0

    required = [
        "日付",
        "着順",
    ]

    for word in required:
        if word in text:
            score += 3

    optional = [
        "開催",
        "レース",
        "距離",
        "タイム",
        "通過",
        "上り",
        "上がり",
        "馬体重",
        "騎手",
        "斤量",
    ]

    for word in optional:
        if word in text:
            score += 1

    rows = table.find_all("tr")

    if len(rows) >= 2:
        score += 2

    return score


def find_result_tables(soup):
    candidates = []

    for index, table in enumerate(
        soup.find_all("table")
    ):
        score = table_score(
            table
        )

        if score >= 8:
            candidates.append(
                (
                    score,
                    index,
                    table
                )
            )

    candidates.sort(
        key=lambda x: (
            -x[0],
            x[1]
        )
    )

    return [
        table
        for _, _, table
        in candidates
    ]


def find_headers(rows):
    for row_index, row in enumerate(
        rows[:10]
    ):
        cells = row.find_all(
            ["th", "td"]
        )

        values = [
            normalize_header(
                cell.get_text(
                    " ",
                    strip=True
                )
            )
            for cell in cells
        ]

        joined = " ".join(
            values
        )

        if (
            "日付" in joined
            and (
                "着順" in joined
                or "着" in joined
            )
        ):
            return (
                row_index,
                values
            )

    return (
        None,
        []
    )


def extract_race_id_from_row(row):
    for link in row.find_all(
        "a",
        href=True
    ):
        href = clean_text(
            link.get("href")
        )

        patterns = [
            r"/race/(\d{12})",
            r"race_id=(\d{12})",
        ]

        for pattern in patterns:
            match = re.search(
                pattern,
                href
            )

            if match:
                return match.group(1)

    return ""


def parse_result_table(table):
    rows = table.find_all(
        "tr"
    )

    (
        header_index,
        headers
    ) = find_headers(
        rows
    )

    if header_index is None:
        return []

    results = []

    for row in rows[
        header_index + 1:
    ]:
        cells = row.find_all(
            "td"
        )

        if not cells:
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

        if len(values) < 3:
            continue

        record = {}

        for i, value in enumerate(
            values
        ):
            if i < len(headers):
                key = headers[i]
            else:
                key = (
                    f"column_{i + 1}"
                )

            record[key] = value

        race_date = get_value(
            record,
            ["日付"]
        )

        if parse_date(
            race_date
        ) is None:
            continue

        distance_raw = get_value(
            record,
            ["距離"]
        )

        (
            surface,
            distance
        ) = parse_distance_surface(
            distance_raw
        )

        result = {
            "race_id":
                extract_race_id_from_row(
                    row
                ),

            "date":
                race_date,

            "meeting":
                get_value(
                    record,
                    ["開催"]
                ),

            "race_name":
                get_value(
                    record,
                    [
                        "レース名",
                        "レース",
                    ]
                ),

            "rank":
                get_value(
                    record,
                    [
                        "着順",
                        "着",
                    ]
                ),

            "jockey":
                get_value(
                    record,
                    ["騎手"]
                ),

            "carried_weight":
                get_value(
                    record,
                    ["斤量"]
                ),

            "surface":
                surface,

            "distance":
                distance,

            "distance_raw":
                distance_raw,

            "track_condition":
                get_value(
                    record,
                    [
                        "馬場状態",
                        "馬場",
                    ]
                ),

            "time":
                get_value(
                    record,
                    ["タイム"]
                ),

            "margin":
                get_value(
                    record,
                    ["着差"]
                ),

            "passing":
                get_value(
                    record,
                    ["通過"]
                ),

            "last3f":
                get_value(
                    record,
                    [
                        "上がり",
                        "上り",
                        "上り3F",
                        "上がり3F",
                    ]
                ),

            "horse_weight":
                get_value(
                    record,
                    ["馬体重"]
                ),

            "odds":
                get_value(
                    record,
                    ["オッズ"]
                ),

            "popularity":
                get_value(
                    record,
                    ["人気"]
                ),
        }

        results.append(
            result
        )

    return results


def result_identity(result):
    race_id = clean_text(
        result.get("race_id")
    )

    if race_id:
        return (
            "race_id",
            race_id
        )

    return (
        "fallback",
        clean_text(
            result.get("date")
        ),
        clean_text(
            result.get("meeting")
        ),
        clean_text(
            result.get("race_name")
        ),
        clean_text(
            result.get("distance_raw")
        ),
    )


def deduplicate_results(results):
    seen = set()
    unique = []

    for result in results:
        key = result_identity(
            result
        )

        if key in seen:
            continue

        seen.add(key)

        unique.append(
            result
        )

    return unique


def collect_all_result_rows(
    soup
):
    tables = find_result_tables(
        soup
    )

    all_results = []

    parsed_table_count = 0

    for table in tables:
        results = parse_result_table(
            table
        )

        if not results:
            continue

        parsed_table_count += 1

        all_results.extend(
            results
        )

    all_results = (
        deduplicate_results(
            all_results
        )
    )

    return (
        all_results,
        len(tables),
        parsed_table_count
    )


def filter_past_races(
    results,
    target_date,
    target_race_id
):
    valid = []

    excluded_target_race = 0
    excluded_same_day = 0
    excluded_future = 0
    excluded_unknown_date = 0

    for result in results:
        race_id = clean_text(
            result.get("race_id")
        )

        race_date = parse_date(
            result.get("date")
        )

        if (
            target_race_id
            and race_id
            and race_id
            == target_race_id
        ):
            excluded_target_race += 1
            continue

        if race_date is None:
            excluded_unknown_date += 1
            continue

        if race_date == target_date:
            excluded_same_day += 1
            continue

        if race_date > target_date:
            excluded_future += 1
            continue

        valid.append(
            result
        )

    valid.sort(
        key=lambda item: (
            parse_date(
                item.get("date")
            )
            or datetime.min.date()
        ),
        reverse=True
    )

    return {
        "valid":
            valid,

        "excluded_target_race":
            excluded_target_race,

        "excluded_same_day":
            excluded_same_day,

        "excluded_future":
            excluded_future,

        "excluded_unknown_date":
            excluded_unknown_date,
    }


def collect_horse_history(
    horse,
    target_date,
    target_race_id
):
    horse_id = horse[
        "horse_id"
    ]

    url = BASE_URL.format(
        horse_id=horse_id
    )

    html = get_html(
        url
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    (
        raw_results,
        candidate_table_count,
        parsed_table_count
    ) = collect_all_result_rows(
        soup
    )

    filtered = filter_past_races(
        raw_results,
        target_date,
        target_race_id
    )

    results = filtered[
        "valid"
    ]

    return {
        "horse_id":
            horse_id,

        "horse_name":
            horse[
                "horse_name"
            ],

        "horse_number":
            horse[
                "horse_number"
            ],

        "source_url":
            url,

        "candidate_table_count":
            candidate_table_count,

        "parsed_table_count":
            parsed_table_count,

        "raw_race_count":
            len(
                raw_results
            ),

        "past_race_count":
            len(
                results
            ),

        "excluded_target_race_count":
            filtered[
                "excluded_target_race"
            ],

        "excluded_same_day_count":
            filtered[
                "excluded_same_day"
            ],

        "excluded_future_count":
            filtered[
                "excluded_future"
            ],

        "excluded_unknown_date_count":
            filtered[
                "excluded_unknown_date"
            ],

        "past_races":
            results,
    }


def build_same_day_cache(
    old_data,
    target_date
):
    cache = {}

    if not isinstance(
        old_data,
        dict
    ):
        return cache

    old_target_date = parse_date(
        old_data.get(
            "target_date"
        )
    )

    # 別日のキャッシュは使用しない。
    # 競走履歴が増えた馬を古い状態で固定しないため。
    if old_target_date != target_date:
        return cache

    if not old_data.get(
        "leak_check_passed"
    ):
        return cache

    horses = old_data.get(
        "horses",
        []
    )

    if not isinstance(
        horses,
        list
    ):
        return cache

    for horse in horses:
        if not isinstance(
            horse,
            dict
        ):
            continue

        horse_id = clean_text(
            horse.get(
                "horse_id"
            )
        )

        if not horse_id:
            continue

        past_races = horse.get(
            "past_races"
        )

        if not isinstance(
            past_races,
            list
        ):
            continue

        # キャッシュ自体にも未来・同日データがないことを再確認
        safe = True

        for past in past_races:
            if not isinstance(
                past,
                dict
            ):
                safe = False
                break

            past_date = parse_date(
                past.get(
                    "date"
                )
            )

            if (
                past_date is None
                or past_date >= target_date
            ):
                safe = False
                break

        if safe:
            cache[
                horse_id
            ] = horse

    return cache


def normalize_cached_horse(
    cached,
    horse,
    target_date,
    target_race_id
):
    raw_results = cached.get(
        "past_races",
        []
    )

    filtered = filter_past_races(
        raw_results,
        target_date,
        target_race_id
    )

    results = filtered[
        "valid"
    ]

    return {
        "horse_id":
            horse[
                "horse_id"
            ],

        "horse_name":
            horse[
                "horse_name"
            ],

        "horse_number":
            horse[
                "horse_number"
            ],

        "source_url":
            clean_text(
                cached.get(
                    "source_url"
                )
            )
            or BASE_URL.format(
                horse_id=horse[
                    "horse_id"
                ]
            ),

        "candidate_table_count":
            int(
                cached.get(
                    "candidate_table_count",
                    0
                )
                or 0
            ),

        "parsed_table_count":
            int(
                cached.get(
                    "parsed_table_count",
                    0
                )
                or 0
            ),

        "raw_race_count":
            int(
                cached.get(
                    "raw_race_count",
                    len(results)
                )
                or 0
            ),

        "past_race_count":
            len(
                results
            ),

        "excluded_target_race_count":
            filtered[
                "excluded_target_race"
            ],

        "excluded_same_day_count":
            filtered[
                "excluded_same_day"
            ],

        "excluded_future_count":
            filtered[
                "excluded_future"
            ],

        "excluded_unknown_date_count":
            filtered[
                "excluded_unknown_date"
            ],

        "past_races":
            results,
    }


def add_horse_to_output(
    output,
    data
):
    output[
        "horses"
    ].append(
        data
    )

    output[
        "collected_horse_count"
    ] += 1

    output[
        "total_candidate_table_count"
    ] += data[
        "candidate_table_count"
    ]

    output[
        "total_parsed_table_count"
    ] += data[
        "parsed_table_count"
    ]

    output[
        "total_raw_race_count"
    ] += data[
        "raw_race_count"
    ]

    output[
        "total_past_race_count"
    ] += data[
        "past_race_count"
    ]

    output[
        "excluded_target_race_count"
    ] += data[
        "excluded_target_race_count"
    ]

    output[
        "excluded_same_day_count"
    ] += data[
        "excluded_same_day_count"
    ]

    output[
        "excluded_future_count"
    ] += data[
        "excluded_future_count"
    ]

    output[
        "excluded_unknown_date_count"
    ] += data[
        "excluded_unknown_date_count"
    ]

    if data[
        "past_race_count"
    ] > 0:
        output[
            "horses_with_past_races"
        ] += 1

    else:
        output[
            "horses_without_past_races"
        ] += 1


def main():
    (
        race_data,
        target_date,
        runners
    ) = load_race_and_runners()

    target_race_id = clean_text(
        race_data.get(
            "race_id"
        )
    )

    old_data = load_json(
        OUTPUT_FILE,
        {}
    )

    cache = build_same_day_cache(
        old_data,
        target_date
    )

    output = {
        "updated_at":
            now_jst(),

        "source":
            "netkeiba",

        "source_race_file":
            RACE_FILE,

        "target_race_id":
            target_race_id,

        "target_date":
            target_date.isoformat(),

        "cache_enabled":
            True,

        "cache_policy":
            "same_target_date_only",

        "cache_hit_count":
            0,

        "fetched_horse_count":
            0,

        "future_race_usage":
            False,

        "leak_check_passed":
            False,

        "target_horse_count":
            len(runners),

        "collected_horse_count":
            0,

        "horses_with_past_races":
            0,

        "horses_without_past_races":
            0,

        "total_candidate_table_count":
            0,

        "total_parsed_table_count":
            0,

        "total_raw_race_count":
            0,

        "total_past_race_count":
            0,

        "excluded_target_race_count":
            0,

        "excluded_same_day_count":
            0,

        "excluded_future_count":
            0,

        "excluded_unknown_date_count":
            0,

        "error_count":
            0,

        "errors":
            [],

        "horses":
            [],
    }

    print("")
    print(
        "===== Runner History ====="
    )

    print(
        "target race id:",
        target_race_id
    )

    print(
        "target date:",
        target_date.isoformat()
    )

    print(
        "target horses:",
        len(runners)
    )

    print(
        "safe same-day cache:",
        len(cache)
    )

    print("")

    for index, horse in enumerate(
        runners,
        start=1
    ):
        print(
            f"[{index}/{len(runners)}] "
            f"{horse['horse_name']} "
            f"({horse['horse_id']})"
        )

        horse_id = horse[
            "horse_id"
        ]

        fetched = False

        try:
            cached = cache.get(
                horse_id
            )

            if cached is not None:
                data = (
                    normalize_cached_horse(
                        cached,
                        horse,
                        target_date,
                        target_race_id
                    )
                )

                output[
                    "cache_hit_count"
                ] += 1

                print(
                    "  CACHE HIT"
                )

            else:
                data = (
                    collect_horse_history(
                        horse,
                        target_date,
                        target_race_id
                    )
                )

                fetched = True

                output[
                    "fetched_horse_count"
                ] += 1

                print(
                    "  FETCH"
                )

            add_horse_to_output(
                output,
                data
            )

            print(
                "  tables:",
                data[
                    "parsed_table_count"
                ],
                "/",
                data[
                    "candidate_table_count"
                ],
                "| raw:",
                data[
                    "raw_race_count"
                ],
                "| valid past:",
                data[
                    "past_race_count"
                ],
                "| target excluded:",
                data[
                    "excluded_target_race_count"
                ],
                "| same-day excluded:",
                data[
                    "excluded_same_day_count"
                ],
                "| future excluded:",
                data[
                    "excluded_future_count"
                ]
            )

        except Exception as e:
            message = str(e)

            output[
                "error_count"
            ] += 1

            output[
                "errors"
            ].append({
                "horse_id":
                    horse[
                        "horse_id"
                    ],

                "horse_name":
                    horse[
                        "horse_name"
                    ],

                "error":
                    message,
            })

            print(
                "  ERROR:",
                message
            )

        # ネット取得した馬だけ待機。
        # キャッシュヒットでは待たない。
        if fetched:
            time.sleep(
                REQUEST_INTERVAL
            )

    # race.jsonと同じ出走順を維持
    horse_order = {
        clean_text(
            horse.get(
                "horse_id"
            )
        ): index
        for index, horse in enumerate(
            runners
        )
    }

    output[
        "horses"
    ].sort(
        key=lambda item: (
            horse_order.get(
                clean_text(
                    item.get(
                        "horse_id"
                    )
                ),
                9999
            )
        )
    )

    # ---------------------------------------------
    # 最終リーク検査
    # ---------------------------------------------

    leak_found = False

    for horse in output[
        "horses"
    ]:
        for past in horse.get(
            "past_races",
            []
        ):
            past_race_id = clean_text(
                past.get(
                    "race_id"
                )
            )

            past_date = parse_date(
                past.get(
                    "date"
                )
            )

            if (
                target_race_id
                and past_race_id
                == target_race_id
            ):
                leak_found = True

            if past_date is None:
                leak_found = True

            elif past_date >= target_date:
                leak_found = True

    output[
        "future_race_usage"
    ] = leak_found

    output[
        "leak_check_passed"
    ] = not leak_found

    output[
        "updated_at"
    ] = now_jst()

    if leak_found:
        raise RuntimeError(
            "runner_historyで未来情報リークを検出。"
            "JSONは保存しません。"
        )

    if (
        output[
            "collected_horse_count"
        ]
        != len(runners)
    ):
        raise RuntimeError(
            "runner_historyが全頭分揃っていません: "
            f"{output['collected_horse_count']}/"
            f"{len(runners)}"
        )

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    print("")
    print(
        "===== Runner History Result ====="
    )

    print(
        "target horses:",
        output[
            "target_horse_count"
        ]
    )

    print(
        "collected horses:",
        output[
            "collected_horse_count"
        ]
    )

    print(
        "cache hit:",
        output[
            "cache_hit_count"
        ]
    )

    print(
        "new fetch:",
        output[
            "fetched_horse_count"
        ]
    )

    print(
        "horses with past races:",
        output[
            "horses_with_past_races"
        ]
    )

    print(
        "horses without past races:",
        output[
            "horses_without_past_races"
        ]
    )

    print(
        "candidate tables:",
        output[
            "total_candidate_table_count"
        ]
    )

    print(
        "parsed tables:",
        output[
            "total_parsed_table_count"
        ]
    )

    print(
        "raw races:",
        output[
            "total_raw_race_count"
        ]
    )

    print(
        "valid past races:",
        output[
            "total_past_race_count"
        ]
    )

    print(
        "target race excluded:",
        output[
            "excluded_target_race_count"
        ]
    )

    print(
        "same-day excluded:",
        output[
            "excluded_same_day_count"
        ]
    )

    print(
        "future excluded:",
        output[
            "excluded_future_count"
        ]
    )

    print(
        "unknown-date excluded:",
        output[
            "excluded_unknown_date_count"
        ]
    )

    print(
        "future race usage:",
        output[
            "future_race_usage"
        ]
    )

    print(
        "leak check passed:",
        output[
            "leak_check_passed"
        ]
    )

    print(
        "errors:",
        output[
            "error_count"
        ]
    )


if __name__ == "__main__":
    main()
