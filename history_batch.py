import json
import re
import time
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

# =========================================================
# 設定
# =========================================================

TARGET_COURSE = "東京"
TARGET_SURFACE = "芝"
TARGET_DISTANCE = 1400

# 最初は安全確認のため最大20レース
MAX_RACES = 20

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def get_json(url):
    r = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )
    r.raise_for_status()
    return r.json()


def get_html(url, params=None):
    r = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30
    )
    r.raise_for_status()
    r.encoding = r.apparent_encoding
    return r.text


# =========================================================
# Race ID抽出
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

    result = []

    for race_id in ids:
        if race_id not in result:
            result.append(race_id)

    return result


# =========================================================
# レース情報
# =========================================================

def parse_race_info(race_id):

    html = get_html(
        "https://race.sp.netkeiba.com/",
        {
            "pid": "race_result",
            "race_id": race_id,
        }
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
        n = int(race_id[-2:])

        if 1 <= n <= 12:
            race_number = f"{n}R"

    course = ""

    for name in [
        "札幌", "函館", "福島", "新潟",
        "東京", "中山", "中京", "京都",
        "阪神", "小倉"
    ]:
        if name in text:
            course = name
            break

    surface = ""
    distance = ""

    patterns = [
        r"(芝|ダート|ダ)\s*([12]\d{3})\s*[mｍ]",
        r"(芝|ダート|ダ)\s*([12]\d{3})",
        r"([12]\d{3})\s*[mｍ]\s*(芝|ダート|ダ)",
    ]

    for pattern in patterns:

        m = re.search(pattern, text)

        if not m:
            continue

        a = m.group(1)
        b = m.group(2)

        if a in ("芝", "ダート", "ダ"):
            surface = a
            distance = int(b)
        else:
            distance = int(a)
            surface = b

        if surface == "ダ":
            surface = "ダート"

        break

    return {
        "race_id": race_id,
        "racecourse": course,
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
    }


# =========================================================
# 開催日のレース一覧からRace ID取得
# =========================================================

def find_races_from_date(date_string):

    url = "https://race.netkeiba.com/top/race_list.html"

    html = get_html(
        url,
        {
            "kaisai_date": date_string
        }
    )

    return extract_race_ids(html)


# =========================================================
# 東京芝1400mだけ抽出
# =========================================================

def filter_target_races(race_ids):

    matches = []

    for race_id in race_ids:

        try:
            info = parse_race_info(race_id)

            print(
                race_id,
                info["racecourse"],
                info["surface"],
                info["distance"]
            )

            if (
                info["racecourse"] == TARGET_COURSE
                and info["surface"] == TARGET_SURFACE
                and info["distance"] == TARGET_DISTANCE
            ):
                matches.append(info)

                print(
                    "  -> 対象レース"
                )

                if len(matches) >= MAX_RACES:
                    break

            # サーバー負荷を抑える
            time.sleep(0.5)

        except Exception as e:

            print(
                "取得失敗:",
                race_id,
                str(e)
            )

    return matches


# =========================================================
# main
# =========================================================

def main():

    # -----------------------------------------------------
    # 最初の検証対象
    # 2026年10月開催
    # -----------------------------------------------------

    dates = [
        "20261003",
        "20261004",
        "20261010",
        "20261011",
        "20261012",
    ]

    all_race_ids = []

    for date_string in dates:

        print(
            "開催日検索:",
            date_string
        )

        try:

            ids = find_races_from_date(
                date_string
            )

            print(
                "Race ID:",
                len(ids)
            )

            for race_id in ids:

                if race_id not in all_race_ids:
                    all_race_ids.append(
                        race_id
                    )

        except Exception as e:

            print(
                "開催日取得失敗:",
                date_string,
                str(e)
            )

        time.sleep(1)

    print(
        "全候補Race ID:",
        len(all_race_ids)
    )

    target_races = filter_target_races(
        all_race_ids
    )

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "condition": {
            "racecourse": TARGET_COURSE,
            "surface": TARGET_SURFACE,
            "distance": TARGET_DISTANCE,
        },

        "race_count": len(target_races),

        "races": target_races,
    }

    with open(
        "history_races.json",
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
        "=============================="
    )

    print(
        "対象レース数:",
        len(target_races)
    )

    for race in target_races:

        print(
            race["race_id"],
            race["racecourse"],
            race["race_number"],
            race["surface"],
            race["distance"]
        )

    print(
        "history_races.json 作成完了"
    )


if __name__ == "__main__":
    main()
