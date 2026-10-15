import json
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

RACE_FILE = "race.json"
OUTPUT_FILE = "training_race.json"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
}

TIMEOUT = 30


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def clean(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def get_race_id(data):
    for key in ("race_id", "raceId", "id"):
        value = data.get(key)
        if value:
            return str(value).strip()

    raise RuntimeError("race.jsonにrace_idがありません")


def get_runners(data):
    for key in ("horses", "runners", "entries"):
        value = data.get(key)
        if isinstance(value, list):
            return value
    return []


def horse_name(horse):
    for key in ("horse_name", "name"):
        if horse.get(key):
            return clean(horse[key])
    return ""


def horse_number(horse):
    for key in ("horse_number", "number", "umaban"):
        if horse.get(key) is not None:
            return clean(horse[key])
    return ""


def extract_times(value):
    # 87.3(18.4) → 87.3
    values = re.findall(
        r"(?<!\d)(\d{2,3}\.\d)(?:\(\d{2,3}\.\d\))?",
        value
    )

    result = []

    for value in values:
        try:
            number = float(value)
        except Exception:
            continue

        if 10 <= number <= 150:
            result.append(number)

    return result


def parse_date(value):
    m = re.search(
        r"(20\d{2}/\d{2}/\d{2})",
        value
    )
    return m.group(1) if m else ""


def detect_course(value):
    patterns = (
        "美Ｗ", "美W",
        "栗坂", "美坂",
        "ＣＷ", "CW",
        "栗Ｗ", "栗W",
        "美芝", "栗芝",
        "美Ｐ", "栗Ｐ",
        "ポリ"
    )

    for p in patterns:
        if p in value:
            return p

    return ""


def detect_effort(value):
    for word in (
        "馬也",
        "馬なり",
        "一杯",
        "強め",
        "仕掛",
        "末強め",
        "直強め"
    ):
        if word in value:
            return word
    return ""


def pairing_text(value):
    words = (
        "併せ",
        "併入",
        "先着",
        "遅れ"
    )

    if not any(x in value for x in words):
        return ""

    for word in words:
        pos = value.find(word)

        if pos >= 0:
            start = max(0, pos - 70)
            end = min(len(value), pos + 100)
            return value[start:end]

    return ""


def row_is_training(value):
    return (
        bool(parse_date(value))
        and bool(extract_times(value))
    )


def parse_page(html, runners):
    soup = BeautifulSoup(html, "html.parser")

    runner_names = [
        horse_name(x)
        for x in runners
        if horse_name(x)
    ]

    results = {
        name: []
        for name in runner_names
    }

    current_name = ""

    # netkeibaの調教表を行単位で処理
    for tr in soup.find_all("tr"):
        row = clean(
            tr.get_text(" ", strip=True)
        )

        if not row:
            continue

        # 行中に馬名があれば現在馬を更新
        for name in runner_names:
            if name in row:
                current_name = name
                break

        if not current_name:
            continue

        if not row_is_training(row):
            continue

        times = extract_times(row)

        workout = {
            "date": parse_date(row),
            "course": detect_course(row),
            "times": times,
            "last_section": (
                times[-1]
                if times
                else None
            ),
            "effort": detect_effort(row),
            "pairing": pairing_text(row),
            "raw": row[:700]
        }

        results[current_name].append(workout)

    # HTML構造によって複数追切が同一tdに入る場合への補完
    page_text = clean(
        soup.get_text(" ", strip=True)
    )

    for index, name in enumerate(runner_names):
        if results[name]:
            continue

        start = page_text.find(name)

        if start < 0:
            continue

        end = len(page_text)

        for next_name in runner_names[index + 1:]:
            next_pos = page_text.find(
                next_name,
                start + len(name)
            )

            if next_pos >= 0:
                end = min(end, next_pos)

        section = page_text[start:end]

        date_positions = list(
            re.finditer(
                r"20\d{2}/\d{2}/\d{2}",
                section
            )
        )

        for i, match in enumerate(date_positions):
            block_start = match.start()

            if i + 1 < len(date_positions):
                block_end = date_positions[i + 1].start()
            else:
                block_end = len(section)

            block = section[
                block_start:block_end
            ]

            times = extract_times(block)

            if not times:
                continue

            results[name].append({
                "date": parse_date(block),
                "course": detect_course(block),
                "times": times,
                "last_section": times[-1],
                "effort": detect_effort(block),
                "pairing": pairing_text(block),
                "raw": block[:700]
            })

    return results


def main():
    with open(
        RACE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        race = json.load(f)

    race_id = get_race_id(race)
    runners = get_runners(race)

    if not runners:
        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    url = (
        "https://race.netkeiba.com/"
        "race/oikiri.html"
        f"?race_id={race_id}&type=1"
    )

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    if response.status_code != 200:
        raise RuntimeError(
            f"調教ページ HTTP {response.status_code}"
        )

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    parsed = parse_page(
        response.text,
        runners
    )

    horses = []

    found = 0

    for runner in runners:
        name = horse_name(runner)
        workouts = parsed.get(name, [])

        if workouts:
            found += 1

        horses.append({
            "horse_id": clean(
                runner.get("horse_id", "")
            ),
            "horse_number": horse_number(runner),
            "horse_name": name,
            "training_found": bool(workouts),
            "training_count": len(workouts),
            "training": workouts
        })

    output = {
        "updated_at": now_jst(),
        "race_id": race_id,
        "source": "netkeiba_race_oikiri",
        "source_url": url,

        "summary": {
            "horse_count": len(horses),
            "training_found_count": found,
            "training_not_found_count":
                len(horses) - found
        },

        "rules": {
            "objective_data_only": True,
            "netkeiba_rating_not_used": True,
            "netkeiba_short_comment_not_used": True,
            "training_is_supporting_data": True,
            "final_workout_not_independent_bonus": True,
            "unknown_not_penalized": True
        },

        "horses": horses
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

    print("===== Training Race =====")
    print("race_id:", race_id)
    print("horses:", len(horses))
    print("training found:", found)
    print(
        "not found:",
        len(horses) - found
    )


if __name__ == "__main__":
    main()
