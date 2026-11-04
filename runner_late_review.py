import json
from collections import Counter
from pathlib import Path


SOURCE = Path("runner_pace_context.json")
OUTPUT = Path("runner_late_review.json")
REVIEW_PATTERNS = {
    ("gained", "widened"): "rank_gained_gap_widened",
    ("lost", "narrowed"): "rank_lost_gap_narrowed",
}


def main():
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    if (
        source.get("version") != "runner_pace_context_v1"
        or source.get("future_race_usage") is not False
        or source.get("leak_check_passed") is not True
        or source.get("scoring_applied") is not False
    ):
        raise ValueError("Unexpected pace context version or safety flags")

    candidates = []
    counts = Counter()
    run_count = 0
    for horse in source["horses"]:
        for run in horse["past_races"]:
            run_count += 1
            position = run["late_position_change"]
            gap = run["late_gap_change"]
            if position["status"] != "ok" or gap["status"] != "ok":
                continue

            pattern = REVIEW_PATTERNS.get((position["direction"], gap["direction"]))
            if pattern is None:
                continue

            counts[pattern] += 1
            candidates.append({
                "pattern": pattern,
                "horse_id": horse["horse_id"],
                "horse_number": horse["horse_number"],
                "horse_name": horse["horse_name"],
                "past_race_id": run["race_id"],
                "past_race_date": run["date"],
                "past_race_name": run["race_name"],
                "position_change": position,
                "gap_change": gap,
                "race_final_minus_preceding_seconds_per_200m": (
                    run["late_race_observation"][
                        "race_final_minus_preceding_seconds_per_200m"
                    ]
                ),
            })

    result = {
        "version": "runner_late_review_v1",
        "target_race_id": source["target_race_id"],
        "source_file": str(SOURCE),
        "source_updated_at": source["updated_at"],
        "scoring_applied": False,
        "summary": {
            "past_run_count": run_count,
            "candidate_count": len(candidates),
            "rank_gained_gap_widened_count": counts["rank_gained_gap_widened"],
            "rank_lost_gap_narrowed_count": counts["rank_lost_gap_narrowed"],
        },
        "candidates": candidates,
    }
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print("Runner late review:", result["target_race_id"], result["summary"])


if __name__ == "__main__":
    main()
