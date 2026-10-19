import json
import re
import time
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
    response = requests.get(
        BASE_URL,
        params={
            "pid": "race_result",
            "race_id": race_id,
        },
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


def parse_corners(soup):
    corners = {
        "corner_1": "",
        "corner_2": "",
        "corner_3": "",
        "corner_4": "",
    }

    target = soup.find(
        "table",
        attrs={"summary": "コーナー通過順位"}
    )

    if target is None:
        return corners

    for tr in target.find_all("tr"):
        th = tr.find("th")
        td = tr.find("td")

        if th is None or td is None:
            continue

        label = th.get_text("", strip=True)
        value = "".join(td.stripped_strings)

        if "1コーナー" in label:
            corners["corner_1"] = value
        elif "2コーナー" in label:
            corners["corner_2"] = value
        elif "3コーナー" in label:
            corners["corner_3"] = value
        elif "4コーナー" in label:
            corners["corner_4"] = value

    return corners


def corner_position(corner_text, horse_number):
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
    rank = txt(
        row.select_one("td.Result_Num .Rank")
    )

    rank = re.sub(
        r"\s*着$",
        "",
        rank
    ).strip()

    nums = row.select("td.Num")

    frame_number = ""
    horse_number = ""

    if len(nums) >= 1:
        frame_number = txt(nums[0])

    if len(nums) >= 2:
        horse_number = txt(nums[1])

    horse_el = row.select_one(".Horse_Name a")

    if not horse_el:
        return None

    horse_name = txt(horse_el)

    horse_id = horse_id_from_href(
        horse_el.get("href", "")
    )

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

    race_time = txt(
        row.select_one("td.Time dt span")
    )

    if not race_time:
        race_time = txt(
            row.select_one("td.Time dt")
        )

    margin = ""
    last3f = ""

    for dd in row.select("td.Time dd"):
        value = txt(dd)

        if not value:
            continue

        m = re.fullmatch(
            r"\((\d+(?:\.\d+)?)\)",
            value
        )

        if m:
            last3f = m.group(1)
            continue

        if not margin:
            margin = value

    odds = txt(
        row.select_one("td.Odds .Odds_Ninki")
    ).replace("倍", "")

    popularity = txt(
        row.select_one("td.Odds dd")
    ).replace("人気", "")

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
        "passing": " / ".join(passing_parts),
        "passing_1c": passing_1c,
        "passing_2c": passing_2c,
        "passing_3c": passing_3c,
        "passing_4c": passing_4c,
        "last3f": last3f,
        "odds": odds,
        "popularity": popularity,
    }


def find_result_rows(soup):
    rows = []

    for tr in soup.select("tr"):
        if (
            tr.select_one("td.Result_Num")
            and tr.select_one(".Horse_Name a")
        ):
            rows.append(tr)

    return rows


def collect_one_race(race):
    race_id = str(
        race.get("race_id", "")
    )

    html = get_html(race_id)

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    corners = parse_corners(soup)
    rows = find_result_rows(soup)

    # ==========================================
    # history_races.json から引き継ぐメタデータ
    # ==========================================

    race_date = str(
        race.get("race_date", "")
    )

    racecourse = str(
        race.get("racecourse", "")
    )

    race_number = str(
        race.get("race_number", "")
    )

    surface = str(
        race.get("surface", "")
    )

    distance = race.get(
        "distance",
        0
    )

    track_condition = str(
        race.get("track_condition", "")
    )

    race_name = str(
        race.get("race_name", "")
    ).strip()

    race_info_text = str(
        race.get("race_info_text", "")
    ).strip()

    race_class = str(
        race.get("race_class", "")
    ).strip()

    age_condition = str(
        race.get("age_condition", "")
    ).strip()

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

        # ======================================
        # レース情報を各結果にも保持
        # ======================================

        item["race_id"] = race_id
        item["race_date"] = race_date
        item["racecourse"] = racecourse
        item["race_number"] = race_number
        item["surface"] = surface
        item["distance"] = distance
        item["track_condition"] = track_condition

        item["race_name"] = race_name
        item["race_info_text"] = race_info_text
        item["race_class"] = race_class
        item["age_condition"] = age_condition

        results.append(item)

    return {
        "race_id": race_id,
        "race_date": race_date,
        "racecourse": racecourse,
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
        "track_condition": track_condition,

        "race_name": race_name,
        "race_info_text": race_info_text,
        "race_class": race_class,
        "age_condition": age_condition,

        "corner_order": {
            "1c": corners["corner_1"],
            "2c": corners["corner_2"],
            "3c": corners["corner_3"],
            "4c": corners["corner_4"],
        },

        "result_count": len(results),
        "results": results,
    }


def load_target_races():
    with open(
        "history_races.json",
        "r",
        encoding="utf-8"
    ) as f:
        data = json.load(f)

    if isinstance(data, list):
        return data

    if isinstance(data, dict):
        for key in (
            "races",
            "target_races",
            "history_races",
        ):
            if isinstance(
                data.get(key),
                list
            ):
                return data[key]

    raise RuntimeError(
        "history_races.json のレース一覧を認識できません"
    )


def main():
    races = load_target_races()

    print("============================")
    print("過去成績 全頭取得開始")
    print("対象レース数:", len(races))
    print("============================")

    all_races = []
    all_results = []
    errors = []

    metadata_complete = 0

    for index, race in enumerate(
        races,
        start=1
    ):
        race_id = str(
            race.get("race_id", "")
        )

        if not re.fullmatch(
            r"\d{12}",
            race_id
        ):
            errors.append({
                "race_id": race_id,
                "error": "race_id不正",
            })
            continue

        print(
            f"[{index}/{len(races)}] 取得:",
            race_id
        )

        try:
            result = collect_one_race(
                race
            )

            all_races.append(
                result
            )

            all_results.extend(
                result["results"]
            )

            if (
                result.get("race_name")
                and result.get("race_info_text")
                and result.get("race_class")
                and result.get("age_condition")
            ):
                metadata_complete += 1

            print(
                "  成功:",
                result["result_count"],
                "頭",
                "|",
                result.get(
                    "race_name",
                    ""
                ),
                "|",
                result.get(
                    "race_class",
                    ""
                ),
                "|",
                result.get(
                    "age_condition",
                    ""
                ),
            )

        except Exception as e:
            print(
                "  失敗:",
                str(e)
            )

            errors.append({
                "race_id": race_id,
                "error": str(e),
            })

        time.sleep(1.5)

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": "netkeiba",

        "metadata": {
            "race_name_connected": True,
            "race_info_text_connected": True,
            "race_class_connected": True,
            "age_condition_connected": True,
            "metadata_complete_race_count":
                metadata_complete,
        },

        "race_count": len(
            all_races
        ),

        "horse_result_count": len(
            all_results
        ),

        "error_count": len(
            errors
        ),

        "races": all_races,
        "results": all_results,
        "errors": errors,
    }

    with open(
        "history_all.json",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("============================")
    print("history_all.json 作成完了")
    print("成功レース:", len(all_races))
    print("全出走結果:", len(all_results))
    print(
        "metadata完全:",
        metadata_complete,
        "/",
        len(all_races),
    )
    print("失敗:", len(errors))
    print("============================")

    if not all_results:
        raise RuntimeError(
            "過去成績を1頭も取得できませんでした"
        )

    if metadata_complete == 0:
        raise RuntimeError(
            "レースクラス・年齢条件を1件も接続できませんでした"
        )


if __name__ == "__main__":
    main()
