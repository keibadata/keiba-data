import json
import os
import re
from datetime import datetime, timezone, timedelta
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup


RACE_FILE = "race.json"
OUTPUT_FILE = "track_condition.json"

JRA_BASE = "https://www.jra.go.jp"
JRA_BABA_PAGE = "https://www.jra.go.jp/keiba/baba/index.html"

TIMEOUT = 20

JST = timezone(timedelta(hours=9))


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(JST).isoformat(timespec="seconds")


def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
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

    s = clean_text(value)

    if not s:
        return None

    m = re.search(r"-?\d+(?:\.\d+)?", s)

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def get_html(url):
    headers = {
        "User-Agent": (
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": (
            "text/html,application/xhtml+xml,"
            "application/xml;q=0.9,*/*;q=0.8"
        ),
        "Accept-Language": "ja,en-US;q=0.8,en;q=0.6",
        "Referer": JRA_BABA_PAGE,
    }

    r = requests.get(
        url,
        headers=headers,
        timeout=TIMEOUT
    )

    r.raise_for_status()

    # JRAページはShift_JIS系の場合がある
    if not r.encoding or r.encoding.lower() in [
        "iso-8859-1",
        "ascii"
    ]:
        r.encoding = r.apparent_encoding

    return r.text


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
    value = clean_text(value)

    for track, aliases in TRACK_ALIASES.items():
        for alias in aliases:
            if alias in value:
                return track

    return value


# ============================================================
# JRAの競馬場ID候補
#
# JRAで一般的に使われる競馬場コード
# ============================================================

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


# ============================================================
# race.json
# ============================================================

race = load_json(RACE_FILE)

if not race:
    raise SystemExit(
        "ERROR: race.json がありません"
    )


race_id = clean_text(
    race.get("race_id")
)

race_date = clean_text(
    race.get("race_date")
    or race.get("date")
)

track = normalize_track(
    race.get("track")
    or race.get("racecourse")
)

surface = clean_text(
    race.get("surface")
)

distance = race.get("distance")

race_track_condition = clean_text(
    race.get("track_condition")
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
print("===== JRA TRACK CONDITION =====")
print("race id:", race_id)
print("date:", race_date)
print("track:", track)
print("surface:", surface)
print("distance:", distance)
print()


# ============================================================
# index.htmlから実データURLを確認
# ============================================================

try:
    index_html = get_html(JRA_BABA_PAGE)
except Exception as e:
    index_html = ""
    print(
        "WARNING: JRA馬場情報ページ取得失敗:",
        str(e)
    )


index_soup = BeautifulSoup(
    index_html,
    "html.parser"
)


# JSで確認できたパスを基本とする
cushion_url = urljoin(
    JRA_BABA_PAGE,
    "_data_cushion.html"
)

moisture_url = urljoin(
    JRA_BABA_PAGE,
    "_data_moisture.html"
)


print("cushion url:", cushion_url)
print("moisture url:", moisture_url)
print()


# ============================================================
# 対象競馬場ブロック探索
# ============================================================

def score_track_container(element, track_name):
    if element is None:
        return -1

    text = clean_text(
        element.get_text(" ", strip=True)
    )

    score = 0

    if track_name in text:
        score += 10

    element_id = clean_text(
        element.get("id")
    ).lower()

    classes = " ".join(
        element.get("class", [])
    ).lower()

    for code in TRACK_CODES.get(
        track_name,
        []
    ):
        code_lower = code.lower()

        if code_lower == element_id:
            score += 20

        if code_lower in element_id:
            score += 8

        if code_lower in classes:
            score += 5

    return score


def find_track_block(soup, track_name):
    if soup is None:
        return None

    candidates = []

    for tag in soup.find_all(
        ["div", "section", "li", "article", "tbody"]
    ):
        text = clean_text(
            tag.get_text(" ", strip=True)
        )

        if track_name not in text:
            continue

        score = score_track_container(
            tag,
            track_name
        )

        # 大きすぎる親要素を避ける
        length = len(text)

        if length > 5000:
            score -= 10
        elif length < 2000:
            score += 3

        candidates.append(
            (
                score,
                length,
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

    # id直接探索
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
# クッション値
# ============================================================

def extract_cushion(html, track_name):
    if not html:
        return {
            "value": None,
            "time": "",
            "found": False,
            "count": 0
        }

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    block = find_track_block(
        soup,
        track_name
    )

    search_root = block or soup

    units = search_root.select(
        ".unit"
    )

    results = []

    for unit in units:
        cushion_el = unit.select_one(
            ".cushion"
        )

        if not cushion_el:
            continue

        value = to_float(
            cushion_el.get_text(
                " ",
                strip=True
            )
        )

        if value is None:
            continue

        # クッション値として妥当な範囲
        if not 5.0 <= value <= 15.0:
            continue

        time_el = unit.select_one(
            ".time"
        )

        time_text = ""

        if time_el:
            time_text = clean_text(
                time_el.get_text(
                    " ",
                    strip=True
                )
            )

        results.append(
            {
                "value": value,
                "time": time_text
            }
        )

    # .unit構造で見つからない場合
    if not results:
        for cushion_el in search_root.select(
            ".cushion"
        ):
            value = to_float(
                cushion_el.get_text(
                    " ",
                    strip=True
                )
            )

            if value is None:
                continue

            if not 5.0 <= value <= 15.0:
                continue

            parent = cushion_el.parent

            time_text = ""

            if parent:
                time_el = parent.select_one(
                    ".time"
                )

                if time_el:
                    time_text = clean_text(
                        time_el.get_text(
                            " ",
                            strip=True
                        )
                    )

            results.append(
                {
                    "value": value,
                    "time": time_text
                }
            )

    if not results:
        return {
            "value": None,
            "time": "",
            "found": False,
            "count": 0
        }

    # JRAの配列順を維持し、最後を最新候補とする
    latest = results[-1]

    return {
        "value": latest["value"],
        "time": latest["time"],
        "found": True,
        "count": len(results),
        "all": results
    }


# ============================================================
# 含水率
# ============================================================

def extract_moisture(html, track_name, surface_name):
    if not html:
        return {
            "finish": None,
            "four_corner": None,
            "found": False
        }

    soup = BeautifulSoup(
        html,
        "html.parser"
    )

    block = find_track_block(
        soup,
        track_name
    )

    search_root = block or soup

    text = clean_text(
        search_root.get_text(
            " ",
            strip=True
        )
    )

    result = {
        "finish": None,
        "four_corner": None,
        "found": False
    }

    # --------------------------------------------------------
    # テーブル構造から探す
    # --------------------------------------------------------

    for row in search_root.find_all(
        ["tr", "li", "div"]
    ):
        row_text = clean_text(
            row.get_text(
                " ",
                strip=True
            )
        )

        if not row_text:
            continue

        if (
            "ゴール前" not in row_text
            and "4コーナー" not in row_text
        ):
            continue

        # 対象馬場を優先
        if surface_name == "ダート":
            if (
                "芝" in row_text
                and "ダート" not in row_text
            ):
                continue

        if surface_name == "芝":
            if (
                "ダート" in row_text
                and "芝" not in row_text
            ):
                continue

        numbers = [
            float(x)
            for x in re.findall(
                r"\d+(?:\.\d+)?",
                row_text
            )
        ]

        plausible = [
            x for x in numbers
            if 0.0 <= x <= 30.0
        ]

        if len(plausible) >= 2:
            result["finish"] = plausible[-2]
            result["four_corner"] = plausible[-1]
            result["found"] = True

    if result["found"]:
        return result

    # --------------------------------------------------------
    # JRA表示テキスト形式
    #
    # 例:
    # 芝 14.0 12.7 ダート 2.1 2.2
    # --------------------------------------------------------

    pattern = re.compile(
        r"芝\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"(\d+(?:\.\d+)?)"
        r".{0,80}?"
        r"ダート\s*"
        r"(\d+(?:\.\d+)?)\s*"
        r"(\d+(?:\.\d+)?)"
    )

    matches = list(
        pattern.finditer(text)
    )

    if matches:
        m = matches[-1]

        turf_finish = float(
            m.group(1)
        )

        turf_four = float(
            m.group(2)
        )

        dirt_finish = float(
            m.group(3)
        )

        dirt_four = float(
            m.group(4)
        )

        if surface_name == "ダート":
            result["finish"] = dirt_finish
            result["four_corner"] = dirt_four
        else:
            result["finish"] = turf_finish
            result["four_corner"] = turf_four

        result["found"] = True

    return result


# ============================================================
# データ取得
# ============================================================

cushion_html = ""
moisture_html = ""

try:
    cushion_html = get_html(
        cushion_url
    )

    print(
        "cushion page: OK",
        len(cushion_html),
        "bytes"
    )

except Exception as e:
    print(
        "WARNING: cushion page:",
        str(e)
    )


try:
    moisture_html = get_html(
        moisture_url
    )

    print(
        "moisture page: OK",
        len(moisture_html),
        "bytes"
    )

except Exception as e:
    print(
        "WARNING: moisture page:",
        str(e)
    )


print()


cushion = extract_cushion(
    cushion_html,
    track
)

moisture = extract_moisture(
    moisture_html,
    track,
    surface
)


# ============================================================
# 芝・ダート別処理
# ============================================================

if surface == "芝":
    cushion_value = cushion.get(
        "value"
    )
else:
    # ダート評価にクッション値を混ぜない
    cushion_value = None


moisture_finish = moisture.get(
    "finish"
)

moisture_4corner = moisture.get(
    "four_corner"
)


# ============================================================
# 既存ファイル
#
# 同一race_idの人手入力バイアスだけ保持可能
# ============================================================

old = load_json(
    OUTPUT_FILE
)

same_race = (
    clean_text(
        old.get("race_id")
    )
    == race_id
)


if same_race:
    time_bias = clean_text(
        old.get("time_bias")
    )

    inside_outside_bias = clean_text(
        old.get("inside_outside_bias")
    )

    running_style_bias = clean_text(
        old.get("running_style_bias")
    )

    reference_race_count = (
        old.get(
            "reference_race_count"
        )
        or 0
    )

    memo = clean_text(
        old.get("memo")
    )

else:
    time_bias = ""
    inside_outside_bias = ""
    running_style_bias = ""
    reference_race_count = 0
    memo = ""


# ============================================================
# data_available
# ============================================================

if surface == "芝":
    physical_data_available = (
        cushion_value is not None
        or moisture_finish is not None
        or moisture_4corner is not None
        or bool(race_track_condition)
    )
else:
    physical_data_available = (
        moisture_finish is not None
        or moisture_4corner is not None
        or bool(race_track_condition)
    )


bias_data_available = any(
    [
        bool(time_bias),
        bool(inside_outside_bias),
        bool(running_style_bias),
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

    "track_condition": race_track_condition,

    "cushion_value": cushion_value,
    "cushion_measurement_time": (
        cushion.get("time", "")
        if surface == "芝"
        else ""
    ),

    "moisture_4corner": moisture_4corner,
    "moisture_finish": moisture_finish,

    "time_bias": time_bias,
    "inside_outside_bias": inside_outside_bias,
    "running_style_bias": running_style_bias,

    "reference_race_count": reference_race_count,

    "data_available": data_available,

    "physical_data_available": physical_data_available,
    "bias_data_available": bias_data_available,

    "source": "JRA",
    "source_url": JRA_BABA_PAGE,

    "cushion_source_url": cushion_url,
    "moisture_source_url": moisture_url,

    "cushion_fetch_found": cushion.get(
        "found",
        False
    ),

    "moisture_fetch_found": moisture.get(
        "found",
        False
    ),

    "surface_rule": (
        "芝: クッション値+含水率を取得。"
        "ダート: クッション値は評価に使用せず含水率を使用。"
    ),

    "memo": memo,

    "updated_at": now_jst()
}


save_json(
    OUTPUT_FILE,
    output
)


# ============================================================
# ログ
# ============================================================

print()
print("===== TRACK CONDITION RESULT =====")

print(
    "race id:",
    race_id
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

print(
    "cushion:",
    cushion_value
)

print(
    "cushion time:",
    (
        cushion.get("time", "")
        if surface == "芝"
        else "not used for dirt"
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

print("==================================")
