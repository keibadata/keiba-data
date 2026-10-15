import json
import os
from datetime import datetime, timezone, timedelta

OUTPUT_FILE = "final_analysis.json"


def load_json(filename):
    if not os.path.exists(filename):
        return None

    with open(filename, "r", encoding="utf-8") as f:
        return json.load(f)


def clamp(value, low, high):
    return max(low, min(high, value))


def round1(value):
    return round(float(value), 1)


def horse_key(horse):
    horse_id = str(horse.get("horse_id", "")).strip()
    if horse_id:
        return ("id", horse_id)

    return (
        "name",
        str(horse.get("horse_name", "")).strip()
    )


def index_horses(data):
    result = {}

    if not data:
        return result

    for horse in data.get("horses", []):
        result[horse_key(horse)] = horse

    return result


def get_number(horse, *keys, default=0):
    for key in keys:
        value = horse.get(key)

        if value is None or value == "":
            continue

        try:
            return float(value)
        except (TypeError, ValueError):
            pass

    return default


def find_horse(index, base):
    key = horse_key(base)

    if key in index:
        return index[key]

    name = str(base.get("horse_name", "")).strip()

    for horse in index.values():
        if str(horse.get("horse_name", "")).strip() == name:
            return horse

    return {}


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


race = load_json("race.json") or {}
ability_data = load_json("runner_analysis.json") or {}
blood_data = load_json("race_bloodline_score.json") or {}

previous_data = (
    load_json("previous_race_analysis.json")
    or load_json("previous_race.json")
    or load_json("previous_analysis.json")
    or {}
)

pace_data = (
    load_json("pace_analysis.json")
    or load_json("scenario_analysis.json")
    or load_json("race_scenario.json")
    or {}
)


ability_index = index_horses(ability_data)
blood_index = index_horses(blood_data)
previous_index = index_horses(previous_data)
pace_index = index_horses(pace_data)


runners = (
    race.get("horses")
    or race.get("runners")
    or race.get("entries")
    or []
)


def evaluate_previous(previous):
    """
    前走着順そのものでは加減点しない。
    客観的なプラス材料・課題・克服材料のみを見る。
    """

    if not previous:
        return 0.0, ["前走詳細不明"]

    positives = previous.get("positives") or []
    issues = previous.get("issues") or []
    overcoming = previous.get("overcoming_materials") or []

    score = 0.0
    reasons = []

    # プラス材料は軽く評価
    if positives:
        score += min(len(positives) * 0.4, 1.2)
        reasons.append(
            f"前走プラス材料{len(positives)}件"
        )

    # 課題があるだけでは大幅減点しない
    if issues:
        score -= min(len(issues) * 0.35, 1.4)
        reasons.append(
            f"前走課題{len(issues)}件"
        )

    # 克服材料を最重要視
    if overcoming:
        score += min(len(overcoming) * 0.8, 2.4)
        reasons.append(
            f"課題克服材料{len(overcoming)}件"
        )

    return clamp(score, -2.0, 3.0), reasons


def evaluate_pace(pace):
    """
    展開は独立した能力点ではなく、
    今回能力を出しやすいかどうかの補正。
    """

    if not pace:
        return 0.0, ["展開適性不明"]

    score = 0.0
    reasons = []

    style = str(
        pace.get("running_style", "")
    )

    slow = get_number(
        pace,
        "slow_score",
        "scenario_slow_score",
        default=0
    )

    middle = get_number(
        pace,
        "middle_score",
        "scenario_middle_score",
        default=0
    )

    high = get_number(
        pace,
        "high_score",
        "scenario_high_score",
        default=0
    )

    base_pace = str(
        pace_data.get("race_scenario", {}).get(
            "base_pace",
            "ミドル"
        )
    )

    if base_pace == "スロー":
        scenario_value = slow
    elif base_pace == "ハイ":
        scenario_value = high
    else:
        scenario_value = middle

    # JSONに数値シナリオがある場合のみ軽く反映
    if scenario_value:
        score += clamp(
            scenario_value / 20.0,
            -2.0,
            2.0
        )

    if style:
        reasons.append(
            f"脚質:{style}"
        )

    reasons.append(
        f"基本展開:{base_pace}"
    )

    # 後方依存は能力減点ではなく発揮リスク
    noise = pace.get("noise_flags") or []

    if isinstance(noise, str):
        noise = [noise]

    if any(
        "後方" in str(x)
        for x in noise
    ):
        score -= 0.8
        reasons.append("後方位置依存")

    return clamp(score, -2.0, 2.0), reasons


def blood_adjustment(blood):
    """
    血統単独で能力を上げない。
    条件適性の補助として最大±2点。
    """

    if not blood:
        return 0.0, ["血統データ不明"]

    raw = get_number(
        blood,
        "bloodline_score",
        "score",
        default=0
    )

    adjustment = clamp(raw * 4.0, -2.0, 2.0)

    if abs(adjustment) < 0.05:
        return 0.0, ["血統補正なし"]

    if adjustment > 0:
        return adjustment, [
            f"条件血統+{round1(adjustment)}"
        ]

    return adjustment, [
        f"条件血統{round1(adjustment)}"
    ]


results = []


for runner in runners:
    ability = find_horse(
        ability_index,
        runner
    )

    blood = find_horse(
        blood_index,
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

    ability_score = get_number(
        ability,
        "ability_score",
        default=50
    )

    performance_rate = get_number(
        ability,
        "performance_rate",
        default=100
    )

    condition_fit = get_number(
        ability,
        "condition_fit_score",
        default=50
    )

    # 能力と発揮率を分離
    base_performance = (
        ability_score
        * performance_rate
        / 100.0
    )

    # 距離・馬場等の条件適性。
    # 過剰に二重評価しないよう補正幅を制限。
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
        blood_adjustment(blood)
    )

    final_score = (
        base_performance
        + condition_adjustment
        + previous_adj
        + pace_adj
        + blood_adj
    )

    noise_flags = (
        ability.get("noise_flags")
        or []
    )

    if isinstance(noise_flags, str):
        noise_flags = [noise_flags]

    # 未知数は減点しない
    unknown = bool(
        ability.get("unknown", False)
    )

    reasons = []

    reasons.append(
        f"能力{round1(ability_score)}"
    )

    reasons.append(
        f"発揮率{round1(performance_rate)}%"
    )

    if condition_adjustment:
        reasons.append(
            f"条件適性補正{round1(condition_adjustment):+}"
        )

    reasons.extend(previous_reasons)
    reasons.extend(pace_reasons)
    reasons.extend(blood_reasons)

    if unknown:
        reasons.append(
            "未知数あり・減点なし"
        )

    results.append({
        "horse_id": str(
            runner.get("horse_id", "")
        ),
        "horse_number": str(
            runner.get(
                "horse_number",
                runner.get("number", "")
            )
        ),
        "horse_name": str(
            runner.get(
                "horse_name",
                runner.get("name", "")
            )
        ),

        "ability_score": round1(
            ability_score
        ),

        "performance_rate": round1(
            performance_rate
        ),

        "base_performance": round1(
            base_performance
        ),

        "condition_fit_score": round1(
            condition_fit
        ),

        "condition_adjustment": round1(
            condition_adjustment
        ),

        "previous_race_adjustment": round1(
            previous_adj
        ),

        "pace_adjustment": round1(
            pace_adj
        ),

        "bloodline_adjustment": round1(
            blood_adj
        ),

        "final_score": round1(
            final_score
        ),

        "unknown": unknown,

        "noise_flags": noise_flags,

        "reasons": reasons
    })


results.sort(
    key=lambda x: x["final_score"],
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

    if horse["noise_flags"]:
        judgement += "/注意"

    horse["judgement"] = judgement


output = {
    "updated_at": now_jst(),

    "race_id": str(
        race.get("race_id", "")
    ),

    "method": {
        "ability_and_performance_rate_separated": True,
        "previous_finish_not_used_alone": True,
        "previous_issue_resolution_emphasized": True,
        "bloodline_is_condition_support_only": True,
        "pace_is_performance_adjustment_only": True,
        "unknown_not_penalized": True,
        "popularity_not_used": True,
        "internet_prediction_not_used": True,
        "training_not_required": True
    },

    "summary": {
        "runner_count": len(results),
        "ranked_count": len(results)
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


print("===== Final Analysis =====")

for horse in results:
    print(
        horse["rank"],
        horse["horse_number"],
        horse["horse_name"],
        horse["final_score"]
    )
