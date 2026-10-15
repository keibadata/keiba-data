import json
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
OUTPUT_FILE = "runner_history.json"

BASE_URL = "https://db.netkeiba.com/horse/{horse_id}/"

REQUEST_INTERVAL = 1.2
TIMEOUT = 20
MAX_RETRIES = 3

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}

JST = timezone(timedelta(hours=9))


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", str(value)).strip()


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def fetch(session, url):
    last_error = None

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            response = session.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT
            )

            if response.status_code == 200:
                response.encoding = (
                    response.apparent_encoding or "EUC-JP"
                )
                return response.text

            last_error = f"HTTP {response.status_code}"

        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(REQUEST_INTERVAL * attempt)

    raise RuntimeError(last_error or "取得失敗")


def extract_horses(data):
    candidates = []

    if isinstance(data, dict):
        for key in [
            "runners",
            "horses",
            "entries",
            "results"
        ]:
            value = data.get(key)
            if isinstance(value, list):
                candidates = value
                break

        if not candidates:
            race = data.get("race")

            if isinstance(race, dict):
                for key in [
                    "runners",
                    "horses",
                    "entries",
                    "results"
                ]:
                    value = race.get(key)
                    if isinstance(value, list):
                        candidates = value
                        break

    elif isinstance(data, list):
        candidates = data

    horses = []

    for item in candidates:
        if not isinstance(item, dict):
            continue

        horse_id = clean_text(
            item.get("horse_id") or item.get("id")
        )

        horse_name = clean_text(
            item.get("horse_name") or item.get("name")
        )

        horse_number = clean_text(
            item.get("horse_number")
            or item.get("number")
            or item.get("umaban")
        )

        if not horse_id:
            continue

        horses.append({
            "horse_id": horse_id,
            "horse_name": horse_name,
            "horse_number": horse_number
        })

    unique = {}

    for horse in horses:
        unique[horse["horse_id"]] = horse

    return list(unique.values())


def get_table_headers(table):
    first_row = table.find("tr")

    if not first_row:
        return []

    return [
        clean_text(cell.get_text(" ", strip=True))
        for cell in first_row.find_all(["th", "td"])
    ]


def find_history_table(soup):
    best_table = None
    best_score = -1

    for table in soup.find_all("table"):
        headers = get_table_headers(table)
        header_text = " ".join(headers)

        score = 0

        for word in [
            "日付",
            "開催",
            "R",
            "レース名",
            "距離",
            "着順",
            "タイム",
            "上り",
            "通過"
        ]:
            if word in header_text:
                score += 1

        if score > best_score:
            best_score = score
            best_table = table

    if best_score < 4:
        return None

    return best_table


def header_index(headers, names):
    for name in names:
        for i, header in enumerate(headers):
            if clean_text(header) == name:
                return i

    for name in names:
        for i, header in enumerate(headers):
            if name in clean_text(header):
                return i

    return -1


def cell_value(cells, index):
    if index < 0 or index >= len(cells):
        return ""

    return clean_text(
        cells[index].get_text(" ", strip=True)
    )


def parse_distance(value):
    value = clean_text(value)

    match = re.search(r"([芝ダ障])\s*(\d+)", value)

    if not match:
        return {
            "surface": "",
            "distance": None
        }

    surface_map = {
        "芝": "芝",
        "ダ": "ダート",
        "障": "障害"
    }

    return {
        "surface": surface_map.get(
            match.group(1),
            match.group(1)
        ),
        "distance": int(match.group(2))
    }


def parse_course(value):
    value = clean_text(value)

    match = re.search(
        r"(\d+回)?"
        r"(東京|中山|京都|阪神|中京|札幌|函館|福島|新潟|小倉)"
        r"(\d+日)?",
        value
    )

    if match:
        return match.group(2)

    return value


def parse_rank(value):
    value = clean_text(value)

    match = re.search(r"\d+", value)

    if not match:
        return None

    try:
        return int(match.group())
    except Exception:
        return None


def parse_weight(value):
    value = clean_text(value)

    match = re.search(
        r"(\d+)(?:\(([+-]?\d+)\))?",
        value
    )

    if not match:
        return {
            "horse_weight": None,
            "weight_change": None
        }

    weight = int(match.group(1))

    change = (
        int(match.group(2))
        if match.group(2)
        else None
    )

    return {
        "horse_weight": weight,
        "weight_change": change
    }


def parse_race_link(cells):
    for cell in cells:
        links = cell.find_all("a", href=True)

        for link in links:
            href = link.get("href", "")

            match = re.search(
                r"/race/(?:result/)?(\d+)",
                href
            )

            if match:
                return match.group(1)

    return ""


def parse_history(html):
    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    table = find_history_table(soup)

    if table is None:
        raise RuntimeError(
            "過去成績テーブルが見つかりません"
        )

    rows = table.find_all("tr")

    if not rows:
        return []

    headers = [
        clean_text(
            cell.get_text(" ", strip=True)
        )
        for cell in rows[0].find_all(["th", "td"])
    ]

    idx_date = header_index(headers, ["日付"])
    idx_course = header_index(headers, ["開催"])
    idx_race_number = header_index(headers, ["R"])
    idx_race_name = header_index(headers, ["レース名"])
    idx_field = header_index(headers, ["頭数"])
    idx_frame = header_index(headers, ["枠番"])
    idx_number = header_index(headers, ["馬番"])
    idx_odds = header_index(headers, ["オッズ"])
    idx_popularity = header_index(headers, ["人気"])
    idx_rank = header_index(headers, ["着順"])
    idx_jockey = header_index(headers, ["騎手"])
    idx_weight_carried = header_index(headers, ["斤量"])
    idx_distance = header_index(headers, ["距離"])
    idx_track = header_index(headers, ["馬場"])
    idx_time = header_index(headers, ["タイム"])
    idx_margin = header_index(headers, ["着差"])
    idx_passing = header_index(headers, ["通過"])
    idx_pace = header_index(headers, ["ペース"])
    idx_last3f = header_index(headers, ["上り"])
    idx_weight = header_index(headers, ["馬体重"])

    history = []

    for tr in rows[1:]:
        cells = tr.find_all(["td", "th"])

        if len(cells) < 5:
            continue

        race_date = cell_value(
            cells,
            idx_date
        )

        rank_raw = cell_value(
            cells,
            idx_rank
        )

        if not race_date:
            continue

        distance_raw = cell_value(
            cells,
            idx_distance
        )

        distance_info = parse_distance(
            distance_raw
        )

        weight_info = parse_weight(
            cell_value(
                cells,
                idx_weight
            )
        )

        race = {
            "race_id": parse_race_link(cells),
            "date": race_date,
            "racecourse": parse_course(
                cell_value(cells, idx_course)
            ),
            "race_number": cell_value(
                cells,
                idx_race_number
            ),
            "race_name": cell_value(
                cells,
                idx_race_name
            ),
            "field_size": cell_value(
                cells,
                idx_field
            ),
            "frame_number": cell_value(
                cells,
                idx_frame
            ),
            "horse_number": cell_value(
                cells,
                idx_number
            ),
            "odds": cell_value(
                cells,
                idx_odds
            ),
            "popularity": cell_value(
                cells,
                idx_popularity
            ),
            "rank": parse_rank(rank_raw),
            "rank_raw": rank_raw,
            "jockey": cell_value(
                cells,
                idx_jockey
            ),
            "carried_weight": cell_value(
                cells,
                idx_weight_carried
            ),
            "surface": distance_info["surface"],
            "distance": distance_info["distance"],
            "distance_raw": distance_raw,
            "track_condition": cell_value(
                cells,
                idx_track
            ),
            "time": cell_value(
                cells,
                idx_time
            ),
            "margin": cell_value(
                cells,
                idx_margin
            ),
            "passing": cell_value(
                cells,
                idx_passing
            ),
            "pace": cell_value(
                cells,
                idx_pace
            ),
            "last3f": cell_value(
                cells,
                idx_last3f
            ),
            "horse_weight": weight_info[
                "horse_weight"
            ],
            "weight_change": weight_info[
                "weight_change"
            ]
        }

        history.append(race)

    return history


def main():
    print("Loading race.json...")

    race_data = load_json(
        RACE_FILE
    )

    horses = extract_horses(
        race_data
    )

    print(
        "Target horses:",
        len(horses)
    )

    if not horses:
        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    session = requests.Session()

    collected = []
    errors = []

    for index, horse in enumerate(
        horses,
        start=1
    ):
        horse_id = horse["horse_id"]
        horse_name = horse["horse_name"]

        url = BASE_URL.format(
            horse_id=horse_id
        )

        print(
            f"[{index}/{len(horses)}] "
            f"{horse_name} "
            f"{horse_id}"
        )

        try:
            html = fetch(
                session,
                url
            )

            history = parse_history(
                html
            )

            collected.append({
                "horse_id": horse_id,
                "horse_number": horse[
                    "horse_number"
                ],
                "horse_name": horse_name,
                "race_count": len(history),
                "races": history
            })

            print(
                "  races:",
                len(history)
            )

        except Exception as e:
            error = {
                "horse_id": horse_id,
                "horse_name": horse_name,
                "error": str(e)
            }

            errors.append(error)

            collected.append({
                "horse_id": horse_id,
                "horse_number": horse[
                    "horse_number"
                ],
                "horse_name": horse_name,
                "race_count": 0,
                "races": []
            })

            print(
                "  ERROR:",
                str(e)
            )

        if index < len(horses):
            time.sleep(
                REQUEST_INTERVAL
            )

    total_races = sum(
        horse["race_count"]
        for horse in collected
    )

    successful_horses = sum(
        1
        for horse in collected
        if horse["race_count"] > 0
    )

    output = {
        "updated_at": datetime.now(
            JST
        ).isoformat(),
        "source": "netkeiba",
        "source_race_file": RACE_FILE,
        "target_horse_count": len(horses),
        "collected_horse_count": successful_horses,
        "total_past_race_count": total_races,
        "error_count": len(errors),
        "errors": errors,
        "horses": collected
    }

    save_json(
        OUTPUT_FILE,
        output
    )

    print("")
    print(
        "Saved:",
        OUTPUT_FILE
    )
    print(
        "target_horse_count:",
        output["target_horse_count"]
    )
    print(
        "collected_horse_count:",
        output["collected_horse_count"]
    )
    print(
        "total_past_race_count:",
        output["total_past_race_count"]
    )
    print(
        "error_count:",
        output["error_count"]
    )


if __name__ == "__main__":
    main()
