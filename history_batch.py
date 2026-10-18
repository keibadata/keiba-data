import json
import os
import re
import time
from datetime import datetime, timedelta, timezone

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
HISTORY_DB_FILE = "history_db.json"
OUTPUT_FILE = "history_races.json"

MAX_RACES = 20
MIN_CACHE_RACES = 10
LOOKBACK_DAYS = 180

REQUEST_WAIT = 0.5
DATE_WAIT = 0.8

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9",
}


# =========================================================
# JSON
# =========================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return {} if default is None else default

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# normalize
# =========================================================

def normalize_surface(value):
    value = str(value or "").strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_distance(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_track(value):
    return str(value or "").strip()


def parse_date(value):
    value = str(value or "").strip()

    if not value:
        return None

    try:
        return datetime.strptime(
            value,
            "%Y-%m-%d"
        ).date()

    except ValueError:
        return None


# =========================================================
# HTTP
# =========================================================

def get_html(url, params=None):
    response = requests.get(
        url,
        params=params,
        headers=HEADERS,
        timeout=30,
    )

    response.raise_for_status()
    response.encoding = response.apparent_encoding

    return response.text


# =========================================================
# race id
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
    seen = set()

    for race_id in ids:
        if race_id in seen:
            continue

        seen.add(race_id)
        result.append(race_id)

    return result


# =========================================================
# race class
# =========================================================

def normalize_race_class(race_name, race_info_text):
    """
    Race_Name / Race_Info の実データからクラスを分類する。

    レース番号や勝ち時計からクラスを推測しない。
    """

    text = (
        f"{race_name} {race_info_text}"
    ).replace("　", " ")

    # G1
    if re.search(
        r"\bG\s*1\b|Ｇ\s*１|GI\b|ＧⅠ",
        text,
        re.IGNORECASE,
    ):
        return "G1"

    # G2
    if re.search(
        r"\bG\s*2\b|Ｇ\s*２|GII\b|ＧⅡ",
        text,
        re.IGNORECASE,
    ):
        return "G2"

    # G3
    if re.search(
        r"\bG\s*3\b|Ｇ\s*３|GIII\b|ＧⅢ",
        text,
        re.IGNORECASE,
    ):
        return "G3"

    # Listed
    if re.search(
        r"\bL\b|リステッド",
        text,
        re.IGNORECASE,
    ):
        return "L"

    # Open
    if (
        "オープン" in text
        or "OP" in text.upper()
    ):
        return "OP"

    # 3勝
    if re.search(
        r"3\s*勝|３\s*勝",
        text,
    ):
        return "3勝クラス"

    # 2勝
    if re.search(
        r"2\s*勝|２\s*勝",
        text,
    ):
        return "2勝クラス"

    # 1勝
    if re.search(
        r"1\s*勝|１\s*勝",
        text,
    ):
        return "1勝クラス"

    # 未勝利
    if "未勝利" in text:
        return "未勝利"

    # 新馬
    if "新馬" in text:
        return "新馬"

    return ""


def extract_age_condition(race_name, race_info_text):
    """
    年齢条件を抽出する。

    例:
    2歳
    3歳
    3歳以上
    4歳以上
    """

    text = (
        f"{race_name} {race_info_text}"
    ).replace("　", " ")

    patterns = [
        (r"(?:2|２)\s*歳以上", "2歳以上"),
        (r"(?:3|３)\s*歳以上", "3歳以上"),
        (r"(?:4|４)\s*歳以上", "4歳以上"),
        (r"(?:2|２)\s*歳", "2歳"),
        (r"(?:3|３)\s*歳", "3歳"),
        (r"(?:4|４)\s*歳", "4歳"),
    ]

    for pattern, label in patterns:
        if re.search(pattern, text):
            return label

    return ""


# =========================================================
# target
# =========================================================

def get_target_condition(race):
    race_info = race.get(
        "race_info",
        {}
    )

    if not isinstance(
        race_info,
        dict
    ):
        race_info = {}

    race_id = str(
        race.get("race_id", "")
    ).strip()

    race_date = str(
        race.get("race_date")
        or race_info.get("race_date")
        or ""
    ).strip()

    track = normalize_track(
        race.get("track")
        or race.get("racecourse")
        or race_info.get("track")
        or race_info.get("racecourse")
        or ""
    )

    surface = normalize_surface(
        race.get("surface")
        or race_info.get("surface")
        or ""
    )

    distance = normalize_distance(
        race.get("distance")
        or race_info.get("distance")
        or 0
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        raise RuntimeError(
            "race.json の race_id が不正です"
        )

    target_date = parse_date(
        race_date
    )

    if target_date is None:
        raise RuntimeError(
            "race.json の race_date を取得できません"
        )

    if not track:
        raise RuntimeError(
            "race.json の競馬場を取得できません"
        )

    if not surface:
        raise RuntimeError(
            "race.json の芝・ダートを取得できません"
        )

    if distance <= 0:
        raise RuntimeError(
            "race.json の距離を取得できません"
        )

    return {
        "race_id": race_id,
        "race_date": race_date,
        "target_date": target_date,
        "racecourse": track,
        "surface": surface,
        "distance": distance,
    }


# =========================================================
# history DB
# =========================================================

def race_condition(row):
    if not isinstance(row, dict):
        return {
            "racecourse": "",
            "surface": "",
            "distance": 0,
        }

    return {
        "racecourse": normalize_track(
            row.get("racecourse")
            or row.get("track")
            or ""
        ),
        "surface": normalize_surface(
            row.get("surface")
            or ""
        ),
        "distance": normalize_distance(
            row.get("distance")
            or 0
        ),
    }


def matches_target(row, target):
    condition = race_condition(
        row
    )

    return (
        condition["racecourse"]
        == target["racecourse"]
        and condition["surface"]
        == target["surface"]
        and condition["distance"]
        == target["distance"]
    )


def get_existing_races(history_db, target):
    races = history_db.get(
        "races",
        []
    )

    if not isinstance(races, list):
        return []

    result = []
    seen = set()

    for race in races:
        if not isinstance(
            race,
            dict
        ):
            continue

        race_id = str(
            race.get(
                "race_id",
                ""
            )
        ).strip()

        if not re.fullmatch(
            r"\d{12}",
            race_id
        ):
            continue

        if race_id == target["race_id"]:
            continue

        if not matches_target(
            race,
            target
        ):
            continue

        race_date = parse_date(
            race.get(
                "race_date",
                ""
            )
        )

        if race_date is not None:
            if race_date >= target["target_date"]:
                continue

        if race_id in seen:
            continue

        seen.add(race_id)

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

        if not race_class:
            race_class = normalize_race_class(
                race_name,
                race_info_text,
            )

        if not age_condition:
            age_condition = extract_age_condition(
                race_name,
                race_info_text,
            )

        result.append({
            "race_id": race_id,
            "race_date": str(
                race.get(
                    "race_date",
                    ""
                )
            ),
            "racecourse": target["racecourse"],
            "race_number": str(
                race.get(
                    "race_number",
                    ""
                )
            ),
            "surface": target["surface"],
            "distance": target["distance"],
            "track_condition": str(
                race.get(
                    "track_condition",
                    ""
                )
            ),
            "race_name": race_name,
            "race_info_text": race_info_text,
            "race_class": race_class,
            "age_condition": age_condition,
        })

    result.sort(
        key=lambda x: (
            x.get("race_date", ""),
            x.get("race_id", ""),
        ),
        reverse=True,
    )

    return result


# =========================================================
# race page parser
# =========================================================

def parse_race_info(race_id):
    html = get_html(
        "https://race.sp.netkeiba.com/",
        {
            "pid": "race_result",
            "race_id": race_id,
        },
    )

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    text = soup.get_text(
        " ",
        strip=True
    )

    # -----------------------------------------------------
    # Race Name
    # -----------------------------------------------------

    race_name = ""

    race_name_el = soup.select_one(
        "h1.Race_Name"
    )

    if race_name_el:
        race_name = race_name_el.get_text(
            " ",
            strip=True
        )

    # fallback
    if not race_name:
        for selector in (
            ".Race_Name",
            ".RaceName",
        ):
            el = soup.select_one(selector)

            if el:
                race_name = el.get_text(
                    " ",
                    strip=True
                )
                break

    # -----------------------------------------------------
    # Race Info
    # -----------------------------------------------------

    race_info_text = ""

    race_info_el = soup.select_one(
        "p.Race_Info"
    )

    if race_info_el:
        race_info_text = race_info_el.get_text(
            " ",
            strip=True
        )

    if not race_info_text:
        for selector in (
            ".Race_Info",
            ".RaceInfo",
        ):
            el = soup.select_one(selector)

            if el:
                race_info_text = el.get_text(
                    " ",
                    strip=True
                )
                break

    # -----------------------------------------------------
    # race number
    # -----------------------------------------------------

    race_number = ""

    if re.fullmatch(
        r"\d{12}",
        race_id
    ):
        number = int(
            race_id[-2:]
        )

        if 1 <= number <= 12:
            race_number = f"{number}R"

    # -----------------------------------------------------
    # racecourse
    # -----------------------------------------------------

    racecourse = ""

    for name in (
        "札幌",
        "函館",
        "福島",
        "新潟",
        "東京",
        "中山",
        "中京",
        "京都",
        "阪神",
        "小倉",
    ):
        if name in text:
            racecourse = name
            break

    # -----------------------------------------------------
    # surface / distance
    # -----------------------------------------------------

    surface = ""
    distance = 0

    patterns = (
        r"(芝|ダート|ダ)\s*([12]\d{3})\s*[mｍ]",
        r"(芝|ダート|ダ)\s*([12]\d{3})",
        r"([12]\d{3})\s*[mｍ]\s*(芝|ダート|ダ)",
    )

    for pattern in patterns:
        match = re.search(
            pattern,
            text
        )

        if not match:
            continue

        a = match.group(1)
        b = match.group(2)

        if a in (
            "芝",
            "ダート",
            "ダ",
        ):
            surface = normalize_surface(a)
            distance = int(b)

        else:
            distance = int(a)
            surface = normalize_surface(b)

        break

    # -----------------------------------------------------
    # track condition
    # -----------------------------------------------------

    track_condition = ""

    candidates = []

    for tag in soup.find_all(
        [
            "div",
            "span",
            "li",
            "p",
            "dd",
            "dt",
            "td",
            "th",
        ]
    ):
        value = tag.get_text(
            " ",
            strip=True
        )

        if value:
            candidates.append(value)

    track_patterns = (
        r"馬場(?:状態)?\s*[:：]?\s*(良|稍重|重|不良)",
        r"芝\s*[:：]?\s*(良|稍重|重|不良)",
        r"ダート\s*[:：]?\s*(良|稍重|重|不良)",
        r"ダ\s*[:：]?\s*(良|稍重|重|不良)",
        r"(?:芝|ダート|ダ)[^。\n]{0,20}?(良|稍重|重|不良)",
    )

    for value in candidates:
        if len(value) > 150:
            continue

        for pattern in track_patterns:
            match = re.search(
                pattern,
                value
            )

            if match:
                track_condition = match.group(1)
                break

        if track_condition:
            break

    if not track_condition:
        for pattern in track_patterns:
            match = re.search(
                pattern,
                text
            )

            if match:
                track_condition = match.group(1)
                break

    # -----------------------------------------------------
    # class / age
    # -----------------------------------------------------

    race_class = normalize_race_class(
        race_name,
        race_info_text,
    )

    age_condition = extract_age_condition(
        race_name,
        race_info_text,
    )

    return {
        "race_id": race_id,
        "racecourse": racecourse,
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
        "track_condition": track_condition,
        "race_name": race_name,
        "race_info_text": race_info_text,
        "race_class": race_class,
        "age_condition": age_condition,
    }


# =========================================================
# date race list
# =========================================================

def find_races_from_date(date_string):
    html = get_html(
        "https://race.netkeiba.com/top/race_list.html",
        {
            "kaisai_date": date_string
        },
    )

    return extract_race_ids(
        html
    )


# =========================================================
# output
# =========================================================

def build_output(
    target,
    races,
    errors,
    cache_used,
    existing_count,
    searched,
    cache_reason,
):
    class_counts = {}

    age_condition_counts = {}

    for race in races:
        race_class = (
            race.get("race_class")
            or "不明"
        )

        age_condition = (
            race.get("age_condition")
            or "不明"
        )

        class_counts[race_class] = (
            class_counts.get(
                race_class,
                0
            ) + 1
        )

        age_condition_counts[
            age_condition
        ] = (
            age_condition_counts.get(
                age_condition,
                0
            ) + 1
        )

    return {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "target_race_id": target["race_id"],

        "condition": {
            "racecourse": target["racecourse"],
            "surface": target["surface"],
            "distance": target["distance"],
        },

        "search": {
            "before_date": target["race_date"],
            "lookback_days": LOOKBACK_DAYS,
            "max_races": MAX_RACES,
            "min_cache_races": MIN_CACHE_RACES,
            "future_races_excluded": True,
            "target_race_excluded": True,
            "cache_used": cache_used,
            "cache_reason": cache_reason,
            "existing_matching_races": existing_count,
            "network_search_performed": searched,
        },

        "metadata": {
            "race_name_collected": True,
            "race_info_text_collected": True,
            "race_class_collected": True,
            "age_condition_collected": True,
            "class_counts": class_counts,
            "age_condition_counts": age_condition_counts,
        },

        "race_count": len(races),
        "races": races,
        "error_count": len(errors),
        "errors": errors,
    }


# =========================================================
# main
# =========================================================

def main():
    race = load_json(
        RACE_FILE
    )

    target = get_target_condition(
        race
    )

    history_db = load_json(
        HISTORY_DB_FILE,
        {}
    )

    print("==============================")
    print("条件別 過去レース探索")
    print("対象Race ID:", target["race_id"])
    print("対象日:", target["race_date"])
    print(
        "条件:",
        target["racecourse"],
        target["surface"],
        target["distance"],
    )
    print("==============================")

    existing = get_existing_races(
        history_db,
        target
    )

    existing_count = len(
        existing
    )

    print(
        "既存DB一致レース:",
        existing_count
    )

    # =====================================================
    # キャッシュ
    #
    # 旧DBには race_class 等が無い可能性がある。
    # 時計基準構築に必要なので、
    # metadata不足ならネット探索へ進む。
    # =====================================================

    metadata_complete_count = sum(
        1
        for row in existing
        if (
            row.get("race_name")
            and row.get("race_info_text")
            and row.get("race_class")
            and row.get("age_condition")
        )
    )

    cache_metadata_ready = (
        existing_count >= MIN_CACHE_RACES
        and metadata_complete_count
        >= MIN_CACHE_RACES
    )

    if cache_metadata_ready:
        selected = existing[
            :MAX_RACES
        ]

        if existing_count >= MAX_RACES:
            cache_reason = (
                "MAX_RACES以上の既存データあり・"
                "クラス情報取得済み"
            )
        else:
            cache_reason = (
                "MIN_CACHE_RACES以上の既存データあり・"
                "クラス情報取得済み"
            )

        output = build_output(
            target=target,
            races=selected,
            errors=[],
            cache_used=True,
            existing_count=existing_count,
            searched=False,
            cache_reason=cache_reason,
        )

        save_json(
            OUTPUT_FILE,
            output
        )

        print("既存DBを使用します")
        print("ネット検索をスキップします")
        print("理由:", cache_reason)
        print("history_races.json 作成完了")
        print("対象条件レース:", len(selected))

        return

    # =====================================================
    # ネット探索
    # =====================================================

    matched = []

    checked_ids = set()

    errors = []

    print(
        "クラス/年齢条件を含む履歴を収集します"
    )

    print(
        "既存一致:",
        existing_count,
        "件"
    )

    print(
        "既存metadata完全:",
        metadata_complete_count,
        "件"
    )

    for days_back in range(
        1,
        LOOKBACK_DAYS + 1
    ):
        if len(matched) >= MAX_RACES:
            break

        search_date = (
            target["target_date"]
            - timedelta(
                days=days_back
            )
        )

        date_string = (
            search_date.strftime(
                "%Y%m%d"
            )
        )

        try:
            race_ids = (
                find_races_from_date(
                    date_string
                )
            )

        except Exception as e:
            errors.append({
                "date": date_string,
                "error": str(e),
            })

            continue

        if not race_ids:
            continue

        print(
            "開催日:",
            date_string,
            "候補:",
            len(race_ids),
        )

        for race_id in race_ids:
            if len(matched) >= MAX_RACES:
                break

            if race_id == target["race_id"]:
                continue

            if race_id in checked_ids:
                continue

            checked_ids.add(
                race_id
            )

            try:
                info = parse_race_info(
                    race_id
                )

                if (
                    info["racecourse"]
                    == target["racecourse"]
                    and info["surface"]
                    == target["surface"]
                    and info["distance"]
                    == target["distance"]
                ):
                    info["race_date"] = (
                        search_date.isoformat()
                    )

                    matched.append(
                        info
                    )

                    print(
                        "  MATCH:",
                        race_id,
                        info["racecourse"],
                        info["surface"],
                        info["distance"],
                        "|",
                        info["race_name"]
                        or "レース名不明",
                        "|",
                        info["race_class"]
                        or "クラス不明",
                        "|",
                        info["age_condition"]
                        or "年齢条件不明",
                    )

                time.sleep(
                    REQUEST_WAIT
                )

            except Exception as e:
                errors.append({
                    "race_id": race_id,
                    "error": str(e),
                })

        if len(matched) >= MAX_RACES:
            break

        time.sleep(
            DATE_WAIT
        )

    # =====================================================
    # 重複除去
    # =====================================================

    unique = []
    seen = set()

    for row in matched:
        race_id = str(
            row.get(
                "race_id",
                ""
            )
        )

        if race_id in seen:
            continue

        seen.add(
            race_id
        )

        unique.append(
            row
        )

    unique.sort(
        key=lambda x: (
            x.get("race_date", ""),
            x.get("race_id", ""),
        ),
        reverse=True,
    )

    unique = unique[
        :MAX_RACES
    ]

    output = build_output(
        target=target,
        races=unique,
        errors=errors,
        cache_used=False,
        existing_count=existing_count,
        searched=True,
        cache_reason=(
            "時計基準用metadataを再収集"
        ),
    )

    save_json(
        OUTPUT_FILE,
        output
    )

    print("==============================")
    print("history_races.json 作成完了")
    print("最終対象レース:", len(unique))
    print("取得エラー:", len(errors))

    print(
        "クラス内訳:",
        output["metadata"][
            "class_counts"
        ],
    )

    print(
        "年齢条件内訳:",
        output["metadata"][
            "age_condition_counts"
        ],
    )

    print("==============================")

    if not unique:
        raise RuntimeError(
            "対象レース以前に同条件の過去レースを取得できませんでした"
        )


if __name__ == "__main__":
    main()
