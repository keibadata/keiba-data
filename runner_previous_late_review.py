import json
from datetime import date
from pathlib import Path


REVIEW = Path("runner_late_review.json")
PREVIOUS = Path("previous_race_analysis.json")
OUTPUT = Path("runner_previous_late_review.json")


def load(path):
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object: {path}")
    return data


def race_key(horse_id, race_id, race_date):
    if not horse_id or not race_id or not race_date:
        return None
    try:
        normalized_date = date.fromisoformat(str(race_date).replace("/", "-"))
    except ValueError:
        return None
    return str(horse_id), str(race_id), normalized_date


def main():
    review = load(REVIEW)
    previous = load(PREVIOUS)
    target_id = review["target_race_id"]
    if (
        not target_id
        or target_id != previous.get("target_race_id")
        or review.get("version") != "runner_late_review_v1"
        or review.get("scoring_applied") is not False
        or previous.get("future_race_usage") is not False
        or previous.get("leak_check_passed") is not True
    ):
        raise ValueError("Target race or source validation failed")

    candidates = {}
    for row in review["candidates"]:
        key = race_key(row["horse_id"], row["past_race_id"], row["past_race_date"])
        if key is None or key in candidates:
            raise ValueError("Invalid or duplicate late review candidate")
        candidates[key] = row

    matches = []
    for horse in previous["horses"]:
        if horse.get("previous_race_available") is not True:
            continue

        run = horse["previous_race"]
        key = race_key(horse["horse_id"], run.get("race_id"), run.get("date"))
        candidate = candidates.get(key)
        if candidate is None:
            continue

        matches.append({
            "horse_id": horse["horse_id"],
            "horse_number": horse["horse_number"],
            "horse_name": horse["horse_name"],
            "previous_race_id": run["race_id"],
            "previous_race_date": key[2].isoformat(),
            "existing_previous_analysis": {
                "issue_summary": horse.get("issue_summary"),
                "overcoming_summary": horse.get("overcoming_summary"),
            },
            "late_review_observation": candidate,
        })

    result = {
        "version": "runner_previous_late_review_v1",
        "target_race_id": target_id,
        "source_files": [str(REVIEW), str(PREVIOUS)],
        "review_source_updated_at": review["source_updated_at"],
        "previous_analysis_updated_at": previous["updated_at"],
        "scoring_applied": False,
        "notes": [
            "馬ID・前走Race ID・開催日が一致した候補のみ収録。",
            "前走分析の要約は原文の参照用。克服確認の判定は行わない。",
            "終盤の観測値は前走課題・克服根拠・採点とは別に保持。",
        ],
        "summary": {
            "horse_count": len(previous["horses"]),
            "candidate_count": len(candidates),
            "matched_previous_run_count": len(matches),
        },
        "matches": matches,
    }

    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(result, ensure_ascii=False, indent=2, allow_nan=False) + "\n",
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)
    print("Previous late review:", target_id, result["summary"])


if __name__ == "__main__":
    main()
