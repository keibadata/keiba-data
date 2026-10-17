import json
import os
import re
from datetime import datetime, timezone, timedelta

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
OUTPUT_FILE = "track_condition.json"

JRA_BABA_PAGE = (
    "https://www.jra.go.jp/keiba/baba/index.html"
)

JRA_CUSHION_URL = (
    "https://www.jra.go.jp/keiba/baba/_data_cushion.html"
)

JRA_MOIST_URL = (
    "https://www.jra.go.jp/keiba/baba/_data_moist.html"
)

TIMEOUT = 30

JST = timezone(
    timedelta(hours=9)
)


HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept": (
        "text/html,application/xhtml+xml,"
        "application/xml;q=0.9,*/*;q=0.8"
    ),
    "Accept-Language": (
        "ja,en-US;q=0.9,en;q=0.8"
    ),
    "Referer": JRA_BABA_PAGE,
}


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def load_json(path):

    if not os.path.exists(path):
        return {}

    try:

        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:

            return json.load(f)

    except Exception:

        return {}


def save_json(
    path,
    data
):

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean_text(value):

    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def to_float(value):

    if value is None:
        return None

    text = clean_text(
        value
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(
            match.group()
        )
    except Exception:
        return None


def get_html(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=TIMEOUT
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in [
            "iso-8859-1",
            "ascii"
        ]
    ):

        response.encoding = (
            response.apparent_encoding
            or "utf-8"
        )

    return response.text


# ============================================================
# 競馬場
# ============================================================

TRACK_ALIASES = {
    "札幌": ["札幌"],
    "函館": ["函館"],
    "福島": ["福島"],
    "新潟": ["新潟"],
    "東京": ["東京"],
    "中山": ["中山"],
    "中京": ["中京"],
    "京都": ["京都"],
    "阪神": ["阪神"],
    "小倉": ["小倉"],
}


def normalize_track(value):

    value = clean_text(
        value
    )

    for track_name, aliases in (
        TRACK_ALIASES.items()
    ):

        for alias in aliases:

            if alias in value:
                return track_name

    return value


# ============================================================
# 日付
# ============================================================

def parse_race_date(value):

    text = clean_text(
        value
    )

    if not text:
        return None

    formats = [
        "%Y-%m-%d",
        "%Y/%m/%d",
    ]

    for fmt in formats:

        try:

            return datetime.strptime(
                text,
                fmt
            ).date()

        except ValueError:
            pass

    return None


def make_jra_date_prefix(
    race_date_obj
):

    if race_date_obj is None:
        return ""

    return (
        f"{race_date_obj.month}月"
        f"{race_date_obj.day}日"
    )


# ============================================================
# race.json
# ============================================================

race = load_json(
    RACE_FILE
)


if not race:

    raise SystemExit(
        "ERROR: race.json がありません"
    )


race_id = clean_text(
    race.get(
        "race_id"
    )
)


race_date_text = clean_text(
    race.get(
        "race_date"
    )
    or race.get(
        "date"
    )
)


race_date_obj = parse_race_date(
    race_date_text
)


track = normalize_track(
    race.get(
        "track"
    )
    or race.get(
        "racecourse"
    )
)


surface = clean_text(
    race.get(
        "surface"
    )
)


distance = race.get(
    "distance"
)


race_track_condition = clean_text(
    race.get(
        "track_condition"
    )
)


if not race_id:

    raise SystemExit(
        "ERROR: race_id がありません"
    )


if not race_date_obj:

    raise SystemExit(
        "ERROR: race_date が不正です"
    )


if not track:

    raise SystemExit(
        "ERROR: 競馬場がありません"
    )


if surface not in [
    "芝",
    "ダート"
]:

    raise SystemExit(
        "ERROR: surface が芝/ダートではありません"
    )


target_date_prefix = (
    make_jra_date_prefix(
        race_date_obj
    )
)


print()
print(
    "===== JRA TRACK CONDITION ====="
)

print(
    "race id:",
    race_id
)

print(
    "date:",
    race_date_text
)

print(
    "target date:",
    target_date_prefix
)

print(
    "track:",
    track
)

print(
    "surface:",
    surface
)

print(
    "distance:",
    distance
)

print()


# ============================================================
# JRA含水率
#
# 実HTML:
#
# <div id="rcA" title="東京">
#   <div class="unit">
#     <div class="time">10月12日 ...</div>
#     <div class="turf">
#       <span class="mg">...</span>
#       <span class="m4c">...</span>
#     </div>
#     <div class="dirt">
#       <span class="mg">...</span>
#       <span class="m4c">...</span>
#     </div>
#   </div>
# </div>
#
# mg  = ゴール前
# m4c = 4コーナー
# ============================================================

def extract_moisture(
    html,
    track_name,
    race_date_obj,
    surface_name
):

    result = {
        "found": False,
        "track_found": False,
        "date_found": False,
        "measurement_time": "",
        "finish": None,
        "four_corner": None,
        "track_block_id": "",
    }


    if not html:
        return result


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # --------------------------------------------------------
    # title="東京" 等で競馬場を直接特定
    # --------------------------------------------------------

    track_block = soup.find(
        attrs={
            "title": track_name
        }
    )


    if track_block is None:

        return result


    result[
        "track_found"
    ] = True


    result[
        "track_block_id"
    ] = clean_text(
        track_block.get(
            "id"
        )
    )


    target_prefix = (
        make_jra_date_prefix(
            race_date_obj
        )
    )


    # --------------------------------------------------------
    # 対象日付のunitだけを選択
    # --------------------------------------------------------

    target_unit = None
    target_time = ""


    for unit in track_block.select(
        ".unit"
    ):

        time_element = unit.select_one(
            ".time"
        )


        if time_element is None:
            continue


        time_text = clean_text(
            time_element.get_text(
                " ",
                strip=True
            )
        )


        if not time_text.startswith(
            target_prefix
        ):
            continue


        target_unit = unit
        target_time = time_text

        break


    if target_unit is None:

        return result


    result[
        "date_found"
    ] = True


    result[
        "measurement_time"
    ] = target_time


    # --------------------------------------------------------
    # 芝 / ダートを明示選択
    # --------------------------------------------------------

    if surface_name == "芝":

        surface_block = (
            target_unit.select_one(
                ".turf"
            )
        )

    else:

        surface_block = (
            target_unit.select_one(
                ".dirt"
            )
        )


    if surface_block is None:

        return result


    # --------------------------------------------------------
    # ゴール前 / 4コーナー
    # --------------------------------------------------------

    finish_element = (
        surface_block.select_one(
            ".mg"
        )
    )


    four_corner_element = (
        surface_block.select_one(
            ".m4c"
        )
    )


    finish = None
    four_corner = None


    if finish_element is not None:

        finish = to_float(
            finish_element.get_text(
                " ",
                strip=True
            )
        )


    if four_corner_element is not None:

        four_corner = to_float(
            four_corner_element.get_text(
                " ",
                strip=True
            )
        )


    # --------------------------------------------------------
    # 含水率として異常値なら破棄
    # --------------------------------------------------------

    if (
        finish is not None
        and not (
            0.0 <= finish <= 30.0
        )
    ):

        finish = None


    if (
        four_corner is not None
        and not (
            0.0 <= four_corner <= 30.0
        )
    ):

        four_corner = None


    result[
        "finish"
    ] = finish


    result[
        "four_corner"
    ] = four_corner


    result[
        "found"
    ] = (
        finish is not None
        or four_corner is not None
    )


    return result


# ============================================================
# JRAクッション値
#
# ダートでは取得値を評価に使用しない。
#
# 芝の場合のみ対象日付を確認して採用。
# ============================================================

def extract_cushion(
    html,
    track_name,
    race_date_obj
):

    result = {
        "found": False,
        "track_found": False,
        "date_found": False,
        "measurement_time": "",
        "value": None,
        "track_block_id": "",
    }


    if not html:
        return result


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    # title属性優先
    track_block = soup.find(
        attrs={
            "title": track_name
        }
    )


    # cushion側はid等の構造が違う可能性があるため
    # titleで見つからなければテキストも確認
    if track_block is None:

        for candidate in soup.find_all(
            [
                "div",
                "section",
                "li"
            ]
        ):

            candidate_text = clean_text(
                candidate.get_text(
                    " ",
                    strip=True
                )
            )


            if track_name not in candidate_text:
                continue


            if len(
                candidate_text
            ) > 3000:
                continue


            track_block = candidate

            break


    if track_block is None:

        return result


    result[
        "track_found"
    ] = True


    result[
        "track_block_id"
    ] = clean_text(
        track_block.get(
            "id"
        )
    )


    target_prefix = (
        make_jra_date_prefix(
            race_date_obj
        )
    )


    # --------------------------------------------------------
    # 対象日付のunit
    # --------------------------------------------------------

    for unit in track_block.select(
        ".unit"
    ):

        time_element = (
            unit.select_one(
                ".time"
            )
        )


        if time_element is None:
            continue


        time_text = clean_text(
            time_element.get_text(
                " ",
                strip=True
            )
        )


        if not time_text.startswith(
            target_prefix
        ):
            continue


        result[
            "date_found"
        ] = True


        result[
            "measurement_time"
        ] = time_text


        cushion_element = (
            unit.select_one(
                ".cushion"
            )
        )


        if cushion_element is None:
            continue


        value = to_float(
            cushion_element.get_text(
                " ",
                strip=True
            )
        )


        if (
            value is not None
            and 5.0 <= value <= 15.0
        ):

            result[
                "value"
            ] = value

            result[
                "found"
            ] = True


        break


    return result


# ============================================================
# JRA取得
# ============================================================

moist_html = ""
cushion_html = ""


try:

    moist_html = get_html(
        JRA_MOIST_URL
    )

    print(
        "moist page: OK",
        len(
            moist_html
        ),
        "bytes"
    )

except Exception as exc:

    print(
        "WARNING: moist page:",
        str(exc)
    )


# 芝の時だけクッション値が必要
if surface == "芝":

    try:

        cushion_html = get_html(
            JRA_CUSHION_URL
        )

        print(
            "cushion page: OK",
            len(
                cushion_html
            ),
            "bytes"
        )

    except Exception as exc:

        print(
            "WARNING: cushion page:",
            str(exc)
        )

else:

    print(
        "cushion page: skipped for dirt"
    )


print()


# ============================================================
# 含水率抽出
# ============================================================

moisture = extract_moisture(
    moist_html,
    track,
    race_date_obj,
    surface
)


# ============================================================
# クッション値抽出
# ============================================================

if surface == "芝":

    cushion = extract_cushion(
        cushion_html,
        track,
        race_date_obj
    )

else:

    cushion = {
        "found": False,
        "track_found": False,
        "date_found": False,
        "measurement_time": "",
        "value": None,
        "track_block_id": "",
    }


# ============================================================
# 適用値
# ============================================================

moisture_finish = (
    moisture.get(
        "finish"
    )
)


moisture_4corner = (
    moisture.get(
        "four_corner"
    )
)


if surface == "芝":

    cushion_value = (
        cushion.get(
            "value"
        )
    )

else:

    # ダートでは絶対にクッション値を評価しない
    cushion_value = None


# ============================================================
# 既存の人手入力バイアス保持
#
# race_id一致時のみ。
# ============================================================

old = load_json(
    OUTPUT_FILE
)


same_race = (
    clean_text(
        old.get(
            "race_id"
        )
    )
    == race_id
)


if same_race:

    time_bias = clean_text(
        old.get(
            "time_bias"
        )
    )

    inside_outside_bias = clean_text(
        old.get(
            "inside_outside_bias"
        )
    )

    running_style_bias = clean_text(
        old.get(
            "running_style_bias"
        )
    )

    reference_race_count = (
        old.get(
            "reference_race_count"
        )
        or 0
    )

    memo = clean_text(
        old.get(
            "memo"
        )
    )

else:

    time_bias = ""
    inside_outside_bias = ""
    running_style_bias = ""

    reference_race_count = 0

    memo = ""


# ============================================================
# データ有効性
# ============================================================

if surface == "芝":

    physical_data_available = any(
        [
            cushion_value
            is not None,

            moisture_finish
            is not None,

            moisture_4corner
            is not None,

            bool(
                race_track_condition
            ),
        ]
    )

else:

    physical_data_available = any(
        [
            moisture_finish
            is not None,

            moisture_4corner
            is not None,

            bool(
                race_track_condition
            ),
        ]
    )


bias_data_available = any(
    [
        bool(
            time_bias
        ),

        bool(
            inside_outside_bias
        ),

        bool(
            running_style_bias
        ),

        reference_race_count > 0,
    ]
)


data_available = (
    physical_data_available
    or bias_data_available
)


# ============================================================
# 保存
# ============================================================

output = {
    "race_id": race_id,

    "race_date": (
        race_date_obj.isoformat()
    ),

    "track": track,
    "racecourse": track,

    "surface": surface,
    "distance": distance,

    "track_condition": (
        race_track_condition
    ),

    # --------------------------------------------------------
    # クッション
    # --------------------------------------------------------

    "cushion_value": (
        cushion_value
    ),

    "cushion_measurement_time": (
        cushion.get(
            "measurement_time",
            ""
        )
        if surface == "芝"
        else ""
    ),

    "cushion_track_found": (
        cushion.get(
            "track_found",
            False
        )
    ),

    "cushion_date_found": (
        cushion.get(
            "date_found",
            False
        )
    ),

    "cushion_fetch_found": (
        cushion.get(
            "found",
            False
        )
    ),

    # --------------------------------------------------------
    # 含水率
    # --------------------------------------------------------

    "moisture_finish": (
        moisture_finish
    ),

    "moisture_4corner": (
        moisture_4corner
    ),

    "moisture_measurement_time": (
        moisture.get(
            "measurement_time",
            ""
        )
    ),

    "moisture_track_found": (
        moisture.get(
            "track_found",
            False
        )
    ),

    "moisture_date_found": (
        moisture.get(
            "date_found",
            False
        )
    ),

    "moisture_fetch_found": (
        moisture.get(
            "found",
            False
        )
    ),

    "moisture_track_block_id": (
        moisture.get(
            "track_block_id",
            ""
        )
    ),

    # --------------------------------------------------------
    # 当日バイアス
    # --------------------------------------------------------

    "time_bias": (
        time_bias
    ),

    "inside_outside_bias": (
        inside_outside_bias
    ),

    "running_style_bias": (
        running_style_bias
    ),

    "reference_race_count": (
        reference_race_count
    ),

    # --------------------------------------------------------
    # 接続状態
    # --------------------------------------------------------

    "physical_data_available": (
        physical_data_available
    ),

    "bias_data_available": (
        bias_data_available
    ),

    "data_available": (
        data_available
    ),

    # --------------------------------------------------------
    # ソース
    # --------------------------------------------------------

    "source": "JRA",

    "source_url": (
        JRA_BABA_PAGE
    ),

    "cushion_source_url": (
        JRA_CUSHION_URL
    ),

    "moisture_source_url": (
        JRA_MOIST_URL
    ),

    "surface_rule": (
        "芝はクッション値・含水率を条件情報として使用。"
        "ダートはクッション値を使用せず含水率のみ使用。"
        "対象競馬場かつ対象日付のunitと一致した値だけ採用。"
    ),

    "memo": (
        memo
    ),

    "updated_at": (
        now_jst()
    ),
}


save_json(
    OUTPUT_FILE,
    output
)


# ============================================================
# ログ
# ============================================================

print()
print(
    "===== TRACK CONDITION RESULT ====="
)

print(
    "race id:",
    race_id
)

print(
    "race date:",
    race_date_obj.isoformat()
)

print(
    "track:",
    track
)

print(
    "surface:",
    surface
)

print(
    "condition:",
    race_track_condition
)


print()
print(
    "----- MOISTURE MATCH -----"
)

print(
    "track found:",
    moisture.get(
        "track_found"
    )
)

print(
    "track block id:",
    moisture.get(
        "track_block_id"
    )
)

print(
    "date found:",
    moisture.get(
        "date_found"
    )
)

print(
    "measurement time:",
    moisture.get(
        "measurement_time"
    )
)

print(
    "moisture finish:",
    moisture_finish
)

print(
    "moisture 4corner:",
    moisture_4corner
)

print(
    "moisture fetch found:",
    moisture.get(
        "found"
    )
)


print()
print(
    "----- CUSHION MATCH -----"
)

if surface == "芝":

    print(
        "track found:",
        cushion.get(
            "track_found"
        )
    )

    print(
        "date found:",
        cushion.get(
            "date_found"
        )
    )

    print(
        "measurement time:",
        cushion.get(
            "measurement_time"
        )
    )

    print(
        "cushion:",
        cushion_value
    )

else:

    print(
        "not used for dirt"
    )


print()
print(
    "----- AVAILABILITY -----"
)

print(
    "physical data:",
    physical_data_available
)

print(
    "bias data:",
    bias_data_available
)

print(
    "data available:",
    data_available
)

print(
    "saved:",
    OUTPUT_FILE
)

print(
    "=================================="
)
