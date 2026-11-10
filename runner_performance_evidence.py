import json
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path

from analysis_evidence import actual_issues, resolution_evidence
from pace_analysis import analyze_horse as analyze_pace
from pace_analysis import build_race_scenario
from runner_ability_evidence import build as validate_history
from runner_previous_late_review import race_key


OUTPUT_FILE = "runner_performance_evidence.json"


def text(value):
    return str(value if value is not None else "").strip()


def read_json(filename):
    with open(filename, encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {filename}")
    return data


def horse_index(data, expected_ids, filename):
    horses = data.get("horses")
    if not isinstance(horses, list):
        raise ValueError(f"Missing horse list: {filename}")
    result = {}
    for horse in horses:
        if not isinstance(horse, dict):
            raise ValueError(f"Invalid horse record: {filename}")
        horse_id = text(horse.get("horse_id"))
        if not horse_id or horse_id in result:
            raise ValueError(f"Missing or duplicate horse ID: {filename}")
        result[horse_id] = horse
    if set(result) != expected_ids:
        raise ValueError(f"Horse IDs mismatch: {filename}")
    return result


def require_target(data, race_id, filename):
    source_ids = {
        text(data[key]) for key in ("target_race_id", "race_id")
        if text(data.get(key))
    }
    if source_ids != {race_id}:
        raise ValueError(f"Race ID mismatch: {filename}")


def optional_source(filename, race, statuses, check_future=False):
    if not Path(filename).exists():
        statuses[filename] = "missing"
        return {}
    try:
        data = read_json(filename)
    except (OSError, ValueError):
        statuses[filename] = "invalid"
        return {}
    if (
        text(data.get("race_id")) != text(race["race_id"])
        or text(data.get("race_date")) != text(race["race_date"])
    ):
        statuses[filename] = "rejected_target_mismatch"
        return {}
    if check_future and data.get("future_race_usage") is not False:
        statuses[filename] = "rejected_future_check"
        return {}
    if check_future:
        references = data.get("reference_race_numbers")
        race_number = int(text(race["race_id"])[-2:])
        if not isinstance(references, list) or any(
            type(number) is not int or not 1 <= number < race_number
            for number in references
        ):
            statuses[filename] = "rejected_reference_races"
            return {}
    statuses[filename] = "matched"
    return data


def track_observations(track, bias):
    physical = {}
    for prefix, keys in (
        ("moisture", ("moisture_finish", "moisture_4corner")),
        ("cushion", ("cushion_value",)),
    ):
        if all(track.get(f"{prefix}_{key}") is True
               for key in ("track_found", "date_found", "fetch_found")):
            for key in keys:
                physical[key] = track.get(key)
            physical[f"{prefix}_measurement_time"] = track.get(
                f"{prefix}_measurement_time"
            )
    return {
        "physical": physical,
        "source_url": track.get("source_url", ""),
        "bias_status": bias.get("status", "unknown"),
        "reference_race_numbers": bias.get("reference_race_numbers", []),
        "reference_race_count": bias.get("reference_race_count"),
        "confidence": bias.get("confidence"),
        "running_style_bias": bias.get("running_style_bias", ""),
        "inside_outside_bias": bias.get("inside_outside_bias", ""),
        "bias_reason": bias.get("reason", ""),
    }


def late_observation_index(race_id, expected_ids, statuses):
    filename = "runner_pace_context.json"
    if not Path(filename).exists():
        statuses[filename] = "missing"
        return {}
    data = read_json(filename)
    require_target(data, race_id, filename)
    if (
        data.get("version") != "runner_pace_context_v1"
        or data.get("future_race_usage") is not False
        or data.get("leak_check_passed") is not True
        or data.get("scoring_applied") is not False
    ):
        raise ValueError("Invalid pace context version or safety flags")
    horses = horse_index(data, expected_ids, filename)
    result = {}
    for horse_id, horse in horses.items():
        for run in horse.get("past_races", []):
            key = race_key(horse_id, run.get("race_id"), run.get("date"))
            if key is None or key in result:
                raise ValueError("Invalid or duplicate pace context run")
            result[key] = run
    statuses[filename] = "matched"
    return result


def previous_late_observation(horse_id, previous, late_runs):
    key = race_key(horse_id, previous.get("race_id"), previous.get("date"))
    run = late_runs.get(key)
    if run is None:
        return {"status": "unknown", "reason": "前走の終盤比較データ未接続"}
    fields = (
        "same_race_clock_comparison", "late_race_observation",
        "late_gap_change", "late_position_change",
    )
    if any((run.get(field) or {}).get("status") != "ok" for field in fields):
        return {"status": "unknown", "reason": "前走の終盤比較データに欠損"}
    return {
        "status": "available_for_review",
        "source": "runner_pace_context.json",
        "past_race_id": run["race_id"],
        "past_race_date": run["date"],
        "clock_comparison": run["same_race_clock_comparison"],
        "leader_gap_at_last_600m": run["late_race_observation"],
        "gap_change": run["late_gap_change"],
        "position_change": run["late_position_change"],
        "interpretation_status": "unknown",
        "pending": "順位変化・時計差変化を観測し、敗因や克服は別途確認する",
    }


def build_horse(runner, ability, previous_horse, pace, race_id, late_runs):
    previous = previous_horse.get("previous_race") or {}
    issues = list(dict.fromkeys(actual_issues(previous)))
    registered = resolution_evidence(previous, race_id)
    observation_keys = (
        "race_id", "date", "rank", "surface", "distance", "margin",
        "passing", "last3f", "position_observations", "margin_observations",
        "condition_changes", "unknowns",
    )
    issue_ids = [f"issue_{index}" for index in range(1, len(issues) + 1)]
    issue_refs = dict(zip(issues, issue_ids))
    resolution_records = [
        {
            "issue_ref": issue_refs[record["issue"]],
            "source": record["source"],
            "fact": record["fact"],
            "registration_status": "confirmed",
            "source_content_verification": "not_checked",
        }
        for record in registered
    ]
    return {
        "horse_id": text(runner["horse_id"]),
        "horse_number": text(runner.get("horse_number")),
        "horse_name": text(runner.get("horse_name")),
        "previous_issues": {
            "source": "previous_race_analysis.json",
            "observations": {key: previous.get(key) for key in observation_keys},
            "issues": [
                {"issue_id": issue_id, "description": issue}
                for issue_id, issue in zip(issue_ids, issues)
            ],
            "cause_assessment": "unknown",
            "late_observation": previous_late_observation(
                text(runner["horse_id"]), previous, late_runs
            ),
            "pending": "前走の観測値だけでは敗因を確定しない",
        },
        "issue_resolution": {
            "issue_refs": issue_ids,
            "registered_evidence": resolution_records,
            "pending": previous.get("overcoming_checks", []),
            "assessment": "unknown",
            "reason": "根拠の登録と出典内容の確認を区別する",
        },
        "condition_fit": {
            "source": "runner_analysis.json",
            "experience": ability.get("condition_evidence"),
            "observed_runs": [
                {key: row.get(key) for key in (
                    "race_id", "date", "surface", "distance", "rank",
                    "time", "margin", "passing", "last3f",
                )}
                for row in ability.get("analysis", [])
            ],
            "assessment": "unknown",
            "pending": "条件経験と、今回能力を出せる根拠を区別する",
        },
        "pace_and_position": {
            "source": "pace_analysis functions + validated runner_history.json",
            "hypotheses": {key: pace.get(key) for key in (
                "running_style", "likely_leader", "slow_pace",
                "middle_pace", "high_pace", "pace_dependency",
            )},
            "past_position_records": pace.get("race_details", []),
            "jockey": runner.get("jockey"),
            "assessment": "unknown",
            "pending": "今回の位置取りと展開別評価は仮説として確認する",
        },
        "track_fit": {
            "shared_observation_ref": "race_track_observations",
            "assessment": "unknown",
            "pending": "当日傾向と各馬の走り方の適合を照合する",
        },
        "body_and_burden": {
            "source": "race.json + previous_race_analysis.json",
            "body_weight": runner.get("body_weight"),
            "body_weight_change": runner.get("body_weight_change"),
            "carried_weight": runner.get("carried_weight"),
            "sex_age": runner.get("sex_age"),
            "previous_body_weight": previous.get("horse_weight"),
            "previous_race_id": previous.get("race_id"),
            "assessment": "unknown",
            "pending": "馬体・斤量単独では状態や能力発揮を判定しない",
        },
    }


def main():
    race = read_json("race.json")
    race_id = text(race.get("race_id"))
    if not re.fullmatch(r"\d{12}", race_id) or not text(race.get("race_date")):
        raise ValueError("Missing race ID or date")
    runners = race.get("horses")
    if not isinstance(runners, list) or not runners:
        raise ValueError("Missing race horses")
    expected = {text(horse.get("horse_id")) for horse in runners}
    horse_index(race, expected, "race.json")

    history = read_json("runner_history.json")
    ability = read_json("runner_analysis.json")
    previous = read_json("previous_race_analysis.json")
    for filename, data in (
        ("runner_history.json", history),
        ("runner_analysis.json", ability),
        ("previous_race_analysis.json", previous),
    ):
        require_target(data, race_id, filename)
    for filename, data in (
        ("runner_history.json", history),
        ("previous_race_analysis.json", previous),
    ):
        if (data.get("future_race_usage") is not False
                or data.get("leak_check_passed") is not True):
            raise ValueError(f"Past race checks failed: {filename}")
    validate_history(race, history, {})
    history_by_id = horse_index(history, expected, "runner_history.json")
    ability_by_id = horse_index(ability, expected, "runner_analysis.json")
    previous_by_id = horse_index(previous, expected, "previous_race_analysis.json")
    pace_by_id = {
        horse_id: analyze_pace(history_by_id[horse_id])
        for horse_id in history_by_id
    }

    statuses = {}
    late_runs = late_observation_index(race_id, expected, statuses)
    track = optional_source("track_condition.json", race, statuses)
    bias = optional_source("day_bias.json", race, statuses, check_future=True)
    output = {
        "schema_version": 1,
        "evidence_version": "performance_evidence_v2",
        "target_race_id": race_id,
        "race_date": race["race_date"],
        "updated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "policy": {
            "diagnostic_only": True,
            "training_used": False,
            "numerical_performance_rate_produced": False,
            "registered_evidence_requires_source_content_review": True,
            "shared_track_observations_stored_once": True,
            "assessment_requires_review": True,
            "pre_start_timing_verified": False,
            "formal_evaluation_eligible": False,
        },
        "optional_source_status": statuses,
        "race_track_observations": track_observations(track, bias),
        "race_pace_hypothesis": build_race_scenario(list(pace_by_id.values())),
        "horses": [
            build_horse(
                runner, ability_by_id[text(runner["horse_id"])],
                previous_by_id[text(runner["horse_id"])],
                pace_by_id[text(runner["horse_id"])], race_id, late_runs,
            )
            for runner in runners
        ],
    }
    temporary = Path(OUTPUT_FILE + ".tmp")
    temporary.write_text(
        json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT_FILE)
    print("Performance evidence:", race_id, "horses:", len(output["horses"]))


if __name__ == "__main__":
    main()
