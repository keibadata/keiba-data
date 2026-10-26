import argparse
import json
import re
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path


VERIFICATION_ROOT = Path("race_verifications")
OUTPUT_FILE = Path("verification_database.json")

SCHEMA_VERSION = 1

JST = timezone(timedelta(hours=9))


def now_jst_iso():
    return datetime.now(JST).isoformat(timespec="seconds")


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )

    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def to_int(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def to_float(value):
    if value is None:
        return None

    if isinstance(value, bool):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def round3(value):
    if value is None:
        return None

    return round(
        float(value),
        3,
    )


def safe_rate(numerator, denominator):
    if not denominator:
        return None

    return round3(
        numerator / denominator
    )


def safe_mean(values):
    cleaned = [
        float(value)
        for value in values
        if value is not None
    ]

    if not cleaned:
        return None

    return round3(
        sum(cleaned) / len(cleaned)
    )


def parse_datetime(value):
    text = str(
        value or ""
    ).strip()

    if not text:
        return None

    try:
        if text.endswith("Z"):
            text = (
                text[:-1]
                + "+00:00"
            )

        return datetime.fromisoformat(
            text
        )

    except ValueError:
        return None


def race_number_from_id(race_id):
    text = str(
        race_id or ""
    ).strip()

    if not re.fullmatch(
        r"\d{12}",
        text,
    ):
        return None

    number = to_int(
        text[-2:]
    )

    if (
        number is None
        or number < 1
        or number > 12
    ):
        return None

    return number


def normalize_start_time(value):
    text = str(
        value or ""
    ).strip()

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        text,
    )

    if not match:
        return ""

    hour = int(
        match.group(1)
    )
    minute = int(
        match.group(2)
    )

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return ""

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def classify_daypart(start_time):
    normalized = normalize_start_time(
        start_time
    )

    if not normalized:
        return "unknown"

    hour = int(
        normalized.split(":")[0]
    )

    if hour < 12:
        return "morning"

    return "afternoon"


def get_snapshot_metadata(
    verification,
):
    prediction_snapshot = (
        verification.get(
            "prediction_snapshot"
        )
        or {}
    )

    snapshot_path_text = str(
        prediction_snapshot.get(
            "path",
            "",
        )
        or ""
    ).strip()

    result = {
        "snapshot_path": (
            snapshot_path_text
        ),
        "scheduled_start_time": "",
        "race_start_at": "",
        "analysis_mode": "",
        "snapshot_loaded": False,
    }

    if not snapshot_path_text:
        return result

    snapshot_path = Path(
        snapshot_path_text
    )

    if not snapshot_path.is_file():
        return result

    try:
        snapshot = load_json(
            snapshot_path
        )
    except (
        OSError,
        json.JSONDecodeError,
    ):
        return result

    race = (
        snapshot.get("race")
        or {}
    )

    timing = (
        snapshot.get("timing")
        or {}
    )

    start_time = normalize_start_time(
        race.get(
            "scheduled_start_time"
        )
    )

    race_start_at = str(
        timing.get(
            "race_start_at",
            "",
        )
        or ""
    ).strip()

    if (
        not start_time
        and race_start_at
    ):
        parsed = parse_datetime(
            race_start_at
        )

        if parsed is not None:
            start_time = (
                f"{parsed.hour:02d}:"
                f"{parsed.minute:02d}"
            )

    result.update(
        {
            "scheduled_start_time": (
                start_time
            ),
            "race_start_at": (
                race_start_at
            ),
            "analysis_mode": str(
                snapshot.get(
                    "analysis_mode",
                    "",
                )
                or ""
            ).strip(),
            "snapshot_loaded": True,
        }
    )

    return result


def verification_sort_key(entry):
    created_at = parse_datetime(
        entry["data"].get(
            "created_at"
        )
    )

    if created_at is not None:
        return (
            created_at.timestamp(),
            entry["path"].as_posix(),
        )

    try:
        mtime = (
            entry["path"]
            .stat()
            .st_mtime
        )
    except OSError:
        mtime = 0.0

    return (
        mtime,
        entry["path"].as_posix(),
    )


def collect_verifications(root):
    if not root.exists():
        return []

    entries = []

    for path in sorted(
        root.rglob(
            "verification_*.json"
        )
    ):
        try:
            data = load_json(path)
        except (
            OSError,
            json.JSONDecodeError,
        ):
            continue

        if (
            data.get(
                "verification_kind"
            )
            != "prediction_vs_result"
        ):
            continue

        race_id = str(
            data.get(
                "race_id",
                "",
            )
            or ""
        ).strip()

        if not re.fullmatch(
            r"\d{12}",
            race_id,
        ):
            continue

        entries.append(
            {
                "path": path,
                "data": data,
                "race_id": race_id,
            }
        )

    return entries


def build_error_categories(horses):
    counter = Counter()

    for horse in horses:
        comparison = (
            horse.get(
                "comparison"
            )
            or {}
        )

        error = (
            comparison.get(
                "error_candidate"
            )
            or {}
        )

        category = str(
            error.get(
                "category",
                "",
            )
            or ""
        ).strip()

        if category:
            counter[category] += 1

    return dict(
        sorted(
            counter.items()
        )
    )


def build_rank_error_values(horses):
    values = []

    for horse in horses:
        comparison = (
            horse.get(
                "comparison"
            )
            or {}
        )

        value = to_float(
            comparison.get(
                "absolute_rank_error"
            )
        )

        if value is not None:
            values.append(value)

    return values


def normalize_verification(
    entry,
):
    data = entry["data"]

    summary = (
        data.get("summary")
        or {}
    )

    horses = (
        data.get("horses")
        or []
    )

    snapshot_info = (
        data.get(
            "prediction_snapshot"
        )
        or {}
    )

    predicted_context = (
        data.get(
            "predicted_race_context"
        )
        or {}
    )

    snapshot_meta = (
        get_snapshot_metadata(
            data
        )
    )

    race_id = entry["race_id"]

    rank_errors = (
        build_rank_error_values(
            horses
        )
    )

    winner = (
        summary.get("winner")
        or {}
    )

    predicted_first = (
        summary.get(
            "predicted_first"
        )
        or {}
    )

    predicted_pace = str(
        predicted_context.get(
            "base_pace",
            "",
        )
        or ""
    ).strip()

    actual_pace = str(
        data.get(
            "actual_pace",
            "",
        )
        or ""
    ).strip()

    pace_match = None

    if (
        predicted_pace
        and actual_pace
    ):
        pace_match = (
            predicted_pace
            == actual_pace
        )

    start_time = (
        snapshot_meta[
            "scheduled_start_time"
        ]
    )

    aggregate_eligible = (
        data.get(
            "aggregate_eligible"
        )
        is True
    )

    record = {
        "race_id": race_id,
        "race_date": str(
            data.get(
                "race_date",
                "",
            )
            or ""
        ).strip(),
        "track": str(
            data.get(
                "track",
                "",
            )
            or ""
        ).strip(),
        "race_number": (
            race_number_from_id(
                race_id
            )
        ),
        "race_name": str(
            data.get(
                "race_name",
                "",
            )
            or ""
        ).strip(),
        "surface": str(
            data.get(
                "surface",
                "",
            )
            or ""
        ).strip(),
        "distance": to_int(
            data.get(
                "distance"
            )
        ),
        "actual_track_condition": str(
            data.get(
                "actual_track_condition",
                "",
            )
            or ""
        ).strip(),
        "scheduled_start_time": (
            start_time
        ),
        "daypart": (
            classify_daypart(
                start_time
            )
        ),
        "analysis_mode": (
            snapshot_meta[
                "analysis_mode"
            ]
            or str(
                predicted_context.get(
                    "analysis_mode",
                    "",
                )
                or ""
            ).strip()
        ),
        "verification_created_at": str(
            data.get(
                "created_at",
                "",
            )
            or ""
        ).strip(),
        "verification_path": (
            entry["path"]
            .as_posix()
        ),
        "snapshot_id": str(
            snapshot_info.get(
                "snapshot_id",
                "",
            )
            or ""
        ).strip(),
        "snapshot_path": str(
            snapshot_info.get(
                "path",
                "",
            )
            or ""
        ).strip(),
        "prediction_saved_at": str(
            snapshot_info.get(
                "prediction_saved_at",
                "",
            )
            or ""
        ).strip(),
        "timing_status": str(
            snapshot_info.get(
                "timing_status",
                "",
            )
            or ""
        ).strip(),
        "evaluation_status": str(
            data.get(
                "evaluation_status",
                "",
            )
            or ""
        ).strip(),
        "aggregate_eligible": (
            aggregate_eligible
        ),
        "aggregate_exclusion_reason": str(
            data.get(
                "aggregate_exclusion_reason",
                "",
            )
            or ""
        ).strip(),
        "matched_horse_count": to_int(
            summary.get(
                "matched_horse_count"
            )
        )
        or 0,
        "race_mae": to_float(
            summary.get(
                "mean_absolute_rank_error"
            )
        ),
        "rank_error_sum": round3(
            sum(rank_errors)
        )
        if rank_errors
        else 0.0,
        "rank_error_count": len(
            rank_errors
        ),
        "actual_top3_count": to_int(
            summary.get(
                "actual_top3_count"
            )
        )
        or 0,
        "actual_top3_in_predicted_top3": (
            to_int(
                summary.get(
                    "actual_top3_in_predicted_top3"
                )
            )
            or 0
        ),
        "actual_top3_in_predicted_top5": (
            to_int(
                summary.get(
                    "actual_top3_in_predicted_top5"
                )
            )
            or 0
        ),
        "top3_coverage_at_3": to_float(
            summary.get(
                "top3_coverage_at_3"
            )
        ),
        "top3_coverage_at_5": to_float(
            summary.get(
                "top3_coverage_at_5"
            )
        ),
        "winner": {
            "horse_number": to_int(
                winner.get(
                    "horse_number"
                )
            ),
            "horse_name": str(
                winner.get(
                    "horse_name",
                    "",
                )
                or ""
            ).strip(),
            "predicted_rank": to_int(
                winner.get(
                    "predicted_rank"
                )
            ),
            "ability_rank": to_int(
                winner.get(
                    "ability_rank"
                )
            ),
        },
        "predicted_first": {
            "horse_number": to_int(
                predicted_first.get(
                    "horse_number"
                )
            ),
            "horse_name": str(
                predicted_first.get(
                    "horse_name",
                    "",
                )
                or ""
            ).strip(),
            "actual_finish": to_int(
                predicted_first.get(
                    "actual_finish"
                )
            ),
        },
        "major_miss_count": to_int(
            summary.get(
                "major_miss_count"
            )
        )
        or 0,
        "predicted_pace": (
            predicted_pace
        ),
        "actual_pace": (
            actual_pace
        ),
        "pace_match": (
            pace_match
        ),
        "day_bias_reference_race_count": (
            to_int(
                predicted_context.get(
                    "day_bias_reference_race_count"
                )
            )
            or 0
        ),
        "predicted_running_style_bias": str(
            predicted_context.get(
                "predicted_running_style_bias",
                "",
            )
            or ""
        ).strip(),
        "predicted_inside_outside_bias": str(
            predicted_context.get(
                "predicted_inside_outside_bias",
                "",
            )
            or ""
        ).strip(),
        "predicted_time_bias": str(
            predicted_context.get(
                "predicted_time_bias",
                "",
            )
            or ""
        ).strip(),
        "error_categories": (
            build_error_categories(
                horses
            )
        ),
    }

    return record


def basic_metrics(records):
    race_count = len(records)

    matched_horses = sum(
        record[
            "matched_horse_count"
        ]
        for record in records
    )

    rank_error_sum = sum(
        record[
            "rank_error_sum"
        ]
        for record in records
    )

    rank_error_count = sum(
        record[
            "rank_error_count"
        ]
        for record in records
    )

    actual_top3_count = sum(
        record[
            "actual_top3_count"
        ]
        for record in records
    )

    top3_in_3 = sum(
        record[
            "actual_top3_in_predicted_top3"
        ]
        for record in records
    )

    top3_in_5 = sum(
        record[
            "actual_top3_in_predicted_top5"
        ]
        for record in records
    )

    winner_ranks = [
        record["winner"][
            "predicted_rank"
        ]
        for record in records
        if (
            record["winner"][
                "predicted_rank"
            ]
            is not None
        )
    ]

    winner_top1 = sum(
        1
        for rank in winner_ranks
        if rank <= 1
    )

    winner_top3 = sum(
        1
        for rank in winner_ranks
        if rank <= 3
    )

    winner_top5 = sum(
        1
        for rank in winner_ranks
        if rank <= 5
    )

    predicted_first_finishes = [
        record[
            "predicted_first"
        ][
            "actual_finish"
        ]
        for record in records
        if (
            record[
                "predicted_first"
            ][
                "actual_finish"
            ]
            is not None
        )
    ]

    predicted_first_wins = sum(
        1
        for finish
        in predicted_first_finishes
        if finish == 1
    )

    pace_records = [
        record
        for record in records
        if (
            record[
                "pace_match"
            ]
            is not None
        )
    ]

    pace_matches = sum(
        1
        for record in pace_records
        if record[
            "pace_match"
        ]
    )

    major_miss_count = sum(
        record[
            "major_miss_count"
        ]
        for record in records
    )

    error_counter = Counter()

    for record in records:
        error_counter.update(
            record[
                "error_categories"
            ]
        )

    return {
        "race_count": (
            race_count
        ),
        "matched_horse_count": (
            matched_horses
        ),
        "race_mean_mae": (
            safe_mean(
                [
                    record[
                        "race_mae"
                    ]
                    for record
                    in records
                ]
            )
        ),
        "horse_weighted_mae": (
            round3(
                rank_error_sum
                / rank_error_count
            )
            if rank_error_count
            else None
        ),
        "actual_top3_count": (
            actual_top3_count
        ),
        "actual_top3_in_predicted_top3": (
            top3_in_3
        ),
        "actual_top3_in_predicted_top5": (
            top3_in_5
        ),
        "top3_coverage_at_3": (
            safe_rate(
                top3_in_3,
                actual_top3_count,
            )
        ),
        "top3_coverage_at_5": (
            safe_rate(
                top3_in_5,
                actual_top3_count,
            )
        ),
        "winner_rank_known_count": (
            len(winner_ranks)
        ),
        "winner_capture_top1_count": (
            winner_top1
        ),
        "winner_capture_top3_count": (
            winner_top3
        ),
        "winner_capture_top5_count": (
            winner_top5
        ),
        "winner_capture_top1_rate": (
            safe_rate(
                winner_top1,
                len(winner_ranks),
            )
        ),
        "winner_capture_top3_rate": (
            safe_rate(
                winner_top3,
                len(winner_ranks),
            )
        ),
        "winner_capture_top5_rate": (
            safe_rate(
                winner_top5,
                len(winner_ranks),
            )
        ),
        "predicted_first_result_count": (
            len(
                predicted_first_finishes
            )
        ),
        "predicted_first_win_count": (
            predicted_first_wins
        ),
        "predicted_first_win_rate": (
            safe_rate(
                predicted_first_wins,
                len(
                    predicted_first_finishes
                ),
            )
        ),
        "predicted_first_mean_finish": (
            safe_mean(
                predicted_first_finishes
            )
        ),
        "pace_known_count": (
            len(pace_records)
        ),
        "pace_match_count": (
            pace_matches
        ),
        "pace_match_rate": (
            safe_rate(
                pace_matches,
                len(pace_records),
            )
        ),
        "major_miss_count": (
            major_miss_count
        ),
        "major_miss_rate_per_horse": (
            safe_rate(
                major_miss_count,
                matched_horses,
            )
        ),
        "error_categories": dict(
            sorted(
                error_counter.items()
            )
        ),
    }


def grouped_metrics(
    records,
    key,
):
    groups = defaultdict(list)

    for record in records:
        value = record.get(key)

        if value in (
            None,
            "",
        ):
            value = "unknown"

        groups[
            str(value)
        ].append(
            record
        )

    return {
        name: basic_metrics(
            group_records
        )
        for (
            name,
            group_records,
        )
        in sorted(
            groups.items()
        )
    }


def aggregate_metrics(records):
    metrics = basic_metrics(
        records
    )

    metrics[
        "by_daypart"
    ] = grouped_metrics(
        records,
        "daypart",
    )

    metrics[
        "by_track"
    ] = grouped_metrics(
        records,
        "track",
    )

    metrics[
        "by_surface"
    ] = grouped_metrics(
        records,
        "surface",
    )

    metrics[
        "by_analysis_mode"
    ] = grouped_metrics(
        records,
        "analysis_mode",
    )

    return metrics


def select_records(entries):
    grouped = defaultdict(list)

    for entry in entries:
        grouped[
            entry["race_id"]
        ].append(
            entry
        )

    diagnostic_selected = []
    formal_selected = []

    for race_id in sorted(
        grouped
    ):
        race_entries = sorted(
            grouped[race_id],
            key=verification_sort_key,
        )

        latest = race_entries[-1]

        diagnostic_selected.append(
            latest
        )

        eligible = [
            entry
            for entry
            in race_entries
            if (
                entry["data"].get(
                    "aggregate_eligible"
                )
                is True
            )
        ]

        if eligible:
            formal_selected.append(
                sorted(
                    eligible,
                    key=(
                        verification_sort_key
                    ),
                )[-1]
            )

    return (
        diagnostic_selected,
        formal_selected,
    )


def build_database(
    verification_root,
):
    entries = collect_verifications(
        verification_root
    )

    (
        diagnostic_entries,
        formal_entries,
    ) = select_records(
        entries
    )

    diagnostic_records = [
        normalize_verification(
            entry
        )
        for entry
        in diagnostic_entries
    ]

    formal_records = [
        normalize_verification(
            entry
        )
        for entry
        in formal_entries
    ]

    diagnostic_records.sort(
        key=lambda record: (
            record[
                "race_date"
            ],
            record[
                "track"
            ],
            record[
                "race_number"
            ]
            or 0,
            record[
                "race_id"
            ],
        )
    )

    formal_records.sort(
        key=lambda record: (
            record[
                "race_date"
            ],
            record[
                "track"
            ],
            record[
                "race_number"
            ]
            or 0,
            record[
                "race_id"
            ],
        )
    )

    database = {
        "schema_version": (
            SCHEMA_VERSION
        ),
        "database_kind": (
            "race_verification_aggregate"
        ),
        "updated_at": (
            now_jst_iso()
        ),
        "source": {
            "verification_root": (
                verification_root
                .as_posix()
            ),
            "source_file_count": (
                len(entries)
            ),
            "unique_race_count": (
                len(
                    diagnostic_records
                )
            ),
            "formal_race_count": (
                len(
                    formal_records
                )
            ),
            "diagnostic_race_count": (
                len(
                    diagnostic_records
                )
            ),
        },
        "policy": {
            "formal_summary_scope": (
                "raceごとに最新の"
                "aggregate_eligible=true"
                "検証のみを使用"
            ),
            "diagnostic_summary_scope": (
                "raceごとに最新の検証を"
                "eligibilityに関係なく使用"
            ),
            "duplicate_race_policy": (
                "同一race_idの複数検証を"
                "重複集計しない"
            ),
            "daypart_policy": (
                "scheduled_start_timeが"
                "12:00未満=morning、"
                "12:00以降=afternoon"
            ),
            "hindsight_protection": (
                "正式精度には"
                "aggregate_eligible=true"
                "のみ使用"
            ),
        },
        "formal_summary": (
            aggregate_metrics(
                formal_records
            )
        ),
        "diagnostic_summary": (
            aggregate_metrics(
                diagnostic_records
            )
        ),
        "formal_records": (
            formal_records
        ),
        "diagnostic_records": (
            diagnostic_records
        ),
    }

    return database


def validate_database(database):
    if (
        database.get(
            "schema_version"
        )
        != SCHEMA_VERSION
    ):
        raise ValueError(
            "schema_version mismatch"
        )

    if (
        database.get(
            "database_kind"
        )
        != "race_verification_aggregate"
    ):
        raise ValueError(
            "database_kind mismatch"
        )

    source = (
        database.get("source")
        or {}
    )

    formal_records = (
        database.get(
            "formal_records"
        )
        or []
    )

    diagnostic_records = (
        database.get(
            "diagnostic_records"
        )
        or []
    )

    formal_summary = (
        database.get(
            "formal_summary"
        )
        or {}
    )

    diagnostic_summary = (
        database.get(
            "diagnostic_summary"
        )
        or {}
    )

    if (
        source.get(
            "formal_race_count"
        )
        != len(formal_records)
    ):
        raise ValueError(
            "formal race count mismatch"
        )

    if (
        source.get(
            "diagnostic_race_count"
        )
        != len(
            diagnostic_records
        )
    ):
        raise ValueError(
            "diagnostic race count mismatch"
        )

    if (
        formal_summary.get(
            "race_count"
        )
        != len(formal_records)
    ):
        raise ValueError(
            "formal summary count mismatch"
        )

    if (
        diagnostic_summary.get(
            "race_count"
        )
        != len(
            diagnostic_records
        )
    ):
        raise ValueError(
            "diagnostic summary count mismatch"
        )

    formal_ids = [
        record.get(
            "race_id"
        )
        for record
        in formal_records
    ]

    diagnostic_ids = [
        record.get(
            "race_id"
        )
        for record
        in diagnostic_records
    ]

    if (
        len(formal_ids)
        != len(
            set(formal_ids)
        )
    ):
        raise ValueError(
            "duplicate formal race_id"
        )

    if (
        len(diagnostic_ids)
        != len(
            set(diagnostic_ids)
        )
    ):
        raise ValueError(
            "duplicate diagnostic race_id"
        )

    for record in formal_records:
        if (
            record.get(
                "aggregate_eligible"
            )
            is not True
        ):
            raise ValueError(
                "ineligible race found "
                "in formal records"
            )

    return True


def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Aggregate race verification "
            "records into one database"
        )
    )

    parser.add_argument(
        "--verification-root",
        default=(
            VERIFICATION_ROOT
            .as_posix()
        ),
    )

    parser.add_argument(
        "--output",
        default=(
            OUTPUT_FILE
            .as_posix()
        ),
    )

    return parser.parse_args()


def main():
    args = parse_args()

    verification_root = Path(
        args.verification_root
    )

    output_path = Path(
        args.output
    )

    database = build_database(
        verification_root
    )

    validate_database(
        database
    )

    save_json(
        output_path,
        database,
    )

    source = database["source"]

    formal = (
        database[
            "formal_summary"
        ]
    )

    diagnostic = (
        database[
            "diagnostic_summary"
        ]
    )

    print()
    print(
        "===== VERIFICATION AGGREGATE ====="
    )
    print(
        "source files:",
        source[
            "source_file_count"
        ],
    )
    print(
        "unique races:",
        source[
            "unique_race_count"
        ],
    )
    print(
        "formal races:",
        formal[
            "race_count"
        ],
    )
    print(
        "diagnostic races:",
        diagnostic[
            "race_count"
        ],
    )
    print(
        "formal top3 @3:",
        formal[
            "top3_coverage_at_3"
        ],
    )
    print(
        "formal top3 @5:",
        formal[
            "top3_coverage_at_5"
        ],
    )
    print(
        "formal winner top5:",
        formal[
            "winner_capture_top5_rate"
        ],
    )
    print(
        "formal pace match:",
        formal[
            "pace_match_rate"
        ],
    )
    print(
        "diagnostic top3 @3:",
        diagnostic[
            "top3_coverage_at_3"
        ],
    )
    print(
        "diagnostic top3 @5:",
        diagnostic[
            "top3_coverage_at_5"
        ],
    )
    print(
        "diagnostic MAE:",
        diagnostic[
            "horse_weighted_mae"
        ],
    )
    print(
        "saved:",
        output_path.as_posix(),
    )
    print(
        "VERIFICATION AGGREGATE OK"
    )
    print(
        "=================================="
    )


if __name__ == "__main__":
    main()
