import sys
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://race.sp.netkeiba.com/"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def text(el):
    return el.get_text(" ", strip=True) if el else ""


def horse_id_from_href(href):
    if not href:
        return ""
    m = re.search(r"/horse/(?:result/)?(\d+)", href)
    return m.group(1) if m else ""


def get_html(race_id):
    r = requests.get(
        BASE_URL,
        params={
            "pid": "race_result",
            "race_id": race_id,
        },
        headers=HEADERS,
        timeout=30,
    )
    r.raise_for_status()

    r.encoding = r.apparent_encoding

    with open("history_debug.html", "w", encoding="utf-8") as f:
        f.write(r.text)

    print("HTTP:", r.status_code)
    print("URL:", r.url)
    print("HTML bytes:", len(r.content))

    return r.text


def parse_result_row(row):
    # 着順
    rank_el = row.select_one("td.Result_Num .Rank")
    rank = text(rank_el)
    rank = re.sub(r"\s*着$", "", rank)

    # 枠番・馬番
    nums = row.select("td.Num")
    frame_number = text(nums[0]) if len(nums) >= 1 else ""
    horse_number = text(nums[1]) if len(nums) >= 2 else ""

    # 馬
    horse_el = row.select_one(".Horse_Name a")
    if not horse_el:
        return None

    horse_name = text(horse_el)
    horse_id = horse_id_from_href(horse_el.get("href", ""))

    # 性齢・馬体重
    detail_left = row.select_one(".Horse_Info_Detail .Detail_Left")
    sex_age = ""
    horse_weight = ""
    weight_change = ""

    if detail_left:
        left_text = text(detail_left)

        m = re.search(r"(牡|牝|セ|騸)\s*(\d+)", left_text)
        if m:
            sex_age = m.group(1) + m.group(2)

        m = re.search(
            r"(\d+)kg\s*\(([+-]?\d+)\)",
            left_text
        )
        if m:
            horse_weight = m.group(1)
            weight_change = m.group(2)

    # 騎手・斤量
    detail_right = row.select_one(
        ".Horse_Info_Detail .Detail_Right"
    )

    jockey = ""
    carried_weight = ""
    trainer = ""

    if detail_right:
        right_text = text(detail_right)

        m = re.search(
            r"(.+?)\s+(\d+(?:\.\d+)?)",
            right_text
        )
        if m:
            jockey = m.group(1).strip()
            carried_weight = m.group(2)

        parts = list(detail_right.stripped_strings)
        if len(parts) >= 2:
            trainer = parts[-1]

    # タイム
    time_el = row.select_one("td.Time dt span")
    if not time_el:
        time_el = row.select_one("td.Time dt")

    race_time = text(time_el)

    # 着差
    margin = ""
    time_dd = row.select("td.Time dd")

    if time_dd:
        # 空欄は除外
        values = [text(x) for x in time_dd if text(x)]

        # (33.3) のような上がり表記は着差にしない
        for value in values:
            if not re.fullmatch(
                r"\(\d+(?:\.\d+)?\)",
                value
            ):
                margin = value
                break

    # 単勝・人気
    odds = text(row.select_one("td.Odds .Odds_Ninki"))

    popularity = ""
    odds_dd = row.select_one("td.Odds dd")
    if odds_dd:
        popularity = text(odds_dd)

    odds = odds.replace("倍", "")
    popularity = popularity.replace("人気", "")

    # 上がり3F
    last3f = ""

    # まず専用セルを探す
    for selector in [
        "td.Last3F",
        ".Last3F",
        "td.Agari",
        ".Agari",
    ]:
        el = row.select_one(selector)
        if el:
            value = text(el)
            m = re.search(r"\d+\.\d+", value)
            if m:
                last3f = m.group(0)
                break

    # スマホ版では Time 内の括弧値の場合がある
    if not last3f:
        for dd in row.select("td.Time dd"):
            value = text(dd)
            m = re.fullmatch(
                r"\((\d+(?:\.\d+)?)\)",
                value
            )
            if m:
                last3f = m.group(1)
                break

    # 通過順位
    passing = ""

    for selector in [
        "td.Passing",
        ".Passing",
        "td.Corner",
        ".Corner",
    ]:
        el = row.select_one(selector)
        if el:
            passing = text(el)
            if passing:
                break

    return {
        "rank": rank,
        "frame_number": frame_number,
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "horse_weight": horse_weight,
        "weight_change": weight_change,
        "carried_weight": carried_weight,
        "jockey": jockey,
        "trainer": trainer,
        "time": race_time,
        "margin": margin,
        "passing": passing,
        "last3f": last3f,
        "odds": odds,
        "popularity": popularity,
    }


def get_race_result(race_id):
    html = get_html(race_id)
    soup = BeautifulSoup(html, "html.parser")

    # 実際のスマホ版結果HTML
    rows = soup.select("tr.FirstDisplay")

    print("FirstDisplay rows:", len(rows))

    # 念のため Result_Num を持つ行も探索
    if not rows:
        rows = [
            tr for tr in soup.select("tr")
            if tr.select_one("td.Result_Num")
            and tr.select_one(".Horse_Name")
        ]

    print("result rows:", len(rows))

    results = []

    for row in rows:
        item = parse_result_row(row)

        if not item:
            continue

        # 馬名だけの誤取得を防止
        if not item["horse_name"]:
            continue

        results.append(item)

    return results


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            '使い方: python history.py "202605040502"'
        )

    race_id = sys.argv[1].strip()

    if not re.fullmatch(r"\d{12}", race_id):
        raise SystemExit(
            f"race_id は12桁で指定してください: {race_id}"
        )

    print("取得開始:", race_id)

    results = get_race_result(race_id)

    data = {
        "race_id": race_id,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": "netkeiba",
        "result_count": len(results),
        "results": results,
    }

    with open(
        "history.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("取得件数:", len(results))
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
    )

    if not results:
        raise RuntimeError(
            "結果行を取得できませんでした。"
            " history_debug.html を確認してください。"
        )


if __name__ == "__main__":
    main()
