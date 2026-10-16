import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
OUTPUT_FILE = "track_condition.json"

JRA_BABA_PAGE = "https://www.jra.go.jp/keiba/baba/index.html"

CUSHION_URL = urljoin(
    JRA_BABA_PAGE,
    "_data_cushion.html"
)

MOIST_URL = urljoin(
    JRA_BABA_PAGE,
    "_data_moist.html"
)

TIMEOUT = 20

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


def normalize_date(value):

    value = clean_text(
        value
    )

    if not value:
        return ""

    value = value.replace(
        "/",
        "-"
    )

    match = re.search(
        r"(\d{4})-(\d{1,2})-(\d{1,2})",
        value
    )

    if not match:
        return ""

    return (
        f"{int(match.group(1)):04d}-"
        f"{int(match.group(2)):02d}-"
        f"{int(match.group(3)):02d}"
    )


# ============================================================
# HTTP
# ============================================================

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


TRACK_CODES = {
    "札幌": ["01", "sapporo"],
    "函館": ["02", "hakodate"],
    "福島": ["03", "fukushima"],
    "新潟": ["04", "niigata"],
    "東京": ["05", "tokyo"],
    "中山": ["06", "nakayama"],
    "中京": ["07", "chukyo"],
    "京都": ["08", "kyoto"],
    "阪神": ["09", "hanshin"],
    "小倉": ["10", "kokura"],
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


race_date = normalize_date(
    race.get("race_date")
    or race.get("date")
)


track = normalize_track(
    race.get("track")
    or race.get("racecourse")
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


if not track:

    raise SystemExit(
        "ERROR: 競馬場がありません"
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
    race_date
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

print(
    "cushion url:",
    CUSHION_URL
)

print(
    "moist url:",
    MOIST_URL
)

print()


# ============================================================
# 対象競馬場ブロック
# ============================================================

def score_track_container(
    element,
    track_name
):

    if element is None:
        return -1

    text = clean_text(
        element.get_text(
            " ",
            strip=True
        )
    )

    score = 0


    if track_name in text:
        score += 20


    element_id = clean_text(
        element.get(
            "id"
        )
    ).lower()


    classes = " ".join(
        element.get(
            "class",
            []
        )
    ).lower()


    for code in TRACK_CODES.get(
        track_name,
        []
    ):

        code = code.lower()

        if element_id == code:
            score += 50

        elif code in element_id:
            score += 20

        if code in classes:
            score += 10


    length = len(
        text
    )


    if length > 8000:
        score -= 20

    elif length < 3000:
        score += 5


    return score


def find_track_block(
    soup,
    track_name
):

    candidates = []


    for tag in soup.find_all(
        [
            "div",
            "section",
            "li",
            "article",
            "tbody"
        ]
    ):

        text = clean_text(
            tag.get_text(
                " ",
                strip=True
            )
        )


        if track_name not in text:
            continue


        score = score_track_container(
            tag,
            track_name
        )


        candidates.append(
            (
                score,
                len(text),
                tag
            )
        )


    if candidates:

        candidates.sort(
            key=lambda x: (
                x[0],
                -x[1]
            ),
            reverse=True
        )

        return candidates[0][2]


    for code in TRACK_CODES.get(
        track_name,
        []
    ):

        tag = soup.find(
            id=re.compile(
                re.escape(code),
                re.I
            )
        )

        if tag:
            return tag


    return None


# ============================================================
# 日付情報抽出
# ============================================================

def extract_dates(text):

    results = []


    patterns = [

        r"(\d{4})[年/\-]"
        r"(\d{1,2})[月/\-]"
        r"(\d{1,2})日?",

        r"(\d{1,2})月"
        r"(\d{1,2})日",

    ]


    for index, pattern in enumerate(
        patterns
    ):

        for match in re.finditer(
            pattern,
            text
        ):

            try:

                if index == 0:

                    year = int(
                        match.group(1)
                    )

                    month = int(
                        match.group(2)
                    )

                    day = int(
                        match.group(3)
                    )

                else:

                    year = datetime.now(
                        JST
                    ).year

                    month = int(
                        match.group(1)
                    )

                    day = int(
                        match.group(2)
                    )


                value = (
                    f"{year:04d}-"
                    f"{month:02d}-"
                    f"{day:02d}"
                )


                if value not in results:
                    results.append(
                        value
                    )

            except Exception:

                pass


    return results


# ============================================================
# クッション値
# ============================================================

def extract_cushion(
    html,
    track_name
):

    result = {
        "value": None,
        "time": "",
        "found": False,
        "dates": [],
        "count": 0
    }


    if not html:
        return result


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    block = find_track_block(
        soup,
        track_name
    )


    root = (
        block
        if block is not None
        else soup
    )


    block_text = clean_text(
        root.get_text(
            " ",
            strip=True
        )
    )


    result["dates"] = extract_dates(
        block_text
    )


    values = []


    for unit in root.select(
        ".unit"
    ):

        cushion_element = unit.select_one(
            ".cushion"
        )


        if cushion_element is None:
            continue


        value = to_float(
            cushion_element.get_text(
                " ",
                strip=True
            )
        )


        if value is None:
            continue


        if not 5.0 <= value <= 15.0:
            continue


        time_element = unit.select_one(
            ".time"
        )


        time_text = ""


        if time_element is not None:

            time_text = clean_text(
                time_element.get_text(
                    " ",
                    strip=True
                )
            )


        values.append(
            {
                "value": value,
                "time": time_text
            }
        )


    if values:

        latest = values[-1]

        result["value"] = latest[
            "value"
        ]

        result["time"] = latest[
            "time"
        ]

        result["found"] = True

        result["count"] = len(
            values
        )

        result["all"] = values


    return result


# ============================================================
# 含水率
#
# JRA baba2025.js:
# _data_moist.html
#
# _moist_data:
# {
#   time: ...,
#   turf: ...,
#   dirt: ...
# }
#
# g  = ゴール前
# 4c = 4コーナー
# ============================================================

def extract_surface_pair(
    element
):

    if element is None:
        return None


    # --------------------------------------
    # class="gm" / class="c4"
    # --------------------------------------

    gm = element.select_one(
        ".gm"
    )

    c4 = element.select_one(
        ".c4"
    )


    if (
        gm is not None
        and c4 is not None
    ):

        finish = to_float(
            gm.get_text(
                " ",
                strip=True
            )
        )

        four_corner = to_float(
            c4.get_text(
                " ",
                strip=True
            )
        )


        if (
            finish is not None
            or four_corner is not None
        ):

            return {
                "finish": finish,
                "four_corner": four_corner
            }


    return None


def extract_moisture(
    html,
    track_name,
    surface_name
):

    result = {
        "finish": None,
        "four_corner": None,
        "time": "",
        "found": False,
        "dates": [],
        "records": []
    }


    if not html:
        return result


    soup = BeautifulSoup(
        html,
        "html.parser"
    )


    block = find_track_block(
        soup,
        track_name
    )


    root = (
        block
        if block is not None
        else soup
    )


    root_text = clean_text(
        root.get_text(
            " ",
            strip=True
        )
    )


    result["dates"] = extract_dates(
        root_text
    )


    # ========================================================
    # 1. JRA表示用IDを直接探索
    # ========================================================

    target_id = (
        "dirt_line"
        if surface_name == "ダート"
        else "turf_line"
    )


    line = root.find(
        id=target_id
    )


    pair = extract_surface_pair(
        line
    )


    if pair:

        result["finish"] = pair[
            "finish"
        ]

        result["four_corner"] = pair[
            "four_corner"
        ]

        result["found"] = True

        return result


    # ========================================================
    # 2. HTML内のデータ属性・クラス探索
    # ========================================================

    surface_word = (
        "ダート"
        if surface_name == "ダート"
        else "芝"
    )


    candidates = []


    for tag in root.find_all(
        [
            "tr",
            "li",
            "div"
        ]
    ):

        text = clean_text(
            tag.get_text(
                " ",
                strip=True
            )
        )


        if surface_word not in text:
            continue


        gm = tag.select_one(
            ".gm"
        )

        c4 = tag.select_one(
            ".c4"
        )


        if (
            gm is None
            or c4 is None
        ):
            continue


        finish = to_float(
            gm.get_text(
                " ",
                strip=True
            )
        )

        four_corner = to_float(
            c4.get_text(
                " ",
                strip=True
            )
        )


        if (
            finish is None
            and four_corner is None
        ):
            continue


        candidates.append(
            {
                "finish": finish,
                "four_corner": four_corner,
                "text": text
            }
        )


    if candidates:

        latest = candidates[-1]

        result["finish"] = latest[
            "finish"
        ]

        result["four_corner"] = latest[
            "four_corner"
        ]

        result["found"] = True

        result["records"] = candidates

        return result


    # ========================================================
    # 3. JRAデータHTMLをテキストとして解析
    #
    # JSが読む
    # turf / dirt / g / 4c
    # を直接確認する
    # ========================================================

    patterns = []


    if surface_name == "ダート":

        patterns = [

            re.compile(
                r"dirt"
                r".{0,500}?"
                r"""(?:class=["']?g["']?|["']g["'])"""
                r".{0,100}?"
                r"(\d+(?:\.\d+)?)"
                r".{0,500}?"
                r"""(?:class=["']?4c["']?|["']4c["'])"""
                r".{0,100}?"
                r"(\d+(?:\.\d+)?)",
                re.I | re.S
            ),

        ]

    else:

        patterns = [

            re.compile(
                r"turf"
                r".{0,500}?"
                r"""(?:class=["']?g["']?|["']g["'])"""
                r".{0,100}?"
                r"(\d+(?:\.\d+)?)"
                r".{0,500}?"
                r"""(?:class=["']?4c["']?|["']4c["'])"""
                r".{0,100}?"
                r"(\d+(?:\.\d+)?)",
                re.I | re.S
            ),

        ]


    for pattern in patterns:

        matches = list(
            pattern.finditer(
                html
            )
        )


        if not matches:
            continue


        match = matches[-1]


        finish = to_float(
            match.group(1)
        )

        four_corner = to_float(
            match.group(2)
        )


        if (
            finish is not None
            or four_corner is not None
        ):

            result["finish"] = finish

            result["four_corner"] = (
                four_corner
            )

            result["found"] = True

            return result


    return result


# ============================================================
# JRA取得
# ============================================================

cushion_html = ""
moist_html = ""


try:

    cushion_html = get_html(
        CUSHION_URL
    )

    print(
        "cushion page: OK",
        len(cushion_html),
        "bytes"
    )

except Exception as exc:

    print(
        "WARNING: cushion page:",
        str(exc)
    )


try:

    moist_html = get_html(
        MOIST_URL
    )

    print(
        "moist page: OK",
        len(moist_html),
        "bytes"
    )

except Exception as exc:

    print(
        "WARNING: moist page:",
        str(exc)
    )


print()


# ============================================================
# 抽出
# ============================================================

cushion = extract_cushion(
    cushion_html,
    track
)


moisture = extract_moisture(
    moist_html,
    track,
    surface
)


# ============================================================
# 日付安全チェック
# ============================================================

source_dates = []


for value in (
    cushion.get(
        "dates",
        []
    )
    + moisture.get(
        "dates",
        []
    )
):

    if value not in source_dates:
        source_dates.append(
            value
        )


today = datetime.now(
    JST
).strftime(
    "%Y-%m-%d"
)


race_is_today = (
    bool(race_date)
    and race_date == today
)


date_verified = (
    bool(race_date)
    and race_date in source_dates
)


# JRA側HTMLに日付が存在しない場合でも、
# 当日レースなら現在ページを使用可能。
current_page_safe = (
    date_verified
    or (
        race_is_today
        and not source_dates
    )
)


# ============================================================
# 値
# ============================================================

raw_cushion_value = cushion.get(
    "value"
)


raw_moisture_finish = moisture.get(
    "finish"
)


raw_moisture_4corner = moisture.get(
    "four_corner"
)


# ============================================================
# 実際に解析へ使用する値
# ============================================================

if (
    surface == "芝"
    and current_page_safe
):

    cushion_value = (
        raw_cushion_value
    )

else:

    cushion_value = None


if current_page_safe:

    moisture_finish = (
        raw_moisture_finish
    )

    moisture_4corner = (
        raw_moisture_4corner
    )

else:

    moisture_finish = None

    moisture_4corner = None


# ============================================================
# 既存ファイル
#
# race_idだけでなく
# 競馬場・馬場種別も一致した場合だけ
# 人手入力バイアスを保持
# ============================================================

old = load_json(
    OUTPUT_FILE
)


same_context = (

    clean_text(
        old.get(
            "race_id"
        )
    )
    == race_id

    and

    normalize_track(
        old.get("track")
        or old.get("racecourse")
    )
    == track

    and

    clean_text(
        old.get(
            "surface"
        )
    )
    == surface
)


if same_context:

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
# 利用可能判定
# ============================================================

if surface == "芝":

    physical_data_available = any(
        [
            cushion_value is not None,
            moisture_finish is not None,
            moisture_4corner is not None,
            bool(
                race_track_condition
            )
        ]
    )

else:

    physical_data_available = any(
        [
            moisture_finish is not None,
            moisture_4corner is not None,
            bool(
                race_track_condition
            )
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
        reference_race_count > 0
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

    "race_date": race_date,

    "track": track,

    "racecourse": track,

    "surface": surface,

    "distance": distance,

    "track_condition": (
        race_track_condition
    ),

    # --------------------------------------------------------
    # 解析に使用可能な値
    # --------------------------------------------------------

    "cushion_value": (
        cushion_value
    ),

    "cushion_measurement_time": (
        cushion.get(
            "time",
            ""
        )
        if (
            surface == "芝"
            and current_page_safe
        )
        else ""
    ),

    "moisture_finish": (
        moisture_finish
    ),

    "moisture_4corner": (
        moisture_4corner
    ),

    # --------------------------------------------------------
    # JRAから取得した生値
    #
    # 日付不一致時は解析には使わない
    # --------------------------------------------------------

    "raw_jra": {

        "cushion_value": (
            raw_cushion_value
        ),

        "cushion_time": (
            cushion.get(
                "time",
                ""
            )
        ),

        "moisture_finish": (
            raw_moisture_finish
        ),

        "moisture_4corner": (
            raw_moisture_4corner
        ),

        "source_dates": (
            source_dates
        ),

    },

    # --------------------------------------------------------
    # 日付検証
    # --------------------------------------------------------

    "source_date_verified": (
        date_verified
    ),

    "race_is_today": (
        race_is_today
    ),

    "current_page_safe": (
        current_page_safe
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
    # 状態
    # --------------------------------------------------------

    "data_available": (
        data_available
    ),

    "physical_data_available": (
        physical_data_available
    ),

    "bias_data_available": (
        bias_data_available
    ),

    # --------------------------------------------------------
    # 取得状態
    # --------------------------------------------------------

    "cushion_fetch_found": (
        cushion.get(
            "found",
            False
        )
    ),

    "moisture_fetch_found": (
        moisture.get(
            "found",
            False
        )
    ),

    # --------------------------------------------------------
    # Source
    # --------------------------------------------------------

    "source": "JRA",

    "source_url": (
        JRA_BABA_PAGE
    ),

    "cushion_source_url": (
        CUSHION_URL
    ),

    "moisture_source_url": (
        MOIST_URL
    ),

    # --------------------------------------------------------
    # ルール
    # --------------------------------------------------------

    "surface_rule": (
        "芝はクッション値・含水率を条件情報として扱う。"
        "ダートではクッション値を使用せず含水率を扱う。"
        "クッション値・含水率は単独加点しない。"
    ),

    "date_safety_rule": (
        "JRA現在ページのデータは対象日との一致を確認できる場合、"
        "または対象レースが当日でページ側に日付情報が無い場合のみ"
        "解析値として使用する。"
        "過去レースに現在値を流用しない。"
    ),

    "memo": (
        memo
    ),

    "updated_at": (
        now_jst()
    )
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
    race_date
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
    "JRA source dates:",
    source_dates
)

print(
    "race is today:",
    race_is_today
)

print(
    "source date verified:",
    date_verified
)

print(
    "current page safe:",
    current_page_safe
)

print()

print(
    "raw cushion:",
    raw_cushion_value
)

print(
    "raw moisture finish:",
    raw_moisture_finish
)

print(
    "raw moisture 4corner:",
    raw_moisture_4corner
)

print()

print(
    "applied cushion:",
    cushion_value
)

print(
    "applied moisture finish:",
    moisture_finish
)

print(
    "applied moisture 4corner:",
    moisture_4corner
)

print()

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
