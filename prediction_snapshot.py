import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


RACE_FILE = "race.json"
FINAL_ANALYSIS_FILE = "final_analysis.json"
OUTPUT_ROOT = Path("prediction_snapshots")

JST = timezone(timedelta(hours=9))


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"required file is missing: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")


def normalize_text(value):
    value = str(
        value or ""
    ).strip()

    return re.sub(
        r"\s+",
        " ",
        value
    )


def normalize_race_id(value):
    race_id = normalize_text(
        value
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        raise ValueError(
            f"invalid race_id: {race_id!r}"
        )

    return race_id


def parse_iso_datetime(value):
    text = normalize_text(
        value
    )

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=JST
        )

    return parsed.astimezone(
        JST
    )


def parse_race_date(value):
    text = normalize_text(
        value
    )

    if not text:
        return None

    try:
        return date.fromisoformat(
            text
        )

    except ValueError:
        return None


def safe_timestamp(
    value,
    fallback
):
    parsed = parse_iso_datetime(
        value
    )

    if parsed is None:
        parsed = fallback

    return parsed.strftime(
        "%Y%m%dT%H%M%S%f%z"
    )


def build_timing(
    race_date_value,
    saved_at
):
    race_day = parse_race_date(
        race_date_value
    )

    saved_day = saved_at.date()

    if race_day is None:
        return {
            "status": "race_date_unknown",
            "evaluation_eligible": None,
            "reason": (
                "race_dateを確認できないため"
                "発走前予想か判定できない"
            ),
        }

    if saved_day < race_day:
        return {
            "status": "before_race_date",
            "evaluation_eligible": True,
            "reason": (
                "レース日前に保存された予想"
            ),
        }

    if saved_day > race_day:
        return {
            "status": "after_race_date",
            "evaluation_eligible": False,
            "reason": (
                "レース日後に保存されたため"
                "事前予想検証には使用しない"
            ),
        }

    return {
        "status": "same_day_unverified",
        "evaluation_eligible": None,
        "reason": (
            "同日保存のため発走時刻取得後に"
            "事前予想か判定する"
        ),
    }


def validate_inputs(
    race,
    final_analysis
):
    race_id = normalize_race_id(
        race.get(
            "race_id"
        )
    )

    final_race_id = normalize_race_id(
        final_analysis.get(
            "race_id"
        )
    )

    if race_id != final_race_id:
        raise ValueError(
            "race_id mismatch: "
            f"race.json={race_id} "
            f"final_analysis.json={final_race_id}"
        )

    ranking = final_analysis.get(
        "ranking"
    )

    if (
        not isinstance(
            ranking,
            list
        )
        or not ranking
    ):
        raise ValueError(
            "final_analysis.json has no ranking"
        )

    summary = final_analysis.get(
        "summary"
    )

    if not isinstance(
        summary,
        dict
    ):
        raise ValueError(
            "final_analysis.json summary is missing"
        )

    runner_count = int(
        summary.get(
            "runner_count",
            0
        )
        or 0
    )

    if runner_count <= 0:
        raise ValueError(
            "final_analysis runner_count is invalid"
        )

    if len(ranking) != runner_count:
        raise ValueError(
            "ranking count mismatch: "
            f"ranking={len(ranking)} "
            f"runner_count={runner_count}"
        )

    race_horse_count = int(
        race.get(
            "horse_count",
            0
        )
        or 0
    )

    if (
        race_horse_count > 0
        and race_horse_count
        != runner_count
    ):
        raise ValueError(
            "race horse_count mismatch: "
            f"race.json={race_horse_count} "
            f"final_analysis={runner_count}"
        )

    return race_id


def build_snapshot(
    race,
    final_analysis,
    saved_at
):
    race_id = validate_inputs(
        race,
        final_analysis
    )

    source_updated_at = normalize_text(
        final_analysis.get(
            "updated_at"
        )
    )

    timing = build_timing(
        race.get(
            "race_date"
        ),
        saved_at
    )

    snapshot_id = (
        race_id
        + "_"
        + safe_timestamp(
            source_updated_at,
            saved_at
        )
    )

    race_context = {
        "race_id": race_id,

        "race_date": normalize_text(
            race.get(
                "race_date"
            )
        ),

        "track": normalize_text(
            race.get(
                "track"
            )
            or race.get(
                "racecourse"
            )
        ),

        "race_name": normalize_text(
            race.get(
                "race_name"
            )
        ),

        "race_class": normalize_text(
            race.get(
                "race_class"
            )
        ),

        "age_condition": normalize_text(
            race.get(
                "age_condition"
            )
        ),

        "is_debut": bool(
            race.get(
                "is_debut",
                False
            )
        ),

        "surface": normalize_text(
            race.get(
                "surface"
            )
        ),

        "distance": race.get(
            "distance",
            0
        ),

        "track_condition": normalize_text(
            race.get(
                "track_condition"
            )
        ),

        "horse_count": int(
            race.get(
                "horse_count",
                0
            )
            or 0
        ),
    }

    return {
        "schema_version": 1,

        "snapshot_id": snapshot_id,

        "prediction_saved_at": (
            saved_at.isoformat()
        ),

        "source_final_analysis_updated_at": (
            source_updated_at
        ),

        "source_race_updated_at": normalize_text(
            race.get(
                "updated_at"
            )
        ),

        "snapshot_kind": "prediction",

        "provenance": {
            "github_run_id": normalize_text(
                os.environ.get(
                    "GITHUB_RUN_ID"
                )
            ),

            "github_run_number": normalize_text(
                os.environ.get(
                    "GITHUB_RUN_NUMBER"
                )
            ),

            "github_workflow": normalize_text(
                os.environ.get(
                    "GITHUB_WORKFLOW"
                )
            ),

            "github_sha": normalize_text(
                os.environ.get(
                    "GITHUB_SHA"
                )
            ),
        },

        "timing": timing,

        "race": race_context,

        "analysis_mode": normalize_text(
            final_analysis.get(
                "analysis_mode"
            )
            or "normal"
        ),

        "analysis": final_analysis,
    }


def snapshot_path(snapshot):
    race = snapshot[
        "race"
    ]

    race_id = race[
        "race_id"
    ]

    race_date = (
        race.get(
            "race_date"
        )
        or "date_unknown"
    )

    snapshot_id = snapshot[
        "snapshot_id"
    ]

    return (
        OUTPUT_ROOT
        / race_date
        / race_id
        / f"{snapshot_id}.json"
    )


def validate_existing_snapshot(
    path,
    snapshot
):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        existing = json.load(
            f
        )

    if (
        existing.get(
            "snapshot_id"
        )
        != snapshot.get(
            "snapshot_id"
        )
    ):
        raise ValueError(
            "existing snapshot id mismatch: "
            f"{path}"
        )

    if (
        existing.get(
            "race",
            {}
        ).get(
            "race_id"
        )
        != snapshot.get(
            "race",
            {}
        ).get(
            "race_id"
        )
    ):
        raise ValueError(
            "existing snapshot race_id mismatch: "
            f"{path}"
        )

    existing_analysis = existing.get(
        "analysis"
    )

    current_analysis = snapshot.get(
        "analysis"
    )

    if (
        existing_analysis
        != current_analysis
    ):
        raise ValueError(
            "snapshot path already exists "
            "but analysis content differs: "
            f"{path}"
        )


def main():
    race = load_json(
        RACE_FILE
    )

    final_analysis = load_json(
        FINAL_ANALYSIS_FILE
    )

    saved_at = datetime.now(
        JST
    )

    snapshot = build_snapshot(
        race=race,
        final_analysis=final_analysis,
        saved_at=saved_at,
    )

    output_path = snapshot_path(
        snapshot
    )

    if output_path.exists():
        validate_existing_snapshot(
            output_path,
            snapshot
        )

        print(
            "PREDICTION SNAPSHOT ALREADY EXISTS"
        )

    else:
        save_json(
            output_path,
            snapshot
        )

        print(
            "PREDICTION SNAPSHOT SAVED"
        )

    print(
        "snapshot_id:",
        snapshot[
            "snapshot_id"
        ]
    )

    print(
        "race_id:",
        snapshot[
            "race"
        ][
            "race_id"
        ]
    )

    print(
        "race_date:",
        snapshot[
            "race"
        ][
            "race_date"
        ]
    )

    print(
        "track:",
        snapshot[
            "race"
        ][
            "track"
        ]
    )

    print(
        "analysis_mode:",
        snapshot[
            "analysis_mode"
        ]
    )

    print(
        "runner_count:",
        snapshot[
            "race"
        ][
            "horse_count"
        ]
    )

    print(
        "timing_status:",
        snapshot[
            "timing"
        ][
            "status"
        ]
    )

    print(
        "evaluation_eligible:",
        snapshot[
            "timing"
        ][
            "evaluation_eligible"
        ]
    )

    print(
        "output:",
        output_path.as_posix()
    )


if __name__ == "__main__":
    main()
