"""Compare ability formulas against a stored pre-race prediction.

From the repository root:
    python ability_scoring_trial.py 3b2efba1

The report is written to stdout. The final-analysis program runs in a
temporary directory with the original inputs from the specified revision.
"""

import argparse
import json
import math
import subprocess
import sys
import tempfile
from collections import Counter
from copy import deepcopy
from datetime import datetime
from pathlib import Path

from runner_analysis import classify, recency_weights, weighted_average


METHODS = (
    "winner_gap",
    "winner_gap_and_relative_last3f",
    "winner_gap_relative_last3f_and_direct_comparison",
)
INPUTS = (
    "race.json",
    "runner_analysis.json",
    "previous_race_analysis.json",
    "pace_analysis.json",
    "race_bloodline_score.json",
    "track_condition.json",
    "day_bias.json",
    "body_weight.json",
    "runner_time_fit.json",
    "final_analysis.py",
)


def is_number(value):
    return type(value) in (int, float) and math.isfinite(value)


def past_race_key(row):
    return str(row.get("race_id") or "").strip(), str(row.get("date") or "").replace("/", "-")


def race_index(rows):
    indexed = {past_race_key(row): row for row in rows}
    if len(indexed) != len(rows):
        raise ValueError("Duplicate past race and date in ability evidence")
    return indexed


def horse_index(rows):
    indexed = {str(row.get("horse_id") or "").strip(): row for row in rows}
    if not indexed or not all(indexed) or len(indexed) != len(rows):
        raise ValueError("Missing or duplicate horse ID")
    return indexed


def relative_last3f(field):
    count = field.get("last3f_observed_count")
    rank = field.get("last3f_rank")
    if (
        type(count) is int
        and count >= 2
        and count == field.get("classified_finish_count")
        and type(rank) is int
        and 1 <= rank <= count
    ):
        return 0.35 + 0.65 * (count - rank) / (count - 1)
    return None


def direct_comparison(field, race_id, horse_id, entrants):
    scores = {}
    for row in field.get("current_opponents", []):
        opponent = str(row.get("horse_id") or "")
        clock_gap = row.get("own_minus_opponent_seconds")
        if (
            opponent not in entrants or opponent == horse_id
            or row.get("outcome") not in ("先着", "同着", "後着")
            or not is_number(clock_gap)
        ):
            continue
        expected_key = "|".join([race_id, *sorted((horse_id, opponent))])
        if row.get("comparison_key") == expected_key:
            scores[opponent] = max(0.0, min(1.0, 0.5 - 0.5 * clock_gap))
    return sum(scores.values()) / len(scores) if scores else None


def trial_run_score(run, evidence, method, horse_id, entrants, counts):
    field = evidence.get("field") or {}
    if (
        evidence.get("finish") != run["rank"]
        or field.get("matched") is not True
        or field.get("comparison_conflicts")
    ):
        return run["performance_score"]

    finish_weight = 0.60
    closing_weight = 0.25
    closing = run["last3f_score"]
    supporting_values = [run["position_score"]]
    supporting_weights = [0.15]

    # A 1-second gap over 1000m reduces the gap component by one point on its
    # 0–1 scale. Keep a 0.10 floor, matching the legacy finish-score floor.
    gap, distance = field.get("winner_time_gap_seconds"), run.get("distance")
    if is_number(gap) and gap >= 0 and is_number(distance) and distance > 0:
        finish_weight -= 0.15
        supporting_values.append(max(0.10, 1.0 - gap * 1000 / distance))
        supporting_weights.append(0.15)
        counts["winner_gap"] += 1

    if method != "winner_gap" and (relative := relative_last3f(field)) is not None:
        supporting_values.append(relative)
        supporting_weights.append(0.15 if closing is not None else 0.25)
        closing_weight = 0.10
        counts["relative_last3f"] += 1

    if method == METHODS[2]:
        head_to_head = direct_comparison(field, run["race_id"], horse_id, entrants)
        if head_to_head is not None:
            finish_weight -= 0.05
            supporting_values.append(head_to_head)
            supporting_weights.append(0.05)
            counts["direct_comparison"] += 1

    if finish_weight == 0.60 and closing_weight == 0.25:
        return run["performance_score"]
    return round(weighted_average(
        [run["finish_score"], closing, *supporting_values],
        [finish_weight, closing_weight, *supporting_weights],
    ), 4)


def score_trial(ability, evidence, method):
    if method not in METHODS:
        raise ValueError(f"Unknown trial formula: {method}")
    if (
        ability["target_race_id"] != evidence.get("target_race_id")
        or evidence.get("version") != "ability_evidence_v1"
        or evidence.get("future_race_usage") is not False
        or evidence.get("leak_check_passed") is not True
    ):
        raise ValueError("Ability evidence target, version or timing mismatch")

    evidence_by_horse = horse_index(evidence["horses"])
    result = deepcopy(ability)
    entrants = horse_index(result["horses"])
    if entrants.keys() != evidence_by_horse.keys():
        raise ValueError("Ability evidence horse IDs do not match")

    coverage = Counter()
    for horse_id, horse in entrants.items():
        recorded = race_index(evidence_by_horse[horse_id]["past_races"])
        legacy_scores, trial_scores = [], []
        for run in horse["analysis"]:
            legacy = run["performance_score"]
            if legacy is None:
                continue
            legacy_scores.append(legacy)
            coverage["scorable_runs"] += 1
            key = past_race_key(run)
            old_race = recorded.get(key) if key[0] else None
            trial_scores.append(trial_run_score(
                run, old_race, method, horse_id, entrants, coverage,
            ) if old_race is not None else legacy)
        if trial_scores:
            weights = recency_weights(len(trial_scores))
            legacy = 100 * weighted_average(legacy_scores, weights)
            stored_score = horse["ability_score"]
            if stored_score is None or abs(legacy - stored_score) > 0.050000001:
                raise ValueError(f"Legacy ability calculation mismatch for horse {horse_id}")
            # A saved one-decimal score can differ at a floating-point midpoint.
            # Preserve it whenever the trial did not change any past-run score.
            if trial_scores != legacy_scores:
                horse["ability_score"] = round(100 * weighted_average(trial_scores, weights), 1)
                horse["ability_grade"] = classify(horse["ability_score"])
        elif horse["ability_score"] is not None:
            raise ValueError(f"Missing saved ability calculations for horse {horse_id}")

    for horse in result["horses"]:
        horse.pop("ability_rank", None)
    scored = [horse for horse in result["horses"] if horse["ability_score"] is not None]
    scored.sort(key=lambda horse: horse["ability_score"], reverse=True)
    for rank, horse in enumerate(scored, start=1):
        horse["ability_rank"] = rank
    return result, dict(coverage)


def git(*args):
    return subprocess.check_output(["git", *args], stderr=subprocess.PIPE)


def revision_files(revision, paths):
    names = set(git("ls-tree", "--name-only", revision, "--", *paths).decode().splitlines())
    return {name: git("show", f"{revision}:{name}") for name in paths if name in names}


def find_snapshot(snapshot_ref, race, final):
    directory = f"prediction_snapshots/{race['race_date']}/{race['race_id']}"
    names = git("ls-tree", "-r", "--name-only", snapshot_ref, "--", directory)
    matches = []
    for name in names.decode().splitlines():
        if not name.endswith(".json"):
            continue
        snapshot = json.loads(git("show", f"{snapshot_ref}:{name}"))
        if (
            snapshot.get("source_final_analysis_updated_at") != final["updated_at"]
            or snapshot.get("analysis_mode") != "normal"
            or snapshot.get("race", {}).get("race_id") != race["race_id"]
            or snapshot.get("timing", {}).get("evaluation_eligible") is not True
            or not snapshot["timing"].get("race_start_at")
        ):
            continue
        if datetime.fromisoformat(snapshot["prediction_saved_at"]) < datetime.fromisoformat(
            snapshot["timing"]["race_start_at"]
        ):
            matches.append((datetime.fromisoformat(snapshot["prediction_saved_at"]), name, snapshot))
    if not matches:
        raise ValueError("No matching pre-race prediction snapshot for this revision")
    _, name, snapshot = max(matches, key=lambda entry: (entry[0], entry[1]))
    return name, snapshot


def replay(inputs, ability=None):
    with tempfile.TemporaryDirectory() as directory:
        root = Path(directory)
        for name, data in inputs.items():
            (root / name).write_bytes(data)
        if ability is not None:
            (root / "runner_analysis.json").write_text(
                json.dumps(ability, ensure_ascii=False, allow_nan=False), encoding="utf-8",
            )
        subprocess.run(
            [sys.executable, "final_analysis.py"], cwd=root, check=True, stdout=subprocess.DEVNULL,
        )
        return json.loads((root / "final_analysis.json").read_text(encoding="utf-8"))


def scores(data):
    fields = ("horse_id", "horse_number", "ability_score", "performance_rate", "final_score", "rank")
    return [{key: horse[key] for key in fields} for horse in data["ranking"]]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("revision", help="Git revision containing the original pre-race inputs")
    parser.add_argument("--snapshot-ref", default="origin/main", help="Git ref containing saved snapshots")
    args = parser.parse_args()
    revision = git("rev-parse", "--verify", "--end-of-options", f"{args.revision}^{{commit}}").decode().strip()
    snapshot_ref = git("rev-parse", "--verify", "--end-of-options", f"{args.snapshot_ref}^{{commit}}").decode().strip()
    files = revision_files(revision, (*INPUTS, "runner_ability_evidence.json", "final_analysis.json"))
    race, ability, evidence, final = (json.loads(files[name]) for name in (
        "race.json", "runner_analysis.json", "runner_ability_evidence.json", "final_analysis.json",
    ))
    path, stored = find_snapshot(snapshot_ref, race, final)
    inputs = {name: files[name] for name in INPUTS if name in files}
    baseline = scores(replay(inputs))
    if baseline != scores(stored["analysis"]):
        raise ValueError("Replayed production ranking differs from the pre-race snapshot")

    report = {
        "race_id": race["race_id"], "revision": revision, "snapshot_path": path,
        "baseline": baseline, "trials": {},
    }
    for method in METHODS:
        candidate, coverage = score_trial(ability, evidence, method)
        ranking = scores(replay(inputs, candidate))
        report["trials"][method] = {"coverage": coverage, "ranking": ranking}
    print(json.dumps(report, ensure_ascii=False, allow_nan=False, indent=2))


if __name__ == "__main__":
    main()
