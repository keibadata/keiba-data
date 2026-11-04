
import json
import math
import re
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


EVIDENCE_FILE = Path("runner_ability_evidence.json")
FEATURES_FILE = Path("runner_lap_features.json")
OUTPUT_FILE = Path("runner_pace_context.json")

VERSION = "runner_pace_context_v1"


def load(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON root: {path}")
    return data


def number(value):
    if type(value) not in (int, float):
        return None
    result = float(value)
    return result if math.isfinite(result) else None


def integer(value):
    return value if type(value) is int else None


def text(value):
    return str(value if value is not None else "").strip()


def safe_ratio(numerator, denominator):
    if (
        numerator is None
        or denominator is None
        or denominator <= 0
    ):
        return None
    return round(numerator / denominator, 4)


def build_context(past, lap):
    field = past.get("field") or {}

    finish = integer(past.get("finish"))
    last3f_rank = integer(field.get("last3f_rank"))
    last3f_count = integer(
        field.get("last3f_observed_count")
    )
    fourth = integer(field.get("passing_4c"))
    field_count = integer(
        field.get("classified_finish_count")
    )

    gap = number(
        field.get("winner_time_gap_seconds")
    )
    last3f = number(past.get("last3f"))

    lap_features = (
        lap.get("features")
        if isinstance(lap, dict)
        and lap.get("status") == "ok"
        else None
    )

    if not isinstance(lap_features, dict):
        lap_features = None

    # 着順・上がり順位・4角位置は独立した
    # 能力加点として扱わない。
    evidence = {
        "finish": finish,
        "field_count": field_count,
        "finish_ratio": safe_ratio(
            finish, field_count
        ),
        "fourth_corner_position": fourth,
        "fourth_corner_ratio": safe_ratio(
            fourth, field_count
        ),
        "fourth_corner_evidence_status": (
            (field.get("passing_4c_evidence") or {})
            .get("status")
        ),
        "last3f_seconds": last3f,
        "last3f_rank": last3f_rank,
        "last3f_observed_count": last3f_count,
        "last3f_rank_ratio": safe_ratio(
            last3f_rank, last3f_count
        ),
        "winner_time_gap_seconds": gap,
    }

    unknowns = []

    if fourth is None:
        unknowns.append("4角位置不明")

    if last3f_rank is None:
        unknowns.append("上がり順位不明")

    if gap is None:
        unknowns.append("勝ち馬との時計差不明")

    if lap_features is None:
        unknowns.append("ラップ特徴量不明")

    return {
        "race_id": text(past.get("race_id")),
        "date": text(past.get("date")),
        "race_name": text(past.get("race_name")),
        "surface": text(past.get("surface")),
        "distance": past.get("distance"),
        "lap_connection_status": (
            "connected"
            if lap_features is not None
            else "unknown"
        ),
        "source_pace_code": (
            lap.get("source_pace_code")
            if lap_features is not None
            else None
        ),
        "race_lap_features": lap_features,
        "horse_performance_evidence": evidence,
        "assessment": {
            "pace_advantage": None,
            "pace_disadvantage": None,
            "individual_lap": None,
            "trouble": None,
            "previous_race_issue": None,
            "issue_resolution": None,
            "ability_adjustment": None,
            "performance_rate_adjustment": None,
        },
        "unknowns": unknowns,
    }


def main():
    evidence = load(EVIDENCE_FILE)
    features = load(FEATURES_FILE)

    target_id = text(
        evidence.get("target_race_id")
    )

    if (
        not re.fullmatch(r"\d{12}", target_id)
        or target_id != text(
            features.get("target_race_id")
        )
    ):
        raise ValueError(
            "Target Race ID mismatch"
        )

    if (
        evidence.get("version")
        != "ability_evidence_v1"
        or evidence.get("future_race_usage")
        is not False
        or evidence.get("leak_check_passed")
        is not True
        or evidence.get("scoring_applied")
        is not False
        or features.get("version")
        != "race_lap_features_v1"
        or features.get("future_race_usage")
        is not False
        or features.get("leak_check_passed")
        is not True
        or features.get("scoring_applied")
        is not False
    ):
        raise ValueError(
            "Source safety validation failed"
        )

    horses = evidence.get("horses")
    feature_rows = features.get("races")

    if (
        not isinstance(horses, list)
        or not isinstance(feature_rows, list)
    ):
        raise ValueError(
            "Invalid source structure"
        )

    feature_map = {}

    for row in feature_rows:
        if not isinstance(row, dict):
            raise ValueError(
                "Invalid feature row"
            )

        race_id = text(row.get("race_id"))

        if (
            not re.fullmatch(r"\d{12}", race_id)
            or race_id in feature_map
        ):
            raise ValueError(
                "Invalid or duplicate Race ID"
            )

        feature_map[race_id] = row

    result_horses = []
    statuses = Counter()

    for horse in horses:
        if not isinstance(horse, dict):
            raise ValueError(
                "Invalid horse row"
            )

        past_races = horse.get("past_races")

        if not isinstance(past_races, list):
            raise ValueError(
                "Invalid past races"
            )

        contexts = []

        for past in past_races:
            if not isinstance(past, dict):
                raise ValueError(
                    "Invalid past race row"
                )

            field = past.get("field") or {}
            race_id = text(past.get("race_id"))
            lap_key = text(
                field.get("race_lap_key")
            )

            lap = None

            if (
                field.get("matched") is True
                and lap_key == race_id
                and race_id in feature_map
            ):
                candidate = feature_map[race_id]

                if (
                    candidate.get("status") == "ok"
                    and text(
                        candidate.get("surface")
                    ) == text(
                        past.get("surface")
                    )
                    and candidate.get("distance")
                    == past.get("distance")
                    and text(
                        candidate.get("race_date")
                    ) == text(
                        past.get("date")
                    )
                    and candidate.get(
                        "source_pace_code"
                    ) == field.get(
                        "source_pace_code"
                    )
                ):
                    lap = candidate

            context = build_context(past, lap)

            statuses[
                context["lap_connection_status"]
            ] += 1

            contexts.append(context)

        result_horses.append({
            "horse_id": horse.get("horse_id"),
            "horse_number": horse.get(
                "horse_number"
            ),
            "horse_name": horse.get(
                "horse_name"
            ),
            "past_race_count": len(contexts),
            "past_races": contexts,
        })

    output = {
        "version": VERSION,
        "updated_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(),
        "target_race_id": target_id,
        "source_files": [
            str(EVIDENCE_FILE),
            str(FEATURES_FILE),
        ],
        "future_race_usage": False,
        "leak_check_passed": True,
        "scoring_applied": False,
        "summary": {
            "horse_count": len(result_horses),
            "past_race_count": sum(
                h["past_race_count"]
                for h in result_horses
            ),
            "lap_connected_run_count": (
                statuses["connected"]
            ),
            "lap_unknown_run_count": (
                statuses["unknown"]
            ),
        },
        "notes": [
            "レース全体のラップと個別馬の実績をRace IDで接続。",
            "4角位置・上がり順位・着順・時計差は観測事実。",
            "4角位置は道中全体の位置取りを保証しない。",
            "上がり順位だけで末脚能力や展開有利を断定しない。",
            "ラップはレース全体の値。個別馬ラップではない。",
            "着順・時計差・上がりを重複加点しない。",
            "不利・敗因・前走課題克服は未判定。",
            "未知数を0点または能力不足として扱わない。",
            "能力点・今回発揮率・最終評価には未反映。",
        ],
        "horses": result_horses,
    }

    temporary = OUTPUT_FILE.with_suffix(
        ".json.tmp"
    )

    temporary.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(OUTPUT_FILE)

    print(
        "Runner pace context:",
        target_id,
        output["summary"],
    )


if __name__ == "__main__":
    main()
