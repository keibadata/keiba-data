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
            "AppleWebKit/605.1.15 Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8",
    }

    response = requests.get(
        url,
        headers=headers,
        timeout=30,
    )
    response.raise_for_status()

    response.encoding = response.apparent_encoding
    soup = BeautifulSoup(response.text, "html.parser")

    # netkeiba結果ページの構造差に対応
    result_rows = soup.select(
        "table.RaceTable01 tbody tr, "
        "table.RaceTable01 tr, "
        ".RaceTable01 tbody tr, "
        ".RaceTable01 tr, "
        "tr.HorseList"
    )

    rows = []
    seen = set()

    for tr in result_rows:

        # 馬リンク
        horse_link = tr.select_one(
            ".Horse_Name a, "
            ".HorseName a, "
            "td.Horse_Info a, "
            "a[href*='/horse/']"
        )

        if not horse_link:
            continue

        href = horse_link.get("href", "")

        horse_id_match = re.search(
            r"/horse/(\d+)",
            href
        )

        horse_id = (
            horse_id_match.group(1)
            if horse_id_match
            else ""
        )

        horse_name = clean_text(horse_link)

        if not horse_name:
            continue

        # 同じ馬の重複取得防止
        unique_key = horse_id or horse_name

        if unique_key in seen:
            continue

        seen.add(unique_key)

        def pick(*selectors):
            for selector in selectors:
                node = tr.select_one(selector)
                if node:
                    text = clean_text(node)
                    if text:
                        return text
            return ""

        # 着順
        finish = pick(
            ".Rank",
            ".Result_Num",
            "td.Result_Num"
        )

        # 馬番
        horse_number = pick(
            ".Num",
            ".Umaban",
            "td.Num"
        )

        # 着差
        margin = pick(
            ".着差",
            ".Margin"
        )

        # 走破時計
        time_value = pick(
            ".Time"
        )

        # 斤量
        carried_weight = pick(
            ".Weight"
        )

        # 騎手
        jockey = pick(
            ".Jockey a",
            ".Jockey"
        )

        # 馬体重
        body_weight = pick(
            ".WeightHorse",
            ".HorseWeight"
        )

        # 通過順位
        passing = pick(
            ".通過",
            ".Passing"
        )

        # 上がり3F
        last3f = pick(
            ".上り",
            ".Last3F"
        )

        # CSSクラスが取れない場合にtdから補完
        cells = [
            clean_text(td)
            for td in tr.select("td")
        ]

        # 最低限、着順・馬番を補完
        if not finish and cells:
            for cell in cells[:3]:
                if re.fullmatch(r"\d+", cell):
                    finish = cell
                    break

        if not horse_number:
            # 馬番候補を馬名より前のセルから探す
            for cell in cells[:5]:
                if re.fullmatch(r"\d{1,2}", cell):
                    if cell != finish:
                        horse_number = cell
                        break

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
            "carried_weight": carried_weight,
            "jockey": jockey,
            "body_weight": body_weight,
        })

    if not rows:
        # デバッグ用情報を残す
        with open(
            "history_debug.html",
            "w",
            encoding="utf-8"
        ) as f:
            f.write(response.text)

        raise RuntimeError(
            "結果行を取得できませんでした。"
            " history_debug.html を保存しました。"
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

    if len(sys.argv) >= 2:
        race_id = sys.argv[1].strip()
    else:
        race_id = "202605040502"

    print(f"取得開始: {race_id}")

    result = get_race_result(race_id)

    with open(
        "history.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            result,
            f,
            ensure_ascii=False,
            indent=2
        )

    print(
        f"取得成功: "
        f"{result['runner_count']}頭"
    )

    for horse in result["runners"]:
        print(
            horse["finish"],
            horse["horse_number"],
            horse["horse_name"],
            horse["time"],
            horse["last3f"]
        )


if __name__ == "__main__":
    main()
