import json
import math
import re
from datetime import datetime, timezone, timedelta


INPUT_FILE = "runner_history.json"
RACE_FILE = "race.json"
EVIDENCE_FILE = "runner_ability_evidence.json"
OUTPUT_FILE = "runner_analysis.json"
ABILITY_VERSION = "legacy_weights_unknown_guard_v1"
RECENCY_WEIGHTS = [1.00, 0.82, 0.67, 0.55, 0.45]
COMPONENT_WEIGHTS = {"finish": 0.60, "last3f": 0.25, "position": 0.15}


def load_json(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return data


def text(value):
    return str(value if value is not None else "").strip()


def number(value):
    match = re.search(r"-?\d+(?:\.\d+)?", text(value))
    if not match:
        return None
    value = float(match.group())
    return value if math.isfinite(value) else None


def rank_number(value):
    value = text(value)
    return int(value) if re.fullmatch(r"[1-9]\d*", value) else None


def parse_last3f(value):
    value = number(value)
    return value if value is not None and 25 <= value <= 50 else None


def parse_distance(value):
    value = number(value)
    return int(value) if value is not None and 800 <= value <= 4000 else None


def passing_position(value):
    value = text(value)
    if not re.fullmatch(r"\d+(?:\s*-\s*\d+)*", value):
        return None
    position = int(re.findall(r"\d+", value)[-1])
    return position if position > 0 else None


def weighted_average(values, weights):
    valid = [(v, w) for v, w in zip(values, weights) if v is not None]
    return sum(v * w for v, w in valid) / sum(w for _, w in valid) if valid else None


def recency_weights(count):
    return [RECENCY_WEIGHTS[i] if i < len(RECENCY_WEIGHTS) else 0.35
            for i in range(count)]


def finish_score(rank):
    if rank is None:
        return None
    return {1: 1.00, 2: 0.88, 3: 0.78, 4: 0.67, 5: 0.58,
            6: 0.48, 7: 0.39, 8: 0.31, 9: 0.24, 10: 0.18}.get(rank, 0.10)


def last3f_score(value):
    if value is None:
        return None
    for limit, score in [(33.5, 1.00), (34.0, 0.92), (34.5, 0.84),
                         (35.0, 0.74), (35.5, 0.64), (36.0, 0.55), (37.0, 0.45)]:
        if value <= limit:
            return score
    return 0.35


def position_score(position):
    if position is None:
        return None
    for limit, score in [(3, 0.72), (6, 0.68), (9, 0.58)]:
        if position <= limit:
            return score
    return 0.48


def distance_score(distance, target_distance):
    if distance is None:
        return None
    diff = abs(distance - target_distance)
    for limit, score in [(0, 1.00), (200, 0.75), (400, 0.45), (600, 0.20)]:
        if diff <= limit:
            return score
    return 0.0


def rounded(value, digits=4):
    return round(value, digits) if value is not None else None


def analyze_race(row, target):
    rank = rank_number(row.get("rank"))
    distance = parse_distance(row.get("distance"))
    closing = parse_last3f(row.get("last3f"))
    position = passing_position(row.get("passing"))
    surface = text(row.get("surface"))
    same_surface = surface == target["surface"] if surface in ("芝", "ダート", "障害") else None
    d_score = distance_score(distance, target["distance"])
    components = [finish_score(rank), last3f_score(closing), position_score(position)]
    weights = list(COMPONENT_WEIGHTS.values())

    # 着順しか分からない走りから能力点を作らない。
    enough_evidence = rank is not None and sum(v is not None for v in components) >= 2
    performance = weighted_average(components, weights) if enough_evidence else None

    condition = weighted_average(
        [float(same_surface) if same_surface is not None else None, d_score],
        [0.55, 0.45],
    ) if rank is not None else None

    result = {key: text(row.get(key)) for key in [
        "race_id", "date", "meeting", "race_name", "surface", "track_condition",
        "time", "margin", "passing", "horse_weight",
    ]}
    result.update({
        "rank": rank, "distance": distance, "last3f": closing,
        "same_surface": same_surface, "distance_fit": rounded(d_score),
        "finish_score": rounded(components[0]),
        "last3f_score": rounded(components[1]),
        "position_score": rounded(components[2]),
        "performance_score": rounded(performance),
        "condition_score": rounded(condition),
        "ability_observed_weight": rounded(
            sum(w for v, w in zip(components, weights) if v is not None)
        ),
        "missing_components": [
            name for name, value in zip(COMPONENT_WEIGHTS, components)
            if value is None
        ],
    })
    return result


def classify(value):
    if value is None:
        return "UNKNOWN"
    for limit, grade in [(80, "A"), (70, "B+"), (60, "B"), (50, "C+"), (40, "C")]:
        if value >= limit:
            return grade
    return "D"


def analyze_horse(horse, target, evidence):
    source = horse.get("past_races", []) or []
    analyzed = []
    excluded = []

    for row in source:
        if rank_number(row.get("rank")) is None:
            excluded.append({
                "race_id": text(row.get("race_id")),
                "date": text(row.get("date")),
                "race_name": text(row.get("race_name")),
                "rank_raw": text(row.get("rank")),
                "reason": "数値着順なし。能力・条件適性の平均と直近順の重みから除外。",
            })
        else:
            analyzed.append(analyze_race(row, target))

    weights = recency_weights(len(analyzed))
    ability_values = [
        r["performance_score"] for r in analyzed
        if r["performance_score"] is not None
    ]
    ability = weighted_average(
        ability_values,
        recency_weights(len(ability_values))
    )
    condition = weighted_average(
        [r["condition_score"] for r in analyzed],
        weights
    )

    ability_score = rounded(ability * 100, 1) if ability is not None else None
    condition_fit = rounded(condition * 100, 1) if condition is not None else None
    rate = rounded(
        max(35, min(100, 45 + condition * 55)), 1
    ) if condition is not None else None

    flags = []
    if len(analyzed) == 1:
        flags.append("評価可能な過去走は1走のみ")
    if excluded:
        flags.append(f"数値着順なし{len(excluded)}走を採点から除外")

    partial = sum(bool(r["missing_components"]) for r in analyzed)
    if partial:
        flags.append(
            f"能力材料の一部不明{partial}走・観測できた項目だけで算出"
        )

    insufficient = sum(r["performance_score"] is None for r in analyzed)
    if insufficient:
        flags.append(
            f"着順以外の能力材料なし{insufficient}走・能力点は不明のまま保持"
        )

    same_count = sum(r["same_surface"] is True for r in analyzed)
    exact_count = sum(r["distance"] == target["distance"] for r in analyzed)

    if analyzed and same_count == 0:
        surface = target["surface"]
        past_surfaces = {row["surface"] for row in analyzed}
        # 最終評価の未知条件ガードへ、反対の馬場種別だけと確認できた馬を渡す。
        if (
            (surface == "芝" and past_surfaces == {"ダート"})
            or (surface == "ダート" and past_surfaces == {"芝"})
        ):
            flags.append(surface + "実績なし")
        else:
            flags.append(surface + "実績未確認")
    if analyzed and exact_count == 0:
        flags.append(str(target["distance"]) + "m実績未確認")

    positions = [
        p for r in analyzed
        if (p := passing_position(r["passing"])) is not None
    ]
    if positions and sum(positions) / len(positions) >= 10:
        flags.append("後方位置依存注意")

    closings = [
        r["last3f"] for r in analyzed
        if r["last3f"] is not None
    ]

    return {
        "horse_id": text(horse.get("horse_id")),
        "horse_number": text(horse.get("horse_number")),
        "horse_name": text(horse.get("horse_name")),
        "past_race_count": len(source),
        "evaluated_race_count": len(analyzed),
        "ability_evaluated_race_count": len(ability_values),
        "excluded_race_count": len(excluded),
        "partial_evidence_count": partial,
        "ability_version": ABILITY_VERSION,
        "ability_score": ability_score,
        "ability_grade": classify(ability_score),
        "condition_fit_score": condition_fit,
        "performance_rate": rate,
        "same_surface_count": same_count,
        "target_distance_count": exact_count,
        "best_last3f": min(closings) if closings else None,
        "unknown": ability_score is None,
        "noise_flags": flags,
        "class_counts": evidence.get("class_counts", {}),
        "analysis": analyzed,
        "excluded_races": excluded,
    }


def main():
    from runner_ability_evidence import build

    race = load_json(RACE_FILE)
    source = load_json(INPUT_FILE)
    evidence = load_json(EVIDENCE_FILE)

    target_id = text(race.get("race_id"))
    target_distance = parse_distance(race.get("distance"))
    target_surface = text(race.get("surface"))

    if (
        not target_id
        or target_distance is None
        or target_surface not in ("芝", "ダート", "障害")
    ):
        raise ValueError("race.json target condition missing or invalid")

    # 既存の未来データ・同日・重複チェックも実行する。
    checked = build(race, source, {})

    if (
        evidence.get("target_race_id") != target_id
        or evidence.get("version") != "ability_evidence_v1"
    ):
        raise ValueError("runner_ability_evidence target/version mismatch")

    facts = {
        h["horse_id"]: h
        for h in evidence.get("horses", [])
    }
    expected = {
        h["horse_id"]
        for h in checked["horses"]
    }

    if (
        len(facts) != len(evidence.get("horses", []))
        or set(facts) != expected
    ):
        raise ValueError("runner_ability_evidence horse IDs mismatch")

    for horse in checked["horses"]:
        if (
            facts[horse["horse_id"]]["class_counts"]
            != horse["class_counts"]
        ):
            raise ValueError("runner_ability_evidence class counts mismatch")

    target = {
        "track": text(race.get("racecourse") or race.get("track")),
        "surface": target_surface,
        "distance": target_distance,
    }
    results = [
        analyze_horse(
            h,
            target,
            facts[text(h.get("horse_id"))]
        )
        for h in source.get("horses", [])
    ]

    for score, rank_key in [
        ("ability_score", "ability_rank"),
        ("performance_rate", "performance_rank"),
    ]:
        ordered = sorted(
            [h for h in results if h[score] is not None],
            key=lambda h: h[score],
            reverse=True,
        )
        for rank, horse in enumerate(ordered, 1):
            horse[rank_key] = rank

    output = {
        "updated_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(),
        "source": INPUT_FILE,
        "target_race_id": target_id,
        "target_condition": target,
        "ability_version": ABILITY_VERSION,
        "method": {
            "target_condition_from_race_json": True,
            "hardcoded_target_distance": False,
            "ability_and_performance_rate_separated": True,
            "unknown_is_not_penalized": True,
            "unknown_ability_not_imputed": True,
            "missing_components_not_imputed": True,
            "non_numeric_finishes_excluded": True,
            "finish_position_is_not_used_alone": True,
            "last3f_is_supporting_signal": True,
            "distance_fit_not_used_as_ability": True,
            "popularity_not_used": True,
            "bloodline_not_used_here": True,
            "component_weights": COMPONENT_WEIGHTS,
            "class_adjustment_applied": False,
            "pace_context_adjustment_applied": False,
            "position_bias_fix_completed": False,
            "ability_model_revision_completed": False,
        },
        "summary": {
            "horse_count": len(results),
            "source_past_race_count": source.get(
                "total_past_race_count", 0
            ),
            "evaluated_race_count": sum(
                h["evaluated_race_count"] for h in results
            ),
            "excluded_race_count": sum(
                h["excluded_race_count"] for h in results
            ),
            "ability_known_count": sum(
                not h["unknown"] for h in results
            ),
            "ability_unknown_count": sum(
                h["unknown"] for h in results
            ),
        },
        "horses": results,
    }

    with open(
        OUTPUT_FILE + ".tmp",
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        )

    from pathlib import Path
    Path(OUTPUT_FILE + ".tmp").replace(OUTPUT_FILE)

    print("Runner analysis:", target_id, ABILITY_VERSION)
    print(output["summary"])

    for h in sorted(
        results,
        key=lambda h: h.get("ability_rank", 999)
    ):
        print(
            h.get("ability_rank"),
            h["horse_number"],
            h["horse_name"],
            h["ability_score"],
            h["performance_rate"],
        )


if __name__ == "__main__":
    main()
