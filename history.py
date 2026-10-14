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


def txt(el):
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

    with open(
        "history_debug.html",
        "w",
        encoding="utf-8"
    ) as f:
        f.write(r.text)

    print("HTTP:", r.status_code)
    print("URL:", r.url)
    print("HTML bytes:", len(r.content))

    return r.text


def parse_result_row(row):

    # --------------------
    # 着順
    # --------------------
    rank = txt(
        row.select_one("td.Result_Num .Rank")
    )

    rank = re.sub(r"\s*着$", "", rank).strip()


    # --------------------
    # 枠番・馬番
    # --------------------
    nums = row.select("td.Num")

    frame_number = ""
    horse_number = ""

    if len(nums) >= 1:
        frame_number = txt(nums[0])

    if len(nums) >= 2:
        horse_number = txt(nums[1])


    # --------------------
    # 馬名・馬ID
    # --------------------
    horse_el = row.select_one(".Horse_Name a")

    if not horse_el:
        return None

    horse_name = txt(horse_el)

    horse_id = horse_id_from_href(
        horse_el.get("href", "")
    )


    # --------------------
    # 性齢・馬体重
    # --------------------
    sex_age = ""
    horse_weight = ""
    weight_change = ""

    detail_left = row.select_one(
        ".Horse_Info_Detail .Detail_Left"
    )

    if detail_left:

        left_text = txt(detail_left)

        m = re.search(
            r"(牡|牝|セ|騸)\s*(\d+)",
            left_text
        )

        if m:
            sex_age = m.group(1) + m.group(2)

        m = re.search(
            r"(\d+)kg\s*\(([+\-−]?\d+)\)",
            left_text
        )

        if m:
            horse_weight = m.group(1)
            weight_change = (
                m.group(2).replace("−", "-")
            )


    # --------------------
    # 騎手・斤量・厩舎
    # --------------------
    jockey = ""
    carried_weight = ""
    trainer = ""

    detail_right = row.select_one(
        ".Horse_Info_Detail .Detail_Right"
    )

    if detail_right:

        parts = list(
            detail_right.stripped_strings
        )

        if parts:

            first = parts[0]

            m = re.match(
                r"(.+?)\s+(\d+(?:\.\d+)?)$",
                first
            )

            if m:
                jockey = m.group(1).strip()
                carried_weight = m.group(2)

        if len(parts) >= 2:
            trainer = parts[-1]


    # --------------------
    # タイム
    # --------------------
    race_time = txt(
        row.select_one("td.Time dt span")
    )

    if not race_time:
        race_time = txt(
            row.select_one("td.Time dt")
        )


    # --------------------
    # 着差
    # --------------------
    margin = ""

    for dd in row.select("td.Time dd"):

        value = txt(dd)

        if not value:
            continue

        # 上がり3Fは除外
        if re.fullmatch(
            r"\(\d+(?:\.\d+)?\)",
            value
        ):
            continue

        margin = value
        break


    # --------------------
    # 上がり3F
    # --------------------
    last3f = ""

    for dd in row.select("td.Time dd"):

        value = txt(dd)

        m = re.fullmatch(
            r"\((\d+(?:\.\d+)?)\)",
            value
        )

        if m:
            last3f = m.group(1)
            break

    if not last3f:

        for selector in [
            "td.Last3F",
            ".Last3F",
            "td.Agari",
            ".Agari",
        ]:

            el = row.select_one(selector)

            if el:

                m = re.search(
                    r"\d+\.\d+",
                    txt(el)
                )

                if m:
                    last3f = m.group(0)
                    break


    # --------------------
    # オッズ・人気
    # --------------------
    odds = txt(
        row.select_one(
            "td.Odds .Odds_Ninki"
        )
    )

    odds = odds.replace("倍", "")

    popularity = txt(
        row.select_one("td.Odds dd")
    )

    popularity = popularity.replace(
        "人気",
        ""
    )


    # --------------------
    # 通過順位
    # --------------------
    passing = ""

    for selector in [
        "td.Passing",
        ".Passing",
        "td.Corner",
        ".Corner",
        "td[class*='Pass']",
        "td[class*='Corner']",
    ]:

        el = row.select_one(selector)

        if el:

            value = txt(el)

            if value:
                passing = value
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


def find_all_result_rows(soup):

    rows = []

    for tr in soup.select("tr"):

        has_result = tr.select_one(
            "td.Result_Num"
        )

        has_horse = tr.select_one(
            ".Horse_Name a"
        )

        if has_result and has_horse:
            rows.append(tr)

    return rows


def get_race_result(race_id):

    html = get_html(race_id)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    rows = find_all_result_rows(soup)

    print(
        "全結果行:",
        len(rows)
    )

    results = []

    seen = set()

    for row in rows:

        item = parse_result_row(row)

        if not item:
            continue

        key = (
            item["horse_id"]
            or item["horse_name"]
        )

        if key in seen:
            continue

        seen.add(key)

        results.append(item)

    print(
        "重複除去後:",
        len(results)
    )

    return results


def main():

    if len(sys.argv) < 2:
        raise SystemExit(
            '使い方: python history.py "202605040502"'
        )

    race_id = sys.argv[1].strip()

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        raise SystemExit(
            f"race_id は12桁で指定してください: {race_id}"
        )

    print(
        "取得開始:",
        race_id
    )

    results = get_race_result(
        race_id
    )

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

    print(
        "取得件数:",
        len(results)
    )

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
        )


if __name__ == "__main__":
    main()
