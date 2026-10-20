import json
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
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.7",
}


def now_jst():
    jst = timezone(timedelta(hours=9))
    return datetime.now(jst).isoformat()


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


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
                response.encoding = response.apparent_encoding
                return response.text

            last_error = f"HTTP {response.status_code}"

        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES - 1:
            time.sleep(2 + attempt)

    raise RuntimeError(last_error or "取得失敗")


def parse_date(value):
    text = clean_text(value)

    if not text:
        return None

    text = (
        text.replace("年", "/")
        .replace("月", "/")
        .replace("日", "")
        .replace("-", "/")
        .replace(".", "/")
    )

    text = re.sub(r"\s+", "", text)

    patterns = [
        "%Y/%m/%d",
        "%Y/%m/%d/",
        "%Y/%m/%d(%a)",
    ]

    for pattern in patterns:
        try:
            return datetime.strptime(text, pattern).date()
        except Exception:
            pass

    match = re.search(
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        text
    )

    if match:
        try:
            return datetime(
                int(match.group(1)),
                int(match.group(2)),
                int(match.group(3))
            ).date()
        except Exception:
            return None

    return None


def extract_target_date(data):
    if not isinstance(data, dict):
        return None

    candidate_keys = [
        "race_date",
        "date",
        "target_date",
    ]

    for key in candidate_keys:
        value = data.get(key)

        parsed = parse_date(value)

        if parsed is not None:
            return parsed

    race_info = data.get("race_info")

    if isinstance(race_info, dict):
        for key in candidate_keys:
            parsed = parse_date(race_info.get(key))

            if parsed is not None:
                return parsed

    return None


def load_race_and_runners():
    with open(RACE_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)

    target_date = extract_target_date(data)

    if target_date is None:
        raise RuntimeError(
            "race.json から対象レース日を取得できません。"
            "未来情報リーク防止のため処理を停止します。"
        )

    candidates = []

    if isinstance(data, dict):
        for key in [
            "runners",
            "horses",
            "entries",
            "race_entries",
            "results",
        ]:
            if isinstance(data.get(key), list):
                candidates = data[key]
                break

        if not candidates:
            for value in data.values():
                if (
                    isinstance(value, list)
                    and value
                    and isinstance(value[0], dict)
                ):
                    candidates = value
                    break

    elif isinstance(data, list):
        candidates = data

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

        if horse_id:
            runners.append({
                "horse_id": horse_id,
                "horse_name": horse_name,
                "horse_number": horse_number,
            })

    return data, target_date, runners


def find_result_table(soup):
    best_table = None
    best_score = -1

    for table in soup.find_all("table"):
        text = clean_text(
            table.get_text(" ", strip=True)
        )

        score = 0

        keywords = [
            "日付",
            "開催",
            "レース名",
            "着順",
            "距離",
            "タイム",
            "通過",
            "上り",
            "馬体重",
        ]

        for keyword in keywords:
            if keyword in text:
                score += 1

        row_count = len(
            table.find_all("tr")
        )

        if row_count >= 2:
            score += 2

        if score > best_score:
            best_score = score
            best_table = table

    if best_score < 5:
        return None

    return best_table


def normalize_header(header):
    h = clean_text(header)

    replacements = {
        "着 順": "着順",
        "レース": "レース名",
        "上り": "上がり",
        "上り3F": "上がり",
        "上がり3F": "上がり",
        "馬場": "馬場状態",
    }

    return replacements.get(h, h)


def get_value(record, names):
    for name in names:
        if (
            name in record
            and clean_text(record[name])
        ):
            return clean_text(record[name])

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

    return surface, distance


def parse_result_table(table):
    rows = table.find_all("tr")

    header_index = None
    headers = []

    for i, row in enumerate(rows[:5]):
        cells = row.find_all(
            ["th", "td"]
        )

        values = [
            normalize_header(
                x.get_text(
                    " ",
                    strip=True
                )
            )
            for x in cells
        ]

        joined = " ".join(values)

        if (
            "日付" in joined
            and (
                "着順" in joined
                or "着" in joined
            )
        ):
            headers = values
            header_index = i
            break

    if header_index is None:
        raise RuntimeError(
            "競走成績ヘッダーを判定できません"
        )

    results = []

    for row in rows[header_index + 1:]:
        cells = row.find_all("td")

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

        for i, value in enumerate(values):
            if i < len(headers):
                key = headers[i]
            else:
                key = f"column_{i + 1}"

            record[key] = value

        race_date = get_value(
            record,
            ["日付"]
        )

        if not race_date:
            continue

        rank = get_value(
            record,
            ["着順", "着"]
        )

        distance_raw = get_value(
            record,
            ["距離"]
        )

        surface, distance = (
            parse_distance_surface(
                distance_raw
            )
        )

        race_name = get_value(
            record,
            ["レース名", "レース"]
        )

        result = {
            "date": race_date,
            "meeting": get_value(
                record,
                ["開催"]
            ),
            "race_name": race_name,
            "rank": rank,
            "jockey": get_value(
                record,
                ["騎手"]
            ),
            "carried_weight": get_value(
                record,
                ["斤量"]
            ),
            "surface": surface,
            "distance": distance,
            "distance_raw": distance_raw,
            "track_condition": get_value(
                record,
                ["馬場状態", "馬場"]
            ),
            "time": get_value(
                record,
                ["タイム"]
            ),
            "margin": get_value(
                record,
                ["着差"]
            ),
            "passing": get_value(
                record,
                ["通過"]
            ),
            "last3f": get_value(
                record,
                [
                    "上がり",
                    "上り",
                    "上り3F",
                    "上がり3F",
                ]
            ),
            "horse_weight": get_value(
                record,
                ["馬体重"]
            ),
            "odds": get_value(
                record,
                ["オッズ"]
            ),
            "popularity": get_value(
                record,
                ["人気"]
            ),
        }

        results.append(result)

    return results


def filter_past_races(
    results,
    target_date
):
    valid = []

    excluded_same_day = 0
    excluded_future = 0
    excluded_unknown_date = 0

    for result in results:
        race_date = parse_date(
            result.get("date")
        )

        if race_date is None:
            excluded_unknown_date += 1
            continue

        if race_date == target_date:
            excluded_same_day += 1
            continue

        if race_date > target_date:
            excluded_future += 1
            continue

        valid.append(result)

    valid.sort(
        key=lambda x: (
            parse_date(
                x.get("date")
            )
            or datetime.min.date()
        ),
        reverse=True
    )

    return {
        "valid": valid,
        "excluded_same_day": (
            excluded_same_day
        ),
        "excluded_future": (
            excluded_future
        ),
        "excluded_unknown_date": (
            excluded_unknown_date
        ),
    }


def collect_horse_history(
    horse,
    target_date
):
    horse_id = horse["horse_id"]

    url = BASE_URL.format(
        horse_id=horse_id
    )

    html = get_html(url)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    table = find_result_table(soup)

    if table is None:
        title = ""

        if soup.title:
            title = clean_text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
            )

        raise RuntimeError(
            "競走成績テーブルなし"
            " / title="
            + title
        )

    raw_results = parse_result_table(
        table
    )

    if not raw_results:
        raise RuntimeError(
            "競走成績0件"
        )

    filtered = filter_past_races(
        raw_results,
        target_date
    )

    results = filtered["valid"]

    return {
        "horse_id": horse_id,
        "horse_name": horse[
            "horse_name"
        ],
        "horse_number": horse[
            "horse_number"
        ],
        "source_url": url,

        "raw_race_count": len(
            raw_results
        ),

        "past_race_count": len(
            results
        ),

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

        "past_races": results,
    }


def main():
    (
        race_data,
        target_date,
        runners,
    ) = load_race_and_runners()

    target_race_id = clean_text(
        race_data.get("race_id")
        if isinstance(
            race_data,
            dict
        )
        else ""
    )

    output = {
        "updated_at": now_jst(),
        "source": "netkeiba",
        "source_race_file": RACE_FILE,

        "target_race_id":
            target_race_id,

        "target_date":
            target_date.isoformat(),

        "future_race_usage": False,

        "target_horse_count":
            len(runners),

        "collected_horse_count": 0,

        "total_raw_race_count": 0,

        "total_past_race_count": 0,

        "excluded_same_day_count": 0,

        "excluded_future_count": 0,

        "excluded_unknown_date_count": 0,

        "error_count": 0,
        "errors": [],
        "horses": [],
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
        "future race usage:",
        False
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

        try:
            data = (
                collect_horse_history(
                    horse,
                    target_date
                )
            )

            output[
                "horses"
            ].append(data)

            output[
                "collected_horse_count"
            ] += 1

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

            print(
                "  raw:",
                data[
                    "raw_race_count"
                ],
                "/ valid past:",
                data[
                    "past_race_count"
                ],
                "/ same-day excluded:",
                data[
                    "excluded_same_day_count"
                ],
                "/ future excluded:",
                data[
                    "excluded_future_count"
                ],
                "/ unknown-date excluded:",
                data[
                    "excluded_unknown_date_count"
                ],
            )

        except Exception as e:
            message = str(e)

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

            output[
                "error_count"
            ] += 1

            print(
                "  ERROR:",
                message
            )

        time.sleep(
            REQUEST_INTERVAL
        )

    output[
        "updated_at"
    ] = now_jst()

    # 最終リーク検査
    leak_found = False

    for horse in output["horses"]:
        for race in horse.get(
            "past_races",
            []
        ):
            race_date = parse_date(
                race.get("date")
            )

            if (
                race_date is None
                or race_date >= target_date
            ):
                leak_found = True

    output[
        "future_race_usage"
    ] = leak_found

    output[
        "leak_check_passed"
    ] = not leak_found

    if leak_found:
        raise RuntimeError(
            "未来情報リークを検出しました。"
            "runner_history.json は保存しません。"
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
        "target:",
        output[
            "target_horse_count"
        ]
    )
    print(
        "collected:",
        output[
            "collected_horse_count"
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
