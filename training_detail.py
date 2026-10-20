import json
import re
import time
from datetime import datetime, timezone, timedelta
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
DETECTION_FILE = "training.json"
OUTPUT_FILE = "training_detail.json"

TIMEOUT = 20
REQUEST_INTERVAL = 1.0
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


def clean_text(value):
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

            last_error = f"HTTP {response.status_code}"

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


def get_race_id(race):
    return clean_text(
        race.get("race_id")
        or race.get("target_race_id")
    )


def normalize_number(value):
    try:
        return int(str(value).strip())
    except Exception:
        return None


def extract_time_values(value):
    """
    追い切り時計候補。

    例:
    82.4
    66.7
    51.8
    37.4
    11.6

    日付・馬体重・年などを極力拾わない。
    """

    s = clean_text(value)

    raw_values = re.findall(
        r"(?<![\d.])(\d{1,3}\.\d)(?![\d.])",
        s
    )

    result = []

    for raw in raw_values:
        try:
            number = float(raw)
        except Exception:
            continue

        if 10.0 <= number <= 150.0:
            result.append(number)

    return result


def extract_date(value):
    s = clean_text(value)

    patterns = [
        r"(\d{1,2}/\d{1,2})",
        r"(\d{1,2}月\d{1,2}日)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            s
        )

        if match:
            return match.group(1)

    return ""


def detect_course(value):
    s = clean_text(value)

    checks = [
        ("栗東坂路", ["栗東坂路"]),
        ("美浦坂路", ["美浦坂路"]),
        ("坂路", ["坂路"]),
        ("CW", ["CW", "ＣＷ"]),
        (
            "美浦W",
            [
                "美浦W",
                "美浦Ｗ",
                "南W",
                "南Ｗ",
                "美浦ウッド"
            ]
        ),
        (
            "栗東CW",
            [
                "栗東CW",
                "栗東ＣＷ"
            ]
        ),
        (
            "ウッド",
            [
                "ウッド",
                "Ｗコース"
            ]
        ),
        (
            "ポリ",
            [
                "ポリ",
                "ポリトラック"
            ]
        ),
        (
            "芝",
            [
                "芝コース",
                "栗東芝",
                "美浦芝"
            ]
        ),
    ]

    for course, words in checks:
        if any(
            word in s
            for word in words
        ):
            return course

    return ""


def extract_effort(value):
    s = clean_text(value)

    words = [
        "馬なり",
        "一杯",
        "強め",
        "末強め",
        "直強め",
        "仕掛け",
        "Ｇ前仕掛け",
        "叩一杯",
    ]

    for word in words:
        if word in s:
            return word

    return ""


def extract_pairing(value):
    s = clean_text(value)

    keywords = [
        "併せ",
        "先着",
        "遅れ",
        "同入",
    ]

    hits = [
        word
        for word in keywords
        if word in s
    ]

    if not hits:
        return ""

    if len(s) <= 200:
        return s

    first_index = min(
        s.find(word)
        for word in hits
        if s.find(word) >= 0
    )

    start = max(
        0,
        first_index - 70
    )

    end = min(
        len(s),
        first_index + 130
    )

    return s[start:end]


def training_keyword_hit(value):
    s = clean_text(value)

    keywords = [
        "調教",
        "追い切",
        "追切",
        "坂路",
        "CW",
        "ＣＷ",
        "南W",
        "南Ｗ",
        "美浦W",
        "美浦Ｗ",
        "ウッド",
        "馬なり",
        "一杯",
        "強め",
        "仕掛け",
        "併せ",
    ]

    return any(
        word in s
        for word in keywords
    )


def is_plausible_training_block(value):
    s = clean_text(value)

    if not s:
        return False

    times = extract_time_values(s)

    if not times:
        return False

    keyword = training_keyword_hit(s)
    course = detect_course(s)

    # 時計だけでは追い切りと断定しない
    if not keyword and not course:
        return False

    return True


def parse_training_block(value):
    raw = clean_text(value)

    if not is_plausible_training_block(raw):
        return None

    times = extract_time_values(raw)

    if not times:
        return None

    course = detect_course(raw)
    effort = extract_effort(raw)

    return {
        "date": extract_date(raw),
        "course": course,
        "times": times,
        "last_section_candidate": (
            times[-1]
            if times
            else None
        ),
        "effort": effort,
        "pairing": extract_pairing(raw),
        "raw": raw[:600],
    }


def quality_score(block):
    score = 0

    if block.get("date"):
        score += 2

    if block.get("course"):
        score += 3

    times = block.get(
        "times",
        []
    )

    if len(times) >= 5:
        score += 5

    elif len(times) >= 4:
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


def extract_tables(soup):
    blocks = []

    tables = soup.find_all("table")

    for table_index, table in enumerate(tables):
        rows = table.find_all("tr")

        for row_index, row in enumerate(rows):
            cells = [
                clean_text(
                    cell.get_text(
                        " ",
                        strip=True
                    )
                )
                for cell in row.find_all(
                    ["th", "td"]
                )
            ]

            if not cells:
                continue

            joined = " | ".join(cells)

            parsed = parse_training_block(
                joined
            )

            if parsed is None:
                continue

            parsed["source_type"] = "table"
            parsed["table_index"] = table_index
            parsed["row_index"] = row_index
            parsed["quality_score"] = (
                quality_score(parsed)
            )

            blocks.append(parsed)

    return blocks


def extract_text_windows(soup):
    blocks = []

    strings = [
        clean_text(value)
        for value in soup.stripped_strings
        if clean_text(value)
    ]

    for index in range(len(strings)):
        start = max(
            0,
            index - 3
        )

        end = min(
            len(strings),
            index + 7
        )

        window = " | ".join(
            strings[start:end]
        )

        parsed = parse_training_block(
            window
        )

        if parsed is None:
            continue

        parsed["source_type"] = "text"
        parsed["line_index"] = index
        parsed["quality_score"] = (
            quality_score(parsed)
        )

        blocks.append(parsed)

    return blocks


def deduplicate(blocks):
    result = []
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
            block.get("effort", ""),
        )

        if key in seen:
            continue

        seen.add(key)
        result.append(block)

    return result


def inspect_page(url):
    response = fetch(url)

    soup = BeautifulSoup(
        response.text,
        "html.parser"
    )

    title = ""

    if soup.title:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
        )

    page_text = clean_text(
        soup.get_text(
            " ",
            strip=True
        )
    )

    blocks = extract_tables(
        soup
    )

    # table以外に描画されるケースへの保険
    text_blocks = extract_text_windows(
        soup
    )

    blocks.extend(
        text_blocks
    )

    blocks = deduplicate(
        blocks
    )

    blocks.sort(
        key=lambda x: x.get(
            "quality_score",
            0
        ),
        reverse=True
    )

    return {
        "title": title,
        "http_status": response.status_code,
        "html_length": len(response.text),
        "table_count": len(
            soup.find_all("table")
        ),
        "page_has_training_keyword": (
            training_keyword_hit(
                page_text
            )
        ),
        "page_time_like_value_count": len(
            extract_time_values(
                page_text
            )
        ),
        "training_block_count": len(
            blocks
        ),
        "training_blocks": blocks[:30],
    }


def build_candidate_urls(
    race_id,
    horse_id
):
    """
    race_id付きURLを優先。

    race.netkeiba の調教画面は
    レース文脈を必要とするケースがあるため、
    race_id + horse_id の候補を先に試す。
    """

    candidates = []

    if race_id:
        params = urlencode({
            "race_id": race_id,
            "horse_id": horse_id,
        })

        candidates.extend([
            (
                "netkeiba_training_race_horse",
                (
                    "https://race.netkeiba.com/"
                    "training/training.html?"
                    + params
                )
            ),
            (
                "netkeiba_training_race",
                (
                    "https://race.netkeiba.com/"
                    "training/training.html"
                    f"?race_id={race_id}"
                )
            ),
        ])

    candidates.extend([
        (
            "netkeiba_training_horse",
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
        ),
    ])

    unique = []
    seen = set()

    for source, url in candidates:
        if url in seen:
            continue

        seen.add(url)

        unique.append(
            (source, url)
        )

    return unique


def block_matches_horse(
    block,
    horse_name
):
    """
    race_id単位のページには複数馬が含まれる可能性がある。

    raw内に馬名がある場合は一致確認。
    馬名自体がページ構造上省略される場合もあるので、
    horse_nameが無いだけでは即除外しない。
    """

    raw = clean_text(
        block.get("raw")
    )

    if not raw:
        return False

    if horse_name and horse_name in raw:
        return True

    return None


def select_blocks_for_horse(
    blocks,
    horse_name,
    source_name
):
    if not blocks:
        return []

    # race全体ページでは他馬混入を避ける
    if source_name == "netkeiba_training_race":
        matched = [
            block
            for block in blocks
            if block_matches_horse(
                block,
                horse_name
            ) is True
        ]

        return matched

    return blocks


def analyze_horse(
    race_id,
    horse
):
    horse_id = clean_text(
        horse.get("horse_id")
    )

    horse_number = clean_text(
        horse.get("horse_number")
    )

    horse_name = clean_text(
        horse.get("horse_name")
    )

    result = {
        "horse_id": horse_id,
        "horse_number": horse_number,
        "horse_name": horse_name,
        "detail_found": False,
        "source": "",
        "source_url": "",
        "training_count": 0,
        "training": [],
        "checks": [],
        "error": "",
    }

    if not horse_id:
        result["error"] = "horse_idなし"
        return result

    best = None

    candidates = build_candidate_urls(
        race_id,
        horse_id
    )

    for source_name, url in candidates:
        check = {
            "source": source_name,
            "url": url,
            "http_ok": False,
            "title": "",
            "html_length": 0,
            "table_count": 0,
            "page_has_training_keyword": False,
            "page_time_like_value_count": 0,
            "training_block_count": 0,
            "horse_training_block_count": 0,
            "error": "",
        }

        try:
            inspection = inspect_page(
                url
            )

            check["http_ok"] = True
            check["title"] = inspection[
                "title"
            ]
            check["html_length"] = inspection[
                "html_length"
            ]
            check["table_count"] = inspection[
                "table_count"
            ]
            check[
                "page_has_training_keyword"
            ] = inspection[
                "page_has_training_keyword"
            ]
            check[
                "page_time_like_value_count"
            ] = inspection[
                "page_time_like_value_count"
            ]
            check[
                "training_block_count"
            ] = inspection[
                "training_block_count"
            ]

            selected_blocks = (
                select_blocks_for_horse(
                    inspection[
                        "training_blocks"
                    ],
                    horse_name,
                    source_name
                )
            )

            check[
                "horse_training_block_count"
            ] = len(
                selected_blocks
            )

            if selected_blocks:
                candidate_score = sum(
                    block.get(
                        "quality_score",
                        0
                    )
                    for block in selected_blocks[:5]
                )

                candidate = {
                    "source": source_name,
                    "url": url,
                    "blocks": selected_blocks,
                    "score": candidate_score,
                }

                if (
                    best is None
                    or candidate["score"]
                    > best["score"]
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
        result["detail_found"] = True
        result["source"] = best[
            "source"
        ]
        result["source_url"] = best[
            "url"
        ]
        result["training"] = best[
            "blocks"
        ]
        result["training_count"] = len(
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

    race_id = get_race_id(
        race
    )

    if not race_id:
        raise RuntimeError(
            "race.jsonにrace_idがありません"
        )

    horses = get_horses(
        race
    )

    if not horses:
        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    results = []

    for index, horse in enumerate(
        horses,
        start=1
    ):
        horse_name = clean_text(
            horse.get("horse_name")
        )

        print(
            f"[{index}/{len(horses)}] "
            f"{horse_name}"
        )

        result = analyze_horse(
            race_id,
            horse
        )

        results.append(
            result
        )

        print(
            " detail:",
            result["detail_found"],
            " blocks:",
            result["training_count"]
        )

        for check in result["checks"]:
            print(
                "  ",
                check["source"],
                "http=",
                check["http_ok"],
                "tables=",
                check["table_count"],
                "time_like=",
                check[
                    "page_time_like_value_count"
                ],
                "blocks=",
                check[
                    "training_block_count"
                ],
                "horse_blocks=",
                check[
                    "horse_training_block_count"
                ],
                "error=",
                check["error"],
            )

    detail_found_count = sum(
        1
        for result in results
        if result["detail_found"]
    )

    total_training_blocks = sum(
        result["training_count"]
        for result in results
    )

    output = {
        "updated_at": now_jst(),
        "source_race_file": RACE_FILE,
        "source_detection_file": (
            DETECTION_FILE
        ),
        "target_race_id": race_id,
        "purpose": (
            "objective_training_detail_extraction"
        ),
        "summary": {
            "horse_count": len(results),
            "detail_found_count": (
                detail_found_count
            ),
            "detail_not_found_count": (
                len(results)
                - detail_found_count
            ),
            "total_training_blocks": (
                total_training_blocks
            ),
        },
        "rules": {
            "training_is_supporting_data": True,
            "final_workout_not_independent_bonus": True,
            "training_used_for_condition_check": True,
            "training_used_for_issue_resolution_check": True,
            "unknown_not_penalized": True,
            "keyword_only_not_counted_as_training": True,
            "time_value_required": True,
            "target_race_context_used": True,
        },
        "horses": results,
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

    print()
    print("TRAINING DETAIL SUMMARY")
    print(
        "target race:",
        race_id
    )
    print(
        "horses:",
        len(results)
    )
    print(
        "detail found:",
        detail_found_count
    )
    print(
        "detail unknown:",
        len(results)
        - detail_found_count
    )
    print(
        "training blocks:",
        total_training_blocks
    )
    print(
        "saved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
