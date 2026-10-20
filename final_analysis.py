import json
import os
from datetime import datetime, timezone, timedelta

OUTPUT_FILE = "final_analysis.json"


# =========================================================
# 共通
# =========================================================

def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def clamp(value, low, high):
    return max(low, min(high, value))


def round1(value):
    return round(float(value), 1)


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def get_number(data, *keys, default=0.0):
    if not isinstance(data, dict):
        return default

    for key in keys:
        value = data.get(key)

        if value in (None, ""):
            continue

        try:
            return float(
                str(value)
                .replace("kg", "")
                .strip()
            )
        except (TypeError, ValueError):
            continue

    return default


def get_optional_number(data, *keys):
    if not isinstance(data, dict):
        return None

    for key in keys:
        value = data.get(key)

        if value in (None, ""):
            continue

        try:
            return float(
                str(value)
                .replace("kg", "")
                .strip()
            )
        except (TypeError, ValueError):
            continue

    return None


def get_name(data):
    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_name")
        or data.get("name")
        or ""
    ).strip()


def get_id(data):
    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_id")
        or ""
    ).strip()


def get_number_string(data):
    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_number")
        or data.get("number")
        or data.get("umaban")
        or ""
    ).strip()


def normalize_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return [
            str(v).strip()
            for v in value
            if str(v).strip()
        ]

    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []

    return [str(value)]


def make_index(items):
    by_id = {}
    by_name = {}
    by_number = {}

    for item in items or []:
        if not isinstance(item, dict):
            continue

        horse_id = get_id(item)
        name = get_name(item)
        number = get_number_string(item)

        if horse_id:
            by_id[horse_id] = item

        if name:
            by_name[name] = item

        if number:
            by_number[number] = item

    return {
        "id": by_id,
        "name": by_name,
        "number": by_number,
    }


def find_horse(index, runner):
    horse_id = get_id(runner)
    name = get_name(runner)
    number = get_number_string(runner)

    if horse_id and horse_id in index["id"]:
        return index["id"][horse_id]

    if name and name in index["name"]:
        return index["name"][name]

    if number and number in index["number"]:
        return index["number"][number]

    return {}


def first_number(primary, secondary, *keys):
    value = get_optional_number(
        primary,
        *keys
    )

    if value is not None:
        return value, "race.json"

    value = get_optional_number(
        secondary,
        *keys
    )

    if value is not None:
        return value, "body_weight.json"

    return None, ""


# =========================================================
# データ読み込み
# =========================================================

race = load_json("race.json")
ability_data = load_json("runner_analysis.json")
previous_data = load_json("previous_race_analysis.json")
pace_data = load_json("pace_analysis.json")
blood_data = load_json("race_bloodline_score.json")

track_data_raw = load_json("track_condition.json")
day_bias_data_raw = load_json("day_bias.json")
body_weight_data_raw = load_json("body_weight.json")

# 新規接続
runner_time_fit_raw = load_json("runner_time_fit.json")


# =========================================================
# Race ID
# =========================================================

race_id = str(
    race.get("race_id", "")
).strip()


# =========================================================
# track_condition
# =========================================================

track_race_id = str(
    track_data_raw.get("race_id", "")
).strip()

track_race_id_matched = (
    bool(race_id)
    and bool(track_race_id)
    and race_id == track_race_id
)

track_data = (
    track_data_raw
    if track_race_id_matched
    else {}
)


# =========================================================
# day_bias
# =========================================================

day_bias_race_id = str(
    day_bias_data_raw.get("race_id", "")
).strip()

day_bias_race_id_matched = (
    bool(race_id)
    and bool(day_bias_race_id)
    and race_id == day_bias_race_id
)

day_bias_future_safe = (
    day_bias_data_raw.get(
        "future_race_usage"
    ) is False
)

day_bias_status = str(
    day_bias_data_raw.get(
        "status",
        ""
    )
).strip()

day_bias_status_valid = (
    day_bias_status == "analyzed"
)

if (
    day_bias_race_id_matched
    and day_bias_future_safe
    and day_bias_status_valid
):
    day_bias_data = day_bias_data_raw
else:
    day_bias_data = {}


# =========================================================
# runner_time_fit
# =========================================================

time_fit_race_id = str(
    runner_time_fit_raw.get(
        "target_race_id",
        ""
    )
).strip()

time_fit_race_id_matched = (
    bool(race_id)
    and bool(time_fit_race_id)
    and race_id == time_fit_race_id
)

time_fit_future_safe = (
    runner_time_fit_raw.get(
        "future_race_usage"
    ) is False
)

time_fit_leak_safe = (
    runner_time_fit_raw.get(
        "leak_check_passed"
    ) is True
)

if (
    time_fit_race_id_matched
    and time_fit_future_safe
    and time_fit_leak_safe
):
    runner_time_fit_data = runner_time_fit_raw
else:
    runner_time_fit_data = {}


# =========================================================
# body_weight
# =========================================================

body_weight_race_id = str(
    body_weight_data_raw.get(
        "race_id",
        ""
    )
).strip()

body_weight_race_id_matched = (
    bool(race_id)
    and bool(body_weight_race_id)
    and race_id == body_weight_race_id
)

body_weight_data = (
    body_weight_data_raw
    if body_weight_race_id_matched
    else {}
)


# =========================================================
# 出走馬
# =========================================================

runners = (
    race.get("horses")
    or race.get("runners")
    or race.get("entries")
    or []
)


# =========================================================
# Index
# =========================================================

ability_index = make_index(
    ability_data.get("horses", [])
)

previous_index = make_index(
    previous_data.get("horses", [])
)

pace_index = make_index(
    pace_data.get("horses", [])
)

blood_index = make_index(
    blood_data.get("ranking", [])
)

body_weight_index = make_index(
    body_weight_data.get("horses", [])
)

time_fit_index = make_index(
    runner_time_fit_data.get(
        "horses",
        []
    )
)


# =========================================================
# レース展開
# =========================================================

race_scenario = pace_data.get(
    "race_scenario",
    {}
)

base_pace = str(
    race_scenario.get(
        "base_pace",
        "不明"
    )
)

leader_candidate_count = int(
    race_scenario.get(
        "leader_candidate_count",
        0
    ) or 0
)

front_candidate_count = int(
    race_scenario.get(
        "front_candidate_count",
        0
    ) or 0
)


# =========================================================
# 年齢
# =========================================================

def get_age(runner):
    sex_age = str(
        runner.get("sex_age", "")
    ).strip()

    digits = "".join(
        ch
        for ch in sex_age
        if ch.isdigit()
    )

    if not digits:
        return None

    try:
        return int(digits)
    except ValueError:
        return None


# =========================================================
# 当日馬場・脚質・内外
#
# 時計適性はここでは加点しない。
# 時計適性はrunner_time_fitで個体別処理。
# =========================================================

def evaluate_track_condition(
    track,
    day_bias,
    running_style
):
    score = 0.0
    reasons = []

    style = str(
        running_style or "不明"
    ).strip()

    if track:
        track_condition = str(
            track.get(
                "track_condition",
                ""
            )
        ).strip()

        cushion = track.get(
            "cushion_value"
        )

        moisture_4 = track.get(
            "moisture_4corner"
        )

        moisture_finish = track.get(
            "moisture_finish"
        )

        if track_condition:
            reasons.append(
                "馬場:" + track_condition
            )

        if cushion not in (None, ""):
            reasons.append(
                "クッション値:"
                + str(cushion)
            )

        if (
            moisture_4 not in (None, "")
            or moisture_finish not in (None, "")
        ):
            reasons.append(
                "含水率:"
                + str(moisture_4)
                + "/"
                + str(moisture_finish)
            )

    else:
        reasons.append(
            "当日馬場実測データなし"
        )

    if not day_bias:
        reasons.extend([
            "当日実レースバイアス未接続",
            "馬場による発揮率補正なし",
        ])

        return 0.0, reasons

    time_bias = str(
        day_bias.get(
            "time_bias",
            ""
        )
    ).strip()

    inside_outside = str(
        day_bias.get(
            "inside_outside_bias",
            ""
        )
    ).strip()

    style_bias = str(
        day_bias.get(
            "running_style_bias",
            ""
        )
    ).strip()

    reference_count = int(
        get_number(
            day_bias,
            "reference_race_count",
            default=0
        )
    )

    confidence = get_optional_number(
        day_bias,
        "confidence"
    )

    if confidence is None:
        confidence = 0.0

    confidence = clamp(
        confidence,
        0.0,
        1.0
    )

    if time_bias:
        reasons.append(
            "時計傾向:" + time_bias
        )
        reasons.append(
            "時計傾向単独では個体補正しない"
        )
    else:
        reasons.append(
            "時計傾向未判定"
        )

    if inside_outside:
        reasons.append(
            "内外:" + inside_outside
        )

    if style_bias:
        reasons.append(
            "脚質傾向:" + style_bias
        )

    reasons.append(
        "当日バイアス参考"
        + str(reference_count)
        + "R"
    )

    reasons.append(
        "当日バイアス信頼度:"
        + format(
            confidence,
            ".2f"
        )
    )

    # -------------------------------
    # 脚質バイアス
    # -------------------------------

    if style_bias == "逃げ有利":

        if style == "逃げ":
            score += 1.2

        elif style in (
            "先行",
            "好位",
        ):
            score += 0.5

        elif style in (
            "中団後",
            "後方",
        ):
            score -= 0.5

    elif style_bias == "先行有利":

        if style in (
            "逃げ",
            "先行",
        ):
            score += 0.9

        elif style == "好位":
            score += 0.5

        elif style in (
            "中団後",
            "後方",
        ):
            score -= 0.5

    elif style_bias == "逃げ・先行有利":

        if style == "逃げ":
            score += 1.0

        elif style in (
            "先行",
            "好位",
        ):
            score += 0.8

        elif style in (
            "中団後",
            "後方",
        ):
            score -= 0.5

    elif style_bias == "差し有利":

        if style in (
            "差し",
            "中団",
            "中団後",
        ):
            score += 0.8

        elif style == "逃げ":
            score -= 0.6

        elif style == "先行":
            score -= 0.3

    elif style_bias == "追込有利":

        if style in (
            "差し",
            "中団後",
            "後方",
        ):
            score += 0.9

        elif style in (
            "逃げ",
            "先行",
        ):
            score -= 0.6

    elif style_bias == "大きな偏りなし":
        reasons.append(
            "脚質バイアス明確差なし"
        )

    # -------------------------------
    # 内外
    # -------------------------------

    if inside_outside in (
        "内有利",
        "内寄り優勢",
    ):
        if style in (
            "逃げ",
            "先行",
            "好位",
        ):
            score += 0.3
            reasons.append(
                "内優勢×前目脚質"
            )

    elif inside_outside in (
        "外有利",
        "外寄り優勢",
    ):
        if style in (
            "差し",
            "中団",
            "中団後",
            "後方",
        ):
            score += 0.3
            reasons.append(
                "外優勢×差し系脚質"
            )

    elif inside_outside == "大きな偏りなし":
        reasons.append(
            "内外バイアス明確差なし"
        )

    score *= confidence

    score = clamp(
        score,
        -1.5,
        1.5
    )

    if score == 0:
        reasons.append(
            "脚質・内外による発揮率補正なし"
        )

    return score, reasons


# =========================================================
# 時計環境適性
#
# 重要:
# ・能力には加えない
# ・今回能力発揮率だけ
# ・未知数は0
# ・有効過去走0も0
# ・単一過去走による強補正禁止
# =========================================================

def evaluate_time_fit(data):
    if not data:
        return {
            "adjustment": 0.0,
            "label": "未知数",
            "median_fit": None,
            "evaluated_count": 0,
            "reasons": [
                "時計環境適性データ未接続・補正なし"
            ],
        }

    label = str(
        data.get(
            "time_fit_label",
            "未知数"
        )
    ).strip()

    evaluated_count = int(
        get_number(
            data,
            "evaluated_past_race_count",
            default=0
        )
    )

    median_fit = get_optional_number(
        data,
        "median_current_bias_fit"
    )

    unknown = bool(
        data.get(
            "unknown",
            True
        )
    )

    current_time_bias = str(
        data.get(
            "current_time_bias",
            ""
        )
    ).strip()

    reasons = []

    if current_time_bias:
        reasons.append(
            "今回時計環境:"
            + current_time_bias
        )

    reasons.append(
        "時計適性判定:"
        + (label or "未知数")
    )

    reasons.append(
        "時計環境評価過去走:"
        + str(evaluated_count)
        + "走"
    )

    # -------------------------------
    # 未知数は完全ニュートラル
    # -------------------------------

    if (
        unknown
        or evaluated_count <= 0
        or median_fit is None
        or label == "未知数"
    ):
        reasons.append(
            "時計環境適性は未知数・減点なし"
        )

        return {
            "adjustment": 0.0,
            "label": "未知数",
            "median_fit": median_fit,
            "evaluated_count": evaluated_count,
            "reasons": reasons,
        }

    median_fit = clamp(
        median_fit,
        0.0,
        1.0
    )

    # -------------------------------
    # 補正
    #
    # 1走だけで大きく動かさない。
    # 2走以上で最大±0.8pt。
    # -------------------------------

    sample_factor = min(
        evaluated_count / 2.0,
        1.0
    )

    if median_fit >= 0.85:
        raw_adjustment = 0.8

    elif median_fit >= 0.70:
        raw_adjustment = 0.5

    elif median_fit >= 0.50:
        raw_adjustment = 0.2

    elif median_fit >= 0.30:
        raw_adjustment = 0.0

    elif median_fit >= 0.15:
        raw_adjustment = -0.3

    else:
        raw_adjustment = -0.6

    adjustment = (
        raw_adjustment
        * sample_factor
    )

    adjustment = clamp(
        adjustment,
        -0.8,
        0.8
    )

    reasons.append(
        "時計環境一致度:"
        + format(
            median_fit,
            ".2f"
        )
    )

    if evaluated_count == 1:
        reasons.append(
            "時計環境評価1走のみ・補正縮小"
        )

    if adjustment > 0:
        reasons.append(
            "今回時計環境への経験接続あり"
        )

    elif adjustment < 0:
        reasons.append(
            "今回時計環境との経験差あり"
        )

    else:
        reasons.append(
            "時計環境による明確な補正なし"
        )

    return {
        "adjustment": adjustment,
        "label": label,
        "median_fit": median_fit,
        "evaluated_count": evaluated_count,
        "reasons": reasons,
    }


# =========================================================
# 馬体重
# =========================================================

def evaluate_body_weight(
    runner,
    body_fallback
):
    body_weight, body_source = first_number(
        runner,
        body_fallback,
        "body_weight",
        "weight"
    )

    change, change_source = first_number(
        runner,
        body_fallback,
        "body_weight_change",
        "weight_change",
        "change"
    )

    carried_weight, carried_source = first_number(
        runner,
        body_fallback,
        "carried_weight",
        "burden_weight",
        "weight_carried",
        "jockey_weight"
    )

    age = get_age(runner)

    reasons = []
    adjustment = 0.0
    weight_ratio = None

    sources = {
        value
        for value in (
            body_source,
            change_source,
            carried_source,
        )
        if value
    }

    if sources:
        reasons.append(
            "馬体データ:"
            + "+".join(
                sorted(sources)
            )
        )

    if body_weight is None or body_weight <= 0:
        return {
            "adjustment": 0.0,
            "body_weight": None,
            "change": change,
            "carried_weight": carried_weight,
            "weight_ratio": None,
            "age": age,
            "source": "",
            "reasons": [
                "当日馬体重不明・補正なし"
            ],
        }

    reasons.append(
        "馬体重:"
        + format(body_weight, ".0f")
        + "kg"
    )

    if change is not None:
        reasons.append(
            "増減:"
            + format(change, "+.0f")
            + "kg"
        )
    else:
        reasons.append(
            "馬体重増減不明"
        )

    if age == 2:
        reasons.append(
            "2歳馬・馬体増は成長分を考慮"
        )

    if (
        carried_weight is not None
        and carried_weight > 0
    ):
        weight_ratio = (
            carried_weight
            / body_weight
            * 100.0
        )

        reasons.append(
            "斤量:"
            + format(
                carried_weight,
                ".1f"
            )
            + "kg"
        )

        reasons.append(
            "斤量体重比:"
            + format(
                weight_ratio,
                ".2f"
            )
            + "%"
        )

        if weight_ratio >= 13.5:
            adjustment -= 0.4
            reasons.append(
                "斤量体重比高め・小幅注意"
            )

        elif weight_ratio >= 13.0:
            adjustment -= 0.2
            reasons.append(
                "斤量体重比やや高め"
            )

        else:
            reasons.append(
                "斤量体重比に明確な負荷なし"
            )

    else:
        reasons.append(
            "斤量不明・斤量体重比補正なし"
        )

    if change is not None:
        abs_change = abs(change)

        if age == 2:
            if abs_change >= 20:
                reasons.append(
                    "2歳・大幅馬体変動・状態確認必要"
                )

            elif abs_change >= 10:
                reasons.append(
                    "2歳・馬体変動あり・成長分含め単独評価しない"
                )

            else:
                reasons.append(
                    "2歳・馬体変動は単独評価しない"
                )

        else:
            if abs_change >= 20:
                reasons.append(
                    "大幅馬体変動・状態確認必要"
                )

            elif abs_change >= 10:
                reasons.append(
                    "馬体変動あり・単独評価しない"
                )

            else:
                reasons.append(
                    "馬体変動は通常範囲"
                )

    adjustment = clamp(
        adjustment,
        -0.5,
        0.0
    )

    source_label = (
        "race.json"
        if "race.json" in sources
        else (
            "body_weight.json"
            if "body_weight.json" in sources
            else ""
        )
    )

    return {
        "adjustment": adjustment,
        "body_weight": body_weight,
        "change": change,
        "carried_weight": carried_weight,
        "weight_ratio": weight_ratio,
        "age": age,
        "source": source_label,
        "reasons": reasons,
    }


# =========================================================
# 前走課題 × 馬体
# =========================================================

def evaluate_body_issue_connection(
    body_result,
    previous_horse
):
    body_weight = body_result.get(
        "body_weight"
    )

    change = body_result.get(
        "change"
    )

    age = body_result.get(
        "age"
    )

    if body_weight is None:
        return 0.0, [
            "馬体重×課題:馬体重不明"
        ]

    if not previous_horse:
        return 0.0, [
            "馬体重×課題:前走解析不明"
        ]

    if not previous_horse.get(
        "previous_race_available",
        False
    ):
        return 0.0, [
            "馬体重×課題:前走データなし"
        ]

    if change is None:
        return 0.0, [
            "馬体重×課題:増減不明"
        ]

    previous = previous_horse.get(
        "previous_race",
        {}
    )

    issues = normalize_list(
        previous.get("issues")
    )

    overcoming = normalize_list(
        previous.get(
            "overcoming_materials"
        )
    )

    if not issues:
        return 0.0, [
            "馬体重に接続する前走課題なし"
        ]

    issue_text = " ".join(issues)
    overcoming_text = " ".join(
        overcoming
    )

    score = 0.0
    reasons = []

    heavy_keywords = (
        "太め",
        "太目",
        "余裕残し",
        "重め",
        "重目",
        "絞れる余地",
        "太かった",
    )

    thin_keywords = (
        "細い",
        "細め",
        "細目",
        "馬体減",
        "減りすぎ",
        "体が減",
        "馬体維持",
        "馬体回復",
    )

    heavy_issue = any(
        keyword in issue_text
        for keyword in heavy_keywords
    )

    thin_issue = any(
        keyword in issue_text
        for keyword in thin_keywords
    )

    if heavy_issue:
        reasons.append(
            "前走太め系課題あり"
        )

        if change <= -4:
            score += 0.4
            reasons.append(
                "馬体減で課題改善方向"
            )

            if any(
                keyword in overcoming_text
                for keyword in (
                    "絞れた",
                    "引き締まった",
                    "良化",
                    "上向き",
                    "仕上がった",
                )
            ):
                score += 0.2
                reasons.append(
                    "既存克服材料とも整合"
                )

        elif change > 0:
            reasons.append(
                "太め系課題に対して馬体増・克服確認できず"
            )

        else:
            reasons.append(
                "太め系課題の克服確認できず"
            )

    if thin_issue:
        reasons.append(
            "前走馬体維持系課題あり"
        )

        if change >= 4:
            if age == 2:
                score += 0.2
                reasons.append(
                    "2歳馬体増・回復方向候補だが成長分も考慮"
                )
            else:
                score += 0.4
                reasons.append(
                    "馬体増で回復方向"
                )

            if any(
                keyword in overcoming_text
                for keyword in (
                    "回復",
                    "ふっくら",
                    "良化",
                    "維持",
                    "戻った",
                )
            ):
                score += 0.2
                reasons.append(
                    "既存克服材料とも整合"
                )

        elif change <= -6:
            score -= 0.3
            reasons.append(
                "さらに馬体減・課題継続注意"
            )

        else:
            reasons.append(
                "馬体維持系課題の克服不明"
            )

    if not heavy_issue and not thin_issue:
        reasons.append(
            "前走課題と馬体重の明確な接続なし"
        )

    return (
        clamp(
            score,
            -0.4,
            0.6
        ),
        reasons,
    )


# =========================================================
# 前走
# =========================================================

def evaluate_previous(data):
    if not data:
        return (
            0.0,
            ["前走解析データ不明"],
            0,
            0,
            0,
        )

    if not data.get(
        "previous_race_available",
        False
    ):
        return (
            0.0,
            ["前走データなし・減点なし"],
            0,
            0,
            0,
        )

    previous = data.get(
        "previous_race",
        {}
    )

    positives = normalize_list(
        previous.get("positives")
    )

    issues = normalize_list(
        previous.get("issues")
    )

    overcoming = normalize_list(
        previous.get(
            "overcoming_materials"
        )
    )

    unknowns = normalize_list(
        previous.get("unknowns")
    )

    score = 0.0
    reasons = []

    if positives:
        positive_add = min(
            len(positives) * 0.30,
            0.9
        )

        score += positive_add

        reasons.append(
            "前走プラス"
            + str(len(positives))
            + "件"
        )

    if issues:
        issue_minus = min(
            len(issues) * 0.25,
            1.0
        )

        score -= issue_minus

        reasons.append(
            "前走課題"
            + str(len(issues))
            + "件"
        )

    else:
        reasons.append(
            "明確な前走課題なし"
        )

    if overcoming:
        if issues:
            resolution_ratio = min(
                len(overcoming)
                / max(
                    len(issues),
                    1
                ),
                1.0
            )

            overcoming_add = (
                0.6
                + resolution_ratio * 0.9
            )

            overcoming_add = min(
                overcoming_add,
                1.5
            )

            score += overcoming_add

            reasons.append(
                "課題克服材料"
                + str(len(overcoming))
                + "件"
            )

            reasons.append(
                "課題克服比率:"
                + format(
                    resolution_ratio,
                    ".2f"
                )
            )

        else:
            score += 0.2
            reasons.append(
                "克服材料あり・対応課題不明"
            )

    elif issues:
        reasons.append(
            "明確な課題克服材料なし"
        )

    if unknowns:
        reasons.append(
            "前走未知数"
            + str(len(unknowns))
            + "件・減点なし"
        )

    score = clamp(
        score,
        -1.3,
        1.8
    )

    return (
        score,
        reasons,
        len(positives),
        len(issues),
        len(overcoming),
    )


# =========================================================
# 血統
# =========================================================

def evaluate_bloodline(data):
    if not data:
        return (
            0.0,
            ["血統データ不明"]
        )

    score = get_number(
        data,
        "bloodline_score",
        default=0.0
    )

    matched = int(
        get_number(
            data,
            "matched_ancestor_count",
            default=0
        )
    )

    positive = int(
        get_number(
            data,
            "positive_ancestor_count",
            default=0
        )
    )

    if matched <= 0:
        adjustment = 0.0

    elif positive <= 0:
        adjustment = clamp(
            score,
            -0.4,
            0.0
        )

    else:
        adjustment = clamp(
            score,
            -0.8,
            0.8
        )

    reasons = [
        "血統スコア"
        + format(score, ".3f"),

        "該当祖先"
        + str(matched)
        + "・プラス"
        + str(positive),

        "血統は今回条件への補助のみ",
    ]

    if matched <= 0:
        reasons.append(
            "血統該当なし・ニュートラル"
        )

    elif positive <= 0:
        reasons.append(
            "プラス祖先なし・血統単独の強い減点禁止"
        )

    return adjustment, reasons


# =========================================================
# 展開
# =========================================================

def evaluate_pace(data):
    if not data:
        return (
            0.0,
            ["展開データ不明"]
        )

    style = str(
        data.get(
            "running_style",
            "不明"
        )
    )

    front_rate = get_number(
        data,
        "front_rate",
        default=0.0
    )

    back_rate = get_number(
        data,
        "back_rate",
        default=0.0
    )

    avg_final = get_number(
        data,
        "average_final_position",
        default=0.0
    )

    score = 0.0

    reasons = [
        "脚質:" + style,
        "基本展開:" + base_pace,
    ]

    if base_pace == "ミドル":
        if style in (
            "先行",
            "好位",
            "中団",
        ):
            score += 0.5

        elif style in (
            "中団後",
            "後方",
        ):
            score -= 0.3

    elif base_pace == "スロー":
        if style in (
            "逃げ",
            "先行",
            "好位",
        ):
            score += 0.7

        elif style in (
            "中団後",
            "後方",
        ):
            score -= 0.7

    elif base_pace == "ハイ":
        if style in (
            "差し",
            "中団",
            "中団後",
        ):
            score += 0.7

        if style == "逃げ":
            score -= 0.5

    if (
        leader_candidate_count == 0
        and front_candidate_count <= 4
        and front_rate >= 0.50
    ):
        score += 0.3
        reasons.append(
            "先行位置を取りやすい構成"
        )

    if (
        leader_candidate_count >= 3
        and style == "逃げ"
    ):
        score -= 0.3
        reasons.append(
            "逃げ候補複数・ハナ争い注意"
        )

    if back_rate >= 0.60:
        score -= 0.6
        reasons.append(
            "後方位置依存注意"
        )

    if avg_final > 0:
        reasons.append(
            "平均最終位置"
            + format(
                avg_final,
                ".2f"
            )
        )

    return (
        clamp(
            score,
            -1.5,
            1.5
        ),
        reasons,
    )


# =========================================================
# 最終統合
# =========================================================

results = []


for runner in runners:
    ability = find_horse(
        ability_index,
        runner
    )

    previous_horse = find_horse(
        previous_index,
        runner
    )

    pace = find_horse(
        pace_index,
        runner
    )

    blood = find_horse(
        blood_index,
        runner
    )

    body_fallback = find_horse(
        body_weight_index,
        runner
    )

    time_fit_horse = find_horse(
        time_fit_index,
        runner
    )

    ability_score = get_number(
        ability,
        "ability_score",
        default=50.0
    )

    original_performance_rate = get_number(
        ability,
        "performance_rate",
        default=100.0
    )

    condition_fit = get_number(
        ability,
        "condition_fit_score",
        default=50.0
    )

    running_style = str(
        pace.get(
            "running_style",
            "不明"
        )
    )

    (
        track_rate_adjustment,
        track_reasons
    ) = evaluate_track_condition(
        track_data,
        day_bias_data,
        running_style
    )

    time_fit_result = evaluate_time_fit(
        time_fit_horse
    )

    time_fit_adjustment = (
        time_fit_result[
            "adjustment"
        ]
    )

    body_result = evaluate_body_weight(
        runner,
        body_fallback
    )

    body_weight_rate_adjustment = (
        body_result[
            "adjustment"
        ]
    )

    (
        body_issue_adjustment,
        body_issue_reasons
    ) = evaluate_body_issue_connection(
        body_result,
        previous_horse
    )

    adjusted_performance_rate = clamp(
        original_performance_rate
        + track_rate_adjustment
        + time_fit_adjustment
        + body_weight_rate_adjustment
        + body_issue_adjustment,
        0.0,
        110.0
    )

    base_performance = (
        ability_score
        * adjusted_performance_rate
        / 100.0
    )

    condition_adjustment = clamp(
        (
            condition_fit
            - 50.0
        )
        / 25.0,
        -2.0,
        2.0
    )

    (
        previous_adj,
        previous_reasons,
        previous_positive_count,
        previous_issue_count,
        overcoming_count
    ) = evaluate_previous(
        previous_horse
    )

    (
        pace_adj,
        pace_reasons
    ) = evaluate_pace(
        pace
    )

    (
        blood_adj,
        blood_reasons
    ) = evaluate_bloodline(
        blood
    )

    final_score = (
        base_performance
        + condition_adjustment
        + previous_adj
        + pace_adj
        + blood_adj
    )

    unknown = bool(
        ability.get(
            "unknown",
            False
        )
    )

    noise_flags = normalize_list(
        ability.get(
            "noise_flags"
        )
    )

    reasons = [
        "能力"
        + format(
            ability_score,
            ".1f"
        ),

        "元発揮率"
        + format(
            original_performance_rate,
            ".1f"
        )
        + "%",

        "馬場補正"
        + format(
            track_rate_adjustment,
            "+.1f"
        )
        + "pt",

        "時計環境補正"
        + format(
            time_fit_adjustment,
            "+.1f"
        )
        + "pt",

        "馬体・斤量補正"
        + format(
            body_weight_rate_adjustment,
            "+.1f"
        )
        + "pt",

        "馬体×課題補正"
        + format(
            body_issue_adjustment,
            "+.1f"
        )
        + "pt",

        "補正後発揮率"
        + format(
            adjusted_performance_rate,
            ".1f"
        )
        + "%",

        "条件適性"
        + format(
            condition_fit,
            ".1f"
        ),
    ]

    reasons.extend(
        track_reasons
    )

    reasons.extend(
        time_fit_result[
            "reasons"
        ]
    )

    reasons.extend(
        body_result["reasons"]
    )

    reasons.extend(
        body_issue_reasons
    )

    reasons.extend(
        previous_reasons
    )

    reasons.extend(
        pace_reasons
    )

    reasons.extend(
        blood_reasons
    )

    if unknown:
        reasons.append(
            "未知数あり・減点なし"
        )

    results.append({
        "horse_id":
            get_id(runner),

        "horse_number":
            get_number_string(runner),

        "horse_name":
            get_name(runner),

        "ability_score":
            round1(
                ability_score
            ),

        "original_performance_rate":
            round1(
                original_performance_rate
            ),

        "track_performance_rate_adjustment":
            round1(
                track_rate_adjustment
            ),

        "time_fit_performance_rate_adjustment":
            round1(
                time_fit_adjustment
            ),

        "time_fit_label":
            time_fit_result[
                "label"
            ],

        "time_fit_evaluated_race_count":
            time_fit_result[
                "evaluated_count"
            ],

        "time_fit_median":
            (
                round(
                    time_fit_result[
                        "median_fit"
                    ],
                    3
                )
                if time_fit_result[
                    "median_fit"
                ] is not None
                else None
            ),

        "body_weight_performance_rate_adjustment":
            round1(
                body_weight_rate_adjustment
            ),

        "body_weight_issue_adjustment":
            round1(
                body_issue_adjustment
            ),

        "performance_rate":
            round1(
                adjusted_performance_rate
            ),

        "base_performance":
            round1(
                base_performance
            ),

        "body_weight":
            (
                round1(
                    body_result[
                        "body_weight"
                    ]
                )
                if body_result[
                    "body_weight"
                ] is not None
                else None
            ),

        "body_weight_change":
            (
                round1(
                    body_result[
                        "change"
                    ]
                )
                if body_result[
                    "change"
                ] is not None
                else None
            ),

        "carried_weight":
            (
                round1(
                    body_result[
                        "carried_weight"
                    ]
                )
                if body_result[
                    "carried_weight"
                ] is not None
                else None
            ),

        "weight_body_ratio":
            (
                round(
                    body_result[
                        "weight_ratio"
                    ],
                    2
                )
                if body_result[
                    "weight_ratio"
                ] is not None
                else None
            ),

        "body_weight_source":
            body_result[
                "source"
            ],

        "condition_fit_score":
            round1(
                condition_fit
            ),

        "condition_adjustment":
            round1(
                condition_adjustment
            ),

        "previous_positive_count":
            previous_positive_count,

        "previous_issue_count":
            previous_issue_count,

        "overcoming_material_count":
            overcoming_count,

        "previous_race_adjustment":
            round1(
                previous_adj
            ),

        "pace_adjustment":
            round1(
                pace_adj
            ),

        "running_style":
            running_style,

        "bloodline_score":
            round(
                get_number(
                    blood,
                    "bloodline_score",
                    default=0.0
                ),
                6
            ),

        "bloodline_adjustment":
            round1(
                blood_adj
            ),

        "final_score":
            round1(
                final_score
            ),

        "unknown":
            unknown,

        "noise_flags":
            noise_flags,

        "reasons":
            reasons,
    })


# =========================================================
# ランキング
# =========================================================

results.sort(
    key=lambda x: (
        x["final_score"],
        x["ability_score"],
    ),
    reverse=True
)


for rank, horse in enumerate(
    results,
    start=1
):
    horse["rank"] = rank

    if rank <= 2:
        judgement = "最上位"

    elif rank <= 4:
        judgement = "上位"

    elif rank <= 7:
        judgement = "相手候補"

    elif rank <= 9:
        judgement = "押さえ"

    else:
        judgement = "低評価"

    if horse["unknown"]:
        judgement += "/未知数"

    if horse["noise_flags"]:
        judgement += "/注意"

    horse["judgement"] = judgement


# =========================================================
# 接続状況
# =========================================================

ability_connected = sum(
    1
    for runner in runners
    if find_horse(
        ability_index,
        runner
    )
)

previous_connected = sum(
    1
    for runner in runners
    if find_horse(
        previous_index,
        runner
    )
)

pace_connected = sum(
    1
    for runner in runners
    if find_horse(
        pace_index,
        runner
    )
)

blood_connected = sum(
    1
    for runner in runners
    if find_horse(
        blood_index,
        runner
    )
)

time_fit_connected = sum(
    1
    for runner in runners
    if find_horse(
        time_fit_index,
        runner
    )
)

time_fit_evaluable_count = sum(
    1
    for horse in results
    if horse[
        "time_fit_evaluated_race_count"
    ] > 0
)

time_fit_effective_count = sum(
    1
    for horse in results
    if horse[
        "time_fit_performance_rate_adjustment"
    ] != 0
)

body_weight_connected = sum(
    1
    for horse in results
    if horse[
        "body_weight"
    ] is not None
)

race_json_body_weight_connected = sum(
    1
    for horse in results
    if (
        horse[
            "body_weight"
        ] is not None
        and horse[
            "body_weight_source"
        ] == "race.json"
    )
)

previous_effective_count = sum(
    1
    for horse in results
    if horse[
        "previous_race_adjustment"
    ] != 0
)

track_effective_count = sum(
    1
    for horse in results
    if horse[
        "track_performance_rate_adjustment"
    ] != 0
)

body_weight_effective_count = sum(
    1
    for horse in results
    if (
        horse[
            "body_weight_performance_rate_adjustment"
        ] != 0
        or horse[
            "body_weight_issue_adjustment"
        ] != 0
    )
)


# =========================================================
# JSON
# =========================================================

output = {
    "updated_at":
        now_jst(),

    "race_id":
        race_id,

    "track_condition": {
        "source_available":
            bool(track_data_raw),

        "race_id_matched":
            track_race_id_matched,

        "source_race_id":
            track_race_id,

        "applied":
            bool(track_data),

        "track_condition":
            track_data.get(
                "track_condition",
                ""
            ),

        "cushion_value":
            track_data.get(
                "cushion_value"
            ),

        "moisture_4corner":
            track_data.get(
                "moisture_4corner"
            ),

        "moisture_finish":
            track_data.get(
                "moisture_finish"
            ),
    },

    "day_bias": {
        "source_available":
            bool(day_bias_data_raw),

        "source_race_id":
            day_bias_race_id,

        "race_id_matched":
            day_bias_race_id_matched,

        "future_race_usage":
            day_bias_data_raw.get(
                "future_race_usage"
            ),

        "future_safe":
            day_bias_future_safe,

        "status":
            day_bias_status,

        "applied":
            bool(day_bias_data),

        "reference_race_count":
            int(
                get_number(
                    day_bias_data,
                    "reference_race_count",
                    default=0
                )
            ),

        "reference_race_numbers":
            day_bias_data.get(
                "reference_race_numbers",
                []
            ),

        "corner_connected_race_count":
            int(
                get_number(
                    day_bias_data,
                    "corner_connected_race_count",
                    default=0
                )
            ),

        "top3_sample_count":
            int(
                get_number(
                    day_bias_data,
                    "top3_sample_count",
                    default=0
                )
            ),

        "confidence":
            get_optional_number(
                day_bias_data,
                "confidence"
            ),

        "time_bias":
            day_bias_data.get(
                "time_bias",
                ""
            ),

        "inside_outside_bias":
            day_bias_data.get(
                "inside_outside_bias",
                ""
            ),

        "running_style_bias":
            day_bias_data.get(
                "running_style_bias",
                ""
            ),
    },

    "runner_time_fit": {
        "source_available":
            bool(runner_time_fit_raw),

        "source_race_id":
            time_fit_race_id,

        "race_id_matched":
            time_fit_race_id_matched,

        "future_safe":
            time_fit_future_safe,

        "leak_check_passed":
            time_fit_leak_safe,

        "applied":
            bool(runner_time_fit_data),

        "current_time_bias":
            runner_time_fit_data.get(
                "current_time_bias",
                ""
            ),

        "connected_horse_count":
            int(
                get_number(
                    runner_time_fit_data,
                    "connected_horse_count",
                    default=0
                )
            ),

        "connected_past_race_count":
            int(
                get_number(
                    runner_time_fit_data,
                    "connected_past_race_count",
                    default=0
                )
            ),
    },

    "body_weight_source": {
        "primary_source":
            "race.json",

        "fallback_source":
            "body_weight.json",

        "fallback_source_available":
            bool(body_weight_data_raw),

        "fallback_race_id_matched":
            body_weight_race_id_matched,

        "fallback_source_race_id":
            body_weight_race_id,
    },

    "race_scenario": {
        "base_pace":
            base_pace,

        "leader_candidate_count":
            leader_candidate_count,

        "front_candidate_count":
            front_candidate_count,
    },

    "method": {
        "ability_and_performance_rate_separated":
            True,

        "track_affects_performance_rate_not_ability":
            True,

        "day_bias_affects_performance_rate_not_ability":
            True,

        "time_fit_affects_performance_rate_not_ability":
            True,

        "time_bias_not_used_as_standalone_horse_score":
            True,

        "time_fit_requires_matching_race_id":
            True,

        "time_fit_requires_no_future_race_usage":
            True,

        "time_fit_requires_leak_check":
            True,

        "time_fit_unknown_not_penalized":
            True,

        "single_time_fit_sample_reduced":
            True,

        "day_bias_requires_matching_race_id":
            True,

        "day_bias_requires_no_future_race_usage":
            True,

        "day_bias_confidence_used_directly":
            True,

        "body_weight_primary_source_is_race_json":
            True,

        "body_weight_json_is_fallback_only":
            True,

        "body_weight_affects_performance_rate_not_ability":
            True,

        "body_weight_change_not_used_alone":
            True,

        "two_year_old_growth_considered":
            True,

        "weight_body_ratio_not_used_as_strong_standalone_factor":
            True,

        "body_weight_connected_to_previous_issue":
            True,

        "track_race_id_must_match":
            True,

        "cushion_value_not_used_alone":
            True,

        "moisture_not_used_alone":
            True,

        "draw_not_used_alone":
            True,

        "previous_finish_not_used_alone":
            True,

        "previous_issue_resolution_emphasized":
            True,

        "bloodline_is_condition_support_only":
            True,

        "bloodline_strong_negative_without_positive_match_prohibited":
            True,

        "unknown_not_penalized":
            True,

        "popularity_not_used":
            True,

        "internet_prediction_not_used":
            True,
    },

    "summary": {
        "runner_count":
            len(results),

        "ranked_count":
            len(results),

        "ability_connected_count":
            ability_connected,

        "previous_connected_count":
            previous_connected,

        "pace_connected_count":
            pace_connected,

        "bloodline_connected_count":
            blood_connected,

        "time_fit_record_connected_count":
            time_fit_connected,

        "time_fit_evaluable_count":
            time_fit_evaluable_count,

        "time_fit_effective_count":
            time_fit_effective_count,

        "body_weight_connected_count":
            body_weight_connected,

        "race_json_body_weight_connected_count":
            race_json_body_weight_connected,

        "previous_effective_count":
            previous_effective_count,

        "track_source_available":
            bool(track_data_raw),

        "track_race_id_matched":
            track_race_id_matched,

        "track_applied":
            bool(track_data),

        "day_bias_source_available":
            bool(day_bias_data_raw),

        "day_bias_race_id_matched":
            day_bias_race_id_matched,

        "day_bias_future_safe":
            day_bias_future_safe,

        "day_bias_applied":
            bool(day_bias_data),

        "day_bias_reference_race_count":
            int(
                get_number(
                    day_bias_data,
                    "reference_race_count",
                    default=0
                )
            ),

        "day_bias_top3_sample_count":
            int(
                get_number(
                    day_bias_data,
                    "top3_sample_count",
                    default=0
                )
            ),

        "track_effective_count":
            track_effective_count,

        "body_weight_effective_count":
            body_weight_effective_count,
    },

    "ranking":
        results,
}


# =========================================================
# 保存
# =========================================================

with open(
    OUTPUT_FILE,
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        output,
        f,
        ensure_ascii=False,
        indent=2
    )


# =========================================================
# ログ
# =========================================================

print(
    "===== FINAL ANALYSIS ====="
)

print(
    "race id:",
    race_id
)

print(
    "track race id matched:",
    track_race_id_matched
)

print(
    "day bias race id matched:",
    day_bias_race_id_matched
)

print(
    "day bias future safe:",
    day_bias_future_safe
)

print(
    "day bias applied:",
    bool(day_bias_data)
)

print(
    "day bias time:",
    day_bias_data.get(
        "time_bias",
        ""
    )
)

print(
    "time fit race id matched:",
    time_fit_race_id_matched
)

print(
    "time fit future safe:",
    time_fit_future_safe
)

print(
    "time fit leak safe:",
    time_fit_leak_safe
)

print(
    "time fit applied:",
    bool(runner_time_fit_data)
)

print(
    "ability:",
    ability_connected,
    "/",
    len(results)
)

print(
    "previous:",
    previous_connected,
    "/",
    len(results)
)

print(
    "pace:",
    pace_connected,
    "/",
    len(results)
)

print(
    "bloodline:",
    blood_connected,
    "/",
    len(results)
)

print(
    "time fit records:",
    time_fit_connected,
    "/",
    len(results)
)

print(
    "time fit evaluable:",
    time_fit_evaluable_count,
    "/",
    len(results)
)

print(
    "time fit effective:",
    time_fit_effective_count,
    "/",
    len(results)
)

print(
    "body weight:",
    body_weight_connected,
    "/",
    len(results)
)

print(
    "track effective:",
    track_effective_count,
    "/",
    len(results)
)

print(
    "previous effective:",
    previous_effective_count,
    "/",
    len(results)
)

print(
    "body weight effective:",
    body_weight_effective_count,
    "/",
    len(results)
)

print()


for horse in results:
    print(
        horse["rank"],
        horse["horse_number"],
        horse["horse_name"],
        "最終",
        horse["final_score"],
        "能力",
        horse["ability_score"],
        "発揮率",
        horse["performance_rate"],
        "馬場",
        horse[
            "track_performance_rate_adjustment"
        ],
        "時計適性",
        horse[
            "time_fit_performance_rate_adjustment"
        ],
        "時計判定",
        horse[
            "time_fit_label"
        ],
        "時計過去走",
        horse[
            "time_fit_evaluated_race_count"
        ],
        "馬体補正",
        horse[
            "body_weight_performance_rate_adjustment"
        ],
        "馬体×課題",
        horse[
            "body_weight_issue_adjustment"
        ],
        "前走",
        horse[
            "previous_race_adjustment"
        ],
        "課題",
        horse[
            "previous_issue_count"
        ],
        "克服",
        horse[
            "overcoming_material_count"
        ],
        "展開",
        horse[
            "pace_adjustment"
        ],
        "血統",
        horse[
            "bloodline_adjustment"
        ]
    )
