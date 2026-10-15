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
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/141.0.0.0 Safari/537.36"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8"
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

            print(
                "  HTTP:",
                response.status_code,
                "bytes:",
                len(response.content)
            )

            if response.status_code == 200:
                response.encoding = (
                    response.apparent_encoding
                    or response.encoding
                    or "EUC-JP"
                )
                return response.text

            last_error = (
                f"HTTP {response.status_code}"
            )

        except Exception as e:
            last_error = str(e)

        if attempt < MAX_RETRIES:
            time.sleep(
                REQUEST_INTERVAL * attempt
            )

    raise RuntimeError(
        last_error or "取得失敗"
    )


def extract_horses(data):
    candidates = []

    if isinstance(data, dict):
        for key in (
            "runners",
            "horses",
            "entries",
            "results"
        ):
            if isinstance(data.get(key), list):
                candidates = data[key]
                break

        if not candidates:
            race = data.get("race")

            if isinstance(race, dict):
                for key in (
                    "runners",
                    "horses",
                    "entries",
                    "results"
                ):
                    if isinstance(
                        race.get(key),
                        list
                    ):
                        candidates = race[key]
                        break

    elif isinstance(data, list):
        candidates = data

    horses = {}

    for item in candidates:
        if not isinstance(item, dict):
            continue

        horse_id = clean_text(
            item.get("horse_id")
            or item.get("id")
        )

        if not horse_id:
            continue

        horses[horse_id] = {
            "horse_id": horse_id,
            "horse_name": clean_text(
                item.get("horse_name")
                or item.get("name")
            ),
            "horse_number": clean_text(
                item.get("horse_number")
                or item.get("number")
                or item.get("umaban")
            )
        }

    return list(horses.values())


def find_result_table(soup):
    # netkeibaで過去走表に使われる代表的なclass
    selectors = [
        "table.db_h_race_results",
        "table.race_table_01",
        "table.nk_tb_common",
    ]

    for selector in selectors:
        tables = soup.select(selector)

        for table in tables:
            text = clean_text(
                table.get_text(
                    " ",
                    strip=True
                )
            )

            if (
                "日付" in text
                and "着順" in text
                and (
                    "レース名" in text
                    or "レース" in text
                )
            ):
                return table

    # classに依存しない予備判定
    for table in soup.find_all("table"):
        text = clean_text(
            table.get_text(
                " ",
                strip=True
            )
        )

        required = 0

        for word in (
            "日付",
            "着順",
            "騎手",
            "距離"
        ):
            if word in text:
                required += 1

        if required >= 3:
            return table

    return None


def build_header_map(table):
    rows = table.find_all("tr")

    if not rows:
        return {}, []

    header_row = None
    headers = []

    for row_index, row in enumerate(rows):
        cells = row.find_all(
            ["th", "td"]
        )

        values = [
            clean_text(
                cell.get_text(
                    " ",
                    strip=True
                )
            )
            for cell in cells
        ]

        joined = " ".join(values)

        if (
            "日付" in joined
            and (
                "着順" in joined
                or "レース名" in joined
            )
        ):
            header_row = row_index
            headers = values
            break

    if header_row is None:
        return {}, rows

    header_map = {}

    for i, header in enumerate(headers):
        if header:
            header_map[header] = i

    return {
        "map": header_map,
        "headers": headers,
        "row_index": header_row
    }, rows


def find_col(headers, *names):
    for name in names:
        for i, header in enumerate(headers):
            if header == name:
                return i

    for name in names:
        for i, header in enumerate(headers):
            if name in header:
                return i

    return -1


def get_cell(cells, index):
    if index < 0:
        return ""

    if index >= len(cells):
        return ""

    return clean_text(
        cells[index].get_text(
            " ",
            strip=True
        )
    )


def parse_int(value):
    match = re.search(
        r"-?\d+",
        clean_text(value)
    )

    if not match:
        return None

    try:
        return int(match.group())
    except Exception:
        return None


def parse_float(value):
    value = clean_text(value).replace(
        ",",
        ""
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        value
    )

    if not match:
        return None

    try:
        return float(match.group())
    except Exception:
        return None


def parse_rank(value):
    return parse_int(value)


def parse_distance(value):
    value = clean_text(value)

    match = re.search(
        r"(芝|ダ|ダート|障)\s*([0-9]+)",
        value
    )

    if not match:
        return "", None

    surface = match.group(1)

    if surface == "ダ":
        surface = "ダート"

    if surface == "障":
        surface = "障害"

    return surface, int(match.group(2))


def parse_course(value):
    value = clean_text(value)

    match = re.search(
        r"(東京|中山|京都|阪神|中京|"
        r"札幌|函館|福島|新潟|小倉|"
        r"大井|川崎|船橋|浦和|門別|"
        r"園田|姫路|名古屋|笠松|"
        r"高知|佐賀|盛岡|水沢)",
        value
    )

    if match:
        return match.group(1)

    return value


def parse_weight(value):
    value = clean_text(value)

    match = re.search(
        r"(\d+)"
        r"(?:\(([+-]?\d+)\))?",
        value
    )

    if not match:
        return None, None

    weight = int(match.group(1))

    change = (
        int(match.group(2))
        if match.group(2)
        else None
    )

    return weight, change


def extract_race_id(cells):
    for cell in cells:
        for link in cell.find_all(
            "a",
            href=True
        ):
            href = link.get(
                "href",
                ""
            )

            patterns = [
                r"/race/(\d{10,14})",
                r"race_id=(\d{10,14})"
            ]

            for pattern in patterns:
                match = re.search(
                    pattern,
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

    table = find_result_table(soup)

    if table is None:
        title = clean_text(
            soup.title.get_text(
                " ",
                strip=True
            )
            if soup.title
            else ""
        )

        raise RuntimeError(
            "過去成績テーブルなし"
            f" / title={title}"
            f" / tables={len(soup.find_all('table'))}"
        )

    header_info, rows = build_header_map(
        table
    )

    if not header_info:
        raise RuntimeError(
            "過去成績のヘッダーを認識できません"
        )

    headers = header_info["headers"]
    start_index = (
        header_info["row_index"] + 1
    )

    idx_date = find_col(
        headers,
        "日付"
    )

    idx_course = find_col(
        headers,
        "開催"
    )

    idx_r = find_col(
        headers,
        "R"
    )

    idx_race = find_col(
        headers,
        "レース名",
        "レース"
    )

    idx_field = find_col(
        headers,
        "頭数"
    )

    idx_frame = find_col(
        headers,
        "枠番",
        "枠"
    )

    idx_number = find_col(
        headers,
        "馬番"
    )

    idx_odds = find_col(
        headers,
        "オッズ"
    )

    idx_popularity = find_col(
        headers,
        "人気"
    )

    idx_rank = find_col(
        headers,
        "着順"
    )

    idx_jockey = find_col(
        headers,
        "騎手"
    )

    idx_weight_carried = find_col(
        headers,
        "斤量"
    )

    idx_distance = find_col(
        headers,
        "距離"
    )

    idx_track = find_col(
        headers,
        "馬場"
    )

    idx_time = find_col(
        headers,
        "タイム"
    )

    idx_margin = find_col(
        headers,
        "着差"
    )

    idx_passing = find_col(
        headers,
        "通過"
    )

    idx_pace = find_col(
        headers,
        "ペース"
    )

    idx_last3f = find_col(
        headers,
        "上り",
        "上がり"
    )

    idx_weight = find_col(
        headers,
        "馬体重"
    )

    history = []

    for row in rows[start_index:]:
        cells = row.find_all(
            ["td", "th"]
        )

        if not cells:
            continue

        date = get_cell(
            cells,
            idx_date
        )

        rank_raw = get_cell(
            cells,
            idx_rank
        )

        if not date:
            continue

        # 日付らしくない行を除外
        if not re.search(
            r"\d{4}[./-]\d{1,2}[./-]\d{1,2}",
            date
        ):
            continue

        distance_raw = get_cell(
            cells,
            idx_distance
        )

        surface, distance = parse_distance(
            distance_raw
        )

        horse_weight, weight_change = (
            parse_weight(
                get_cell(
                    cells,
                    idx_weight
                )
            )
        )

        history.append({
            "race_id": extract_race_id(
                cells
            ),
            "date": date,
            "racecourse": parse_course(
                get_cell(
                    cells,
                    idx_course
                )
            ),
            "race_number": get_cell(
                cells,
                idx_r
            ),
            "race_name": get_cell(
                cells,
                idx_race
            ),
            "field_size": parse_int(
                get_cell(
                    cells,
                    idx_field
                )
            ),
            "frame_number": parse_int(
                get_cell(
                    cells,
                    idx_frame
                )
            ),
            "horse_number": parse_int(
                get_cell(
                    cells,
                    idx_number
                )
            ),
            "odds": parse_float(
                get_cell(
                    cells,
                    idx_odds
                )
            ),
            "popularity": parse_int(
                get_cell(
                    cells,
                    idx_popularity
                )
            ),
            "rank": parse_rank(
                rank_raw
            ),
            "rank_raw": rank_raw,
            "jockey": get_cell(
                cells,
                idx_jockey
            ),
            "carried_weight": parse_float(
                get_cell(
                    cells,
                    idx_weight_carried
                )
            ),
            "surface": surface,
            "distance": distance,
            "distance_raw": distance_raw,
            "track_condition": get_cell(
                cells,
                idx_track
            ),
            "time": get_cell(
                cells,
                idx_time
            ),
            "margin": get_cell(
                cells,
                idx_margin
            ),
            "passing": get_cell(
                cells,
                idx_passing
            ),
            "pace": get_cell(
                cells,
                idx_pace
            ),
            "last3f": parse_float(
                get_cell(
                    cells,
                    idx_last3f
                )
            ),
            "horse_weight": horse_weight,
            "weight_change": weight_change
        })

    if not history:
        raise RuntimeError(
            "過去成績テーブルは存在するが"
            "レース行を取得できません"
        )

    return history


def main():
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

        print(
            f"[{index}/{len(horses)}] "
            f"{horse_name} "
            f"{horse_id}"
        )

        try:
            html = fetch(
                session,
                BASE_URL.format(
                    horse_id=horse_id
                )
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
                "  OK races:",
                len(history)
            )

        except Exception as e:
            message = str(e)

            print(
                "  ERROR:",
                message
            )

            errors.append({
                "horse_id": horse_id,
                "horse_name": horse_name,
                "error": message
            })

            collected.append({
                "horse_id": horse_id,
                "horse_number": horse[
                    "horse_number"
                ],
                "horse_name": horse_name,
                "race_count": 0,
                "races": []
            })

        if index < len(horses):
            time.sleep(
                REQUEST_INTERVAL
            )

    total_races = sum(
        x["race_count"]
        for x in collected
    )

    collected_count = sum(
        1
        for x in collected
        if x["race_count"] > 0
    )

    output = {
        "updated_at": datetime.now(
            JST
        ).isoformat(),
        "source": "netkeiba",
        "source_race_file": RACE_FILE,
        "target_horse_count": len(horses),
        "collected_horse_count": (
            collected_count
        ),
        "total_past_race_count": (
            total_races
        ),
        "error_count": len(errors),
        "errors": errors,
        "horses": collected
    }

    save_json(
        OUTPUT_FILE,
        output
    )

    print("")
    print("===== RESULT =====")
    print(
        "target_horse_count:",
        len(horses)
    )
    print(
        "collected_horse_count:",
        collected_count
    )
    print(
        "total_past_race_count:",
        total_races
    )
    print(
        "error_count:",
        len(errors)
    )


if __name__ == "__main__":
    main()
