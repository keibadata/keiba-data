import json
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
OUTPUT_FILE = "history_races.json"

MAX_RACES = 20
LOOKBACK_DAYS = 180
REQUEST_WAIT = 0.5
DATE_WAIT = 0.8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def normalize_surface(value):
    value = str(value or "").strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_distance(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_html(url, params=None):
    r = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    return r.text


def extract_race_ids(html):
    ids = re.findall(
        r"race_id=(\d{12})",
        html
    )

    ids += re.findall(
        r"/race/(?:result/)?(\d{12})",
        html
    )

    result = []
    seen = set()

    for race_id in ids:
        if race_id in seen:
            continue

        seen.add(race_id)
        result.append(race_id)

    return result


def get_target_condition(race):
    race_info = race.get("race_info", {})

    if not isinstance(race_info, dict):
        race_info = {}

    race_id = str(
        race.get("race_id", "")
    ).strip()

    race_date = str(
        race.get("race_date")
        or race_info.get("race_date")
        or ""
    ).strip()

    track = str(
        race.get("track")
        or race.get("racecourse")
        or race_info.get("track")
        or race_info.get("racecourse")
        or ""
    ).strip()

    surface = normalize_surface(
        race.get("surface")
        or race_info.get("surface")
        or ""
    )

    distance = normalize_distance(
        race.get("distance")
        or race_info.get("distance")
        or 0
    )

    if not re.fullmatch(r"\d{12}", race_id):
        raise RuntimeError(
            "race.json の race_id が不正です"
        )

    try:
        target_date = datetime.strptime(
            race_date,
            "%Y-%m-%d"
        ).date()
    except ValueError:
        raise RuntimeError(
            "race.json の race_date を取得できません"
        )

    if not track:
        raise RuntimeError(
            "race.json の競馬場を取得できません"
        )

    if not surface:
        raise RuntimeError(
            "race.json の芝・ダートを取得できません"
        )

    if distance <= 0:
        raise RuntimeError(
            "race.json の距離を取得できません"
        )

    return {
        "race_id": race_id,
        "race_date": race_date,
        "target_date": target_date,
        "racecourse": track,
        "surface": surface,
        "distance": distance,
    }


def parse_race_info(race_id):
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

    text = soup.get_text(
        " ",
        strip=True
    )

    race_number = ""

    if re.fullmatch(r"\d{12}", race_id):
        number = int(race_id[-2:])

        if 1 <= number <= 12:
            race_number = f"{number}R"

    racecourse = ""

    for name in (
        "札幌", "函館", "福島", "新潟",
        "東京", "中山", "中京", "京都",
        "阪神", "小倉",
    ):
        if name in text:
            racecourse = name
            break

    surface = ""
    distance = 0

    patterns = (
        r"(芝|ダート|ダ)\s*([12]\d{3})\s*[mｍ]",
        r"(芝|ダート|ダ)\s*([12]\d{3})",
        r"([12]\d{3})\s*[mｍ]\s*(芝|ダート|ダ)",
    )

    for pattern in patterns:
        m = re.search(pattern, text)

        if not m:
            continue

        a = m.group(1)
        b = m.group(2)

        if a in ("芝", "ダート", "ダ"):
            surface = normalize_surface(a)
            distance = int(b)
        else:
            distance = int(a)
            surface = normalize_surface(b)

        break

    return {
        "race_id": race_id,
        "racecourse": racecourse,
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
    }


def find_races_from_date(date_string):
    html = get_html(
        "https://race.netkeiba.com/top/race_list.html",
        {
            "kaisai_date": date_string
        },
    )

    return extract_race_ids(html)


def main():
    race = load_json(RACE_FILE)
    target = get_target_condition(race)

    print("==============================")
    print("条件別 過去レース探索")
    print("対象Race ID:", target["race_id"])
    print("対象日:", target["race_date"])
    print(
        "条件:",
        target["racecourse"],
        target["surface"],
        target["distance"],
    )
    print("==============================")

    matched = []
    checked_ids = set()
    errors = []

    # 対象レース当日は含めない。
    # 前日から過去方向へ探索する。
    for days_back in range(1, LOOKBACK_DAYS + 1):
        search_date = (
            target["target_date"]
            - timedelta(days=days_back)
        )

        date_string = search_date.strftime(
            "%Y%m%d"
        )

        try:
            race_ids = find_races_from_date(
                date_string
            )
        except Exception as e:
            errors.append({
                "date": date_string,
                "error": str(e),
            })
            continue

        if not race_ids:
            continue

        print(
            "開催日:",
            date_string,
            "候補:",
            len(race_ids),
        )

        for race_id in race_ids:
            if race_id == target["race_id"]:
                continue

            if race_id in checked_ids:
                continue

            checked_ids.add(race_id)

            try:
                info = parse_race_info(
                    race_id
                )

                if (
                    info["racecourse"]
                    == target["racecourse"]
                    and info["surface"]
                    == target["surface"]
                    and info["distance"]
                    == target["distance"]
                ):
                    info["race_date"] = (
                        search_date.isoformat()
                    )

                    matched.append(info)

                    print(
                        "  MATCH:",
                        race_id,
                        info["racecourse"],
                        info["surface"],
                        info["distance"],
                    )

                    if len(matched) >= MAX_RACES:
                        break

                time.sleep(REQUEST_WAIT)

            except Exception as e:
                errors.append({
                    "race_id": race_id,
                    "error": str(e),
                })

        if len(matched) >= MAX_RACES:
            break

        time.sleep(DATE_WAIT)

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "target_race_id": target["race_id"],

        "condition": {
            "racecourse": target["racecourse"],
            "surface": target["surface"],
            "distance": target["distance"],
        },

        "search": {
            "before_date": target["race_date"],
            "lookback_days": LOOKBACK_DAYS,
            "max_races": MAX_RACES,
            "future_races_excluded": True,
            "target_race_excluded": True,
        },

        "race_count": len(matched),
        "races": matched,
        "error_count": len(errors),
        "errors": errors,
    }

    save_json(
        OUTPUT_FILE,
        output
    )

    print("==============================")
    print("history_races.json 作成完了")
    print("対象条件レース:", len(matched))
    print("取得エラー:", len(errors))
    print("==============================")

    if not matched:
        raise RuntimeError(
            "対象レース以前に同条件の過去レースを取得できませんでした"
        )


if __name__ == "__main__":
    main()
