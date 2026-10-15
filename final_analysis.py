import json
import os
from datetime import datetime, timezone, timedelta

OUTPUT_FILE = "final_analysis.json"


def load_json(filename):
    if not os.path.exists(filename):
        return {}

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


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

        if value is None or value == "":
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            continue

    return default


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
        "number": by_number
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


def normalize_list(value):
    if value is None:
        return []

    if isinstance(value, list):
        return value

    if isinstance(value, str):
        value = value.strip()
        return [value] if value else []

    return [str(value)]


# -------------------------
# データ読み込み
# -------------------------

race = load_json("race.json")
ability_data = load_json("runner_analysis.json")
previous_data = load_json("previous_race_analysis.json")
pace_data = load_json("pace_analysis.json")
blood_data = load_json("race_bloodline_score.json")


runners = (
    race.get("horses")
    or race.get("runners")
    or race.get("entries")
    or []
)

ability_index = make_index(
    ability_data.get("horses", [])
)

previous_index = make_index(
    previous_data.get("horses", [])
)

pace_index = make_index(
    pace_data.get("horses", [])
)

# 血統だけ ranking 配列
blood_index = make_index(
    blood_data.get("ranking", [])
)


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


# -------------------------
# 前走処理
# -------------------------

def evaluate_previous(data):
    if not data:
        return 0.0, ["前走解析データ不明"]

    if not data.get(
        "previous_race_available",
        False
    ):
        return 0.0, ["前走データなし・減点なし"]

    positives = normalize_list(
        data.get("positives")
    )

    issues = normalize_list(
        data.get("issues")
    )

    overcoming = normalize_list(
        data.get("overcoming_materials")
    )

    score = 0.0
    reasons = []

    # 前走の良い内容
    if positives:
        add = min(
            len(positives) * 0.35,
            1.0
        )

        score += add

        reasons.append(
            f"前走プラス材料{len(positives)}件"
        )

    # 課題そのものは軽いマイナス
    # 着順だけでは減点しない
    if issues:
        minus = min(
            len(issues) * 0.30,
            1.2
        )

        score -= minus

        reasons.append(
            f"前走課題{len(issues)}件"
        )

    # 課題克服材料を最重視
    if overcoming:
        add = min(
            len(overcoming) * 0.80,
            2.4
        )

        score += add

        reasons.append(
            f"課題克服材料{len(overcoming)}件"
        )

    if not reasons:
        reasons.append(
            "前走補正材料なし"
        )

    return (
        clamp(score, -1.5, 2.5),
        reasons
    )


# -------------------------
# 血統
# -------------------------

def evaluate_bloodline(data):
    if not data:
        return 0.0, ["血統データ不明"]

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

    # 血統は能力そのものではなく
    # 今回条件への適性補助
    adjustment = clamp(
        score * 4.0,
        -2.0,
        2.0
    )

    reasons = [
        f"血統スコア{score:.3f}",
        f"該当祖先{matched}・プラス{positive}"
    ]

    return adjustment, reasons


# -------------------------
# 展開
# -------------------------

def evaluate_pace(data):
    if not data:
        return 0.0, ["展開データ不明"]

    style = str(
        data.get(
            "running_style",
            "不明"
        )
    )

    escape_rate = get_number(
        data,
        "escape_rate",
        default=0.0
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
        f"脚質:{style}",
        f"基本展開:{base_pace}"
    ]

    # 今回はミドルが基本。
    # 展開は能力点ではなく
    # 「能力を出しやすいか」の小補正。

    if base_pace == "ミドル":
        if style in (
            "先行",
            "好位",
            "中団"
        ):
            score += 0.5

        elif style in (
            "中団後",
            "後方"
        ):
            score -= 0.3

    elif base_pace == "スロー":
        if style in (
            "逃げ",
            "先行",
            "好位"
        ):
            score += 0.7

        elif style in (
            "後方",
            "中団後"
        ):
            score -= 0.7

    elif base_pace == "ハイ":
        if style in (
            "差し",
            "中団",
            "中団後"
        ):
            score += 0.7

        if style == "逃げ":
            score -= 0.5

    # ハナ争いが激しくない今回、
    # 先行経験はわずかに安定材料。
    if (
        leader_candidate_count == 0
        and front_candidate_count <= 4
        and front_rate >= 0.50
    ):
        score += 0.3
        reasons.append(
            "先行位置を取りやすい構成"
        )

    # 後方依存は発揮リスク。
    if back_rate >= 0.60:
        score -= 0.6
        reasons.append(
            "後方位置依存注意"
        )

    if avg_final > 0:
        reasons.append(
            f"平均最終位置{avg_final:.2f}"
        )

    return (
        clamp(score, -1.5, 1.5),
        reasons
    )


# -------------------------
# 最終統合
# -------------------------

results = []


for runner in runners:

    ability = find_horse(
        ability_index,
        runner
    )

    previous = find_horse(
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

    ability_score = get_number(
        ability,
        "ability_score",
        default=50.0
    )

    performance_rate = get_number(
        ability,
        "performance_rate",
        default=100.0
    )

    condition_fit = get_number(
        ability,
        "condition_fit_score",
        default=50.0
    )

    # 能力と今回発揮率を分離
    base_performance = (
        ability_score
        * performance_rate
        / 100.0
    )

    # 条件適性は二重評価防止のため最大±2
    condition_adjustment = clamp(
        (condition_fit - 50.0) / 25.0,
        -2.0,
        2.0
    )

    previous_adj, previous_reasons = (
        evaluate_previous(previous)
    )

    pace_adj, pace_reasons = (
        evaluate_pace(pace)
    )

    blood_adj, blood_reasons = (
        evaluate_bloodline(blood)
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
        f"能力{ability_score:.1f}",
        f"発揮率{performance_rate:.1f}%",
        f"条件適性{condition_fit:.1f}"
    ]

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
        "horse_id": get_id(runner),
        "horse_number":
            get_number_string(runner),
        "horse_name":
            get_name(runner),

        "ability_score":
            round1(ability_score),

        "performance_rate":
            round1(performance_rate),

        "base_performance":
            round1(base_performance),

        "condition_fit_score":
            round1(condition_fit),

        "condition_adjustment":
            round1(condition_adjustment),

        "previous_race_adjustment":
            round1(previous_adj),

        "pace_adjustment":
            round1(pace_adj),

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
            round1(blood_adj),

        "final_score":
            round1(final_score),

        "running_style":
            str(
                pace.get(
                    "running_style",
                    "不明"
                )
            ),

        "unknown": unknown,

        "noise_flags":
            noise_flags,

        "reasons":
            reasons
    })


results.sort(
    key=lambda x: (
        x["final_score"],
        x["ability_score"]
    ),
    reverse=True
)


for i, horse in enumerate(
    results,
    start=1
):
    horse["rank"] = i

    if i <= 2:
        judgement = "最上位"

    elif i <= 4:
        judgement = "上位"

    elif i <= 7:
        judgement = "相手候補"

    elif i <= 9:
        judgement = "押さえ"

    else:
        judgement = "低評価"

    if horse["noise_flags"]:
        judgement += "/注意"

    horse["judgement"] = judgement


output = {
    "updated_at": now_jst(),

    "race_id": str(
        race.get(
            "race_id",
            ""
        )
    ),

    "race_scenario": {
        "base_pace": base_pace,
        "leader_candidate_count":
            leader_candidate_count,
        "front_candidate_count":
            front_candidate_count
    },

    "method": {
        "ability_and_performance_rate_separated":
            True,

        "previous_finish_not_used_alone":
            True,

        "previous_issue_resolution_emphasized":
            True,

        "bloodline_is_condition_support_only":
            True,

        "pace_is_performance_adjustment_only":
            True,

        "unknown_not_penalized":
            True,

        "popularity_not_used":
            True,

        "internet_prediction_not_used":
            True,

        "training_not_required":
            True
    },

    "summary": {
        "runner_count":
            len(results),

        "ranked_count":
            len(results),

        "ability_connected_count":
            sum(
                1 for runner in runners
                if find_horse(
                    ability_index,
                    runner
                )
            ),

        "previous_connected_count":
            sum(
                1 for runner in runners
                if find_horse(
                    previous_index,
                    runner
                )
            ),

        "pace_connected_count":
            sum(
                1 for runner in runners
                if find_horse(
                    pace_index,
                    runner
                )
            ),

        "bloodline_connected_count":
            sum(
                1 for runner in runners
                if find_horse(
                    blood_index,
                    runner
                )
            )
    },

    "ranking": results
}


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


print("===== FINAL ANALYSIS =====")

print(
    "ability:",
    output["summary"][
        "ability_connected_count"
    ],
    "/",
    len(results)
)

print(
    "previous:",
    output["summary"][
        "previous_connected_count"
    ],
    "/",
    len(results)
)

print(
    "pace:",
    output["summary"][
        "pace_connected_count"
    ],
    "/",
    len(results)
)

print(
    "bloodline:",
    output["summary"][
        "bloodline_connected_count"
    ],
    "/",
    len(results)
)

for horse in results:
    print(
        horse["rank"],
        horse["horse_number"],
        horse["horse_name"],
        horse["final_score"],
        "前走",
        horse["previous_race_adjustment"],
        "展開",
        horse["pace_adjustment"],
        "血統",
        horse["bloodline_adjustment"]
    )
