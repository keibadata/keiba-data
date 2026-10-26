import json
import re
import subprocess
import sys
from pathlib import Path


RACE_ID_FILE = Path("race_id.txt")
RACE_FILE = Path("race.json")
FINAL_FILE = Path("final_analysis.json")
SNAPSHOT_SCRIPT = Path("prediction_snapshot.py")

REQUIRED_FILES = [
    "race.json",
    "history_db.json",
    "condition_history.json",
    "day_races.json",
    "day_time_history.json",
    "track_condition.json",
    "day_bias.json",
    "runner_history.json",
    "runner_race_db.json",
    "runner_time_fit.json",
    "runner_analysis.json",
    "previous_race_analysis.json",
    "pace_analysis.json",
    "race_bloodline_score.json",
    "final_analysis.json",
    "prediction_snapshot.py",
]


def fail(message):
    raise RuntimeError(message)


def load_json(path):
    path = Path(path)

    if not path.exists():
        fail(f"required file is missing: {path}")

    try:
        with path.open("r", encoding="utf-8") as f:
            return json.load(f)

    except Exception as exc:
        fail(
            f"cannot load JSON: {path}: {exc}"
        )


def normalize_race_id(value):
    race_id = str(
        value or ""
    ).strip()

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        fail(
            f"invalid race_id: {race_id!r}"
        )

    return race_id


def read_target_race_id():
    if not RACE_ID_FILE.exists():
        fail(
            "race_id.txt is missing"
        )

    return normalize_race_id(
        RACE_ID_FILE.read_text(
            encoding="utf-8"
        )
    )


def validate_required_files():
    missing = [
        path
        for path in REQUIRED_FILES
        if not Path(path).exists()
    ]

    if missing:
        fail(
            "required files are missing: "
            + ", ".join(missing)
        )


def validate_identity(
    target_race_id,
    race,
    final_analysis,
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

    if race_id != target_race_id:
        fail(
            "race.json race_id mismatch: "
            f"target={target_race_id} "
            f"race.json={race_id}"
        )

    if final_race_id != target_race_id:
        fail(
            "final_analysis race_id mismatch: "
            f"target={target_race_id} "
            f"final_analysis={final_race_id}"
        )


def validate_newcomer(
    final_analysis,
    summary,
    ranking,
    total,
):
    if not final_analysis.get(
        "is_debut",
        False
    ):
        fail(
            "newcomer mode without is_debut"
        )

    method = final_analysis.get(
        "method",
        {}
    )

    if not isinstance(
        method,
        dict
    ):
        fail(
            "newcomer method is missing"
        )

    if not method.get(
        "pedigree_only",
        False
    ):
        fail(
            "newcomer mode is not pedigree_only"
        )

    forbidden_flags = (
        "ability_used",
        "previous_race_used",
        "pace_used",
        "training_used",
        "jockey_used",
        "draw_used",
        "body_weight_used",
        "popularity_used",
        "track_bias_used",
        "time_fit_used",
    )

    for key in forbidden_flags:
        if method.get(
            key,
            False
        ):
            fail(
                "forbidden newcomer factor enabled: "
                + key
            )

    scored_count = int(
        summary.get(
            "pedigree_scored_count",
            0
        )
        or 0
    )

    missing_count = int(
        summary.get(
            "pedigree_missing_count",
            0
        )
        or 0
    )

    ranked_count = int(
        summary.get(
            "ranked_count",
            0
        )
        or 0
    )

    unranked_count = int(
        summary.get(
            "unranked_unknown_count",
            0
        )
        or 0
    )

    if (
        scored_count
        + missing_count
        != total
    ):
        fail(
            "newcomer pedigree "
            "scored/missing count mismatch"
        )

    if ranked_count != scored_count:
        fail(
            "newcomer ranked count "
            "must equal pedigree scored count"
        )

    if (
        unranked_count
        != missing_count
    ):
        fail(
            "newcomer unranked count "
            "must equal pedigree missing count"
        )

    if scored_count <= 0:
        fail(
            "newcomer has no pedigree scores"
        )

    actual_ranked = 0
    actual_missing = 0
    actual_ranks = []
    ranked_horses = []

    for horse in ranking:
        name = str(
            horse.get(
                "horse_name",
                ""
            )
        )

        horse_mode = str(
            horse.get(
                "analysis_mode",
                ""
            )
        ).strip()

        if (
            horse_mode
            != "newcomer_pedigree_only"
        ):
            fail(
                "horse analysis mode mismatch: "
                + name
            )

        bloodline_score = horse.get(
            "bloodline_score"
        )

        final_score = horse.get(
            "final_score"
        )

        rank = horse.get(
            "rank"
        )

        if (
            horse.get(
                "ability_score"
            )
            is not None
        ):
            fail(
                "newcomer ability score used: "
                + name
            )

        if (
            horse.get(
                "performance_rate"
            )
            is not None
        ):
            fail(
                "newcomer performance rate used: "
                + name
            )

        if (
            horse.get(
                "condition_fit_score"
            )
            is not None
        ):
            fail(
                "newcomer condition fit used: "
                + name
            )

        forbidden_adjustments = {
            "track":
                horse.get(
                    "track_performance_rate_adjustment",
                    0
                ),

            "time_fit":
                horse.get(
                    "time_fit_performance_rate_adjustment",
                    0
                ),

            "body_weight":
                horse.get(
                    "body_weight_performance_rate_adjustment",
                    0
                ),

            "body_issue":
                horse.get(
                    "body_weight_issue_adjustment",
                    0
                ),

            "condition":
                horse.get(
                    "condition_adjustment",
                    0
                ),

            "previous":
                horse.get(
                    "previous_race_adjustment",
                    0
                ),

            "pace":
                horse.get(
                    "pace_adjustment",
                    0
                ),

            "bloodline_support":
                horse.get(
                    "bloodline_adjustment",
                    0
                ),
        }

        for (
            factor_name,
            value
        ) in forbidden_adjustments.items():

            try:
                numeric_value = float(
                    value or 0
                )

            except (
                TypeError,
                ValueError
            ):
                fail(
                    "invalid newcomer adjustment "
                    f"{factor_name}: {name}"
                )

            if abs(
                numeric_value
            ) > 1e-9:
                fail(
                    "newcomer non-pedigree "
                    "adjustment detected: "
                    f"{factor_name} / {name}"
                )

        if bloodline_score is None:
            actual_missing += 1

            if final_score is not None:
                fail(
                    "newcomer missing pedigree "
                    "received final score: "
                    + name
                )

            if rank is not None:
                fail(
                    "newcomer missing pedigree "
                    "was ranked: "
                    + name
                )

            continue

        actual_ranked += 1

        if final_score is None:
            fail(
                "newcomer pedigree horse "
                "has no final score: "
                + name
            )

        try:
            bloodline_value = float(
                bloodline_score
            )

            final_value = float(
                final_score
            )

        except (
            TypeError,
            ValueError
        ):
            fail(
                "invalid newcomer score: "
                + name
            )

        if abs(
            final_value
            - bloodline_value
        ) > 1e-9:
            fail(
                "newcomer final score "
                "must equal bloodline score: "
                + name
            )

        if rank is None:
            fail(
                "newcomer pedigree horse "
                "has no rank: "
                + name
            )

        try:
            rank_int = int(
                rank
            )

        except (
            TypeError,
            ValueError
        ):
            fail(
                "invalid newcomer rank: "
                + name
            )

        actual_ranks.append(
            rank_int
        )

        ranked_horses.append(
            horse
        )

    if actual_ranked != scored_count:
        fail(
            "actual newcomer ranked count mismatch"
        )

    if actual_missing != missing_count:
        fail(
            "actual newcomer missing count mismatch"
        )

    if actual_ranks != list(
        range(
            1,
            scored_count + 1
        )
    ):
        fail(
            "newcomer ranks are not continuous"
        )

    for index in range(
        1,
        len(ranked_horses)
    ):
        previous_score = float(
            ranked_horses[
                index - 1
            ][
                "bloodline_score"
            ]
        )

        current_score = float(
            ranked_horses[
                index
            ][
                "bloodline_score"
            ]
        )

        if (
            current_score
            > previous_score
            + 1e-9
        ):
            fail(
                "newcomer ranking is not "
                "bloodline score descending"
            )

    print()
    print(
        "===== NEWCOMER VALIDATION OK ====="
    )

    print(
        "Pedigree scored:",
        f"{scored_count}/{total}"
    )

    print(
        "Pedigree missing:",
        f"{missing_count}/{total}"
    )

    print(
        "Ranked:",
        f"{ranked_count}/{total}"
    )

    print(
        "Final score: BLOODLINE ONLY"
    )

    print(
        "Normal race factors: DISABLED"
    )


def validate_normal(
    summary,
    ranking,
    total,
):
    record_checks = {
        "ability records":
            int(
                summary.get(
                    "ability_record_connected_count",
                    0
                )
                or 0
            ),

        "previous records":
            int(
                summary.get(
                    "previous_connected_count",
                    0
                )
                or 0
            ),

        "pace records":
            int(
                summary.get(
                    "pace_connected_count",
                    0
                )
                or 0
            ),

        "bloodline records":
            int(
                summary.get(
                    "bloodline_connected_count",
                    0
                )
                or 0
            ),
    }

    for (
        name,
        count
    ) in record_checks.items():

        print(
            f"{name}: {count}/{total}"
        )

        if count != total:
            fail(
                f"{name} incomplete "
                f"({count}/{total})"
            )

    ability_known = int(
        summary.get(
            "ability_known_count",
            0
        )
        or 0
    )

    ability_unknown = int(
        summary.get(
            "ability_unknown_count",
            0
        )
        or 0
    )

    ranked_count = int(
        summary.get(
            "ranked_count",
            0
        )
        or 0
    )

    unranked_unknown = int(
        summary.get(
            "unranked_unknown_count",
            0
        )
        or 0
    )

    if (
        ability_known
        + ability_unknown
        != total
    ):
        fail(
            "ability known/unknown count mismatch"
        )

    if ranked_count != ability_known:
        fail(
            "ranked count must equal "
            "known ability count"
        )

    if (
        ranked_count
        + unranked_unknown
        != total
    ):
        fail(
            "ranked + unknown count mismatch"
        )

    actual_known = 0
    actual_unknown = 0

    for horse in ranking:
        name = str(
            horse.get(
                "horse_name",
                ""
            )
        )

        ability_is_known = bool(
            horse.get(
                "ability_known",
                False
            )
        )

        ability_score = horse.get(
            "ability_score"
        )

        final_score = horse.get(
            "final_score"
        )

        rank = horse.get(
            "rank"
        )

        condition_fit = horse.get(
            "condition_fit_score"
        )

        try:
            blood_adj = float(
                horse.get(
                    "bloodline_adjustment",
                    0
                )
                or 0
            )

        except (
            TypeError,
            ValueError
        ):
            fail(
                "invalid bloodline adjustment: "
                + name
            )

        if ability_is_known:
            actual_known += 1

            if ability_score is None:
                fail(
                    "known horse has "
                    "null ability_score: "
                    + name
                )

            if final_score is None:
                fail(
                    "known horse has "
                    "null final_score: "
                    + name
                )

            if rank is None:
                fail(
                    "known horse has no rank: "
                    + name
                )

        else:
            actual_unknown += 1

            if ability_score is not None:
                fail(
                    "UNKNOWN horse has "
                    "imputed ability_score: "
                    + name
                )

            if final_score is not None:
                fail(
                    "UNKNOWN horse has "
                    "final_score: "
                    + name
                )

            if rank is not None:
                fail(
                    "UNKNOWN horse is ranked: "
                    + name
                )

        if (
            condition_fit is None
            and abs(
                blood_adj
            ) > 1e-9
        ):
            fail(
                "bloodline adjustment applied "
                "without known condition fit: "
                f"{name} ({blood_adj})"
            )

    if actual_known != ability_known:
        fail(
            "actual known count mismatch"
        )

    if actual_unknown != ability_unknown:
        fail(
            "actual unknown count mismatch"
        )

    print()
    print(
        "===== NORMAL VALIDATION OK ====="
    )

    print(
        "Ability known:",
        f"{ability_known}/{total}"
    )

    print(
        "Ability unknown:",
        f"{ability_unknown}/{total}"
    )

    print(
        "Ranked:",
        f"{ranked_count}/{total}"
    )

    print(
        "Training: DISABLED"
    )

    print(
        "Bloodline standalone adjustment: PROHIBITED"
    )


def validate_leak_safety(
    final_analysis
):
    day_bias = final_analysis.get(
        "day_bias",
        {}
    )

    if not isinstance(
        day_bias,
        dict
    ):
        day_bias = {}

    if (
        day_bias.get(
            "source_available"
        )
        and not day_bias.get(
            "future_safe"
        )
    ):
        fail(
            "day bias future safety failed"
        )

    time_fit = final_analysis.get(
        "runner_time_fit",
        {}
    )

    if not isinstance(
        time_fit,
        dict
    ):
        time_fit = {}

    if (
        time_fit.get(
            "source_available"
        )
        and not time_fit.get(
            "future_safe"
        )
    ):
        fail(
            "runner time fit "
            "future safety failed"
        )

    if (
        time_fit.get(
            "source_available"
        )
        and not time_fit.get(
            "leak_check_passed"
        )
    ):
        fail(
            "runner time fit "
            "leak check failed"
        )


def validate_final_analysis(
    target_race_id,
    race,
    final_analysis,
):
    validate_identity(
        target_race_id,
        race,
        final_analysis,
    )

    summary = final_analysis.get(
        "summary",
        {}
    )

    ranking = final_analysis.get(
        "ranking",
        []
    )

    if not isinstance(
        summary,
        dict
    ):
        fail(
            "final_analysis summary is missing"
        )

    if not isinstance(
        ranking,
        list
    ):
        fail(
            "final_analysis ranking is invalid"
        )

    total = int(
        summary.get(
            "runner_count",
            0
        )
        or 0
    )

    if total <= 0:
        fail(
            "no runners"
        )

    if len(
        ranking
    ) != total:
        fail(
            "ranking record count mismatch "
            f"({len(ranking)}/{total})"
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
        != total
    ):
        fail(
            "race horse_count mismatch "
            f"({race_horse_count}/{total})"
        )

    analysis_mode = str(
        final_analysis.get(
            "analysis_mode",
            ""
        )
    ).strip()

    is_newcomer = (
        analysis_mode
        == "newcomer_pedigree_only"
    )

    print(
        "Target race:",
        target_race_id
    )

    print(
        "Runners:",
        total
    )

    print(
        "Analysis mode:",
        (
            analysis_mode
            if analysis_mode
            else "normal"
        )
    )

    if is_newcomer:
        validate_newcomer(
            final_analysis,
            summary,
            ranking,
            total,
        )

    else:
        validate_normal(
            summary,
            ranking,
            total,
        )

    validate_leak_safety(
        final_analysis
    )

    print()
    print(
        "===== FINAL ANALYSIS VALIDATION OK ====="
    )

    return total


def run_prediction_snapshot():
    completed = subprocess.run(
        [
            sys.executable,
            SNAPSHOT_SCRIPT.as_posix()
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    if completed.stdout:
        print(
            completed.stdout,
            end=""
        )

    if completed.stderr:
        print(
            completed.stderr,
            end="",
            file=sys.stderr
        )

    if completed.returncode != 0:
        fail(
            "prediction_snapshot.py failed with "
            f"exit code {completed.returncode}"
        )

    output_path = None

    for line in completed.stdout.splitlines():
        if line.startswith(
            "output:"
        ):
            output_path = Path(
                line.split(
                    ":",
                    1
                )[1].strip()
            )

    if output_path is None:
        fail(
            "prediction_snapshot.py did not "
            "report an output path"
        )

    if not output_path.exists():
        fail(
            "prediction snapshot output is missing: "
            f"{output_path}"
        )

    return output_path


def validate_snapshot(
    output_path,
    target_race_id,
    final_analysis,
    runner_count,
):
    snapshot = load_json(
        output_path
    )

    if int(
        snapshot.get(
            "schema_version",
            0
        )
        or 0
    ) != 2:
        fail(
            "prediction snapshot "
            "schema_version must be 2"
        )

    if (
        snapshot.get(
            "snapshot_kind"
        )
        != "prediction"
    ):
        fail(
            "prediction snapshot kind mismatch"
        )

    snapshot_race = snapshot.get(
        "race",
        {}
    )

    if not isinstance(
        snapshot_race,
        dict
    ):
        fail(
            "prediction snapshot "
            "race context is missing"
        )

    if normalize_race_id(
        snapshot_race.get(
            "race_id"
        )
    ) != target_race_id:
        fail(
            "prediction snapshot race_id mismatch"
        )

    snapshot_horse_count = int(
        snapshot_race.get(
            "horse_count",
            0
        )
        or 0
    )

    if (
        snapshot_horse_count
        != runner_count
    ):
        fail(
            "prediction snapshot "
            "horse_count mismatch: "
            f"{snapshot_horse_count}/"
            f"{runner_count}"
        )

    if (
        snapshot.get(
            "analysis"
        )
        != final_analysis
    ):
        fail(
            "prediction snapshot analysis "
            "differs from final_analysis.json"
        )

    timing = snapshot.get(
        "timing",
        {}
    )

    if not isinstance(
        timing,
        dict
    ):
        fail(
            "prediction snapshot timing is missing"
        )

    timing_status = str(
        timing.get(
            "status",
            ""
        )
    ).strip()

    evaluation_eligible = timing.get(
        "evaluation_eligible"
    )

    allowed_statuses = {
        "before_race_date": True,
        "after_race_date": False,
        "same_day_before_start": True,
        "same_day_at_or_after_start": False,
        "same_day_start_time_unknown": None,
        "race_date_unknown": None,
    }

    if (
        timing_status
        not in allowed_statuses
    ):
        fail(
            "unknown prediction snapshot "
            "timing status: "
            + timing_status
        )

    if (
        evaluation_eligible
        is not allowed_statuses[
            timing_status
        ]
    ):
        fail(
            "prediction snapshot "
            "evaluation_eligible mismatch: "
            f"status={timing_status} "
            f"value={evaluation_eligible!r}"
        )

    if (
        timing_status
        in {
            "same_day_before_start",
            "same_day_at_or_after_start",
        }
        and not snapshot_race.get(
            "scheduled_start_time"
        )
    ):
        fail(
            "same-day timing status requires "
            "scheduled_start_time"
        )

    snapshot_id = str(
        snapshot.get(
            "snapshot_id",
            ""
        )
    ).strip()

    if not snapshot_id:
        fail(
            "prediction snapshot_id is missing"
        )

    print()
    print(
        "===== PRODUCTION SNAPSHOT VALIDATION OK ====="
    )

    print(
        "snapshot_id:",
        snapshot_id
    )

    print(
        "output:",
        output_path.as_posix()
    )

    print(
        "timing_status:",
        timing_status
    )

    print(
        "evaluation_eligible:",
        evaluation_eligible
    )

    print(
        "scheduled_start_time:",
        snapshot_race.get(
            "scheduled_start_time",
            ""
        )
    )


def main():
    try:
        validate_required_files()

        target_race_id = (
            read_target_race_id()
        )

        race = load_json(
            RACE_FILE
        )

        final_analysis = load_json(
            FINAL_FILE
        )

        runner_count = (
            validate_final_analysis(
                target_race_id,
                race,
                final_analysis,
            )
        )

        output_path = (
            run_prediction_snapshot()
        )

        validate_snapshot(
            output_path,
            target_race_id,
            final_analysis,
            runner_count,
        )

        print()
        print(
            "===== PRODUCTION SNAPSHOT HOOK OK ====="
        )

    except Exception as exc:
        print(
            "PRODUCTION SNAPSHOT HOOK FAILED:",
            str(exc),
            file=sys.stderr,
        )

        raise


if __name__ == "__main__":
    main()
