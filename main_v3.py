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
    value = value.replace("\u3000", " ")
    value = re.sub(r"\s+", " ", value)
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

def extract_race_condition(soup, race_id):
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
                ).strftime("%Y-%m-%d")

            except (TypeError, ValueError):
                race_date = ""

            if race_date:
                break

        if race_date:
            break

    # -----------------------------------------------------
    # 競馬場
    # race_id の場コードを正とする。
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
            race_info_candidates.append(text)

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
    # 過去走0件は判定材料にしない。
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
                race_data_texts.append(text)

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

def extract_horse_link(row):
    """
    馬IDを持つリンクを取得。
    馬IDが存在しないHorseList行は実出走馬として扱わない。
    """
    links = row.select(
        'a[href*="/horse/"]'
    )

    for link in links:
        href = str(
            link.get(
                "href",
                ""
            )
        )

        if re.search(
            r"/horse/\d+",
            href
        ):
            return link

    return None


def extract_horse_id(row):
    link = extract_horse_link(
        row
    )

    if not link:
        return ""

    href = str(
        link.get(
            "href",
            ""
        )
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


def normalize_horse_name(value):
    value = normalize_text(
        value
    )

    suffix_patterns = [
        r"\s*のデータベース\s*$",
        r"\s*データベース\s*$",
        r"\s*の競走馬データ\s*$",
        r"\s*競走馬データ\s*$",
    ]

    for pattern in suffix_patterns:
        value = re.sub(
            pattern,
            "",
            value
        )

    return normalize_text(
        value
    )


def extract_horse_name(row):
    selectors = [
        ".HorseName a",
        ".HorseName",
        ".HorseInfo .HorseName a",
        ".HorseInfo .HorseName",
    ]

    for selector in selectors:
        element = row.select_one(
            selector
        )

        if not element:
            continue

        name = normalize_horse_name(
            clean_text(element)
        )

        if name:
            return name

    link = extract_horse_link(
        row
    )

    if link:
        name = normalize_horse_name(
            clean_text(link)
        )

        if name:
            return name

        for attr in (
            "title",
            "aria-label",
        ):
            value = normalize_horse_name(
                link.get(
                    attr,
                    ""
                )
            )

            if value:
                return value

    return ""


def valid_horse_number(value):
    try:
        number = int(
            str(value).strip()
        )

    except (
        TypeError,
        ValueError
    ):
        return ""

    if 1 <= number <= 18:
        return str(number)

    return ""


def extract_horse_number(row):
    """
    実HTML確認済み:
    馬番はHorseList行のWaku1～Waku8系セル内に存在する。

    枠番そのものと混同しないため、
    Wakuクラスを持つセルの「表示テキスト」を馬番として使用する。
    """

    # -----------------------------------------------------
    # 1. Waku系セル
    # -----------------------------------------------------

    for element in row.find_all(
        ["td", "div", "span"]
    ):
        classes = [
            str(x)
            for x in element.get(
                "class",
                []
            )
        ]

        if not classes:
            continue

        has_waku_class = any(
            re.fullmatch(
                r"Waku\d+",
                class_name,
                re.IGNORECASE
            )
            for class_name in classes
        )

        if not has_waku_class:
            continue

        text = normalize_text(
            clean_text(element)
        )

        match = re.search(
            r"\b(\d{1,2})\b",
            text
        )

        if match:
            number = valid_horse_number(
                match.group(1)
            )

            if number:
                return number

    # -----------------------------------------------------
    # 2. data属性フォールバック
    # -----------------------------------------------------

    data_attributes = [
        "data-horse-number",
        "data-umaban",
        "data-horse-num",
    ]

    for attr in data_attributes:
        element = row.select_one(
            f"[{attr}]"
        )

        if not element:
            continue

        value = element.get(
            attr,
            ""
        )

        match = re.search(
            r"\d{1,2}",
            str(value)
        )

        if match:
            number = valid_horse_number(
                match.group(0)
            )

            if number:
                return number

    # -----------------------------------------------------
    # 3. 従来classフォールバック
    # -----------------------------------------------------

    selectors = [
        ".Umaban",
        "td.Umaban",
        ".Horse_Num",
        ".HorseNumber",
        "td.HorseNumber",
        '[class^="Umaban"]',
        '[class*=" Umaban"]',
        '[class^="Horse_Num"]',
    ]

    for selector in selectors:
        for element in row.select(
            selector
        ):
            text = normalize_text(
                clean_text(element)
            )

            match = re.search(
                r"\d{1,2}",
                text
            )

            if match:
                number = valid_horse_number(
                    match.group(0)
                )

                if number:
                    return number

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


def extract_jockey_and_weight(row):
    """
    実HTML確認済み:
    騎手リンクの表示が
        ルメール 55.0
        幸 56.0
    のように騎手名＋斤量になっている。

    末尾の2桁重量を斤量として分離する。
    """

    jockey_element = None

    selectors = [
        ".Jockey a",
        'a[href*="/jockey/"]',
        ".Jockey",
    ]

    for selector in selectors:
        element = row.select_one(
            selector
        )

        if element:
            text = normalize_text(
                clean_text(element)
            )

            if text:
                jockey_element = element
                break

    if jockey_element is None:
        return "", ""

    text = normalize_text(
        clean_text(jockey_element)
    )

    # 末尾重量
    match = re.search(
        r"\s+(\d{2}(?:\.\d)?)\s*$",
        text
    )

    if match:
        carried_weight = (
            match.group(1)
        )

        jockey = normalize_text(
            text[:match.start()]
        )

        return (
            jockey,
            carried_weight
        )

    # 斤量がリンク外にあるケースへのフォールバック
    carried_weight = ""

    weight_candidates = [
        ".Jockey .Weight",
        ".Weight",
        "td.Weight",
    ]

    for selector in weight_candidates:
        element = row.select_one(
            selector
        )

        if not element:
            continue

        candidate = normalize_text(
            clean_text(element)
        )

        match = re.fullmatch(
            r"\d{2}(?:\.\d)?",
            candidate
        )

        if match:
            carried_weight = (
                match.group(0)
            )
            break

    return (
        text,
        carried_weight
    )


def extract_body_weight(row):
    """
    馬体重のみ取得。

    斤量55.0/56.0を馬体重として誤認しないよう、
    3桁kg表記だけを対象とする。
    """

    selectors = [
        ".Weight",
        ".HorseWeight",
        ".BodyWeight",
        ".Weight_Body",
        "td.Weight",
    ]

    candidates = []

    for selector in selectors:
        for element in row.select(
            selector
        ):
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

            if (
                match.lastindex
                and match.lastindex >= 2
            ):
                body_weight_change = (
                    match.group(2)
                    .replace(
                        "−",
                        "-"
                    )
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

    # -----------------------------------------------------
    # 実出走馬判定
    #
    # HorseListには出走馬以外の行が含まれる場合がある。
    # 馬IDリンクを持つ行だけ採用する。
    # -----------------------------------------------------

    horse_id = extract_horse_id(
        row
    )

    if not horse_id:
        continue

    horse_name = extract_horse_name(
        row
    )

    horse_number = extract_horse_number(
        row
    )

    sex_age = extract_sex_age(
        row
    )

    (
        jockey,
        carried_weight
    ) = extract_jockey_and_weight(
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

    # レース前の馬体重未発表は正常なので、
    # body_weightはwarning対象にしない。

    if missing:
        warnings.append(
            {
                "horse_number": horse_number,
                "horse_name": horse_name,
                "missing": missing,
            }
        )


# =========================================================
# 重複チェック
# =========================================================

seen_horse_ids = set()
unique_horses = []

for horse in horses:
    horse_id = str(
        horse.get(
            "horse_id",
            ""
        )
    ).strip()

    if (
        horse_id
        and horse_id in seen_horse_ids
    ):
        continue

    if horse_id:
        seen_horse_ids.add(
            horse_id
        )

    unique_horses.append(
        horse
    )

horses = unique_horses


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
