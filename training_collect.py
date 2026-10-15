import json
import re
import time
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup

RACE_FILE = "race.json"
OUTPUT_FILE = "training.json"

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
    return str(value).strip()


def fetch(url):
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            response = requests.get(
                url,
                headers=HEADERS,
                timeout=TIMEOUT,
            )

            if response.status_code == 200:
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


def candidate_urls(horse_id):
    """
    取得可否を検証する段階。
    horse_idから候補ページを確認する。
    """

    return [
        (
            "netkeiba_horse",
            f"https://db.netkeiba.com/horse/{horse_id}/"
        ),
        (
            "netkeiba_training",
            f"https://race.netkeiba.com/training/"
            f"training.html?horse_id={horse_id}"
        ),
    ]


def inspect_page(response):
    """
    調教らしい情報がHTML内に存在するかだけ確認。
    この段階では評価しない。
    """

    response.encoding = (
        response.apparent_encoding
        or response.encoding
        or "utf-8"
    )

    html = response.text

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    page_text = soup.get_text(
        " ",
        strip=True
    )

    keywords = [
        "調教",
        "追い切り",
        "坂路",
        "ウッド",
        "CW",
        "美浦",
        "栗東",
    ]

    found_keywords = [
        word
        for word in keywords
        if word in page_text
    ]

    # タイムらしい表記
    time_patterns = re.findall(
        r"\b\d{2}\.\d\b",
        page_text
    )

    tables = soup.find_all("table")

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

        "found_keywords":
            found_keywords,

        "table_count":
            len(tables),

        "time_like_value_count":
            len(time_patterns),

        "possible_training_data":
            bool(
                found_keywords
                and (
                    len(tables) > 0
                    or len(time_patterns) > 0
                )
            ),
    }


def inspect_horse(horse):

    horse_id = text(
        horse.get("horse_id")
    )

    horse_number = text(
        horse.get("horse_number")
    )

    horse_name = text(
        horse.get("horse_name")
    )

    result = {
        "horse_id": horse_id,
        "horse_number": horse_number,
        "horse_name": horse_name,

        "training_data_found":
            False,

        "selected_source":
            "",

        "selected_url":
            "",

        "checks":
            [],

        "error":
            "",
    }

    if not horse_id:
        result["error"] = (
            "horse_idなし"
        )
        return result

    for source_name, url in candidate_urls(
        horse_id
    ):

        check = {
            "source":
                source_name,

            "url":
                url,

            "http_ok":
                False,

            "inspection":
                None,

            "error":
                "",
        }

        try:
            response = fetch(url)

            check["http_ok"] = True

            inspection = inspect_page(
                response
            )

            check["inspection"] = (
                inspection
            )

            result["checks"].append(
                check
            )

            if inspection[
                "possible_training_data"
            ]:

                result[
                    "training_data_found"
                ] = True

                result[
                    "selected_source"
                ] = source_name

                result[
                    "selected_url"
                ] = url

                break

        except Exception as e:

            check["error"] = str(e)

            result["checks"].append(
                check
            )

        time.sleep(
            REQUEST_INTERVAL
        )

    return result


def get_horses(data):

    # race.jsonの構造差に対応
    for key in (
        "horses",
        "runners",
        "entries",
    ):
        value = data.get(key)

        if isinstance(value, list):
            return value

    return []


def main():

    with open(
        RACE_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        race = json.load(f)

    horses = get_horses(race)

    if not horses:
        raise RuntimeError(
            "race.jsonから出走馬を取得できません"
        )

    results = []

    for index, horse in enumerate(
        horses,
        start=1
    ):

        print(
            f"[{index}/{len(horses)}] "
            f"{text(horse.get('horse_name'))}"
        )

        result = inspect_horse(
            horse
        )

        results.append(
            result
        )

        time.sleep(
            REQUEST_INTERVAL
        )

    found_count = sum(
        1
        for x in results
        if x["training_data_found"]
    )

    output = {
        "updated_at":
            now_jst(),

        "purpose":
            "training_source_detection",

        "source_race_file":
            RACE_FILE,

        "summary": {
            "horse_count":
                len(results),

            "training_data_found_count":
                found_count,

            "not_found_count":
                len(results) -
                found_count,
        },

        "rules": {
            "training_not_scored_yet":
                True,

            "final_workout_not_independent_bonus":
                True,

            "training_used_for_condition_check":
                True,

            "training_used_for_issue_resolution_check":
                True,

            "unknown_not_penalized":
                True,
        },

        "horses":
            results,
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
        "===== Training Source Detection ====="
    )

    print(
        "horses:",
        len(results)
    )

    print(
        "training data found:",
        found_count
    )

    print(
        "not found:",
        len(results) - found_count
    )


if __name__ == "__main__":
    main()
