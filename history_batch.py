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
# grade
# =========================================================

def normalize_grade_text(value):
    """
    G1 / GI / ＧⅠ 等を統一する。
    """
    text = str(value or "")

    text = (
        text
        .replace("Ｇ", "G")
        .replace("Ⅰ", "I")
        .replace("Ⅱ", "II")
        .replace("Ⅲ", "III")
        .replace("１", "1")
        .replace("２", "2")
        .replace("３", "3")
    )

    text = re.sub(
        r"\s+",
        "",
        text,
    ).upper()

    return text


def grade_from_text(value):
    """
    与えられた文字列そのものから
    G1/G2/G3/L を判定する。

    ページ全体から無差別に拾う用途ではなく、
    グレード候補要素に対して使用する。
    """
    text = normalize_grade_text(value)

    if not text:
        return ""

    if re.search(
        r"(^|[^A-Z0-9])G(?:1|I)([^A-Z0-9]|$)",
        text,
    ):
        return "G1"

    if text in {
        "G1",
        "GI",
    }:
        return "G1"

    if re.search(
        r"(^|[^A-Z0-9])G(?:2|II)([^A-Z0-9]|$)",
        text,
    ):
        return "G2"

    if text in {
        "G2",
        "GII",
    }:
        return "G2"

    if re.search(
        r"(^|[^A-Z0-9])G(?:3|III)([^A-Z0-9]|$)",
        text,
    ):
        return "G3"

    if text in {
        "G3",
        "GIII",
    }:
        return "G3"

    if text in {
        "L",
        "LISTED",
    }:
        return "L"

    if "リステッド" in str(value or ""):
        return "L"

    return ""


def extract_grade_from_soup(soup, race_name_el=None):
    """
    netkeiba のHTML上にあるグレード表示を抽出する。

    レース名ハードコードは行わない。
    G1/G2/G3/L の実表示だけを根拠にする。
    """

    candidates = []

    if race_name_el is not None:
        candidates.append(
            race_name_el.get_text(
                " ",
                strip=True,
            )
        )

        for tag in race_name_el.find_all(True):
            value = tag.get_text(
                " ",
                strip=True,
            )

            if value:
                candidates.append(value)

            class_value = " ".join(
                tag.get("class", [])
            )

            if class_value:
                candidates.append(class_value)

            for attr in (
                "title",
                "alt",
                "aria-label",
                "data-grade",
            ):
                attr_value = tag.get(attr)

                if attr_value:
                    candidates.append(attr_value)

    grade_like_elements = soup.find_all(
        lambda tag: (
            tag.name
            and (
                any(
                    (
                        "grade" in str(c).lower()
                        or "icon" in str(c).lower()
                    )
                    for c in tag.get("class", [])
                )
                or tag.has_attr("data-grade")
            )
        )
    )

    for tag in grade_like_elements:
        value = tag.get_text(
            " ",
            strip=True,
        )

        if value:
            candidates.append(value)

        class_value = " ".join(
            tag.get("class", [])
        )

        if class_value:
            candidates.append(class_value)

        for attr in (
            "title",
            "alt",
            "aria-label",
            "data-grade",
        ):
            attr_value = tag.get(attr)

            if attr_value:
                candidates.append(attr_value)

        for img in tag.find_all("img"):
            for attr in (
                "alt",
                "title",
            ):
                attr_value = img.get(attr)

                if attr_value:
                    candidates.append(
                        attr_value
                    )

            src = img.get("src")

            if src:
                candidates.append(src)

    for img in soup.find_all("img"):
        for attr in (
            "alt",
            "title",
        ):
            value = img.get(attr)

            if value:
                candidates.append(value)

        src = img.get("src")

        if src and re.search(
            r"grade|g1|g2|g3|gi|gii|giii",
            src,
            re.IGNORECASE,
        ):
            candidates.append(src)

    for candidate in candidates:
        grade = grade_from_text(
            candidate
        )

        if grade:
            return grade

    return ""


# =========================================================
# race class
# =========================================================

def normalize_race_class(
    race_name,
    race_info_text,
    explicit_grade="",
):
    """
    クラス分類。

    優先順位:
    1. HTMLから直接取得したグレード
    2. Race_Name / Race_Info 内の明示グレード
    3. Listed
    4. OP
    5. 条件戦
    6. 未勝利
    7. 新馬

    レース番号や勝ち時計からクラスを推測しない。
    """

    explicit_grade = str(
        explicit_grade or ""
    ).strip()

    if explicit_grade in {
        "G1",
        "G2",
        "G3",
        "L",
    }:
        return explicit_grade

    text = (
        f"{race_name} {race_info_text}"
    ).replace("　", " ")

    normalized = normalize_grade_text(
        text
    )

    if re.search(
        r"\bG1\b|\bGI\b",
        normalized,
    ):
        return "G1"

    if re.search(
        r"\bG2\b|\bGII\b",
        normalized,
    ):
        return "G2"

    if re.search(
        r"\bG3\b|\bGIII\b",
        normalized,
    ):
        return "G3"

    if (
        re.search(
            r"\bL\b",
            normalized,
        )
        or "リステッド" in text
    ):
        return "L"

    if (
        "オープン" in text
        or re.search(
            r"\bOP\b",
            text.upper(),
        )
    ):
        return "OP"

    if re.search(
        r"3\s*勝|３\s*勝",
        text,
    ):
        return "3勝クラス"

    if re.search(
        r"2\s*勝|２\s*勝",
        text,
    ):
        return "2勝クラス"

    if re.search(
        r"1\s*勝|１\s*勝",
        text,
    ):
        return "1勝クラス"

    if "未勝利" in text:
        return "未勝利"

    if "新馬" in text:
        return "新馬"

    return ""


def extract_age_condition(
    race_name,
    race_info_text,
):
    text = (
        f"{race_name} {race_info_text}"
    ).replace("　", " ")

    patterns = [
        (
            r"(?:2|２)\s*歳以上",
            "2歳以上",
        ),
        (
            r"(?:3|３)\s*歳以上",
            "3歳以上",
        ),
        (
            r"(?:4|４)\s*歳以上",
            "4歳以上",
        ),
        (
            r"(?:2|２)\s*歳",
            "2歳",
        ),
        (
            r"(?:3|３)\s*歳",
            "3歳",
        ),
        (
            r"(?:4|４)\s*歳",
            "4歳",
        ),
    ]

    for pattern, label in patterns:
        if re.search(
            pattern,
            text,
        ):
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
        race.get(
            "race_id",
            ""
        )
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
    if not isinstance(
        row,
        dict
    ):
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


def matches_target(
    row,
    target,
):
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


def get_existing_races(
    history_db,
    target,
):
    races = history_db.get(
        "races",
        []
    )

    if not isinstance(
        races,
        list
    ):
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
            target,
        ):
            continue

        race_date = parse_date(
            race.get(
                "race_date",
                ""
            )
        )

        if race_date is not None:
            if (
                race_date
                >= target["target_date"]
            ):
                continue

        if race_id in seen:
            continue

        seen.add(race_id)

        race_name = str(
            race.get(
                "race_name",
                ""
            )
        ).strip()

        race_info_text = str(
            race.get(
                "race_info_text",
                ""
            )
        ).strip()

        race_class = str(
            race.get(
                "race_class",
                ""
            )
        ).strip()

        age_condition = str(
            race.get(
                "age_condition",
                ""
            )
        ).strip()

        if not race_class:
            race_class = (
                normalize_race_class(
                    race_name,
                    race_info_text,
                )
            )

        if not age_condition:
            age_condition = (
                extract_age_condition(
                    race_name,
                    race_info_text,
                )
            )

        result.append({
            "race_id": race_id,
            "race_date": str(
                race.get(
                    "race_date",
                    ""
                )
            ),
            "racecourse": (
                target["racecourse"]
            ),
            "race_number": str(
                race.get(
                    "race_number",
                    ""
                )
            ),
            "surface": (
                target["surface"]
            ),
            "distance": (
                target["distance"]
            ),
            "track_condition": str(
                race.get(
                    "track_condition",
                    ""
                )
            ),
            "race_name": race_name,
            "race_info_text": (
                race_info_text
            ),
            "race_class": race_class,
            "age_condition": (
                age_condition
            ),
        })

    result.sort(
        key=lambda x: (
            x.get(
                "race_date",
                ""
            ),
            x.get(
                "race_id",
                ""
            ),
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
        race_name = (
            race_name_el.get_text(
                " ",
                strip=True
            )
        )

    if not race_name:
        for selector in (
            ".Race_Name",
            ".RaceName",
        ):
            el = soup.select_one(
                selector
            )

            if el:
                race_name = (
                    el.get_text(
                        " ",
                        strip=True
                    )
                )
                race_name_el = el
                break

    # -----------------------------------------------------
    # Race Info
    # -----------------------------------------------------

    race_info_text = ""

    race_info_el = soup.select_one(
        "p.Race_Info"
    )

    if race_info_el:
        race_info_text = (
            race_info_el.get_text(
                " ",
                strip=True
            )
        )

    if not race_info_text:
        for selector in (
            ".Race_Info",
            ".RaceInfo",
        ):
            el = soup.select_one(
                selector
            )

            if el:
                race_info_text = (
                    el.get_text(
                        " ",
                        strip=True
                    )
                )
                break

    # -----------------------------------------------------
    # grade
    # -----------------------------------------------------

    explicit_grade = (
        extract_grade_from_soup(
            soup,
            race_name_el,
        )
    )

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
            race_number = (
                f"{number}R"
            )

    # -----------------------------------------------------
    # racecourse
    # -----------------------------------------------------
    #
    # JRA Race ID:
    # YYYY + 場コード2桁 + 開催回2桁 + 開催日2桁 + R番号2桁
    #
    # ページ全文には他競馬場名が含まれる可能性があるため、
    # 競馬場は Race ID の場コードを正とする。
    # -----------------------------------------------------

    jra_tracks = {
        "01": "札幌",
        "02": "函館",
        "03": "福島",
        "04": "新潟",
        "05": "東京",
        "06": "中山",
        "07": "中京",
        "08": "京都",
        "09": "阪神",
        "10": "小倉",
    }

    racecourse = ""

    if re.fullmatch(
        r"\d{12}",
        race_id
    ):
        track_code = race_id[
            4:6
        ]

        racecourse = (
            jra_tracks.get(
                track_code,
                ""
            )
        )

    # -----------------------------------------------------
    # surface / distance
    # -----------------------------------------------------

    surface = ""
    distance = 0

    patterns = (
        (
            r"(芝|ダート|ダ)"
            r"\s*([12]\d{3})"
            r"\s*[mｍ]"
        ),
        (
            r"(芝|ダート|ダ)"
            r"\s*([12]\d{3})"
        ),
        (
            r"([12]\d{3})"
            r"\s*[mｍ]"
            r"\s*(芝|ダート|ダ)"
        ),
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
            surface = (
                normalize_surface(a)
            )
            distance = int(b)

        else:
            distance = int(a)
            surface = (
                normalize_surface(b)
            )

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
            candidates.append(
                value
            )

    track_patterns = (
        (
            r"馬場(?:状態)?"
            r"\s*[:：]?\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"芝\s*[:：]?\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"ダート\s*[:：]?\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"ダ\s*[:：]?\s*"
            r"(良|稍重|重|不良)"
        ),
        (
            r"(?:芝|ダート|ダ)"
            r"[^。\n]{0,20}?"
            r"(良|稍重|重|不良)"
        ),
    )

    for value in candidates:
        if len(value) > 150:
            continue

        for pattern in (
            track_patterns
        ):
            match = re.search(
                pattern,
                value
            )

            if match:
                track_condition = (
                    match.group(1)
                )
                break

        if track_condition:
            break

    if not track_condition:
        for pattern in (
            track_patterns
        ):
            match = re.search(
                pattern,
                text
            )

            if match:
                track_condition = (
                    match.group(1)
                )
                break

    # -----------------------------------------------------
    # class / age
    # -----------------------------------------------------

    race_class = (
        normalize_race_class(
            race_name,
            race_info_text,
            explicit_grade,
        )
    )

    age_condition = (
        extract_age_condition(
            race_name,
            race_info_text,
        )
    )

    return {
        "race_id": race_id,
        "racecourse": racecourse,
        "race_number": race_number,
        "surface": surface,
        "distance": distance,
        "track_condition": (
            track_condition
        ),
        "race_name": race_name,
        "race_info_text": (
            race_info_text
        ),
        "race_class": race_class,
        "age_condition": (
            age_condition
        ),
    }


# =========================================================
# existing metadata refresh
# =========================================================

def refresh_suspicious_classes(
    existing,
):
    """
    既存DBにmetadataが揃っていても、
    OPの中に重賞が誤分類されている可能性がある。

    そのため OP のみページを再確認する。

    20件全部を探索し直すのではなく、
    既存race_idへ直接アクセスするので高速。
    """

    refreshed = []
    refresh_count = 0
    changed_count = 0
    errors = []

    for row in existing:
        current = dict(row)

        old_class = str(
            current.get(
                "race_class",
                ""
            )
        ).strip()

        if old_class != "OP":
            refreshed.append(
                current
            )
            continue

        race_id = str(
            current.get(
                "race_id",
                ""
            )
        ).strip()

        if not re.fullmatch(
            r"\d{12}",
            race_id
        ):
            refreshed.append(
                current
            )
            continue

        try:
            info = parse_race_info(
                race_id
            )

            refresh_count += 1

            new_class = str(
                info.get(
                    "race_class",
                    ""
                )
            ).strip()

            for key in (
                "racecourse",
                "race_number",
                "surface",
                "distance",
                "track_condition",
                "race_name",
                "race_info_text",
                "race_class",
                "age_condition",
            ):
                value = info.get(
                    key
                )

                if value not in (
                    None,
                    "",
                    0,
                ):
                    current[key] = value

            if (
                new_class
                and new_class
                != old_class
            ):
                changed_count += 1

                print(
                    "クラス修正:",
                    race_id,
                    old_class,
                    "->",
                    new_class,
                    "|",
                    current.get(
                        "race_name",
                        ""
                    ),
                )

            time.sleep(
                REQUEST_WAIT
            )

        except Exception as e:
            errors.append({
                "race_id": race_id,
                "error": str(e),
            })

            print(
                "OP再確認失敗:",
                race_id,
                str(e),
            )

        refreshed.append(
            current
        )

    return (
        refreshed,
        refresh_count,
        changed_count,
        errors,
    )


# =========================================================
# date race list
# =========================================================

def find_races_from_date(
    date_string
):
    html = get_html(
        (
            "https://race.netkeiba.com/"
            "top/race_list.html"
        ),
        {
            "kaisai_date": (
                date_string
            )
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
    class_refresh_count=0,
    class_changed_count=0,
):
    class_counts = {}
    age_condition_counts = {}

    for race in races:
        race_class = (
            race.get("race_class")
            or "不明"
        )

        age_condition = (
            race.get(
                "age_condition"
            )
            or "不明"
        )

        class_counts[
            race_class
        ] = (
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
        "updated_at": (
            datetime.now(
                timezone.utc
            ).isoformat()
        ),

        "target_race_id": (
            target["race_id"]
        ),

        "condition": {
            "racecourse": (
                target["racecourse"]
            ),
            "surface": (
                target["surface"]
            ),
            "distance": (
                target["distance"]
            ),
        },

        "search": {
            "before_date": (
                target["race_date"]
            ),
            "lookback_days": (
                LOOKBACK_DAYS
            ),
            "max_races": (
                MAX_RACES
            ),
            "min_cache_races": (
                MIN_CACHE_RACES
            ),
            "future_races_excluded": True,
            "target_race_excluded": True,
            "cache_used": (
                cache_used
            ),
            "cache_reason": (
                cache_reason
            ),
            "existing_matching_races": (
                existing_count
            ),
            "network_search_performed": (
                searched
            ),
            "class_refresh_count": (
                class_refresh_count
            ),
            "class_changed_count": (
                class_changed_count
            ),
        },

        "metadata": {
            "race_name_collected": True,
            "race_info_text_collected": True,
            "race_class_collected": True,
            "age_condition_collected": True,
            "grade_html_detection": True,
            "class_counts": (
                class_counts
            ),
            "age_condition_counts": (
                age_condition_counts
            ),
        },

        "race_count": len(
            races
        ),
        "races": races,
        "error_count": len(
            errors
        ),
        "errors": errors,
    }


# =========================================================
# main
# =========================================================

def main():
    race = load_json(
        RACE_FILE
    )

    target = (
        get_target_condition(
            race
        )
    )

    history_db = load_json(
        HISTORY_DB_FILE,
        {}
    )

    print(
        "=============================="
    )
    print(
        "条件別 過去レース探索"
    )
    print(
        "対象Race ID:",
        target["race_id"]
    )
    print(
        "対象日:",
        target["race_date"]
    )
    print(
        "条件:",
        target["racecourse"],
        target["surface"],
        target["distance"],
    )
    print(
        "=============================="
    )

    existing = (
        get_existing_races(
            history_db,
            target
        )
    )

    existing_count = len(
        existing
    )

    print(
        "既存DB一致レース:",
        existing_count
    )

    metadata_complete_count = sum(
        1
        for row in existing
        if (
            row.get("race_name")
            and row.get(
                "race_info_text"
            )
            and row.get(
                "race_class"
            )
            and row.get(
                "age_condition"
            )
        )
    )

    cache_metadata_ready = (
        existing_count
        >= MIN_CACHE_RACES
        and metadata_complete_count
        >= MIN_CACHE_RACES
    )

    if cache_metadata_ready:
        print(
            "既存DB metadata:",
            metadata_complete_count,
            "/",
            existing_count,
        )

        (
            refreshed,
            refresh_count,
            changed_count,
            refresh_errors,
        ) = refresh_suspicious_classes(
            existing
        )

        selected = refreshed[
            :MAX_RACES
        ]

        if existing_count >= MAX_RACES:
            cache_reason = (
                "MAX_RACES以上の既存データあり・"
                "metadata取得済み・"
                "OPのみグレード再確認"
            )
        else:
            cache_reason = (
                "MIN_CACHE_RACES以上の既存データあり・"
                "metadata取得済み・"
                "OPのみグレード再確認"
            )

        output = build_output(
            target=target,
            races=selected,
            errors=refresh_errors,
            cache_used=True,
            existing_count=(
                existing_count
            ),
            searched=False,
            cache_reason=(
                cache_reason
            ),
            class_refresh_count=(
                refresh_count
            ),
            class_changed_count=(
                changed_count
            ),
        )

        save_json(
            OUTPUT_FILE,
            output
        )

        print(
            "既存DBを使用します"
        )
        print(
            "日付ネット探索をスキップします"
        )
        print(
            "OPクラス再確認:",
            refresh_count,
            "件"
        )
        print(
            "クラス修正:",
            changed_count,
            "件"
        )
        print(
            "history_races.json 作成完了"
        )
        print(
            "対象条件レース:",
            len(selected)
        )
        print(
            "クラス内訳:",
            output[
                "metadata"
            ][
                "class_counts"
            ],
        )

        return

    matched = []
    checked_ids = set()
    errors = []

    print(
        "クラス/年齢条件を含む"
        "履歴を収集します"
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
        if (
            len(matched)
            >= MAX_RACES
        ):
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
                "date": (
                    date_string
                ),
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
            if (
                len(matched)
                >= MAX_RACES
            ):
                break

            if (
                race_id
                == target["race_id"]
            ):
                continue

            if race_id in checked_ids:
                continue

            checked_ids.add(
                race_id
            )

            try:
                info = (
                    parse_race_info(
                        race_id
                    )
                )

                if (
                    info["racecourse"]
                    == target[
                        "racecourse"
                    ]
                    and info["surface"]
                    == target[
                        "surface"
                    ]
                    and info["distance"]
                    == target[
                        "distance"
                    ]
                ):
                    info[
                        "race_date"
                    ] = (
                        search_date
                        .isoformat()
                    )

                    matched.append(
                        info
                    )

                    print(
                        "  MATCH:",
                        race_id,
                        info[
                            "racecourse"
                        ],
                        info[
                            "surface"
                        ],
                        info[
                            "distance"
                        ],
                        "|",
                        (
                            info[
                                "race_name"
                            ]
                            or
                            "レース名不明"
                        ),
                        "|",
                        (
                            info[
                                "race_class"
                            ]
                            or
                            "クラス不明"
                        ),
                        "|",
                        (
                            info[
                                "age_condition"
                            ]
                            or
                            "年齢条件不明"
                        ),
                    )

                time.sleep(
                    REQUEST_WAIT
                )

            except Exception as e:
                errors.append({
                    "race_id": (
                        race_id
                    ),
                    "error": str(e),
                })

        if (
            len(matched)
            >= MAX_RACES
        ):
            break

        time.sleep(
            DATE_WAIT
        )

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
            x.get(
                "race_date",
                ""
            ),
            x.get(
                "race_id",
                ""
            ),
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
        existing_count=(
            existing_count
        ),
        searched=True,
        cache_reason=(
            "時計基準用metadataを再収集"
        ),
    )

    save_json(
        OUTPUT_FILE,
        output
    )

    print(
        "=============================="
    )
    print(
        "history_races.json 作成完了"
    )
    print(
        "最終対象レース:",
        len(unique)
    )
    print(
        "取得エラー:",
        len(errors)
    )

    print(
        "クラス内訳:",
        output[
            "metadata"
        ][
            "class_counts"
        ],
    )

    print(
        "年齢条件内訳:",
        output[
            "metadata"
        ][
            "age_condition_counts"
        ],
    )

    print(
        "=============================="
    )

    if not unique:
        raise RuntimeError(
            "対象レース以前に"
            "同条件の過去レースを"
            "取得できませんでした"
        )


if __name__ == "__main__":
    main()
