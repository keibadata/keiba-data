import json
import math
import re
from datetime import datetime, timezone, timedelta

INPUT_FILE = "runner_history.json"
OUTPUT_FILE = "runner_analysis.json"

TARGET_SURFACE = "芝"
TARGET_DISTANCE = 1400


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def text(v):
    if v is None:
        return ""
    return str(v).strip()


def number(v):
    s = text(v)
    m = re.search(r"-?\d+(?:\.\d+)?", s)
    if not m:
        return None
    try:
        return float(m.group())
    except Exception:
        return None


def rank_number(v):
    s = text(v)

    # 中止・取消・除外などは数値化しない
    if not re.fullmatch(r"\d+", s):
        return None

    try:
        return int(s)
    except Exception:
        return None


def parse_last3f(v):
    x = number(v)

    if x is None:
        return None

    if 25 <= x <= 50:
        return x

    return None


def parse_distance(v):
    x = number(v)

    if x is None:
        return None

    if 800 <= x <= 4000:
        return int(x)

    return None


def parse_margin(v):
    """
    着差は表記揺れが大きいため、
    数値として安全に読める場合だけ利用。
    """
    s = text(v)

    if not s:
        return None

    try:
        return float(s)
    except Exception:
        return None


def passing_position(v):
    """
    通過順の最後の位置を取得。
    例:
      3-3 -> 3
      5-5-4 -> 4
    """
    s = text(v)

    nums = re.findall(r"\d+", s)

    if not nums:
        return None

    try:
        return int(nums[-1])
    except Exception:
        return None


def surface_match(race):
    return text(race.get("surface")) == TARGET_SURFACE


def distance_score(distance):
    """
    1400mへの距離近似度。
    血統とは独立した過去走実績評価。
    """
    if distance is None:
        return 0.0

    diff = abs(distance - TARGET_DISTANCE)

    if diff == 0:
        return 1.0
    if diff <= 200:
        return 0.75
    if diff <= 400:
        return 0.45
    if diff <= 600:
        return 0.20

    return 0.0


def finish_score(rank):
    if rank is None:
        return 0.0

    table = {
        1: 1.00,
        2: 0.88,
        3: 0.78,
        4: 0.67,
        5: 0.58,
        6: 0.48,
        7: 0.39,
        8: 0.31,
        9: 0.24,
        10: 0.18,
    }

    return table.get(rank, 0.10)


def last3f_score(last3f):
    """
    絶対時計だけで能力を決めない。
    補助評価として弱めに使用。
    """
    if last3f is None:
        return 0.50

    if last3f <= 33.5:
        return 1.00
    if last3f <= 34.0:
        return 0.92
    if last3f <= 34.5:
        return 0.84
    if last3f <= 35.0:
        return 0.74
    if last3f <= 35.5:
        return 0.64
    if last3f <= 36.0:
        return 0.55
    if last3f <= 37.0:
        return 0.45

    return 0.35


def position_score(position):
    """
    脚質そのものを優劣化しない。
    極端な後方依存だけ発揮率上のリスクとして確認。
    """
    if position is None:
        return 0.50

    if position <= 3:
        return 0.72
    if position <= 6:
        return 0.68
    if position <= 9:
        return 0.58

    return 0.48


def recency_weights(n):
    """
    新しいレースほど重くする。
    runner_history.json が新しい順である前提。
    """
    base = [1.00, 0.82, 0.67, 0.55, 0.45]

    result = []

    for i in range(n):
        if i < len(base):
            result.append(base[i])
        else:
            result.append(0.35)

    return result


def analyze_race(race):
    rank = rank_number(race.get("rank"))
    distance = parse_distance(race.get("distance"))
    last3f = parse_last3f(race.get("last3f"))
    position = passing_position(race.get("passing"))
    margin = parse_margin(race.get("margin"))

    same_surface = surface_match(race)
    d_score = distance_score(distance)
    f_score = finish_score(rank)
    l_score = last3f_score(last3f)
    p_score = position_score(position)

    # 能力評価の基礎
    performance = (
        f_score * 0.55
        + l_score * 0.20
        + d_score * 0.15
        + p_score * 0.10
    )

    # 芝1400の今回条件との接続
    condition = 0.0

    if same_surface:
        condition += 0.55

    condition += d_score * 0.45

    return {
        "date": text(race.get("date")),
        "meeting": text(race.get("meeting")),
        "race_name": text(race.get("race_name")),
        "rank": rank,
        "surface": text(race.get("surface")),
        "distance": distance,
        "track_condition": text(race.get("track_condition")),
        "time": text(race.get("time")),
        "margin": text(race.get("margin")),
        "passing": text(race.get("passing")),
        "last3f": last3f,
        "horse_weight": text(race.get("horse_weight")),
        "same_surface": same_surface,
        "distance_fit": round(d_score, 4),
        "finish_score": round(f_score, 4),
        "last3f_score": round(l_score, 4),
        "position_score": round(p_score, 4),
        "performance_score": round(performance, 4),
        "condition_score": round(condition, 4),
    }


def weighted_average(values, weights):
    valid = [
        (v, w)
        for v, w in zip(values, weights)
        if v is not None
    ]

    if not valid:
        return 0.0

    total_weight = sum(w for _, w in valid)

    if total_weight == 0:
        return 0.0

    return sum(v * w for v, w in valid) / total_weight


def classify(value):
    if value >= 80:
        return "A"
    if value >= 70:
        return "B+"
    if value >= 60:
        return "B"
    if value >= 50:
        return "C+"
    if value >= 40:
        return "C"
    return "D"


def analyze_horse(horse):
    races = horse.get("past_races", [])

    analyzed = [
        analyze_race(race)
        for race in races
    ]

    if not analyzed:
        return {
            "horse_id": text(horse.get("horse_id")),
            "horse_number": text(horse.get("horse_number")),
            "horse_name": text(horse.get("horse_name")),
            "past_race_count": 0,
            "ability_score": None,
            "ability_grade": "UNKNOWN",
            "condition_fit_score": None,
            "performance_rate": None,
            "unknown": True,
            "noise_flags": [],
            "analysis": [],
        }

    weights = recency_weights(len(analyzed))

    performance_values = [
        r["performance_score"]
        for r in analyzed
    ]

    condition_values = [
        r["condition_score"]
        for r in analyzed
    ]

    ability_raw = weighted_average(
        performance_values,
        weights
    )

    condition_raw = weighted_average(
        condition_values,
        weights
    )

    # 0-100化
    ability_score = round(
        max(0, min(100, ability_raw * 100)),
        1
    )

    condition_fit_score = round(
        max(0, min(100, condition_raw * 100)),
        1
    )

    # 能力と今回能力発揮率を分離
    #
    # 発揮率は今回条件との接続を中心にする。
    # 過去着順だけで機械的に上下させない。
    performance_rate = round(
        max(
            35,
            min(
                100,
                45 + condition_raw * 55
            )
        ),
        1
    )

    noise_flags = []

    # 1走しかない馬は低評価にしない。
    # 情報量不足として明示するだけ。
    if len(analyzed) == 1:
        noise_flags.append("過去1走のみ")

    same_surface_count = sum(
        1 for r in analyzed
        if r["same_surface"]
    )

    exact_distance_count = sum(
        1 for r in analyzed
        if r["distance"] == TARGET_DISTANCE
    )

    if same_surface_count == 0:
        noise_flags.append("芝実績なし")

    if exact_distance_count == 0:
        noise_flags.append("1400m実績なし")

    # 極端な後方依存をチェック
    positions = [
        passing_position(r.get("passing"))
        for r in races
    ]

    valid_positions = [
        x for x in positions
        if x is not None
    ]

    if valid_positions:
        avg_pos = sum(valid_positions) / len(valid_positions)

        if avg_pos >= 10:
            noise_flags.append("後方位置依存注意")

    best_last3f = None

    last3fs = [
        r["last3f"]
        for r in analyzed
        if r["last3f"] is not None
    ]

    if last3fs:
        best_last3f = min(last3fs)

    return {
        "horse_id": text(horse.get("horse_id")),
        "horse_number": text(horse.get("horse_number")),
        "horse_name": text(horse.get("horse_name")),
        "past_race_count": len(analyzed),

        "ability_score": ability_score,
        "ability_grade": classify(ability_score),

        "condition_fit_score": condition_fit_score,

        "performance_rate": performance_rate,

        "same_surface_count": same_surface_count,
        "target_distance_count": exact_distance_count,

        "best_last3f": best_last3f,

        "unknown": False,

        "noise_flags": noise_flags,

        "analysis": analyzed,
    }


def main():
    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        source = json.load(f)

    horses = source.get("horses", [])

    results = [
        analyze_horse(horse)
        for horse in horses
    ]

    # 能力順位
    ability_sorted = sorted(
        [
            x for x in results
            if x["ability_score"] is not None
        ],
        key=lambda x: x["ability_score"],
        reverse=True,
    )

    for i, horse in enumerate(
        ability_sorted,
        start=1
    ):
        horse["ability_rank"] = i

    # 発揮率順位
    performance_sorted = sorted(
        [
            x for x in results
            if x["performance_rate"] is not None
        ],
        key=lambda x: x["performance_rate"],
        reverse=True,
    )

    for i, horse in enumerate(
        performance_sorted,
        start=1
    ):
        horse["performance_rank"] = i

    # 馬番順も保持
    def horse_number_key(x):
        try:
            return int(x["horse_number"])
        except Exception:
            return 999

    results.sort(
        key=horse_number_key
    )

    output = {
        "updated_at": now_jst(),

        "source": INPUT_FILE,

        "target_condition": {
            "surface": TARGET_SURFACE,
            "distance": TARGET_DISTANCE,
        },

        "method": {
            "ability_and_performance_rate_separated": True,
            "unknown_is_not_penalized": True,
            "last3f_is_supporting_signal": True,
            "finish_position_is_not_used_alone": True,
            "popularity_not_used": True,
            "bloodline_not_used_here": True,
        },

        "summary": {
            "horse_count": len(results),
            "source_past_race_count":
                source.get(
                    "total_past_race_count",
                    0
                ),
        },

        "horses": results,
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

    print("===== Runner Analysis =====")
    print("horses:", len(results))
    print(
        "past races:",
        source.get(
            "total_past_race_count",
            0
        )
    )

    print("")
    print("ABILITY RANKING")

    for horse in ability_sorted:
        print(
            horse["ability_rank"],
            horse["horse_number"],
            horse["horse_name"],
            horse["ability_score"],
            horse["performance_rate"],
        )


if __name__ == "__main__":
    main()
