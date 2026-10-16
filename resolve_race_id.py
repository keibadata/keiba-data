import os
import re
import sys
import requests
from bs4 import BeautifulSoup
from datetime import datetime


TRACK_CODES = {
    "札幌": "01",
    "函館": "02",
    "福島": "03",
    "新潟": "04",
    "東京": "05",
    "中山": "06",
    "中京": "07",
    "京都": "08",
    "阪神": "09",
    "小倉": "10",
}


def normalize_date(value):
    value = str(value).strip()

    for fmt in (
        "%Y%m%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(value, fmt).strftime("%Y%m%d")
        except ValueError:
            pass

    raise ValueError(
        f"開催日の形式が不正です: {value}"
    )


def normalize_race_no(value):
    text = str(value).strip().upper()
    text = text.replace("Ｒ", "R")

    match = re.search(r"(\d{1,2})", text)

    if not match:
        raise ValueError(
            f"R番号を取得できません: {value}"
        )

    race_no = int(match.group(1))

    if not 1 <= race_no <= 12:
        raise ValueError(
            f"R番号は1〜12で指定してください: {race_no}"
        )

    return race_no


def get_race_ids_from_html(html):
    ids = set()

    patterns = [
        r"race_id=(\d{12})",
        r"/race/[^\"']*?(\d{12})",
        r"\b(\d{12})\b",
    ]

    for pattern in patterns:
        for race_id in re.findall(pattern, html):
            ids.add(race_id)

    return sorted(ids)


def fetch_race_list(date):
    url = (
        "https://race.netkeiba.com/"
        f"top/race_list.html?kaisai_date={date}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/17.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9,en;q=0.8",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


def resolve_race_id(date, track, race_no):
    date = normalize_date(date)
    track = str(track).strip()
    race_no = normalize_race_no(race_no)

    if track not in TRACK_CODES:
        raise ValueError(
            f"未対応の競馬場です: {track}"
        )

    track_code = TRACK_CODES[track]

    print(
        f"Race ID検索: {date} / "
        f"{track} / {race_no}R"
    )

    html = fetch_race_list(date)

    race_ids = get_race_ids_from_html(html)

    print(
        f"レース一覧から {len(race_ids)} 件の"
        "Race ID候補を取得"
    )

    candidates = []

    for race_id in race_ids:
        if len(race_id) != 12:
            continue

        year = race_id[0:4]
        venue = race_id[4:6]
        race_number = race_id[10:12]

        if year != date[0:4]:
            continue

        if venue != track_code:
            continue

        if int(race_number) != race_no:
            continue

        candidates.append(race_id)

    candidates = sorted(set(candidates))

    if not candidates:
        raise RuntimeError(
            "該当Race IDが見つかりませんでした: "
            f"{date} / {track} / {race_no}R"
        )

    if len(candidates) > 1:
        raise RuntimeError(
            "Race ID候補が複数見つかりました: "
            + ", ".join(candidates)
        )

    race_id = candidates[0]

    print(f"Race ID確定: {race_id}")

    return race_id


def write_race_id(race_id):
    with open(
        "race_id.txt",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(race_id + "\n")

    print("race_id.txt 更新完了")


def write_github_output(race_id):
    output_path = os.environ.get("GITHUB_OUTPUT")

    if not output_path:
        return

    with open(
        output_path,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(f"race_id={race_id}\n")


def main():
    date = os.environ.get("RACE_DATE", "").strip()
    track = os.environ.get("RACE_TRACK", "").strip()
    race_no = os.environ.get("RACE_NO", "").strip()

    if not date:
        raise ValueError(
            "RACE_DATE が指定されていません"
        )

    if not track:
        raise ValueError(
            "RACE_TRACK が指定されていません"
        )

    if not race_no:
        raise ValueError(
            "RACE_NO が指定されていません"
        )

    race_id = resolve_race_id(
        date,
        track,
        race_no,
    )

    write_race_id(race_id)
    write_github_output(race_id)

    print(
        "Race ID自動取得完了: "
        f"{date} / {track} / {race_no}R"
        f" -> {race_id}"
    )


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        print(
            f"Race ID自動取得エラー: {e}",
            file=sys.stderr,
        )
        sys.exit(1)
