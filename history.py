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


def parse_corners(soup):
    corners = {
        "corner_1": "",
        "corner_2": "",
        "corner_3": "",
        "corner_4": "",
    }

    tables = soup.find_all("table")

    target = None

    for table in tables:
        summary = table.get("summary", "")

        if "コーナー通過順位" in summary:
            target = table
            break

    if target is None:
        # summary属性が無い場合の予備処理
        for table in tables:
            table_text = txt(table)

            if (
                "3コーナー" in table_text
                or "4コーナー" in table_text
            ):
                target = table
                break

    if target is None:
        print("コーナー通過順位: 見つからず")
        return corners

    for tr in target.select("tr"):
        th = tr.find("th")
        td = tr.find("td")

        if not th or not td:
            continue

        label = txt(th)
        value = td.get_text("", strip=True)

        if "1コーナー" in label:
            corners["corner_1"] = value

        elif "2コーナー" in label:
            corners["corner_2"] = value

        elif "3コーナー" in label:
            corners["corner_3"] = value

        elif "4コーナー" in label:
            corners["corner_4"] = value

    print("1角:", corners["corner_1"])
    print("2角:", corners["corner_2"])
    print("3角:", corners["corner_3"])
    print("4角:", corners["corner_4"])

    return corners


def corner_position(corner_text, horse_number):
    """
    コーナー隊列原文から対象馬が
    左から何番目に記載されているかを返す。

    例:
    (*8,12)(3,5)...
    馬番8  -> 1
    馬番12 -> 2
    馬番3  -> 3

    同位置グループ等の記号はcorner原文側に保持する。
    """

    if not corner_text or not horse_number:
        return ""

    numbers = re.findall(
        r"(?<!\d)\d+(?!\d)",
        corner_text
    )

    target = str(horse_number)

    try:
        return numbers.index(target) + 1
    except ValueError:
        return ""


def parse_result_row(row, corners):

    # 着順
    rank = txt(
        row.select_one("td.Result_Num .Rank")
    )

    rank = re.sub(
        r"\s*着$",
        "",
        rank
    ).strip()


    # 枠番・馬番
    nums = row.select("td.Num")

    frame_number = ""
    horse_number = ""

    if len(nums) >= 1:
        frame_number = txt(nums[0])

    if len(nums) >= 2:
        horse_number = txt(nums[1])


    # 馬名・馬ID
    horse_el = row.select_one(
        ".Horse_Name a"
    )

    if not horse_el:
        return None

    horse_name = txt(horse_el)

    horse_id = horse_id_from_href(
        horse_el.get("href", "")
    )


    # 性齢・馬体重
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


    # 騎手・斤量・厩舎
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
            m = re.match(
                r"(.+?)\s+(\d+(?:\.\d+)?)$",
                parts[0]
            )

            if m:
                jockey = m.group(1).strip()
                carried_weight = m.group(2)

        if len(parts) >= 2:
            trainer = parts[-1]


    # タイム
    race_time = txt(
        row.select_one("td.Time dt span")
    )

    if not race_time:
        race_time = txt(
            row.select_one("td.Time dt")
        )


    # 着差
    margin = ""

    for dd in row.select("td.Time dd"):
        value = txt(dd)

        if not value:
            continue

        if re.fullmatch(
            r"\(\d+(?:\.\d+)?\)",
            value
        ):
            continue

        margin = value
        break


    # 上がり3F
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


    # オッズ・人気
    odds = txt(
        row.select_one(
            "td.Odds .Odds_Ninki"
        )
    ).replace("倍", "")

    popularity = txt(
        row.select_one("td.Odds dd")
    ).replace("人気", "")


    # 各馬のコーナー位置
    passing_1c = corner_position(
        corners["corner_1"],
        horse_number
    )

    passing_2c = corner_position(
        corners["corner_2"],
        horse_number
    )

    passing_3c = corner_position(
        corners["corner_3"],
        horse_number
    )

    passing_4c = corner_position(
        corners["corner_4"],
        horse_number
    )

    passing_parts = []

    if passing_1c != "":
        passing_parts.append(
            f"1C:{passing_1c}"
        )

    if passing_2c != "":
        passing_parts.append(
            f"2C:{passing_2c}"
        )

    if passing_3c != "":
        passing_parts.append(
            f"3C:{passing_3c}"
        )

    if passing_4c != "":
        passing_parts.append(
            f"4C:{passing_4c}"
        )

    passing = " / ".join(
        passing_parts
    )


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
        "passing_1c": passing_1c,
        "passing_2c": passing_2c,
        "passing_3c": passing_3c,
        "passing_4c": passing_4c,
        "last3f": last3f,
        "odds": odds,
        "popularity": popularity,
    }


def find_all_result_rows(soup):
    rows = []

    for tr in soup.select("tr"):

        if (
            tr.select_one("td.Result_Num")
            and tr.select_one(".Horse_Name a")
        ):
            rows.append(tr)

    return rows


def get_race_result(race_id):
    html = get_html(race_id)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    corners = parse_corners(soup)

    rows = find_all_result_rows(
        soup
    )

    print(
        "全結果行:",
        len(rows)
    )

    results = []
    seen = set()

    for row in rows:

        item = parse_result_row(
            row,
            corners
        )

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

    return results, corners


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

    results, corners = (
        get_race_result(race_id)
    )

    data = {
        "race_id": race_id,
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),
        "source": "netkeiba",

        "corner_order": {
            "1c": corners["corner_1"],
            "2c": corners["corner_2"],
            "3c": corners["corner_3"],
            "4c": corners["corner_4"],
        },

        "result_count": len(results),
        "results": results,
    }

    with
