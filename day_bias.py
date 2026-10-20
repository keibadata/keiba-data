import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
TRACK_FILE = "track_condition.json"
DAY_RACES_FILE = "day_races.json"
DAY_TIME_HISTORY_FILE = "day_time_history.json"
OUTPUT_FILE = "day_bias.json"

JST = timezone(timedelta(hours=9))

# robust z-score:
# 0.6745 * (x - median) / MAD
# と同値の
# (x - median) / (1.4826 * MAD)
MAD_SCALE = 1.4826

# 時計バイアス判定
TIME_STRONG_THRESHOLD = 1.50
TIME_MILD_THRESHOLD = 0.75

# MADが極端に小さい場合の暴走防止。
# MAD自体は保存値を使うが、標準化時の分母だけ下限を置く。
MIN_SCALED_DISPERSION_SECONDS = 0.20


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


def normalize_surface(value):
    value = clean_text(value)

    if value.startswith("芝"):
        return "芝"

    if (
        value.startswith("ダ")
        or "ダート" in value
    ):
        return "ダート"

    if value.startswith("障"):
        return "障害"

    return value


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# ============================================================
# race_idからR番号
# ============================================================

def get_race_number(race_id):
    race_id = clean_text(race_id)

    if not re.fullmatch(r"\d{12}", race_id):
        return None

    try:
        race_no = int(race_id[-2:])
    except ValueError:
        return None

    if not 1 <= race_no <= 12:
        return None

    return race_no


# ============================================================
# コーナー処理
# ============================================================

def normalize_corner_text(value):
    text = clean_text(value)

    if not text:
        return ""

    text = text.replace("（", "(")
    text = text.replace("）", ")")
    text = text.replace("，", ",")
    text = re.sub(r"\s+", "", text)

    return text


def parse_corner_order(value):
    text = normalize_corner_text(value)

    if not text:
        return []

    numbers = re.findall(r"\d+", text)

    order = []
    seen = set()

    for number in numbers:
        try:
            horse_number = int(number)
        except ValueError:
            continue

        if not 1 <= horse_number <= 18:
            continue

        if horse_number in seen:
            continue

        seen.add(horse_number)
        order.append(horse_number)

    return order


def build_corner_position_map(value):
    order = parse_corner_order(value)

    output = {}

    for index, horse_number in enumerate(order, start=1):
        output[horse_number] = index

    return output


def select_reference_corner(corner_positions):
    if not isinstance(corner_positions, dict):
        return "", ""

    for corner_number in ["4", "3", "2", "1"]:
        value = clean_text(
            corner_positions.get(corner_number)
        )

        if value:
            return corner_number, value

    return "", ""


def classify_running_style(
    horse_number,
    position_map
):
    if horse_number is None:
        return ""

    if not position_map:
        return ""

    position = position_map.get(horse_number)

    if position is None:
        return ""

    field_size = len(position_map)

    if field_size <= 0:
        return ""

    if position == 1:
        return "逃げ"

    position_rate = position / field_size

    if position_rate <= 0.35:
        return "先行"

    if position_rate <= 0.70:
        return "中団"

    return "後方"


# ============================================================
# 時計バイアス
# ============================================================

def calculate_time_bias(
    day_time_history,
    target_race_id
):
    result = {
        "connected": False,
        "status": "not_connected",
        "time_bias": "",
        "score": None,
        "reference_count": 0,
        "scores": [],
        "reference_details": [],
        "reason": "",
    }

    if not day_time_history:
        result["status"] = "file_not_found"
        result["reason"] = (
            "day_time_history.json が存在しないため"
            "時計バイアスを判定しない。"
        )
        return result

    history_target_id = clean_text(
        day_time_history.get("target_race_id")
    )

    if history_target_id != target_race_id:
        raise SystemExit(
            "ERROR: day_time_history.json race_id mismatch"
        )

    if day_time_history.get("future_race_usage") is True:
        raise SystemExit(
            "ERROR: day_time_history.json に未来レース使用フラグがあります"
        )

    if day_time_history.get("leak_check_passed") is not True:
        raise SystemExit(
            "ERROR: day_time_history.json leak check failed"
        )

    if safe_int(
        day_time_history.get("error_count")
    ) not in (None, 0):
        result["status"] = "history_error"
        result["reason"] = (
            "day_time_history.json にエラーがあるため"
            "時計バイアスを判定しない。"
        )
        return result

    references = (
        day_time_history.get(
            "reference_races",
            []
        )
        or []
    )

    for ref in references:
        if not isinstance(ref, dict):
            continue

        if ref.get("baseline_connected") is not True:
            continue

        race_id = clean_text(
            ref.get("race_id")
        )

        race_number = safe_int(
            ref.get("race_number")
        )

        distance = safe_int(
            ref.get("distance")
        )

        sample_count = safe_int(
            ref.get("baseline_sample_count")
        )

        delta = safe_float(
            ref.get("time_delta_seconds")
        )

        mad = safe_float(
            ref.get("baseline_mad_seconds")
        )

        baseline_median = safe_float(
            ref.get("baseline_median_seconds")
        )

        actual = safe_float(
            ref.get("winner_time_seconds")
        )

        if sample_count is None or sample_count < 5:
            continue

        if delta is None:
            continue

        if mad is None or mad <= 0:
            continue

        scaled_dispersion = (
            MAD_SCALE * mad
        )

        # MADが極端に小さい時だけ、
        # 標準化スコアの暴走を防止する。
        denominator = max(
            scaled_dispersion,
            MIN_SCALED_DISPERSION_SECONDS
        )

        robust_z = (
            delta / denominator
        )

        robust_z = round(
            robust_z,
            3
        )

        result["scores"].append(
            robust_z
        )

        result["reference_details"].append({
            "race_id": race_id,
            "race_number": race_number,
            "distance": distance,
            "sample_count": sample_count,
            "actual_seconds": actual,
            "baseline_median_seconds": baseline_median,
            "mad_seconds": mad,
            "time_delta_seconds": delta,
            "scaled_dispersion_seconds": round(
                scaled_dispersion,
                4
            ),
            "robust_z": robust_z,
        })

    result["reference_count"] = len(
        result["scores"]
    )

    if not result["scores"]:
        result["status"] = "no_valid_baseline"
        result["reason"] = (
            "有効な基準時計サンプルがないため"
            "時計バイアスを判定しない。"
        )
        return result

    # 距離ごとの生秒差ではなく、
    # 各条件内で標準化した値の中央値を使う。
    combined_score = statistics.median(
        result["scores"]
    )

    combined_score = round(
        combined_score,
        3
    )

    result["score"] = combined_score
    result["connected"] = True
    result["status"] = "analyzed"

    if combined_score <= -TIME_STRONG_THRESHOLD:
        time_bias = "高速"

    elif combined_score <= -TIME_MILD_THRESHOLD:
        time_bias = "やや高速"

    elif combined_score >= TIME_STRONG_THRESHOLD:
        time_bias = "低速"

    elif combined_score >= TIME_MILD_THRESHOLD:
        time_bias = "やや低速"

    else:
        time_bias = "標準"

    result["time_bias"] = time_bias

    result["reason"] = (
        f"基準時計接続{result['reference_count']}件。"
        f"距離別の実測－基準中央値をMADで標準化し、"
        f"robust z-scoreの中央値"
        f"{combined_score}で判定。"
        f"異なる距離の生時計差は直接平均していない。"
    )

    return result


# ============================================================
# 入力
# ============================================================

race = load_json(RACE_FILE)
track_condition = load_json(TRACK_FILE)
day_races = load_json(DAY_RACES_FILE)
day_time_history = load_json(
    DAY_TIME_HISTORY_FILE
)

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

racecourse = clean_text(
    race.get("track")
    or race.get("racecourse")
)

surface = normalize_surface(
    race.get("surface")
)

distance = safe_int(
    race.get("distance")
)

race_no = get_race_number(
    race_id
)

if race_no is None:
    raise SystemExit(
        "ERROR: race_idからR番号を取得できません"
    )


# ============================================================
# track_condition整合性
# ============================================================

track_race_id = clean_text(
    track_condition.get("race_id")
)

track_matched = (
    bool(track_condition)
    and track_race_id == race_id
)

if (
    track_condition
    and not track_matched
):
    raise SystemExit(
        "ERROR: track_condition.json race_id mismatch"
    )


# ============================================================
# day_races整合性
# ============================================================

day_races_race_id = clean_text(
    day_races.get("race_id")
)

day_races_matched = (
    bool(day_races)
    and day_races_race_id == race_id
)

if (
    day_races
    and not day_races_matched
):
    raise SystemExit(
        "ERROR: day_races.json race_id mismatch"
    )


# ============================================================
# 対象レースより前だけ
# ============================================================

previous_race_numbers = list(
    range(1, race_no)
)


# ============================================================
# 初期値
# ============================================================

status = ""

reference_race_count = 0

time_bias = ""

inside_outside_bias = ""

running_style_bias = ""

confidence = 0.0

reason = ""

reference_races = []

style_counts = {
    "逃げ": 0,
    "先行": 0,
    "中団": 0,
    "後方": 0,
}

top3_style_counts = {
    "逃げ": 0,
    "先行": 0,
    "中団": 0,
    "後方": 0,
}

top3_samples = 0

winner_last3f = []

top3_last3f = []

inside_top3 = 0
outside_top3 = 0
middle_top3 = 0

future_race_detected = False

corner_connected_race_count = 0

corner_missing_race_numbers = []

reference_corner_numbers = {}


# 時計
time_analysis = {
    "connected": False,
    "status": "not_run",
    "time_bias": "",
    "score": None,
    "reference_count": 0,
    "scores": [],
    "reference_details": [],
    "reason": "",
}


# ============================================================
# 1R
# ============================================================

if race_no == 1:
    status = "no_previous_races"

    reason = (
        "対象が1Rのため、対象レース以前の"
        "同日実レースが存在しない。"
        "未来レースを使用しないため"
        "当日バイアス判定は行わない。"
    )


# ============================================================
# day_races 未取得
# ============================================================

elif not day_races:
    status = "day_races_not_found"

    reason = (
        "対象レースより前のRは存在するが、"
        "day_races.json が存在しない。"
        "推測によるバイアス判定は行わない。"
    )


# ============================================================
# day_races 接続
# ============================================================

else:
    collected_races = (
        day_races.get(
            "collected_races",
            []
        )
        or []
    )

    # --------------------------------------------------------
    # 未来レース混入チェック
    # --------------------------------------------------------

    for item in collected_races:
        item_race_no = safe_int(
            item.get("race_number")
        )

        if item_race_no is None:
            continue

        if item_race_no >= race_no:
            future_race_detected = True
            break

    if future_race_detected:
        raise SystemExit(
            "ERROR: day_races.json に"
            "対象レース以降のデータが混入しています"
        )

    # --------------------------------------------------------
    # 同一馬場だけ
    # --------------------------------------------------------

    for item in collected_races:
        item_race_no = safe_int(
            item.get("race_number")
        )

        if item_race_no is None:
            continue

        if item_race_no >= race_no:
            continue

        item_surface = normalize_surface(
            item.get("surface")
        )

        if item_surface != surface:
            continue

        if (
            item.get("status")
            not in [
                "ok",
                "condition_parse_incomplete",
            ]
        ):
            continue

        results = (
            item.get(
                "results",
                []
            )
            or []
        )

        if not results:
            continue

        reference_races.append(
            item
        )

    reference_race_count = len(
        reference_races
    )

    # --------------------------------------------------------
    # 各参考レース解析
    # --------------------------------------------------------

    for item in reference_races:
        item_race_no = safe_int(
            item.get("race_number")
        )

        results = (
            item.get(
                "results",
                []
            )
            or []
        )

        corner_positions = (
            item.get(
                "corner_positions",
                {}
            )
            or {}
        )

        (
            reference_corner_number,
            reference_corner_text
        ) = select_reference_corner(
            corner_positions
        )

        if reference_corner_text:
            position_map = (
                build_corner_position_map(
                    reference_corner_text
                )
            )
        else:
            position_map = {}

        if position_map:
            corner_connected_race_count += 1

            if item_race_no is not None:
                reference_corner_numbers[
                    str(item_race_no)
                ] = reference_corner_number

        else:
            if item_race_no is not None:
                corner_missing_race_numbers.append(
                    item_race_no
                )

        valid_results = []

        for race_result in results:
            finish = safe_int(
                race_result.get("finish")
            )

            if finish is None:
                continue

            horse_number = safe_int(
                race_result.get(
                    "horse_number"
                )
            )

            last3f = safe_float(
                race_result.get("last3f")
            )

            style = classify_running_style(
                horse_number,
                position_map
            )

            corner_position = None

            if (
                horse_number is not None
                and position_map
            ):
                corner_position = (
                    position_map.get(
                        horse_number
                    )
                )

            record = {
                "finish": finish,
                "style": style,
                "horse_number": horse_number,
                "last3f": last3f,
                "corner_number":
                    reference_corner_number,
                "corner_position":
                    corner_position,
            }

            valid_results.append(record)

            if style in style_counts:
                style_counts[style] += 1

        top3 = [
            x
            for x in valid_results
            if 1 <= x["finish"] <= 3
        ]

        for race_result in top3:
            style = race_result["style"]

            if style in top3_style_counts:
                top3_style_counts[
                    style
                ] += 1

                top3_samples += 1

            horse_number = race_result[
                "horse_number"
            ]

            if horse_number is not None:
                if horse_number <= 5:
                    inside_top3 += 1

                elif horse_number >= 11:
                    outside_top3 += 1

                else:
                    middle_top3 += 1

            last3f = race_result[
                "last3f"
            ]

            if last3f is not None:
                top3_last3f.append(
                    last3f
                )

            if (
                race_result["finish"] == 1
                and last3f is not None
            ):
                winner_last3f.append(
                    last3f
                )

    # --------------------------------------------------------
    # 脚質バイアス
    # --------------------------------------------------------

    front_top3 = (
        top3_style_counts["逃げ"]
        + top3_style_counts["先行"]
    )

    back_top3 = (
        top3_style_counts["中団"]
        + top3_style_counts["後方"]
    )

    if top3_samples >= 3:
        front_rate = (
            front_top3
            / top3_samples
        )

        back_rate = (
            back_top3
            / top3_samples
        )

        if front_rate >= 0.67:
            running_style_bias = (
                "逃げ・先行有利"
            )

        elif back_rate >= 0.67:
            running_style_bias = (
                "差し有利"
            )

        else:
            running_style_bias = (
                "大きな偏りなし"
            )

    # --------------------------------------------------------
    # 内外バイアス
    # --------------------------------------------------------

    position_samples = (
        inside_top3
        + middle_top3
        + outside_top3
    )

    if position_samples >= 3:
        inside_rate = (
            inside_top3
            / position_samples
        )

        outside_rate = (
            outside_top3
            / position_samples
        )

        if inside_rate >= 0.60:
            inside_outside_bias = (
                "内寄り優勢"
            )

        elif outside_rate >= 0.60:
            inside_outside_bias = (
                "外寄り優勢"
            )

        else:
            inside_outside_bias = (
                "大きな偏りなし"
            )

    # --------------------------------------------------------
    # 時計バイアス
    # --------------------------------------------------------

    time_analysis = calculate_time_bias(
        day_time_history,
        race_id
    )

    time_bias = time_analysis[
        "time_bias"
    ]

    # --------------------------------------------------------
    # 信頼度
    #
    # 従来通り同日参考レース数を基本とする。
    # 時計のrobust zは別フィールドで保持する。
    # --------------------------------------------------------

    if reference_race_count >= 5:
        confidence = 1.0

    elif reference_race_count == 4:
        confidence = 0.8

    elif reference_race_count == 3:
        confidence = 0.6

    elif reference_race_count == 2:
        confidence = 0.4

    elif reference_race_count == 1:
        confidence = 0.2

    else:
        confidence = 0.0

    # --------------------------------------------------------
    # status
    # --------------------------------------------------------

    if reference_race_count == 0:
        status = (
            "no_same_surface_reference"
        )

        reason = (
            "対象レース以前の同日レースは"
            "収集済みだが、対象と同じ馬場の"
            "有効な参考レースが存在しない。"
            "推測によるバイアス判定は行わない。"
        )

    else:
        status = "analyzed"

        time_reason = ""

        if time_analysis["connected"]:
            time_reason = (
                f"時計基準接続"
                f"{time_analysis['reference_count']}件、"
                f"時計判定={time_bias}、"
                f"標準化スコア="
                f"{time_analysis['score']}。"
            )
        else:
            time_reason = (
                "時計基準は有効サンプル不足のため"
                "判定していない。"
            )

        reason = (
            f"対象レース以前の同日・同競馬場・"
            f"同馬場の実レース"
            f"{reference_race_count}件を使用。"
            f"対象レース以降のデータは使用していない。"
            f"通過順位接続"
            f"{corner_connected_race_count}/"
            f"{reference_race_count}件。"
            f"{time_reason}"
        )


# ============================================================
# 平均上がり
# ============================================================

average_top3_last3f = None

if top3_last3f:
    average_top3_last3f = round(
        statistics.mean(
            top3_last3f
        ),
        2
    )


average_winner_last3f = None

if winner_last3f:
    average_winner_last3f = round(
        statistics.mean(
            winner_last3f
        ),
        2
    )


# ============================================================
# 出力
# ============================================================

output = {
    "race_id": race_id,
    "race_date": race_date,
    "racecourse": racecourse,
    "surface": surface,
    "distance": distance,
    "race_number": race_no,

    "eligible_previous_race_numbers":
        previous_race_numbers,

    "future_race_usage": False,

    "day_races_connected":
        day_races_matched,

    "status":
        status,

    "reference_race_count":
        reference_race_count,

    "reference_race_numbers": [
        item.get("race_number")
        for item in reference_races
    ],

    "corner_connected_race_count":
        corner_connected_race_count,

    "corner_missing_race_numbers":
        corner_missing_race_numbers,

    "reference_corner_numbers":
        reference_corner_numbers,

    "time_bias":
        time_bias,

    "time_bias_connected":
        time_analysis["connected"],

    "time_bias_status":
        time_analysis["status"],

    "time_bias_score":
        time_analysis["score"],

    "time_bias_reference_count":
        time_analysis["reference_count"],

    "time_bias_reference_scores":
        time_analysis["scores"],

    "time_bias_reference_details":
        time_analysis["reference_details"],

    "time_bias_reason":
        time_analysis["reason"],

    "inside_outside_bias":
        inside_outside_bias,

    "running_style_bias":
        running_style_bias,

    "confidence":
        confidence,

    "reason":
        reason,

    "style_counts":
        style_counts,

    "top3_style_counts":
        top3_style_counts,

    "top3_sample_count":
        top3_samples,

    "inside_top3":
        inside_top3,

    "middle_top3":
        middle_top3,

    "outside_top3":
        outside_top3,

    "average_top3_last3f":
        average_top3_last3f,

    "average_winner_last3f":
        average_winner_last3f,

    "track_condition_connected":
        track_matched,

    "moisture_finish": (
        track_condition.get(
            "moisture_finish"
        )
        if track_matched
        else None
    ),

    "moisture_4corner": (
        track_condition.get(
            "moisture_4corner"
        )
        if track_matched
        else None
    ),

    "cushion_value": (
        track_condition.get(
            "cushion_value"
        )
        if track_matched
        else None
    ),

    "updated_at":
        now_jst(),
}


save_json(
    OUTPUT_FILE,
    output
)


# ============================================================
# ログ
# ============================================================

print()
print("===== DAY BIAS =====")
print("race id:", race_id)
print("date:", race_date)
print("racecourse:", racecourse)
print("surface:", surface)
print("race number:", race_no)

print(
    "eligible previous races:",
    previous_race_numbers
)

print(
    "future race usage:",
    False
)

print(
    "day races connected:",
    day_races_matched
)

print(
    "track condition connected:",
    track_matched
)

print(
    "reference race count:",
    reference_race_count
)

print(
    "reference races:",
    output[
        "reference_race_numbers"
    ]
)

print(
    "corner connected:",
    corner_connected_race_count,
    "/",
    reference_race_count
)

print(
    "reference corners:",
    reference_corner_numbers
)

print(
    "corner missing races:",
    corner_missing_race_numbers
)

print(
    "top3 sample count:",
    top3_samples
)

print(
    "style counts:",
    style_counts
)

print(
    "top3 style counts:",
    top3_style_counts
)

print(
    "running style bias:",
    running_style_bias
)

print(
    "inside / middle / outside:",
    inside_top3,
    middle_top3,
    outside_top3
)

print(
    "inside outside bias:",
    inside_outside_bias
)

print(
    "average top3 last3f:",
    average_top3_last3f
)

print(
    "average winner last3f:",
    average_winner_last3f
)

print(
    "time bias connected:",
    time_analysis["connected"]
)

print(
    "time bias references:",
    time_analysis["reference_count"]
)

print(
    "time bias scores:",
    time_analysis["scores"]
)

print(
    "time bias score:",
    time_analysis["score"]
)

print(
    "time bias:",
    time_bias
)

print(
    "time bias reason:",
    time_analysis["reason"]
)

print(
    "confidence:",
    confidence
)

print(
    "moisture finish:",
    output["moisture_finish"]
)

print(
    "moisture 4corner:",
    output["moisture_4corner"]
)

print(
    "cushion value:",
    output["cushion_value"]
)

print(
    "status:",
    status
)

print(
    "reason:",
    reason
)

print(
    "saved:",
    OUTPUT_FILE
)

print("====================")
