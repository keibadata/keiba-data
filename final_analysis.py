import json
import os
import re
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


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def clamp(value, low, high):
    return max(low, min(high, value))


def round1(value):
    if value is None:
        return None
    return round(float(value), 1)


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
                .replace("%", "")
                .strip()
            )
        except (TypeError, ValueError):
            continue

    return None


def get_number(data, *keys, default=0.0):
    value = get_optional_number(
        data,
        *keys
    )

    return (
        default
        if value is None
        else value
    )


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
        horse_name = get_name(item)
        horse_number = get_number_string(item)

        if horse_id:
            by_id[horse_id] = item

        if horse_name:
            by_name[horse_name] = item

        if horse_number:
            by_number[horse_number] = item

    return {
        "id": by_id,
        "name": by_name,
        "number": by_number,
    }


def find_horse(index, runner):
    horse_id = get_id(runner)
    horse_name = get_name(runner)
    horse_number = get_number_string(runner)

    if (
        horse_id
        and horse_id in index["id"]
    ):
        return index["id"][horse_id]

    if (
        horse_name
        and horse_name in index["name"]
    ):
        return index["name"][horse_name]

    if (
        horse_number
        and horse_number in index["number"]
    ):
        return index["number"][horse_number]

    return {}


def horse_number_sort_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def get_age(runner):
    sex_age = str(
        runner.get(
            "sex_age",
            ""
        )
    ).strip()

    match = re.search(
        r"(\d+)",
        sex_age
    )

    if not match:
        return None

    try:
        return int(
            match.group(1)
        )
    except ValueError:
        return None


def first_number(
    primary,
    secondary,
    *keys
):
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


def normalize_surface(value):
    value = str(
        value or ""
    ).strip()

    if "芝" in value:
        return "芝"

    if (
        "ダート" in value
        or value == "ダ"
    ):
        return "ダート"

    return value


def normalize_distance(value):
    try:
        return int(
            float(value)
        )
    except (TypeError, ValueError):
        return None


def get_analysis_rows(data):
    if not isinstance(data, dict):
        return []

    candidates = [
        data.get("analysis"),
        data.get("races"),
        data.get("past_races"),
        data.get("history"),
        data.get("race_analysis"),
    ]

    for candidate in candidates:
        if isinstance(candidate, list):
            return [
                row
                for row in candidate
                if isinstance(row, dict)
            ]

        if isinstance(candidate, dict):
            for key in (
                "races",
                "past_races",
                "history",
            ):
                rows = candidate.get(key)

                if isinstance(rows, list):
                    return [
                        row
                        for row in rows
                        if isinstance(row, dict)
                    ]

    return []


def get_row_surface(row):
    return normalize_surface(
        row.get("surface")
        or row.get("track_type")
        or row.get("course_type")
        or ""
    )


def get_row_distance(row):
    return normalize_distance(
        row.get("distance")
        or row.get("race_distance")
    )


def get_row_meeting(row):
    return str(
        row.get("meeting")
        or row.get("track")
        or row.get("racecourse")
        or row.get("course")
        or ""
    ).strip()


def get_row_performance_score(row):
    value = get_optional_number(
        row,
        "performance_score",
        "race_performance_score",
        "performance"
    )

    if value is None:
        return None

    if value > 1.5:
        value /= 100.0

    return value


def parse_passing_positions(value):
    if value is None:
        return []

    if isinstance(value, list):
        values = []

        for item in value:
            try:
                values.append(
                    int(item)
                )
            except (TypeError, ValueError):
                pass

        return values

    text = str(value)

    numbers = re.findall(
        r"\d+",
        text
    )

    positions = []

    for number in numbers:
        try:
            positions.append(
                int(number)
            )
        except ValueError:
            pass

    return positions


# =========================================================
# データ読み込み
#
# 調教は使用しない。
# =========================================================

race = load_json(
    "race.json"
)

ability_data = load_json(
    "runner_analysis.json"
)

previous_data = load_json(
    "previous_race_analysis.json"
)

pace_data = load_json(
    "pace_analysis.json"
)

blood_data = load_json(
    "race_bloodline_score.json"
)

track_data_raw = load_json(
    "track_condition.json"
)

day_bias_data_raw = load_json(
    "day_bias.json"
)

body_weight_data_raw = load_json(
    "body_weight.json"
)

runner_time_fit_raw = load_json(
    "runner_time_fit.json"
)


race_id = str(
    race.get(
        "race_id",
        ""
    )
).strip()

target_track = str(
    race.get(
        "track",
        ""
    )
).strip()

target_surface = normalize_surface(
    race.get(
        "surface",
        ""
    )
)

target_distance = normalize_distance(
    race.get(
        "distance"
    )
)


# =========================================================
# track_condition
# =========================================================

track_race_id = str(
    track_data_raw.get(
        "race_id",
        ""
    )
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
    day_bias_data_raw.get(
        "race_id",
        ""
    )
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
    runner_time_fit_data = (
        runner_time_fit_raw
    )
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
    ability_data.get(
        "horses",
        []
    )
)

previous_index = make_index(
    previous_data.get(
        "horses",
        []
    )
)

pace_index = make_index(
    pace_data.get(
        "horses",
        []
    )
)

blood_index = make_index(
    blood_data.get(
        "ranking",
        []
    )
)

body_weight_index = make_index(
    body_weight_data.get(
        "horses",
        []
    )
)

time_fit_index = make_index(
    runner_time_fit_data.get(
        "horses",
        []
    )
)


# =========================================================
# 展開
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
).strip()

leader_candidate_count = int(
    get_number(
        race_scenario,
        "leader_candidate_count",
        default=0
    )
)

front_candidate_count = int(
    get_number(
        race_scenario,
        "front_candidate_count",
        default=0
    )
)


# =========================================================
# 当日馬場
# =========================================================

def evaluate_track_condition(
    track,
    day_bias,
    running_style
):
    score = 0.0
    reasons = []

    style = str(
        running_style
        or "不明"
    ).strip()

    if track:
        condition = str(
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

        if condition:
            reasons.append(
                "馬場:" + condition
            )

        if cushion not in (
            None,
            ""
        ):
            reasons.append(
                "クッション値:"
                + str(cushion)
            )

        if (
            moisture_4 not in (
                None,
                ""
            )
            or moisture_finish not in (
                None,
                ""
            )
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

        return (
            0.0,
            reasons
        )

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
            "時計傾向:"
            + time_bias
        )

        reasons.append(
            "時計傾向単独では個体補正しない"
        )

    if inside_outside:
        reasons.append(
            "内外:"
            + inside_outside
        )

    if style_bias:
        reasons.append(
            "脚質傾向:"
            + style_bias
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

    return (
        score,
        reasons
    )


# =========================================================
# 時計環境
#
# 経験と適性を分離。
# 診断専用。
# =========================================================

def evaluate_time_fit(data):
    if not data:
        return {
            "adjustment": 0.0,
            "label": "未知数",
            "median_fit": None,
            "evaluated_count": 0,
            "reasons": [
                "時計環境データ未接続・補正なし"
            ],
        }

    label = str(
        data.get(
            "time_fit_label",
            "未知数"
        )
    ).strip() or "未知数"

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

    current_time_bias = str(
        data.get(
            "current_time_bias",
            ""
        )
    ).strip()

    unknown = bool(
        data.get(
            "unknown",
            True
        )
    )

    reasons = []

    if current_time_bias:
        reasons.append(
            "今回時計環境:"
            + current_time_bias
        )

    reasons.append(
        "時計環境経験判定:"
        + label
    )

    reasons.append(
        "時計環境評価過去走:"
        + str(evaluated_count)
        + "走"
    )

    if median_fit is not None:
        reasons.append(
            "時計環境一致度:"
            + format(
                clamp(
                    median_fit,
                    0.0,
                    1.0
                ),
                ".2f"
            )
        )

    if (
        unknown
        or evaluated_count <= 0
        or label == "未知数"
    ):
        reasons.append(
            "時計環境経験は未知数・減点なし"
        )

    else:
        reasons.append(
            "時計環境経験は診断のみ・数値補正なし"
        )

    return {
        "adjustment": 0.0,
        "label": label,
        "median_fit": median_fit,
        "evaluated_count": evaluated_count,
        "reasons": reasons,
    }


# =========================================================
# 馬体重・斤量
# =========================================================

def evaluate_body_weight(
    runner,
    body_fallback
):
    (
        body_weight,
        body_source
    ) = first_number(
        runner,
        body_fallback,
        "body_weight",
        "weight"
    )

    (
        change,
        change_source
    ) = first_number(
        runner,
        body_fallback,
        "body_weight_change",
        "weight_change",
        "change"
    )

    (
        carried_weight,
        carried_source
    ) = first_number(
        runner,
        body_fallback,
        "carried_weight",
        "burden_weight",
        "weight_carried",
        "jockey_weight"
    )

    age = get_age(
        runner
    )

    reasons = []
    adjustment = 0.0
    weight_ratio = None

    sources = {
        x
        for x in (
            body_source,
            change_source,
            carried_source,
        )
        if x
    }

    if (
        body_weight is None
        or body_weight <= 0
    ):
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
        + format(
            body_weight,
            ".0f"
        )
        + "kg"
    )

    if change is not None:
        reasons.append(
            "増減:"
            + format(
                change,
                "+.0f"
            )
            + "kg"
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

    if change is not None:
        abs_change = abs(
            change
        )

        if age == 2:

            if abs_change >= 20:
                reasons.append(
                    "2歳・大幅馬体変動・状態確認必要"
                )

            else:
                reasons.append(
                    "2歳・馬体増減単独では評価しない"
                )

        elif abs_change >= 20:
            reasons.append(
                "大幅馬体変動・状態確認必要"
            )

        else:
            reasons.append(
                "馬体増減単独では評価しない"
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
# 馬体 × 前走課題
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
        return (
            0.0,
            ["馬体重×課題:馬体重不明"]
        )

    if not previous_horse:
        return (
            0.0,
            ["馬体重×課題:前走解析不明"]
        )

    if not previous_horse.get(
        "previous_race_available",
        False
    ):
        return (
            0.0,
            ["馬体重×課題:前走データなし"]
        )

    if change is None:
        return (
            0.0,
            ["馬体重×課題:増減不明"]
        )

    previous = previous_horse.get(
        "previous_race",
        {}
    )

    issues = normalize_list(
        previous.get(
            "issues"
        )
    )

    overcoming = normalize_list(
        previous.get(
            "overcoming_materials"
        )
    )

    if not issues:
        return (
            0.0,
            ["馬体に接続する前走課題なし"]
        )

    issue_text = " ".join(
        issues
    )

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

        elif change > 0:
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
                    "2歳・回復方向候補だが成長分も考慮"
                )

            else:
                score += 0.4

                reasons.append(
                    "馬体増で回復方向"
                )

        elif change <= -6:
            score -= 0.3

            reasons.append(
                "さらに馬体減・課題継続注意"
            )

    if (
        not heavy_issue
        and not thin_issue
    ):
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
        previous.get(
            "positives"
        )
    )

    issues = normalize_list(
        previous.get(
            "issues"
        )
    )

    overcoming = normalize_list(
        previous.get(
            "overcoming_materials"
        )
    )

    unknowns = normalize_list(
        previous.get(
            "unknowns"
        )
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

    if (
        overcoming
        and issues
    ):
        resolution_ratio = min(
            len(overcoming)
            / max(
                len(issues),
                1
            ),
            1.0
        )

        overcoming_add = min(
            0.6
            + resolution_ratio * 0.9,
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

    elif overcoming:
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

    return (
        clamp(
            score,
            -1.3,
            1.8
        ),
        reasons,
        len(positives),
        len(issues),
        len(overcoming),
    )


# =========================================================
# 課題克服 → 今回発揮率
#
# 課題克服を最終点だけでなく
# 「今回能力を出せるか」へ接続する。
# =========================================================

def evaluate_issue_resolution_support(
    previous_horse
):
    if not previous_horse:
        return (
            0.0,
            False,
            ["課題克服→発揮率:前走解析不明"]
        )

    if not previous_horse.get(
        "previous_race_available",
        False
    ):
        return (
            0.0,
            False,
            ["課題克服→発揮率:前走データなし"]
        )

    previous = previous_horse.get(
        "previous_race",
        {}
    )

    issues = normalize_list(
        previous.get(
            "issues"
        )
    )

    overcoming = normalize_list(
        previous.get(
            "overcoming_materials"
        )
    )

    if (
        not issues
        or not overcoming
    ):
        return (
            0.0,
            False,
            ["課題克服→発揮率:接続材料なし"]
        )

    resolution_ratio = min(
        len(overcoming)
        / max(
            len(issues),
            1
        ),
        1.0
    )

    adjustment = (
        0.5
        + 1.5 * resolution_ratio
    )

    adjustment = clamp(
        adjustment,
        0.0,
        2.0
    )

    reasons = [
        "課題克服材料を今回発揮率へ接続",
        "課題克服率:"
        + format(
            resolution_ratio,
            ".2f"
        ),
        "課題克服発揮率補正:"
        + format(
            adjustment,
            "+.1f"
        )
        + "pt",
    ]

    return (
        adjustment,
        True,
        reasons
    )


# =========================================================
# 未知条件ガード
#
# 「実績なし」を「苦手」と扱わない。
#
# 芝/ダート未経験・距離未経験等が
# noise_flags に存在する場合、
#
# ・条件適性マイナスを遮断
# ・発揮率が85未満なら85まで戻す
#
# 未知をプラス評価するのではなく、
# 未知による過剰な減点だけを消す。
# =========================================================

def evaluate_unknown_condition_guard(
    noise_flags,
    original_performance_rate
):
    text = " ".join(
        normalize_list(
            noise_flags
        )
    )

    unknown_keywords = (
        "芝実績なし",
        "ダート実績なし",
        "距離実績なし",
        "今回距離実績なし",
        "コース実績なし",
        "今回条件実績なし",
        "初芝",
        "初ダート",
        "初距離",
    )

    condition_unknown = any(
        keyword in text
        for keyword in unknown_keywords
    )

    performance_floor = None
    reasons = []

    if condition_unknown:
        reasons.append(
            "今回条件の実績なしを未知数として処理"
        )

        reasons.append(
            "未知条件による条件適性マイナスを遮断"
        )

        if (
            original_performance_rate
            is not None
            and original_performance_rate < 85.0
        ):
            performance_floor = 85.0

            reasons.append(
                "未知条件による過剰減点防止:"
                "発揮率85%を下限"
            )

        else:
            reasons.append(
                "未知条件ガードによる発揮率補正不要"
            )

    else:
        reasons.append(
            "未知条件ガード対象なし"
        )

    return {
        "condition_unknown":
            condition_unknown,

        "performance_floor":
            performance_floor,

        "reasons":
            reasons,
    }


# =========================================================
# 今回条件への直接接続
#
# 単純な着順ではなく、
# 同コース・同距離・同馬場種別で
# 実際に能力を出した証拠を拾う。
#
# 実績なしは減点しない。
# =========================================================

def evaluate_condition_connection(
    ability
):
    rows = get_analysis_rows(
        ability
    )

    reasons = []

    if (
        not rows
        or not target_surface
        or target_distance is None
    ):
        return {
            "score": 0.0,
            "reproducibility": 0.0,
            "exact_count": 0,
            "same_distance_count": 0,
            "good_direct_count": 0,
            "evidence": False,
            "reproducibility_evidence": False,
            "reasons": [
                "今回条件への直接接続データなし・減点なし"
            ],
        }

    exact = []
    same_distance = []

    for row in rows:
        row_surface = get_row_surface(
            row
        )

        row_distance = get_row_distance(
            row
        )

        meeting = get_row_meeting(
            row
        )

        if (
            row_surface != target_surface
            or row_distance != target_distance
        ):
            continue

        same_distance.append(
            row
        )

        if (
            target_track
            and target_track in meeting
        ):
            exact.append(
                row
            )

    score = 0.0

    if exact:
        score += min(
            0.6
            + 0.25 * len(exact),
            1.4
        )

        reasons.append(
            "同コース同距離実績:"
            + str(len(exact))
            + "走"
        )

        direct_rows = exact

    elif same_distance:
        score += min(
            0.4
            + 0.20 * len(same_distance),
            1.0
        )

        reasons.append(
            "同馬場種別・同距離実績:"
            + str(len(same_distance))
            + "走"
        )

        direct_rows = same_distance

    else:
        direct_rows = []

        reasons.append(
            "同距離実績なし・減点なし"
        )

    good_direct_count = 0

    for row in direct_rows:
        performance_score = (
            get_row_performance_score(
                row
            )
        )

        if (
            performance_score is not None
            and performance_score >= 0.60
        ):
            good_direct_count += 1

    if good_direct_count > 0:
        direct_bonus = min(
            good_direct_count * 0.35,
            0.8
        )

        score += direct_bonus

        reasons.append(
            "今回条件で能力発揮確認:"
            + str(good_direct_count)
            + "走"
        )

    score = clamp(
        score,
        0.0,
        2.0
    )

    reproducibility = 0.0

    if len(exact) >= 2:
        reproducibility = (
            0.5
            + 0.25
            * (
                len(exact)
                - 1
            )
        )

        reproducibility = clamp(
            reproducibility,
            0.0,
            1.2
        )

        reasons.append(
            "同コース同距離で再現性確認"
        )

    elif len(same_distance) >= 2:
        reproducibility = (
            0.4
            + 0.20
            * (
                len(same_distance)
                - 1
            )
        )

        reproducibility = clamp(
            reproducibility,
            0.0,
            1.2
        )

        reasons.append(
            "同距離で再現性確認"
        )

    else:
        reasons.append(
            "再現性は未確認・減点なし"
        )

    return {
        "score":
            score,

        "reproducibility":
            reproducibility,

        "exact_count":
            len(exact),

        "same_distance_count":
            len(same_distance),

        "good_direct_count":
            good_direct_count,

        "evidence":
            bool(
                exact
                or same_distance
            ),

        "reproducibility_evidence":
            reproducibility > 0,

        "reasons":
            reasons,
    }


# =========================================================
# 距離延長への接続性
#
# 未経験距離そのものは減点しない。
#
# 近い短距離側のレースで
# ・一定以上のパフォーマンス
# ・道中で大きく位置を上げても維持
#
# が確認できた場合のみ、
# 長い距離へ接続可能な材料として扱う。
#
# 血統単独では判定しない。
# =========================================================

def evaluate_distance_transfer(
    ability
):
    rows = get_analysis_rows(
        ability
    )

    if (
        not rows
        or target_distance is None
        or target_distance <= 0
    ):
        return {
            "score": 0.0,
            "evidence": False,
            "candidate_count": 0,
            "reasons": [
                "距離延長接続データなし"
            ],
        }

    allowed_gap = max(
        400,
        int(
            target_distance * 0.20
        )
    )

    candidates = []

    for row in rows:
        row_distance = get_row_distance(
            row
        )

        row_surface = get_row_surface(
            row
        )

        if row_distance is None:
            continue

        if (
            target_surface
            and row_surface
            and row_surface != target_surface
        ):
            continue

        distance_gap = (
            target_distance
            - row_distance
        )

        if (
            distance_gap <= 0
            or distance_gap > allowed_gap
        ):
            continue

        performance_score = (
            get_row_performance_score(
                row
            )
        )

        passing = (
            row.get("passing")
            or row.get("passing_order")
            or row.get("corner_order")
            or row.get("corner_positions")
        )

        positions = parse_passing_positions(
            passing
        )

        position_gain = 0

        if len(positions) >= 2:
            start_position = (
                positions[0]
            )

            best_later_position = min(
                positions[1:]
            )

            position_gain = max(
                0,
                start_position
                - best_later_position
            )

        candidate_score = 0.0

        if (
            performance_score is not None
            and performance_score >= 0.55
        ):
            candidate_score += 0.4

        if (
            performance_score is not None
            and performance_score >= 0.70
        ):
            candidate_score += 0.3

        if position_gain >= 5:
            candidate_score += 0.6

        elif position_gain >= 3:
            candidate_score += 0.3

        if candidate_score > 0:
            candidates.append({
                "distance":
                    row_distance,

                "performance_score":
                    performance_score,

                "position_gain":
                    position_gain,

                "score":
                    candidate_score,
            })

    if not candidates:
        return {
            "score": 0.0,
            "evidence": False,
            "candidate_count": 0,
            "reasons": [
                "近距離実績から距離延長への明確な接続なし・減点なし"
            ],
        }

    best = max(
        candidates,
        key=lambda x: x["score"]
    )

    score = clamp(
        best["score"],
        0.0,
        1.3
    )

    reasons = [
        "距離延長への接続材料あり",
        "接続元距離:"
        + str(
            best["distance"]
        )
        + "m",
    ]

    if (
        best["performance_score"]
        is not None
    ):
        reasons.append(
            "接続元パフォーマンス:"
            + format(
                best[
                    "performance_score"
                ],
                ".2f"
            )
        )

    if (
        best["position_gain"]
        > 0
    ):
        reasons.append(
            "道中位置上昇:"
            + str(
                best[
                    "position_gain"
                ]
            )
        )

    return {
        "score":
            score,

        "evidence":
            True,

        "candidate_count":
            len(candidates),

        "reasons":
            reasons,
    }


# =========================================================
# 血統
# =========================================================

def evaluate_bloodline(
    data,
    condition_fit
):
    if not data:
        return (
            0.0,
            False,
            ["血統データ不明"]
        )

    raw_score = get_number(
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

    reasons = [
        "血統スコア"
        + format(
            raw_score,
            ".3f"
        ),

        "該当祖先"
        + str(matched)
        + "・プラス"
        + str(positive),

        "血統は今回条件への補助のみ",
    ]

    if condition_fit is None:
        reasons.append(
            "条件適性UNKNOWNのため血統補助適用なし"
        )

        return (
            0.0,
            False,
            reasons
        )

    if matched <= 0:
        reasons.append(
            "血統該当なし・ニュートラル"
        )

        return (
            0.0,
            False,
            reasons
        )

    if condition_fit < 45.0:

        if raw_score < 0:
            adjustment = clamp(
                raw_score,
                -0.4,
                0.0
            )

            reasons.append(
                "独立条件適性低め・血統マイナス補助のみ適用"
            )

            return (
                adjustment,
                adjustment != 0.0,
                reasons
            )

        reasons.append(
            "独立条件適性低め・血統プラスで反転させない"
        )

        return (
            0.0,
            False,
            reasons
        )

    if positive <= 0:
        adjustment = clamp(
            raw_score,
            -0.4,
            0.0
        )

        reasons.append(
            "プラス祖先なし・強い血統単独減点禁止"
        )

        return (
            adjustment,
            adjustment != 0.0,
            reasons
        )

    adjustment = clamp(
        raw_score,
        -0.8,
        0.8
    )

    reasons.append(
        "独立条件適性確認済み・血統を補助適用"
    )

    return (
        adjustment,
        adjustment != 0.0,
        reasons
    )


# =========================================================
# 展開シナリオ
#
# スロー・ミドル・ハイを最後まで保持。
#
# 基本シナリオ60%
# 他2シナリオ各20%
#
# 1つに決め打ちしない。
# =========================================================

def get_explicit_scenario_score(
    data,
    scenario
):
    keys = {
        "スロー": (
            "slow_score",
            "slow_adjustment",
        ),

        "ミドル": (
            "middle_score",
            "middle_adjustment",
        ),

        "ハイ": (
            "high_score",
            "high_adjustment",
        ),
    }

    return get_optional_number(
        data,
        *keys[scenario]
    )


def fallback_scenario_score(
    data,
    scenario
):
    style = str(
        data.get(
            "running_style",
            "不明"
        )
    ).strip()

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

    score = 0.0

    if scenario == "スロー":

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

    elif scenario == "ミドル":

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

    elif scenario == "ハイ":

        if style in (
            "差し",
            "中団",
            "中団後",
        ):
            score += 0.7

        elif style == "逃げ":
            score -= 0.5

    if (
        scenario in (
            "スロー",
            "ミドル",
        )
        and leader_candidate_count == 0
        and front_candidate_count <= 4
        and front_rate >= 0.50
    ):
        score += 0.3

    if (
        leader_candidate_count >= 3
        and style == "逃げ"
    ):
        score -= 0.3

    if back_rate >= 0.60:
        score -= 0.6

    return clamp(
        score,
        -1.5,
        1.5
    )


def evaluate_pace(data):
    if not data:
        return {
            "adjustment": 0.0,
            "slow": 0.0,
            "middle": 0.0,
            "high": 0.0,
            "reasons": [
                "展開データ不明"
            ],
        }

    style = str(
        data.get(
            "running_style",
            "不明"
        )
    ).strip()

    avg_final = get_number(
        data,
        "average_final_position",
        default=0.0
    )

    scenario_scores = {}

    for scenario in (
        "スロー",
        "ミドル",
        "ハイ",
    ):
        explicit = (
            get_explicit_scenario_score(
                data,
                scenario
            )
        )

        if explicit is None:
            score = (
                fallback_scenario_score(
                    data,
                    scenario
                )
            )

        else:
            score = clamp(
                explicit,
                -1.5,
                1.5
            )

        scenario_scores[
            scenario
        ] = score

    if base_pace in (
        "スロー",
        "ミドル",
        "ハイ",
    ):
        weights = {
            "スロー": 0.20,
            "ミドル": 0.20,
            "ハイ": 0.20,
        }

        weights[
            base_pace
        ] = 0.60

    else:
        weights = {
            "スロー": 1.0 / 3.0,
            "ミドル": 1.0 / 3.0,
            "ハイ": 1.0 / 3.0,
        }

    weighted = sum(
        scenario_scores[
            scenario
        ]
        * weights[
            scenario
        ]
        for scenario in (
            "スロー",
            "ミドル",
            "ハイ",
        )
    )

    weighted = clamp(
        weighted,
        -1.5,
        1.5
    )

    reasons = [
        "脚質:"
        + style,

        "基本展開:"
        + base_pace,

        "スロー:"
        + format(
            scenario_scores["スロー"],
            "+.2f"
        ),

        "ミドル:"
        + format(
            scenario_scores["ミドル"],
            "+.2f"
        ),

        "ハイ:"
        + format(
            scenario_scores["ハイ"],
            "+.2f"
        ),

        "展開加重:"
        + format(
            weighted,
            "+.2f"
        ),
    ]

    if avg_final > 0:
        reasons.append(
            "平均最終位置"
            + format(
                avg_final,
                ".2f"
            )
        )

    return {
        "adjustment":
            weighted,

        "slow":
            scenario_scores["スロー"],

        "middle":
            scenario_scores["ミドル"],

        "high":
            scenario_scores["ハイ"],

        "reasons":
            reasons,
    }


# =========================================================
# 能力 × 発揮率乖離
#
# 能力が高いだけで最終上位へ固定しない。
#
# 能力上位でも今回発揮率が明確に低ければ
# 最終順位側で小幅修正する。
# =========================================================

def evaluate_ability_performance_gap(
    ability_score,
    performance_rate
):
    if (
        ability_score is None
        or performance_rate is None
    ):
        return (
            0.0,
            []
        )

    adjustment = 0.0
    reasons = []

    if (
        ability_score >= 75.0
        and performance_rate < 82.0
    ):
        adjustment -= 1.0

        reasons.append(
            "能力上位だが今回発揮率82%未満"
        )

    if (
        ability_score >= 85.0
        and performance_rate < 80.0
    ):
        adjustment -= 0.7

        reasons.append(
            "高能力馬だが今回発揮率80%未満"
        )

    return (
        adjustment,
        reasons
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

    # -----------------------------------------------------
    # 能力
    # -----------------------------------------------------

    ability_score = get_optional_number(
        ability,
        "ability_score"
    )

    original_performance_rate = (
        get_optional_number(
            ability,
            "performance_rate"
        )
    )

    condition_fit = get_optional_number(
        ability,
        "condition_fit_score"
    )

    source_unknown = bool(
        ability.get(
            "unknown",
            False
        )
    )

    ability_known = (
        ability_score is not None
        and not source_unknown
    )

    performance_rate_known = (
        original_performance_rate
        is not None
        and ability_known
    )

    condition_fit_known = (
        condition_fit is not None
    )

    unknown = (
        not ability_known
    )

    noise_flags = normalize_list(
        ability.get(
            "noise_flags"
        )
    )

    running_style = str(
        pace.get(
            "running_style",
            "不明"
        )
    ).strip()

    # -----------------------------------------------------
    # 未知条件ガード
    # -----------------------------------------------------

    unknown_guard = (
        evaluate_unknown_condition_guard(
            noise_flags,
            original_performance_rate
        )
    )

    condition_unknown = (
        unknown_guard[
            "condition_unknown"
        ]
    )

    # -----------------------------------------------------
    # 馬場
    # -----------------------------------------------------

    (
        track_rate_adjustment,
        track_reasons
    ) = evaluate_track_condition(
        track_data,
        day_bias_data,
        running_style
    )

    # -----------------------------------------------------
    # 時計
    # -----------------------------------------------------

    time_fit_result = (
        evaluate_time_fit(
            time_fit_horse
        )
    )

    time_fit_adjustment = (
        time_fit_result[
            "adjustment"
        ]
    )

    # -----------------------------------------------------
    # 馬体
    # -----------------------------------------------------

    body_result = (
        evaluate_body_weight(
            runner,
            body_fallback
        )
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

    # -----------------------------------------------------
    # 前走
    # -----------------------------------------------------

    (
        previous_adj,
        previous_reasons,
        previous_positive_count,
        previous_issue_count,
        overcoming_count
    ) = evaluate_previous(
        previous_horse
    )

    # -----------------------------------------------------
    # 課題克服 → 発揮率
    # -----------------------------------------------------

    (
        issue_resolution_support,
        issue_resolution_evidence,
        issue_resolution_reasons
    ) = evaluate_issue_resolution_support(
        previous_horse
    )

    # -----------------------------------------------------
    # 今回条件への直接接続
    # -----------------------------------------------------

    condition_connection = (
        evaluate_condition_connection(
            ability
        )
    )

    condition_connection_score = (
        condition_connection[
            "score"
        ]
    )

    reproducibility_support = (
        condition_connection[
            "reproducibility"
        ]
    )

    # -----------------------------------------------------
    # 距離延長接続
    # -----------------------------------------------------

    distance_transfer = (
        evaluate_distance_transfer(
            ability
        )
    )

    distance_transfer_support = (
        distance_transfer[
            "score"
        ]
    )

    # -----------------------------------------------------
    # 展開
    # -----------------------------------------------------

    pace_result = (
        evaluate_pace(
            pace
        )
    )

    pace_adj = (
        pace_result[
            "adjustment"
        ]
    )

    # -----------------------------------------------------
    # 発揮率
    # -----------------------------------------------------

    if performance_rate_known:

        adjusted_performance_rate = (
            original_performance_rate
        )

        # 未知条件を苦手扱いしない
        performance_floor = (
            unknown_guard[
                "performance_floor"
            ]
        )

        if (
            performance_floor is not None
            and adjusted_performance_rate
            < performance_floor
        ):
            adjusted_performance_rate = (
                performance_floor
            )

        adjusted_performance_rate += (
            track_rate_adjustment
            + time_fit_adjustment
            + body_weight_rate_adjustment
            + body_issue_adjustment
            + issue_resolution_support
        )

        adjusted_performance_rate = clamp(
            adjusted_performance_rate,
            0.0,
            110.0
        )

    else:
        adjusted_performance_rate = None

    # -----------------------------------------------------
    # 能力 × 発揮率
    # -----------------------------------------------------

    if (
        ability_known
        and adjusted_performance_rate
        is not None
    ):
        base_performance = (
            ability_score
            * adjusted_performance_rate
            / 100.0
        )

    else:
        base_performance = None

    # -----------------------------------------------------
    # 条件適性
    #
    # UNKNOWNはニュートラル。
    # 実績なし由来の低条件適性もマイナス遮断。
    # -----------------------------------------------------

    effective_condition_fit = (
        None
        if condition_unknown
        else condition_fit
    )

    if (
        effective_condition_fit
        is not None
    ):
        condition_adjustment = clamp(
            (
                effective_condition_fit
                - 50.0
            )
            / 25.0,
            -2.0,
            2.0
        )

    else:
        condition_adjustment = 0.0

    # -----------------------------------------------------
    # 血統
    #
    # 未知条件なら血統単独加点禁止。
    # -----------------------------------------------------

    (
        blood_adj,
        blood_support_applied,
        blood_reasons
    ) = evaluate_bloodline(
        blood,
        effective_condition_fit
    )

    if effective_condition_fit is None:
        blood_adj = 0.0
        blood_support_applied = False

    # -----------------------------------------------------
    # 複数根拠チェック
    #
    # 大きな順位上昇は
    # 独立した根拠が2つ以上ある場合のみ。
    # -----------------------------------------------------

    promotion_evidence_count = 0

    if condition_connection[
        "evidence"
    ]:
        promotion_evidence_count += 1

    if condition_connection[
        "reproducibility_evidence"
    ]:
        promotion_evidence_count += 1

    if distance_transfer[
        "evidence"
    ]:
        promotion_evidence_count += 1

    if issue_resolution_evidence:
        promotion_evidence_count += 1

    raw_integration_support = (
        condition_connection_score
        + reproducibility_support
        + distance_transfer_support
    )

    if promotion_evidence_count >= 2:
        integration_adjustment = (
            raw_integration_support
        )

    elif promotion_evidence_count == 1:
        integration_adjustment = min(
            raw_integration_support,
            1.0
        )

    else:
        integration_adjustment = 0.0

    # -----------------------------------------------------
    # 能力 × 発揮率乖離
    # -----------------------------------------------------

    (
        ability_performance_gap_adjustment,
        ability_performance_gap_reasons
    ) = evaluate_ability_performance_gap(
        ability_score,
        adjusted_performance_rate
    )

    # -----------------------------------------------------
    # 穴警戒
    #
    # クムシラコ型を無理に順位上昇させない。
    #
    # 能力60未満
    # 発揮率92%以上
    # 独立根拠2未満
    #
    # → 最終点の強制上昇ではなく穴警戒。
    # -----------------------------------------------------

    hole_alert = bool(
        ability_known
        and ability_score is not None
        and ability_score < 60.0
        and adjusted_performance_rate
        is not None
        and adjusted_performance_rate >= 92.0
        and promotion_evidence_count < 2
    )

    # -----------------------------------------------------
    # 最終点
    # -----------------------------------------------------

    if base_performance is not None:

        final_score = (
            base_performance
            + condition_adjustment
            + previous_adj
            + pace_adj
            + blood_adj
            + integration_adjustment
            + ability_performance_gap_adjustment
        )

    else:
        final_score = None

    # -----------------------------------------------------
    # 理由
    # -----------------------------------------------------

    reasons = []

    if ability_known:
        reasons.append(
            "能力"
            + format(
                ability_score,
                ".1f"
            )
        )

    else:
        reasons.append(
            "能力UNKNOWN・架空の基準点を付与しない"
        )

    if (
        original_performance_rate
        is not None
    ):
        reasons.append(
            "元発揮率"
            + format(
                original_performance_rate,
                ".1f"
            )
            + "%"
        )

    else:
        reasons.append(
            "元発揮率UNKNOWN・100%を仮置きしない"
        )

    reasons.append(
        "馬場補正"
        + format(
            track_rate_adjustment,
            "+.1f"
        )
        + "pt"
    )

    reasons.append(
        "時計環境補正"
        + format(
            time_fit_adjustment,
            "+.1f"
        )
        + "pt"
    )

    reasons.append(
        "馬体・斤量補正"
        + format(
            body_weight_rate_adjustment,
            "+.1f"
        )
        + "pt"
    )

    reasons.append(
        "馬体×課題補正"
        + format(
            body_issue_adjustment,
            "+.1f"
        )
        + "pt"
    )

    reasons.append(
        "課題克服→発揮率"
        + format(
            issue_resolution_support,
            "+.1f"
        )
        + "pt"
    )

    if (
        adjusted_performance_rate
        is not None
    ):
        reasons.append(
            "補正後発揮率"
            + format(
                adjusted_performance_rate,
                ".1f"
            )
            + "%"
        )

    else:
        reasons.append(
            "補正後発揮率UNKNOWN"
        )

    if condition_unknown:
        reasons.append(
            "条件適性は実績なし由来の未知数としてニュートラル"
        )

    elif condition_fit_known:
        reasons.append(
            "条件適性"
            + format(
                condition_fit,
                ".1f"
            )
        )

    else:
        reasons.append(
            "条件適性UNKNOWN"
        )

    reasons.append(
        "今回条件接続"
        + format(
            condition_connection_score,
            "+.2f"
        )
    )

    reasons.append(
        "再現性補助"
        + format(
            reproducibility_support,
            "+.2f"
        )
    )

    reasons.append(
        "距離延長接続"
        + format(
            distance_transfer_support,
            "+.2f"
        )
    )

    reasons.append(
        "独立上昇根拠:"
        + str(
            promotion_evidence_count
        )
        + "件"
    )

    reasons.append(
        "統合補正"
        + format(
            integration_adjustment,
            "+.2f"
        )
    )

    if (
        ability_performance_gap_adjustment
        != 0
    ):
        reasons.append(
            "能力×発揮率乖離補正"
            + format(
                ability_performance_gap_adjustment,
                "+.1f"
            )
        )

    if hole_alert:
        reasons.append(
            "高発揮率だが独立上昇根拠不足・穴警戒に留める"
        )

    reasons.extend(
        unknown_guard[
            "reasons"
        ]
    )

    reasons.extend(
        track_reasons
    )

    reasons.extend(
        time_fit_result[
            "reasons"
        ]
    )

    reasons.extend(
        body_result[
            "reasons"
        ]
    )

    reasons.extend(
        body_issue_reasons
    )

    reasons.extend(
        previous_reasons
    )

    reasons.extend(
        issue_resolution_reasons
    )

    reasons.extend(
        condition_connection[
            "reasons"
        ]
    )

    reasons.extend(
        distance_transfer[
            "reasons"
        ]
    )

    reasons.extend(
        pace_result[
            "reasons"
        ]
    )

    reasons.extend(
        ability_performance_gap_reasons
    )

    reasons.extend(
        blood_reasons
    )

    if unknown:
        reasons.append(
            "能力未知数・減点なし"
        )

        reasons.append(
            "能力不明のため最終スコア・順位を生成しない"
        )

    results.append({
        "horse_id":
            get_id(runner),

        "horse_number":
            get_number_string(runner),

        "horse_name":
            get_name(runner),

        "ability_known":
            ability_known,

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

        "issue_resolution_performance_adjustment":
            round1(
                issue_resolution_support
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
            round1(
                body_result[
                    "body_weight"
                ]
            ),

        "body_weight_change":
            round1(
                body_result[
                    "change"
                ]
            ),

        "carried_weight":
            round1(
                body_result[
                    "carried_weight"
                ]
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

        "condition_unknown":
            condition_unknown,

        "condition_adjustment":
            round1(
                condition_adjustment
            ),

        "condition_connection_score":
            round1(
                condition_connection_score
            ),

        "condition_exact_count":
            condition_connection[
                "exact_count"
            ],

        "condition_same_distance_count":
            condition_connection[
                "same_distance_count"
            ],

        "condition_good_direct_count":
            condition_connection[
                "good_direct_count"
            ],

        "reproducibility_support":
            round1(
                reproducibility_support
            ),

        "distance_transfer_support":
            round1(
                distance_transfer_support
            ),

        "distance_transfer_candidate_count":
            distance_transfer[
                "candidate_count"
            ],

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

        "scenario_performance": {
            "slow":
                round1(
                    pace_result[
                        "slow"
                    ]
                ),

            "middle":
                round1(
                    pace_result[
                        "middle"
                    ]
                ),

            "high":
                round1(
                    pace_result[
                        "high"
                    ]
                ),

            "weighted":
                round1(
                    pace_adj
                ),
        },

        "running_style":
            running_style,

        "promotion_evidence_count":
            promotion_evidence_count,

        "integration_adjustment":
            round1(
                integration_adjustment
            ),

        "ability_performance_gap_adjustment":
            round1(
                ability_performance_gap_adjustment
            ),

        "hole_alert":
            hole_alert,

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

        "bloodline_support_applied":
            blood_support_applied,

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

        "rank":
            None,

        "judgement":
            "",
    })


# =========================================================
# ランキング
# =========================================================

known_results = [
    horse
    for horse in results
    if (
        horse[
            "ability_known"
        ]
        and horse[
            "final_score"
        ] is not None
    )
]

unknown_results = [
    horse
    for horse in results
    if not (
        horse[
            "ability_known"
        ]
        and horse[
            "final_score"
        ] is not None
    )
]


known_results.sort(
    key=lambda x: (
        x["final_score"],
        (
            x["ability_score"]
            if x[
                "ability_score"
            ] is not None
            else -9999
        ),
    ),
    reverse=True
)


for rank, horse in enumerate(
    known_results,
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

    if horse[
        "hole_alert"
    ]:
        judgement += "/穴警戒"

    if horse[
        "noise_flags"
    ]:
        judgement += "/注意"

    horse[
        "judgement"
    ] = judgement


unknown_results.sort(
    key=lambda x: (
        horse_number_sort_value(
            x[
                "horse_number"
            ]
        ),
        x[
            "horse_name"
        ],
    )
)


for horse in unknown_results:
    horse[
        "rank"
    ] = None

    horse[
        "judgement"
    ] = "能力不明/未知数"


results = (
    known_results
    + unknown_results
)


# =========================================================
# 接続状況
# =========================================================

ability_record_connected = sum(
    1
    for runner in runners
    if find_horse(
        ability_index,
        runner
    )
)

ability_known_count = sum(
    1
    for horse in results
    if horse[
        "ability_known"
    ]
)

ability_unknown_count = (
    len(results)
    - ability_known_count
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

bloodline_effective_count = sum(
    1
    for horse in results
    if horse[
        "bloodline_adjustment"
    ] != 0
)

bloodline_blocked_unknown_condition_count = sum(
    1
    for horse in results
    if (
        horse[
            "condition_unknown"
        ]
        and horse[
            "bloodline_adjustment"
        ] == 0
    )
)

condition_connection_effective_count = sum(
    1
    for horse in results
    if horse[
        "condition_connection_score"
    ] > 0
)

reproducibility_effective_count = sum(
    1
    for horse in results
    if horse[
        "reproducibility_support"
    ] > 0
)

distance_transfer_effective_count = sum(
    1
    for horse in results
    if horse[
        "distance_transfer_support"
    ] > 0
)

issue_resolution_effective_count = sum(
    1
    for horse in results
    if horse[
        "issue_resolution_performance_adjustment"
    ] > 0
)

hole_alert_count = sum(
    1
    for horse in results
    if horse[
        "hole_alert"
    ]
)

unknown_condition_guard_count = sum(
    1
    for horse in results
    if horse[
        "condition_unknown"
    ]
)


# =========================================================
# JSON
# =========================================================

output = {
    "updated_at":
        now_jst(),

    "race_id":
        race_id,

    "analysis_version":
        "alignment_v2",

    "track_condition": {
        "source_available":
            bool(
                track_data_raw
            ),

        "race_id_matched":
            track_race_id_matched,

        "source_race_id":
            track_race_id,

        "applied":
            bool(
                track_data
            ),

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
            bool(
                day_bias_data_raw
            ),

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
            bool(
                day_bias_data
            ),

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
            bool(
                runner_time_fit_raw
            ),

        "source_race_id":
            time_fit_race_id,

        "race_id_matched":
            time_fit_race_id_matched,

        "future_safe":
            time_fit_future_safe,

        "leak_check_passed":
            time_fit_leak_safe,

        "applied":
            bool(
                runner_time_fit_data
            ),

        "scoring_applied":
            False,

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
            bool(
                body_weight_data_raw
            ),

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

        "scenario_weighting": {
            "base":
                0.60,

            "alternative_1":
                0.20,

            "alternative_2":
                0.20,
        },
    },

    "method": {
        "alignment_version":
            "v2",

        "ability_and_performance_rate_separated":
            True,

        "unknown_ability_not_imputed":
            True,

        "unknown_performance_rate_not_imputed":
            True,

        "unknown_ability_not_ranked":
            True,

        "unknown_not_penalized":
            True,

        "unknown_condition_guard_enabled":
            True,

        "unknown_condition_performance_floor":
            85.0,

        "unknown_condition_negative_fit_blocked":
            True,

        "final_score_requires_known_ability":
            True,

        "direct_condition_connection_enabled":
            True,

        "reproducibility_support_enabled":
            True,

        "distance_transfer_support_enabled":
            True,

        "distance_unknown_not_penalized":
            True,

        "issue_resolution_connected_to_performance_rate":
            True,

        "multiple_pace_scenarios_retained":
            True,

        "base_scenario_weight":
            0.60,

        "alternative_scenario_weight":
            0.20,

        "large_promotion_requires_multiple_evidence":
            True,

        "hole_alert_separated_from_forced_promotion":
            True,

        "ability_performance_gap_checked":
            True,

        "bloodline_cannot_create_ability_ranking":
            True,

        "bloodline_is_condition_support_only":
            True,

        "bloodline_requires_known_condition_fit":
            True,

        "bloodline_cannot_reverse_unknown_condition":
            True,

        "bloodline_raw_score_is_diagnostic":
            True,

        "track_affects_performance_rate_not_ability":
            True,

        "day_bias_affects_performance_rate_not_ability":
            True,

        "time_bias_not_used_as_standalone_horse_score":
            True,

        "time_fit_is_diagnostic_only":
            True,

        "time_fit_exposure_not_equal_suitability":
            True,

        "time_fit_requires_matching_race_id":
            True,

        "time_fit_requires_no_future_race_usage":
            True,

        "time_fit_requires_leak_check":
            True,

        "time_fit_unknown_not_penalized":
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

        "bloodline_strong_negative_without_positive_match_prohibited":
            True,

        "popularity_not_used":
            True,

        "internet_prediction_not_used":
            True,

        "training_data_used":
            False,

        "training_affects_score":
            False,
    },

    "summary": {
        "runner_count":
            len(
                results
            ),

        "ranked_count":
            ability_known_count,

        "unranked_unknown_count":
            ability_unknown_count,

        "ability_record_connected_count":
            ability_record_connected,

        "ability_known_count":
            ability_known_count,

        "ability_unknown_count":
            ability_unknown_count,

        "previous_connected_count":
            previous_connected,

        "pace_connected_count":
            pace_connected,

        "bloodline_connected_count":
            blood_connected,

        "bloodline_effective_count":
            bloodline_effective_count,

        "bloodline_blocked_unknown_condition_count":
            bloodline_blocked_unknown_condition_count,

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
            bool(
                track_data_raw
            ),

        "track_race_id_matched":
            track_race_id_matched,

        "track_applied":
            bool(
                track_data
            ),

        "day_bias_source_available":
            bool(
                day_bias_data_raw
            ),

        "day_bias_race_id_matched":
            day_bias_race_id_matched,

        "day_bias_future_safe":
            day_bias_future_safe,

        "day_bias_applied":
            bool(
                day_bias_data
            ),

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

        "condition_connection_effective_count":
            condition_connection_effective_count,

        "reproducibility_effective_count":
            reproducibility_effective_count,

        "distance_transfer_effective_count":
            distance_transfer_effective_count,

        "issue_resolution_effective_count":
            issue_resolution_effective_count,

        "unknown_condition_guard_count":
            unknown_condition_guard_count,

        "hole_alert_count":
            hole_alert_count,

        "training_used":
            False,
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
# 最終自己検査
# =========================================================

for horse in results:

    if (
        horse[
            "condition_unknown"
        ]
        and horse[
            "bloodline_adjustment"
        ] != 0
    ):
        raise RuntimeError(
            "bloodline standalone adjustment "
            "on unknown condition: "
            + horse[
                "horse_name"
            ]
        )

    if (
        horse[
            "promotion_evidence_count"
        ] == 0
        and horse[
            "integration_adjustment"
        ] != 0
    ):
        raise RuntimeError(
            "integration adjustment without evidence: "
            + horse[
                "horse_name"
            ]
        )

    if (
        horse[
            "promotion_evidence_count"
        ] == 1
        and horse[
            "integration_adjustment"
        ] > 1.0
    ):
        raise RuntimeError(
            "single evidence promotion exceeded cap: "
            + horse[
                "horse_name"
            ]
        )

    if not horse[
        "ability_known"
    ]:

        if horse[
            "ability_score"
        ] is not None:
            raise RuntimeError(
                "UNKNOWN ability was imputed: "
                + horse[
                    "horse_name"
                ]
            )

        if horse[
            "final_score"
        ] is not None:
            raise RuntimeError(
                "UNKNOWN horse received final score: "
                + horse[
                    "horse_name"
                ]
            )

        if horse[
            "rank"
        ] is not None:
            raise RuntimeError(
                "UNKNOWN horse was ranked: "
                + horse[
                    "horse_name"
                ]
            )


# =========================================================
# ログ
# =========================================================

print(
    "===== FINAL ANALYSIS alignment_v2 ====="
)

print(
    "race id:",
    race_id
)

print(
    "target:",
    target_track,
    target_surface,
    target_distance
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
    bool(
        day_bias_data
    )
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
    bool(
        runner_time_fit_data
    )
)

print(
    "training:",
    "DISABLED"
)

print(
    "ability records:",
    ability_record_connected,
    "/",
    len(
        results
    )
)

print(
    "ability known:",
    ability_known_count,
    "/",
    len(
        results
    )
)

print(
    "ability unknown:",
    ability_unknown_count,
    "/",
    len(
        results
    )
)

print(
    "previous:",
    previous_connected,
    "/",
    len(
        results
    )
)

print(
    "pace:",
    pace_connected,
    "/",
    len(
        results
    )
)

print(
    "bloodline:",
    blood_connected,
    "/",
    len(
        results
    )
)

print(
    "condition connection:",
    condition_connection_effective_count,
    "/",
    len(
        results
    )
)

print(
    "reproducibility:",
    reproducibility_effective_count,
    "/",
    len(
        results
    )
)

print(
    "distance transfer:",
    distance_transfer_effective_count,
    "/",
    len(
        results
    )
)

print(
    "issue resolution:",
    issue_resolution_effective_count,
    "/",
    len(
        results
    )
)

print(
    "unknown condition guard:",
    unknown_condition_guard_count,
    "/",
    len(
        results
    )
)

print(
    "hole alerts:",
    hole_alert_count,
    "/",
    len(
        results
    )
)

print()


if ability_known_count == 0:

    print(
        "FINAL RANKING: no known ability data"
    )

    print(
        "UNKNOWN horses are intentionally not ranked."
    )

    print()


for horse in results:

    print(
        (
            horse[
                "rank"
            ]
            if horse[
                "rank"
            ] is not None
            else "-"
        ),

        horse[
            "horse_number"
        ],

        horse[
            "horse_name"
        ],

        "最終",
        (
            horse[
                "final_score"
            ]
            if horse[
                "final_score"
            ] is not None
            else "UNKNOWN"
        ),

        "能力",
        (
            horse[
                "ability_score"
            ]
            if horse[
                "ability_score"
            ] is not None
            else "UNKNOWN"
        ),

        "発揮率",
        (
            horse[
                "performance_rate"
            ]
            if horse[
                "performance_rate"
            ] is not None
            else "UNKNOWN"
        ),

        "条件接続",
        horse[
            "condition_connection_score"
        ],

        "再現性",
        horse[
            "reproducibility_support"
        ],

        "距離接続",
        horse[
            "distance_transfer_support"
        ],

        "展開",
        horse[
            "pace_adjustment"
        ],

        "根拠数",
        horse[
            "promotion_evidence_count"
        ],

        "統合",
        horse[
            "integration_adjustment"
        ],

        "穴",
        horse[
            "hole_alert"
        ],

        "判定",
        horse[
            "judgement"
        ]
    )
