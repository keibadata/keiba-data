import json
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

RACE_FILE = "race.json"
DETECTION_FILE = "training.json"
OUTPUT_FILE = "training_detail.json"

TIMEOUT = 20
REQUEST_INTERVAL = 1.2
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def text(value):
    if value is None:
        return ""
    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def fetch(url):

    last_error = ""

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
                    or response.encoding
                    or "utf-8"
                )

                return response

            last_error = (
                f"HTTP {response.status_code}"
            )

        except Exception as e:
            last_error = str(e)

        time.sleep(
            REQUEST_INTERVAL * (attempt + 1)
        )

    raise RuntimeError(
        last_error or "取得失敗"
    )


def get_horses(race):

    for key in (
        "horses",
        "runners",
        "entries"
    ):
        value = race.get(key)

        if isinstance(value, list):
            return value

    return []


def normalize_time_values(value):

    s = text(value)

    values = re.findall(
        r"(?<!\d)(\d{2,3}\.\d)(?!\d)",
        s
    )

    result = []

    for v in values:

        try:
            n = float(v)
        except Exception:
            continue

        # 追い切り時計として極端な値を除外
        if 10.0 <= n <= 150.0:
            result.append(n)

    return result


def detect_course(value):

    s = text(value)

    patterns = [
        ("坂路", ["坂路"]),
        ("CW", ["CW", "ＣＷ"]),
        ("W", [
            "南W",
            "美浦W",
            "ウッド",
            "Ｗ"
        ]),
        ("栗東芝", ["栗東芝"]),
        ("美浦芝", ["美浦芝"]),
        ("ポリ", [
            "ポリ",
            "P",
            "Ｐ"
        ])
    ]

    for course, words in patterns:

        for word in words:

            if word in s:
                return course

    return ""


def looks_like_training(value):

    s = text(value)

    if not s:
        return False

    keywords = [
        "調教",
        "追い切",
        "坂路",
        "CW",
        "ＣＷ",
        "南W",
        "美浦W",
        "ウッド",
        "栗東",
        "美浦",
        "併せ",
        "馬なり",
        "一杯",
        "強め"
    ]

    keyword_hit = any(
        word in s
        for word in keywords
    )

    times = normalize_time_values(s)

    return (
        keyword_hit
        and len(times) >= 1
    )


def extract_date(value):

    s = text(value)

    patterns = [
        r"(\d{1,2}/\d{1,2})",
        r"(\d{1,2}月\d{1,2}日)"
    ]

    for pattern in patterns:

        m = re.search(
            pattern,
            s
        )

        if m:
            return m.group(1)

    return ""


def extract_effort(value):

    s = text(value)

    for word in (
        "馬なり",
        "一杯",
        "強め",
        "末強め",
        "直強め",
        "仕掛け"
    ):

        if word in s:
            return word

    return ""


def extract_pairing(value):

    s = text(value)

    keywords = [
        "併せ",
        "先着",
        "遅れ",
        "同入"
    ]

    found = [
        x
        for x in keywords
        if x in s
    ]

    if not found:
        return ""

    # 長大なHTML文章を保存しない
    if len(s) <= 180:
        return s

    for word in found:

        index = s.find(word)

        if index >= 0:

            start = max(
                0,
                index - 60
            )

            end = min(
                len(s),
                index + 100
            )

            return s[start:end]

    return ""


def parse_training_block(value):

    raw = text(value)

    times = normalize_time_values(
        raw
    )

    if not times:
        return None

    return {
        "date":
            extract_date(raw),

        "course":
            detect_course(raw),

        "times":
            times,

        # 最後の区間値を終い候補として保持。
        # この時点では能力加点しない。
        "last_section_candidate":
            times[-1]
            if times else None,

        "effort":
            extract_effort(raw),

        "pairing":
            extract_pairing(raw),

        "raw":
            raw[:500]
    }


def extract_from_tables(soup):

    blocks = []

    for table_index, table in enumerate(
        soup.find_all("table")
    ):

        rows = table.find_all("tr")

        for row_index, row in enumerate(rows):

            cells = [
                text(cell.get_text(
                    " ",
                    strip=True
                ))
                for cell in row.find_all(
                    ["th", "td"]
                )
            ]

            if not cells:
                continue

            joined = " | ".join(
                cells
            )

            if not looks_like_training(
                joined
            ):
                continue

            parsed = parse_training_block(
                joined
            )

            if parsed is None:
                continue

            parsed[
                "source_type"
            ] = "table"

            parsed[
                "table_index"
            ] = table_index

            parsed[
                "row_index"
            ] = row_index

            blocks.append(
                parsed
            )

    return blocks


def extract_from_text(soup):

    blocks = []

    lines = [
        text(x)
        for x in soup.stripped_strings
    ]

    # 1行では分割されるページがあるので
    # 周辺行も結合する
    for i in range(len(lines)):

        current = lines[i]

        neighborhood = " | ".join(
            lines[
                max(0, i - 2):
                min(len(lines), i + 5)
            ]
        )

        if not looks_like_training(
            neighborhood
        ):
            continue

        parsed = parse_training_block(
            neighborhood
        )

        if parsed is None:
            continue

        parsed[
            "source_type"
        ] = "text"

        parsed[
            "line_index"
        ] = i

        blocks.append(
            parsed
        )

    return blocks


def deduplicate(blocks):

    unique = []
    seen = set()

    for block in blocks:

        key = (
            block.get("date", ""),
            block.get("course", ""),
            tuple(
                block.get(
                    "times",
                    []
                )
            ),
            block.get(
                "effort",
                ""
            )
        )

        if key in seen:
            continue

        seen.add(key)
        unique.append(block)

    return unique


def quality_score(block):

    score = 0

    if block.get("date"):
        score += 2

    if block.get("course"):
        score += 2

    times = block.get(
        "times",
        []
    )

    if len(times) >= 4:
        score += 4
    elif len(times) >= 2:
        score += 2
    elif len(times) == 1:
        score += 1

    if block.get("effort"):
        score += 1

    if block.get("pairing"):
        score += 1

    return score


def inspect_url(url):

    response = fetch(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    blocks = extract_from_tables(
        soup
    )

    # table抽出が弱い場合だけ
    # 全文側も追加
    if len(blocks) < 2:

        blocks.extend(
            extract_from_text(
                soup
            )
        )

    blocks = deduplicate(
        blocks
    )

    for block in blocks:

        block[
            "quality_score"
        ] = quality_score(
            block
        )

    blocks.sort(
        key=lambda x:
            x.get(
                "quality_score",
                0
            ),
        reverse=True
    )

    return {
        "title":
            text(
                soup.title.get_text(
                    " ",
                    strip=True
                )
                if soup.title
                else ""
            ),

        "training_block_count":
            len(blocks),

        "training_blocks":
            blocks[:20]
    }


def horse_urls(horse_id):

    return [
        (
            "netkeiba_training",
            (
                "https://race.netkeiba.com/"
                "training/training.html"
                f"?horse_id={horse_id}"
            )
        ),
        (
            "netkeiba_horse",
            (
                "https://db.netkeiba.com/"
                f"horse/{horse_id}/"
            )
        )
    ]


def analyze_horse(horse):

    horse_id = text(
        horse.get("horse_id")
    )

    result = {
        "horse_id":
            horse_id,

        "horse_number":
            text(
                horse.get(
                    "horse_number"
                )
            ),

        "horse_name":
            text(
                horse.get(
                    "horse_name"
                )
            ),

        "detail_found":
            False,

        "source":
            "",

        "source_url":
            "",

        "training_count":
            0,

        "training":
            [],

        "checks":
            [],

        "error":
            ""
    }

    if not horse_id:

        result["error"] = (
            "horse_idなし"
        )

        return result

    best = None

    for source_name, url in horse_urls(
        horse_id
    ):

        check = {
            "source":
                source_name,

            "url":
                url,

            "ok":
                False,

            "training_block_count":
                0,

            "error":
                ""
        }

        try:

            inspection = inspect_url(
                url
            )

            check["ok"] = True

            check[
                "training_block_count"
            ] = inspection[
                "training_block_count"
            ]

            result["checks"].append(
                check
            )

            blocks = inspection[
                "training_blocks"
            ]

            if blocks:

                candidate = {
                    "source":
                        source_name,

                    "url":
                        url,

                    "blocks":
                        blocks,

                    "score":
                        sum(
                            x[
                                "quality_score"
                            ]
                            for x in blocks[
                                :5
                            ]
                        )
                }

                if (
                    best is None
                    or
                    candidate["score"]
                    >
                    best["score"]
                ):
                    best = candidate

        except Exception as e:

            check["error"] = str(e)

            result["checks"].append(
                check
            )

        time.sleep(
            REQUEST_INTERVAL
        )

    if best is not None:

        result[
            "detail_found"
        ] = True

        result[
            "source"
        ] = best["source"]

        result[
            "source_url"
        ] = best["url"]

        result[
            "training"
        ] = best["blocks"]

        result[
            "training_count"
        ] = len(
            best["blocks"]
        )

    return result


def main():

    with open(
        RACE_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        race = json.load(f)

    horses = get_horses(
        race
    )

    if not horses:

        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    results = []

    for i, horse in enumerate(
        horses,
        start=1
    ):

        print(
            f"[{i}/{len(horses)}] "
            f"{text(horse.get('horse_name'))}"
        )

        result = analyze_horse(
            horse
        )

        results.append(
            result
        )

        print(
            " detail:",
            result[
                "detail_found"
            ],
            " blocks:",
            result[
                "training_count"
            ]
        )

    detail_count = sum(
        1
        for x in results
        if x["detail_found"]
    )

    output = {
        "updated_at":
            now_jst(),

        "source_race_file":
            RACE_FILE,

        "purpose":
            "objective_training_detail_extraction",

        "summary": {
            "horse_count":
                len(results),

            "detail_found_count":
                detail_count,

            "detail_not_found_count":
                len(results)
                - detail_count
        },

        "rules": {
            "training_is_supporting_data":
                True,

            "final_workout_not_independent_bonus":
                True,

            "training_used_for_condition":
                True,

            "training_used_for_issue_resolution":
                True,

            "unknown_not_penalized":
                True,

            "internet_prediction_not_used":
                True
        },

        "horses":
            results
    }

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

    print(
        "===== Training Detail ====="
    )

    print(
        "horses:",
        len(results)
    )

    print(
        "detail found:",
        detail_count
    )

    print(
        "not found:",
        len(results)
        - detail_count
    )


if __name__ == "__main__":
    main()
