import json
import re
import sys
from datetime import datetime
from zoneinfo import ZoneInfo

import requests
from bs4 import BeautifulSoup


def clean_text(value):
    if value is None:
        return ""
    return re.sub(r"\s+", " ", value.get_text(" ", strip=True)).strip()


def get_race_result(race_id):
    if not re.fullmatch(r"\d{12}", race_id):
        raise ValueError(f"RaceIDが不正です: {race_id}")

    url = (
        "https://race.netkeiba.com/race/result.html"
        f"?race_id={race_id}"
    )

    headers = {
        "User-Agent": (
            "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1"
        )
    }

    response = requests.get(url, headers=headers, timeout=30)
    response.raise_for_status()
    response.encoding = response.apparent_encoding

    soup = BeautifulSoup(response.text, "html.parser")

    rows = []

    for tr in soup.select("tr.HorseList"):
        horse_link = tr.select_one(".Horse_Name a, .HorseName a")

        if not horse_link:
            continue

        href = horse_link.get("href", "")

        horse_id_match = re.search(r"/horse/(\d+)", href)
        horse_id = horse_id_match.group(1) if horse_id_match else ""

        def pick(*selectors):
            for selector in selectors:
                node = tr.select_one(selector)
                if node:
                    return clean_text(node)
            return ""

        horse_number = pick(".Num", ".Umaban")
        horse_name = clean_text(horse_link)

        finish = pick(".Rank")
        margin = pick(".着差", ".Margin")
        time_value = pick(".Time")
        weight = pick(".Weight")
        jockey = pick(".Jockey")
        body_weight = pick(".WeightHorse", ".HorseWeight")
        passing = pick(".通過", ".Passing")
        last3f = pick(".上り", ".Last3F")

        rows.append({
            "race_id": race_id,
            "horse_id": horse_id,
            "horse_number": horse_number,
            "horse_name": horse_name,
            "finish": finish,
            "margin": margin,
            "passing": passing,
            "last3f": last3f,
            "time": time_value,
            "carried_weight": weight,
            "jockey": jockey,
            "body_weight": body_weight,
        })

    if not rows:
        raise RuntimeError(
            "結果テーブルを取得できませんでした。"
            "HTML構造変更またはRaceIDを確認してください。"
        )

    return {
        "race_id": race_id,
        "source": "netkeiba",
        "source_url": url,
        "updated_at": datetime.now(
            ZoneInfo("Asia/Tokyo")
        ).isoformat(),
        "runner_count": len(rows),
        "runners": rows,
    }


def main():
    race_ids = sys.argv[1:]

    if not race_ids:
        # 接続確認用：2026/10/12 東京2R
        race_ids = ["202605040502"]

    results = []

    for race_id in race_ids:
        print(f"取得開始: {race_id}")
        result = get_race_result(race_id)
        results.append(result)

        print(
            f"取得成功: {race_id} "
            f"/ {result['runner_count']}頭"
        )

    output = {
        "updated_at": datetime.now(
            ZoneInfo("Asia/Tokyo")
        ).isoformat(),
        "race_count": len(results),
        "races": results,
    }

    with open(
        "history.json",
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
        f"history.json作成完了: "
        f"{len(results)}レース"
    )


if __name__ == "__main__":
    main()
