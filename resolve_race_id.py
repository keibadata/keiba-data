import os
import re
import sys
import requests
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


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 17_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/17.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def normalize_date(value):
    value = str(value).strip()

    for fmt in (
        "%Y%m%d",
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                value,
                fmt,
            ).strftime("%Y%m%d")
        except ValueError:
            pass

    raise ValueError(
        f"開催日の形式が不正です: {value}"
    )


def normalize_race_no(value):
    text = str(value).strip()
    text = text.upper().replace("Ｒ", "R")

    match = re.search(
        r"(\d{1,2})",
        text,
    )

    if not match:
        raise ValueError(
            f"R番号を取得できません: {value}"
        )

    race_no = int(match.group(1))

    if not 1 <= race_no <= 12:
        raise ValueError(
            f"R番号は1〜12です: {race_no}"
        )

    return race_no


def fetch(url):
    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    return response.text


def extract_race_ids(html):
    race_ids = re.findall(
        r"race_id=(\d{12})",
        html,
    )

    return list(
        dict.fromkeys(race_ids)
    )


def verify_race_date(
    race_id,
    target_date,
):
    url = (
        "https://race.netkeiba.com/"
        "race/shutuba.html"
        f"?race_id={race_id}"
    )

    try:
        html = fetch(url)
    except Exception as e:
        print(
            f"日付確認失敗 {race_id}: {e}"
        )
        return False

    compact = re.sub(
        r"\s+",
        "",
        html,
    )

    dt = datetime.strptime(
        target_date,
        "%Y%m%d",
    )

    patterns = [
        dt.strftime("%Y年%m月%d日"),
        (
            f"{dt.year}年"
            f"{dt.month}月"
            f"{dt.day}日"
        ),
        dt.strftime("%Y/%m/%d"),
        dt.strftime("%Y-%m-%d"),
        target_date,
    ]

    for pattern in patterns:
        if pattern in compact:
            return True

    return False


def resolve_race_id(
    date,
    track,
    race_no,
):
    date = normalize_date(date)
    track = str(track).strip()
    race_no = normalize_race_no(race_no)

    if track not in TRACK_CODES:
        raise ValueError(
            f"未対応の競馬場です: {track}"
        )

    track_code = TRACK_CODES[track]

    print(
        "Race ID検索:",
        date,
        "/",
        track,
        "/",
        f"{race_no}R",
    )

    list_url = (
        "https://race.netkeiba.com/"
        "top/race_list.html"
        f"?kaisai_date={date}"
    )

    html = fetch(list_url)

    race_ids = extract_race_ids(html)

    print(
        "レース一覧から",
        len(race_ids),
        "件のRace IDを取得",
    )

    if not race_ids:
        raise RuntimeError(
            "レース一覧から"
            "Race IDを取得できません"
        )

    candidates = []

    for race_id in race_ids:
        if not re.fullmatch(
            r"\d{12}",
            race_id,
        ):
            continue

        if race_id[4:6] != track_code:
            continue

        if int(race_id[10:12]) != race_no:
            continue

        candidates.append(race_id)

    candidates = list(
        dict.fromkeys(candidates)
    )

    print(
        "一次候補:",
        candidates,
    )

    if not candidates:
        raise RuntimeError(
            "競馬場・R番号に一致する"
            "Race IDがありません"
        )

    verified = []

    for race_id in candidates:
        print(
            "開催日確認:",
            race_id,
        )

        if verify_race_date(
            race_id,
            date,
        ):
            verified.append(race_id)

            print(
                "開催日一致:",
                race_id,
            )
        else:
            print(
                "開催日不一致:",
                race_id,
            )

    if not verified:
        raise RuntimeError(
            "指定開催日に一致する"
            "Race IDが見つかりません"
        )

    if len(verified) > 1:
        raise RuntimeError(
            "開催日確認後も"
            "Race ID候補が複数あります: "
            + ", ".join(verified)
        )

    race_id = verified[0]

    print(
        "Race ID確定:",
        race_id,
    )

    return race_id


def write_race_id(race_id):
    with open(
        "race_id.txt",
        "w",
        encoding="utf-8",
    ) as f:
        f.write(
            race_id + "\n"
        )

    print(
        "race_id.txt 更新完了"
    )


def write_github_output(race_id):
    output_path = os.environ.get(
        "GITHUB_OUTPUT"
    )

    if not output_path:
        return

    with open(
        output_path,
        "a",
        encoding="utf-8",
    ) as f:
        f.write(
            f"race_id={race_id}\n"
        )


def main():
    date = os.environ.get(
        "RACE_DATE",
        "",
    ).strip()

    track = os.environ.get(
        "RACE_TRACK",
        "",
    ).strip()

    race_no = os.environ.get(
        "RACE_NO",
        "",
    ).strip()

    if not date:
        raise ValueError(
            "RACE_DATE がありません"
        )

    if not track:
        raise ValueError(
            "RACE_TRACK がありません"
        )

    if not race_no:
        raise ValueError(
            "RACE_NO がありません"
        )

    race_id = resolve_race_id(
        date,
        track,
        race_no,
    )

    write_race_id(
        race_id
    )

    write_github_output(
        race_id
    )

    print(
        "Race ID自動取得完了:",
        date,
        "/",
        track,
        "/",
        race_no + "R",
        "->",
        race_id,
    )


if __name__ == "__main__":
    try:
        main()

    except Exception as e:
        print(
            "Race ID自動取得エラー:",
            e,
            file=sys.stderr,
        )

        sys.exit(1)
