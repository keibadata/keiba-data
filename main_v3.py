import json
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


# =========================================================
# Race ID
# =========================================================

DEFAULT_RACE_ID = "202605040502"


def load_race_id():
    env_race_id = os.environ.get("RACE_ID", "").strip()

    if env_race_id:
        if not re.fullmatch(r"\d{12}", env_race_id):
            raise ValueError(
                "環境変数 RACE_ID は12桁の数字で指定してください。"
            )

        print("race id source: environment")
        return env_race_id

    if os.path.exists("race_id.txt"):
        with open(
            "race_id.txt",
            "r",
            encoding="utf-8"
        ) as f:
            file_race_id = f.read().strip()

        if file_race_id:
            if not re.fullmatch(r"\d{12}", file_race_id):
                raise ValueError(
                    "race_id.txt は12桁の数字で指定してください。"
                )

            print("race id source: race_id.txt")
            return file_race_id

    if not re.fullmatch(r"\d{12}", DEFAULT_RACE_ID):
        raise ValueError(
            "DEFAULT_RACE_ID が不正です。"
        )

    print("race id source: default")
    return DEFAULT_RACE_ID


RACE_ID = load_race_id()

URL = (
    "https://race.netkeiba.com/"
    f"race/shutuba.html?race_id={RACE_ID}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


print("========================================")
print("RACE COLLECTOR")
print("========================================")
print("Target Race ID:", RACE_ID)
print("URL:", URL)


response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(
    response.text,
    "html.parser"
)


# =========================================================
# 共通
# =========================================================

def clean_text(element):
    if element is None:
        return ""

    return element.get_text(
        " ",
        strip=True
    )


def normalize_text(value):
    value = str(value or "")

    value = value.replace(
        "\u3000",
        " "
    )

    value = re.sub(
        r"\s+",
        " ",
        value
    )

    return value.strip()


def first_text(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)

        if element:
            text = normalize_text(
                clean_text(element)
            )

            if text:
                return text

    return ""


def meta_content(soup, selector):
    element = soup.select_one(selector)

    if element is None:
        return ""

    return normalize_text(
        element.get("content", "")
    )


# =========================================================
# レース条件
# =========================================================

def extract_race_condition(
    soup,
    race_id
):
    page_text = normalize_text(
        clean_text(soup)
    )

    # -----------------------------------------------------
    # 開催日
    # -----------------------------------------------------

    race_date = ""

    date_texts = []

    date_selectors = [
        ".RaceData02",
        ".RaceData01",
        ".RaceData",
        ".RaceList_Date",
        ".RaceList_Data",
        ".RaceList_Item01",
        ".RaceList_Item02",
        ".RaceList_NameBox",
    ]

    for selector in date_selectors:
        for element in soup.select(selector):
            text = normalize_text(
                clean_text(element)
            )

            if text:
                date_texts.append(text)

    title_text = normalize_text(
        clean_text(
            soup.select_one("title")
        )
    )

    og_title = meta_content(
        soup,
        'meta[property="og:title"]'
    )

    description = meta_content(
        soup,
        'meta[name="description"]'
    )

    og_description = meta_content(
        soup,
        'meta[property="og:description"]'
    )

    date_texts.extend(
        [
            title_text,
            og_title,
            description,
            og_description,
            page_text,
        ]
    )

    date_patterns = [
        (
            r"(20\d{2})年\s*"
            r"(\d{1,2})月\s*"
            r"(\d{1,2})日"
        ),
        (
            r"(20\d{2})/"
            r"(\d{1,2})/"
            r"(\d{1,2})"
        ),
        (
            r"(20\d{2})-"
            r"(\d{1,2})-"
            r"(\d{1,2})"
        ),
        (
            r"(20\d{2})\."
            r"(\d{1,2})\."
            r"(\d{1,2})"
        ),
    ]

    for text in date_texts:
        if not text:
            continue

        for pattern in date_patterns:
            match = re.search(
                pattern,
                text
            )

            if not match:
                continue

            try:
                race_date = datetime(
                    int(match.group(1)),
                    int(match.group(2)),
                    int(match.group(3))
                ).strftime(
                    "%Y-%m-%d"
                )

            except (
                TypeError,
                ValueError
            ):
                race_date = ""

            if race_date:
                break

        if race_date:
            break

    # -----------------------------------------------------
    # 競馬場
    #
    # race_id の場コードを正とする。
    # HTML全文から競馬場を上書きしない。
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

    track = ""

    if len(race_id) == 12:
        track_code = race_id[4:6]

        track = jra_tracks.get(
            track_code,
            ""
        )

    # -----------------------------------------------------
    # レース情報候補
    #
    # netkeibaはページによってRaceName系classが
    # 空になることがあるため、title / metaも確認する。
    # -----------------------------------------------------

    header_texts = []

    header_selectors = [
        ".RaceName",
        "h1.RaceName",
        ".RaceName_main",
        ".RaceList_NameBox",
        ".RaceList_Name",
        ".RaceList_ItemTitle",
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
        "h1",
    ]

    for selector in header_selectors:
        for element in soup.select(selector):
            text = normalize_text(
                clean_text(element)
            )

            if text:
                header_texts.append(text)

    metadata_texts = [
        title_text,
        og_title,
        description,
        og_description,
    ]

    race_info_candidates = []

    for text in (
        header_texts
        + metadata_texts
    ):
        text = normalize_text(text)

        if (
            text
            and text not in race_info_candidates
        ):
            race_info_candidates.append(
                text
            )

    race_info_text = normalize_text(
        " ".join(
            race_info_candidates
        )
    )

    # -----------------------------------------------------
    # レース名
    # -----------------------------------------------------

    race_name = first_text(
        soup,
        [
            ".RaceName",
            "h1.RaceName",
            ".RaceName_main",
            ".RaceList_Name",
            ".RaceList_ItemTitle",
        ]
    )

    if not race_name:
        race_name_patterns = [
            r"(メイクデビュー[^|｜\-–—]*)",
            r"((?:2歳|3歳|4歳以上|3歳以上)?\s*新馬)",
            r"((?:2歳|3歳|4歳以上|3歳以上)?\s*未勝利)",
            r"([^|｜]+(?:ステークス|カップ|賞|記念))",
        ]

        for source in metadata_texts:
            if not source:
                continue

            for pattern in race_name_patterns:
                match = re.search(
                    pattern,
                    source,
                    re.IGNORECASE
                )

                if match:
                    race_name = normalize_text(
                        match.group(1)
                    )
                    break

            if race_name:
                break

    # -----------------------------------------------------
    # クラス
    # -----------------------------------------------------

    race_class = ""

    class_patterns = [
        (
            "新馬",
            r"(?:新馬|メイクデビュー)"
        ),
        (
            "未勝利",
            r"未勝利"
        ),
        (
            "1勝クラス",
            r"(?:1勝クラス|500万下)"
        ),
        (
            "2勝クラス",
            r"(?:2勝クラス|1000万下)"
        ),
        (
            "3勝クラス",
            r"(?:3勝クラス|1600万下)"
        ),
        (
            "G1",
            r"(?:G1|GI|GⅠ)"
        ),
        (
            "G2",
            r"(?:G2|GII|GⅡ)"
        ),
        (
            "G3",
            r"(?:G3|GIII|GⅢ)"
        ),
        (
            "リステッド",
            r"(?:リステッド|Listed|\(L\))"
        ),
        (
            "オープン",
            r"(?:オープン|\bOP\b)"
        ),
    ]

    class_source = normalize_text(
        race_name
        + " "
        + race_info_text
    )

    for label, pattern in class_patterns:
        if re.search(
            pattern,
            class_source,
            re.IGNORECASE
        ):
            race_class = label
            break

    # -----------------------------------------------------
    # 年齢条件
    # -----------------------------------------------------

    age_condition = ""

    age_patterns = [
        (
            "3歳以上",
            r"3歳以上"
        ),
        (
            "4歳以上",
            r"4歳以上"
        ),
        (
            "2歳",
            r"2歳"
        ),
        (
            "3歳",
            r"3歳"
        ),
    ]

    for label, pattern in age_patterns:
        if re.search(
            pattern,
            race_info_text
        ):
            age_condition = label
            break

    # -----------------------------------------------------
    # 新馬戦判定
    #
    # 過去走0件は判定材料にしない。
    #
    # RaceName / RaceData / title / og:title /
    # description等のレース情報に
    # 「新馬」「メイクデビュー」が明示された場合のみtrue。
    # -----------------------------------------------------

    debut_pattern = (
        r"(?:新馬|メイクデビュー)"
    )

    is_debut = bool(
        re.search(
            debut_pattern,
            class_source,
            re.IGNORECASE
        )
    )

    if is_debut:
        race_class = "新馬"

    # -----------------------------------------------------
    # 芝 / ダート / 障害・距離
    # -----------------------------------------------------

    surface = ""
    distance = 0

    race_data_texts = []

    selectors = [
        ".RaceData01",
        ".RaceData02",
        ".RaceData",
        ".RaceName",
        ".RaceList_Item02",
        ".RaceList_NameBox",
    ]

    for selector in selectors:
        for element in soup.select(selector):
            text = normalize_text(
                clean_text(element)
            )

            if text:
                race_data_texts.append(
                    text
                )

    race_data_texts.extend(
        metadata_texts
    )

    race_data_texts.append(
        page_text
    )

    for text in race_data_texts:
        if not text:
            continue

        match = re.search(
            r"芝\s*([0-9]{3,4})\s*[mｍ]?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "芝"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            r"(?:ダート|ダ)\s*([0-9]{3,4})\s*[mｍ]?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "ダート"
            distance = int(
                match.group(1)
            )
            break

        match = re.search(
            r"障(?:害)?\s*([0-9]{3,4})\s*[mｍ]?",
            text,
            re.IGNORECASE
        )

        if match:
            surface = "障害"
            distance = int(
                match.group(1)
            )
            break

    # -----------------------------------------------------
    # 馬場状態
    # -----------------------------------------------------

    track_condition = ""

    condition_patterns = [
        r"馬場\s*[:：]\s*(良|稍重|重|不良)",
        r"芝\s*[:：]\s*(良|稍重|重|不良)",
        r"ダート?\s*[:：]\s*(良|稍重|重|不良)",
    ]

    for pattern in condition_patterns:
        match = re.search(
            pattern,
            page_text
        )

        if match:
            track_condition = (
                match.group(1)
            )
            break

    return {
        "race_date": race_date,
        "track": track,
        "race_name": race_name,
        "race_class": race_class,
        "age_condition": age_condition,
        "is_debut": is_debut,
        "surface": surface,
        "distance": distance,
        "track_condition": track_condition,
    }


race_condition = extract_race_condition(
    soup,
    RACE_ID
)


# =========================================================
# 出走馬
# =========================================================

def extract_horse_id(row):
    link = row.select_one(
        'a[href*="/horse/"]'
    )

    if not link:
        return ""

    href = link.get(
        "href",
        ""
    )

    patterns = [
        r"/horse/(\d+)",
        r"horse_id=(\d+)",
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            href
        )

        if match:
            return match.group(1)

    return ""


def extract_horse_name(row):
    name = first_text(
        row,
        [
            ".HorseName a",
            ".HorseInfo .HorseName a",
            'a[href*="/horse/"]',
        ]
    )

    return normalize_text(name)


def extract_horse_number(row):
    selectors = [
        ".Umaban",
        ".Horse_Num",
        ".HorseNumber",
        "td.Umaban",
    ]

    text = first_text(
        row,
        selectors
    )

    match = re.search(
        r"\d+",
        text
    )

    if match:
        return match.group(0)

    number_element = row.select_one(
        "[data-horse-number]"
    )

    if number_element:
        value = number_element.get(
            "data-horse-number",
            ""
        )

        if value:
            return str(value)

    return ""


def extract_sex_age(row):
    text = first_text(
        row,
        [
            ".Barei",
            ".HorseInfo .Barei",
            ".Horse_Info .Barei",
            "td.Barei",
        ]
    )

    match = re.search(
        r"[牡牝セ騙]\s*\d+",
        text
    )

    if match:
        return re.sub(
            r"\s+",
            "",
            match.group(0)
        )

    row_text = normalize_text(
        clean_text(row)
    )

    match = re.search(
        r"[牡牝セ騙]\s*\d+",
        row_text
    )

    if match:
        return re.sub(
            r"\s+",
            "",
            match.group(0)
        )

    return ""


def extract_carried_weight(row):
    text = first_text(
        row,
        [
            ".Weight",
            ".Jockey .Weight",
            ".HorseInfo .Weight",
            "td.Weight",
        ]
    )

    match = re.search(
        r"\d{2}(?:\.\d)?",
        text
    )

    if match:
        return match.group(0)

    return ""


def extract_jockey(row):
    jockey = first_text(
        row,
        [
            ".Jockey a",
            ".Jockey",
            'a[href*="/jockey/"]',
        ]
    )

    return normalize_text(jockey)


def extract_body_weight(row):
    selectors = [
        ".Weight",
        ".HorseWeight",
        ".BodyWeight",
        ".Weight_Body",
        "td.Weight",
    ]

    candidates = []

    for selector in selectors:
        for element in row.select(selector):
            text = normalize_text(
                clean_text(element)
            )

            if text:
                candidates.append(text)

    candidates.append(
        normalize_text(
            clean_text(row)
        )
    )

    patterns = [
        r"(\d{3})\s*kg\s*\(([+\-−]?\d+)\)",
        r"(\d{3})\s*\(([+\-−]?\d+)\)",
        r"(\d{3})\s*kg",
    ]

    for text in candidates:
        for pattern in patterns:
            match = re.search(
                pattern,
                text,
                re.IGNORECASE
            )

            if not match:
                continue

            body_weight = (
                match.group(1)
            )

            body_weight_change = ""

            if match.lastindex and match.lastindex >= 2:
                body_weight_change = (
                    match.group(2)
                    .replace("−", "-")
                )

            return (
                body_weight,
                body_weight_change
            )

    return "", ""


# =========================================================
# 馬行取得
# =========================================================

rows = soup.select(
    "tr.HorseList"
)

if not rows:
    rows = soup.select(
        ".HorseList"
    )


horses = []
warnings = []

for row in rows:
    horse_id = extract_horse_id(
        row
    )

    horse_name = extract_horse_name(
        row
    )

    if not horse_id and not horse_name:
        continue

    horse_number = extract_horse_number(
        row
    )

    sex_age = extract_sex_age(
        row
    )

    carried_weight = extract_carried_weight(
        row
    )

    jockey = extract_jockey(
        row
    )

    (
        body_weight,
        body_weight_change
    ) = extract_body_weight(
        row
    )

    horse = {
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "carried_weight": carried_weight,
        "jockey": jockey,
        "body_weight": body_weight,
        "body_weight_change": body_weight_change,
    }

    horses.append(
        horse
    )

    missing = []

    if not horse_number:
        missing.append(
            "horse_number"
        )

    if not horse_id:
        missing.append(
            "horse_id"
        )

    if not horse_name:
        missing.append(
            "horse_name"
        )

    if not sex_age:
        missing.append(
            "sex_age"
        )

    if not carried_weight:
        missing.append(
            "carried_weight"
        )

    if not jockey:
        missing.append(
            "jockey"
        )

    if not body_weight:
        missing.append(
            "body_weight"
        )

    if missing:
        warnings.append(
            {
                "horse_number": horse_number,
                "horse_name": horse_name,
                "missing": missing,
            }
        )


# =========================================================
# 馬番順
# =========================================================

def horse_number_sort_key(horse):
    value = str(
        horse.get(
            "horse_number",
            ""
        )
    )

    if value.isdigit():
        return (
            0,
            int(value)
        )

    return (
        1,
        999
    )


horses.sort(
    key=horse_number_sort_key
)


# =========================================================
# 出力
# =========================================================

JST = timezone(
    timedelta(hours=9)
)

output = {
    "race_id": RACE_ID,
    "race_date": race_condition.get(
        "race_date",
        ""
    ),
    "updated_at": datetime.now(
        JST
    ).isoformat(),
    "source": "netkeiba",
    "source_url": URL,
    "track": race_condition.get(
        "track",
        ""
    ),
    "racecourse": race_condition.get(
        "track",
        ""
    ),
    "race_name": race_condition.get(
        "race_name",
        ""
    ),
    "race_class": race_condition.get(
        "race_class",
        ""
    ),
    "age_condition": race_condition.get(
        "age_condition",
        ""
    ),
    "is_debut": bool(
        race_condition.get(
            "is_debut",
            False
        )
    ),
    "surface": race_condition.get(
        "surface",
        ""
    ),
    "distance": race_condition.get(
        "distance",
        0
    ),
    "track_condition": race_condition.get(
        "track_condition",
        ""
    ),
    "horse_count": len(
        horses
    ),
    "warnings": warnings,
    "horses": horses,
}


with open(
    "race.json",
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
    json.dumps(
        output,
        ensure_ascii=False,
        indent=2
    )
)

print()
print("--- RACE CONDITION ---")
print(
    "race_id:",
    output["race_id"]
)
print(
    "race_date:",
    output["race_date"]
)
print(
    "track:",
    output["track"]
)
print(
    "race_name:",
    output["race_name"]
)
print(
    "race_class:",
    output["race_class"]
)
print(
    "age_condition:",
    output["age_condition"]
)
print(
    "is_debut:",
    output["is_debut"]
)
print(
    "surface:",
    output["surface"]
)
print(
    "distance:",
    output["distance"]
)
print(
    "track_condition:",
    output["track_condition"]
)

print()
print("--- HORSES ---")
print(
    "horse_count:",
    len(horses)
)

for horse in horses:
    print(
        horse.get(
            "horse_number",
            ""
        ),
        horse.get(
            "horse_name",
            ""
        ),
        horse.get(
            "sex_age",
            ""
        ),
        horse.get(
            "carried_weight",
            ""
        ),
        horse.get(
            "jockey",
            ""
        ),
        horse.get(
            "body_weight",
            ""
        ),
        horse.get(
            "body_weight_change",
            ""
        ),
    )


if warnings:
    print()
    print("--- WARNINGS ---")

    for warning in warnings:
        print(
            warning
        )


print()
print(
    "========================================"
)
print(
    "RACE COLLECTION FINISHED"
)
print(
    "========================================"
)
