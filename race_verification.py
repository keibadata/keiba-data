import argparse
import json
import os
import re
import subprocess
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"

SNAPSHOT_ROOT = Path(
    "prediction_snapshots"
)

VERIFICATION_ROOT = Path(
    "race_verifications"
)

RESULT_FILE = (
    "verification_day_results.json"
)

COLLECTOR_FILE = (
    "day_race_collector.py"
)

SCHEMA_VERSION = 1

JST = timezone(
    timedelta(hours=9)
)


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def load_json(path):
    path = Path(path)

    if not path.exists():
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
    )

    translation = str.maketrans(
        "０１２３４５６７８９：．－＋",
        "0123456789:.-+",
    )

    value = value.translate(
        translation
    )

    value = value.replace(
        "\u3000",
        " "
    )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


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


def to_int(value):
    if value is None:
        return None

    try:
        return int(
            value
        )
    except Exception:
        pass

    text = normalize_text(
        value
    )

    match = re.search(
        r"-?\d+",
        text
    )

    if not match:
        return None

    try:
        return int(
            match.group()
        )
    except Exception:
        return None


def to_float(value):
    if value is None:
        return None

    try:
        return float(
            value
        )
    except Exception:
        pass

    text = normalize_text(
        value
    )

    match = re.search(
        r"-?\d+(?:\.\d+)?",
        text
    )

    if not match:
        return None

    try:
        return float(
            match.group()
        )
    except Exception:
        return None


def parse_datetime(value):
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


# ============================================================
# race.json
# ============================================================

def load_race():
    race = load_json(
        RACE_FILE
    )

    race_id = normalize_race_id(
        race.get(
            "race_id"
        )
    )

    race_date = normalize_text(
        race.get(
            "race_date"
        )
        or race.get(
            "date"
        )
    )

    if not race_date:
        raise ValueError(
            "race_date is missing"
        )

    return (
        race,
        race_id,
        race_date,
    )


# ============================================================
# 予想スナップショット
# ============================================================

def snapshot_directory(
    race_date,
    race_id,
):
    return (
        SNAPSHOT_ROOT
        / race_date
        / race_id
    )


def load_snapshot_candidates(
    race_date,
    race_id,
):
    directory = (
        snapshot_directory(
            race_date,
            race_id,
        )
    )

    if not directory.exists():
        raise FileNotFoundError(
            "prediction snapshot directory "
            "is missing: "
            + directory.as_posix()
        )

    candidates = []

    for path in directory.glob(
        "*.json"
    ):
        try:
            data = load_json(
                path
            )
        except Exception:
            continue

        if (
            data.get(
                "snapshot_kind"
            )
            != "prediction"
        ):
            continue

        snapshot_race_id = (
            normalize_text(
                data
                .get(
                    "race",
                    {}
                )
                .get(
                    "race_id"
                )
            )
        )

        if snapshot_race_id != race_id:
            continue

        saved_at = parse_datetime(
            data.get(
                "prediction_saved_at"
            )
        )

        if saved_at is None:
            continue

        timing = data.get(
            "timing",
            {}
        )

        eligible = (
            timing.get(
                "evaluation_eligible"
            )
            is True
        )

        candidates.append(
            {
                "path": path,
                "data": data,
                "saved_at": saved_at,
                "eligible": eligible,
            }
        )

    if not candidates:
        raise ValueError(
            "usable prediction snapshot "
            "was not found"
        )

    return candidates


def select_snapshot(
    race_date,
    race_id,
):
    candidates = (
        load_snapshot_candidates(
            race_date,
            race_id,
        )
    )

    eligible = [
        item
        for item in candidates
        if item[
            "eligible"
        ]
    ]

    if eligible:
        selected = max(
            eligible,
            key=lambda item:
                item[
                    "saved_at"
                ],
        )

        selection_reason = (
            "latest_evaluation_eligible_snapshot"
        )

    else:
        selected = max(
            candidates,
            key=lambda item:
                item[
                    "saved_at"
                ],
        )

        selection_reason = (
            "no_eligible_snapshot_"
            "latest_used_for_diagnostic_only"
        )

    return (
        selected,
        selection_reason,
        len(candidates),
        len(eligible),
    )


# ============================================================
# 確定結果取得
# ============================================================

def collect_result():
    if not os.path.exists(
        COLLECTOR_FILE
    ):
        raise FileNotFoundError(
            f"{COLLECTOR_FILE} is missing"
        )

    command = [
        sys.executable,
        COLLECTOR_FILE,
        "--include-target",
        "--output",
        RESULT_FILE,
    ]

    print(
        "RESULT COLLECTOR START"
    )

    print(
        "command:",
        " ".join(command)
    )

    completed = subprocess.run(
        command,
        check=False,
    )

    if completed.returncode != 0:
        raise RuntimeError(
            "day_race_collector.py "
            "failed: "
            f"exit={completed.returncode}"
        )

    result_data = load_json(
        RESULT_FILE
    )

    if (
        result_data.get(
            "mode"
        )
        != "result_verification"
    ):
        raise ValueError(
            "result collector mode "
            "is not result_verification"
        )

    if (
        result_data.get(
            "include_target"
        )
        is not True
    ):
        raise ValueError(
            "target race was not requested"
        )

    if (
        result_data.get(
            "target_race_included"
        )
        is not True
    ):
        raise ValueError(
            "target race was not included"
        )

    if (
        result_data.get(
            "future_race_usage"
        )
        is True
    ):
        raise ValueError(
            "future race data detected"
        )

    return result_data


def find_target_result(
    result_data,
    race_id,
):
    races = result_data.get(
        "races",
        []
    )

    matched = [
        item
        for item in races
        if normalize_text(
            item.get(
                "race_id"
            )
        )
        == race_id
    ]

    if len(matched) != 1:
        raise ValueError(
            "target result count "
            f"is invalid: {len(matched)}"
        )

    target = matched[0]

    if (
        target.get(
            "finished"
        )
        is not True
    ):
        raise ValueError(
            "target race is not finished"
        )

    finishers = target.get(
        "finishers",
        []
    )

    if not finishers:
        raise ValueError(
            "target race has no finishers"
        )

    return target


# ============================================================
# 馬照合
# ============================================================

def horse_key_by_id(item):
    horse_id = normalize_text(
        item.get(
            "horse_id"
        )
    )

    if horse_id:
        return (
            "horse_id",
            horse_id,
        )

    return None


def horse_key_by_number(item):
    number = to_int(
        item.get(
            "horse_number"
        )
    )

    if number is None:
        return None

    return (
        "horse_number",
        number,
    )


def build_actual_maps(
    finishers,
):
    by_id = {}
    by_number = {}

    for item in finishers:
        id_key = (
            horse_key_by_id(
                item
            )
        )

        number_key = (
            horse_key_by_number(
                item
            )
        )

        if id_key:
            by_id[
                id_key[1]
            ] = item

        if number_key:
            by_number[
                number_key[1]
            ] = item

    return (
        by_id,
        by_number,
    )


def find_actual(
    prediction,
    by_id,
    by_number,
):
    horse_id = normalize_text(
        prediction.get(
            "horse_id"
        )
    )

    if (
        horse_id
        and horse_id
        in by_id
    ):
        return (
            by_id[
                horse_id
            ],
            "horse_id",
        )

    horse_number = to_int(
        prediction.get(
            "horse_number"
        )
    )

    if (
        horse_number is not None
        and horse_number
        in by_number
    ):
        return (
            by_number[
                horse_number
            ],
            "horse_number",
        )

    return (
        None,
        "",
    )


# ============================================================
# 能力順位
# ============================================================

def build_ability_ranks(
    ranking,
):
    valid = []

    for item in ranking:
        if (
            item.get(
                "ability_known"
            )
            is not True
        ):
            continue

        score = to_float(
            item.get(
                "ability_score"
            )
        )

        if score is None:
            continue

        valid.append(
            (
                score,
                to_int(
                    item.get(
                        "horse_number"
                    )
                )
                or 999,
                normalize_text(
                    item.get(
                        "horse_id"
                    )
                ),
            )
        )

    valid.sort(
        key=lambda item: (
            -item[0],
            item[1],
        )
    )

    result = {}

    for index, item in enumerate(
        valid,
        start=1,
    ):
        score, number, horse_id = item

        if horse_id:
            result[
                (
                    "horse_id",
                    horse_id,
                )
            ] = index

        result[
            (
                "horse_number",
                number,
            )
        ] = index

    return result


def get_ability_rank(
    prediction,
    ability_ranks,
):
    horse_id = normalize_text(
        prediction.get(
            "horse_id"
        )
    )

    if horse_id:
        key = (
            "horse_id",
            horse_id,
        )

        if key in ability_ranks:
            return ability_ranks[
                key
            ]

    horse_number = to_int(
        prediction.get(
            "horse_number"
        )
    )

    if horse_number is not None:
        return ability_ranks.get(
            (
                "horse_number",
                horse_number,
            )
        )

    return None


# ============================================================
# 誤差候補分類
# ============================================================

def classify_error_candidate(
    predicted_rank,
    ability_rank,
    actual_finish,
):
    if (
        predicted_rank is None
        or actual_finish is None
    ):
        return {
            "category": (
                "unclassified"
            ),
            "severity": "",
            "note": (
                "順位情報不足"
            ),
        }

    if (
        actual_finish <= 3
        and predicted_rank <= 3
    ):
        return {
            "category": (
                "top3_correct"
            ),
            "severity": "none",
            "note": (
                "予想上位3頭と実着上位3頭が一致"
            ),
        }

    if (
        actual_finish <= 3
        and predicted_rank <= 5
    ):
        return {
            "category": (
                "near_miss"
            ),
            "severity": "low",
            "note": (
                "実着上位3頭を予想5位以内には保持"
            ),
        }

    if (
        actual_finish <= 3
        and predicted_rank > 5
    ):
        if (
            ability_rank is not None
            and ability_rank > 5
        ):
            return {
                "category": (
                    "ability_underestimate_candidate"
                ),
                "severity": "high",
                "note": (
                    "好走馬を能力順位段階から"
                    "低く評価した可能性"
                ),
            }

        return {
            "category": (
                "performance_or_adjustment_"
                "underestimate_candidate"
            ),
            "severity": "high",
            "note": (
                "能力順位では残っていたが"
                "最終順位を下げた補正要因を要検証"
            ),
        }

    if (
        predicted_rank <= 3
        and actual_finish > 5
    ):
        return {
            "category": (
                "overvaluation_candidate"
            ),
            "severity": "high",
            "note": (
                "予想上位馬が実着6着以下。"
                "能力・発揮率・展開を要検証"
            ),
        }

    if (
        predicted_rank <= 5
        and actual_finish > 8
    ):
        return {
            "category": (
                "moderate_overvaluation_candidate"
            ),
            "severity": "medium",
            "note": (
                "予想上位候補が実着下位。"
                "評価根拠を要検証"
            ),
        }

    return {
        "category": (
            "normal_rank_error"
        ),
        "severity": "low",
        "note": (
            "通常範囲の順位差"
        ),
    }


# ============================================================
# 個別馬検証
# ============================================================

def build_horse_verifications(
    snapshot,
    target_result,
):
    analysis = snapshot.get(
        "analysis",
        {}
    )

    ranking = analysis.get(
        "ranking",
        []
    )

    finishers = target_result.get(
        "finishers",
        []
    )

    (
        by_id,
        by_number,
    ) = build_actual_maps(
        finishers
    )

    ability_ranks = (
        build_ability_ranks(
            ranking
        )
    )

    horses = []
    unmatched = []

    for prediction in ranking:
        (
            actual,
            matched_by,
        ) = find_actual(
            prediction,
            by_id,
            by_number,
        )

        predicted_rank = to_int(
            prediction.get(
                "rank"
            )
        )

        ability_rank = (
            get_ability_rank(
                prediction,
                ability_ranks,
            )
        )

        if actual is None:
            unmatched.append(
                {
                    "horse_id":
                        normalize_text(
                            prediction.get(
                                "horse_id"
                            )
                        ),
                    "horse_number":
                        to_int(
                            prediction.get(
                                "horse_number"
                            )
                        ),
                    "horse_name":
                        normalize_text(
                            prediction.get(
                                "horse_name"
                            )
                        ),
                    "predicted_rank":
                        predicted_rank,
                }
            )

            continue

        actual_finish = to_int(
            actual.get(
                "finish"
            )
        )

        rank_difference = None
        absolute_rank_error = None

        if (
            predicted_rank is not None
            and actual_finish is not None
        ):
            rank_difference = (
                actual_finish
                - predicted_rank
            )

            absolute_rank_error = abs(
                rank_difference
            )

        error_candidate = (
            classify_error_candidate(
                predicted_rank,
                ability_rank,
                actual_finish,
            )
        )

        horses.append(
            {
                "horse_id":
                    normalize_text(
                        prediction.get(
                            "horse_id"
                        )
                    ),

                "horse_number":
                    to_int(
                        prediction.get(
                            "horse_number"
                        )
                    ),

                "horse_name":
                    normalize_text(
                        prediction.get(
                            "horse_name"
                        )
                    ),

                "matched_by":
                    matched_by,

                "prediction": {
                    "rank":
                        predicted_rank,

                    "judgement":
                        normalize_text(
                            prediction.get(
                                "judgement"
                            )
                        ),

                    "ability_known":
                        bool(
                            prediction.get(
                                "ability_known",
                                False
                            )
                        ),

                    "ability_rank":
                        ability_rank,

                    "ability_score":
                        to_float(
                            prediction.get(
                                "ability_score"
                            )
                        ),

                    "performance_rate":
                        to_float(
                            prediction.get(
                                "performance_rate"
                            )
                        ),

                    "condition_fit_score":
                        to_float(
                            prediction.get(
                                "condition_fit_score"
                            )
                        ),

                    "final_score":
                        to_float(
                            prediction.get(
                                "final_score"
                            )
                        ),

                    "running_style":
                        normalize_text(
                            prediction.get(
                                "running_style"
                            )
                        ),

                    "previous_positive_count":
                        to_int(
                            prediction.get(
                                "previous_positive_count"
                            )
                        ),

                    "previous_issue_count":
                        to_int(
                            prediction.get(
                                "previous_issue_count"
                            )
                        ),

                    "overcoming_material_count":
                        to_int(
                            prediction.get(
                                "overcoming_material_count"
                            )
                        ),

                    "pace_adjustment":
                        to_float(
                            prediction.get(
                                "pace_adjustment"
                            )
                        ),

                    "bloodline_adjustment":
                        to_float(
                            prediction.get(
                                "bloodline_adjustment"
                            )
                        ),

                    "time_fit_label":
                        normalize_text(
                            prediction.get(
                                "time_fit_label"
                            )
                        ),
                },

                "actual": {
                    "finish":
                        actual_finish,

                    "race_time":
                        normalize_text(
                            actual.get(
                                "race_time"
                            )
                        ),

                    "race_time_seconds":
                        to_float(
                            actual.get(
                                "race_time_seconds"
                            )
                        ),

                    "margin":
                        normalize_text(
                            actual.get(
                                "margin"
                            )
                        ),

                    "last3f":
                        to_float(
                            actual.get(
                                "last3f"
                            )
                        ),

                    "popularity":
                        to_int(
                            actual.get(
                                "popularity"
                            )
                        ),

                    "odds":
                        to_float(
                            actual.get(
                                "odds"
                            )
                        ),

                    "body_weight":
                        to_int(
                            actual.get(
                                "body_weight"
                            )
                        ),

                    "body_weight_change":
                        to_int(
                            actual.get(
                                "body_weight_change"
                            )
                        ),

                    "jockey":
                        normalize_text(
                            actual.get(
                                "jockey"
                            )
                        ),

                    "carried_weight":
                        to_float(
                            actual.get(
                                "carried_weight"
                            )
                        ),
                },

                "comparison": {
                    "rank_difference":
                        rank_difference,

                    "absolute_rank_error":
                        absolute_rank_error,

                    "predicted_top1":
                        predicted_rank == 1,

                    "predicted_top3":
                        (
                            predicted_rank
                            is not None
                            and predicted_rank <= 3
                        ),

                    "predicted_top5":
                        (
                            predicted_rank
                            is not None
                            and predicted_rank <= 5
                        ),

                    "actual_top1":
                        actual_finish == 1,

                    "actual_top3":
                        (
                            actual_finish
                            is not None
                            and actual_finish <= 3
                        ),

                    "error_candidate":
                        error_candidate,
                },
            }
        )

    horses.sort(
        key=lambda item:
            item[
                "prediction"
            ].get(
                "rank"
            )
            or 999
    )

    return (
        horses,
        unmatched,
    )


# ============================================================
# レース単位集計
# ============================================================

def build_race_summary(
    horses,
):
    matched_count = len(
        horses
    )

    if matched_count <= 0:
        raise ValueError(
            "no horses were matched"
        )

    absolute_errors = [
        item[
            "comparison"
        ][
            "absolute_rank_error"
        ]
        for item in horses
        if item[
            "comparison"
        ][
            "absolute_rank_error"
        ]
        is not None
    ]

    mae = None

    if absolute_errors:
        mae = round(
            sum(
                absolute_errors
            )
            / len(
                absolute_errors
            ),
            3,
        )

    actual_top3 = [
        item
        for item in horses
        if item[
            "comparison"
        ][
            "actual_top3"
        ]
    ]

    top3_in_predicted_top3 = sum(
        1
        for item in actual_top3
        if item[
            "comparison"
        ][
            "predicted_top3"
        ]
    )

    top3_in_predicted_top5 = sum(
        1
        for item in actual_top3
        if item[
            "comparison"
        ][
            "predicted_top5"
        ]
    )

    winner = next(
        (
            item
            for item in horses
            if item[
                "comparison"
            ][
                "actual_top1"
            ]
        ),
        None,
    )

    predicted_first = next(
        (
            item
            for item in horses
            if item[
                "comparison"
            ][
                "predicted_top1"
            ]
        ),
        None,
    )

    major_misses = [
        item
        for item in horses
        if (
            item[
                "comparison"
            ][
                "error_candidate"
            ][
                "severity"
            ]
            == "high"
        )
    ]

    return {
        "matched_horse_count":
            matched_count,

        "mean_absolute_rank_error":
            mae,

        "actual_top3_count":
            len(
                actual_top3
            ),

        "actual_top3_in_predicted_top3":
            top3_in_predicted_top3,

        "actual_top3_in_predicted_top5":
            top3_in_predicted_top5,

        "top3_coverage_at_3":
            round(
                top3_in_predicted_top3
                / len(actual_top3),
                3,
            )
            if actual_top3
            else None,

        "top3_coverage_at_5":
            round(
                top3_in_predicted_top5
                / len(actual_top3),
                3,
            )
            if actual_top3
            else None,

        "winner": {
            "horse_number":
                winner.get(
                    "horse_number"
                )
                if winner
                else None,

            "horse_name":
                winner.get(
                    "horse_name"
                )
                if winner
                else "",

            "predicted_rank":
                winner[
                    "prediction"
                ].get(
                    "rank"
                )
                if winner
                else None,

            "ability_rank":
                winner[
                    "prediction"
                ].get(
                    "ability_rank"
                )
                if winner
                else None,
        },

        "predicted_first": {
            "horse_number":
                predicted_first.get(
                    "horse_number"
                )
                if predicted_first
                else None,

            "horse_name":
                predicted_first.get(
                    "horse_name"
                )
                if predicted_first
                else "",

            "actual_finish":
                predicted_first[
                    "actual"
                ].get(
                    "finish"
                )
                if predicted_first
                else None,
        },

        "major_miss_count":
            len(
                major_misses
            ),

        "major_miss_horses": [
            {
                "horse_number":
                    item.get(
                        "horse_number"
                    ),

                "horse_name":
                    item.get(
                        "horse_name"
                    ),

                "predicted_rank":
                    item[
                        "prediction"
                    ].get(
                        "rank"
                    ),

                "actual_finish":
                    item[
                        "actual"
                    ].get(
                        "finish"
                    ),

                "category":
                    item[
                        "comparison"
                    ][
                        "error_candidate"
                    ][
                        "category"
                    ],
            }
            for item in major_misses
        ],
    }


# ============================================================
# 検証JSON
# ============================================================

def build_verification():
    (
        race,
        race_id,
        race_date,
    ) = load_race()

    (
        selected,
        selection_reason,
        candidate_count,
        eligible_count,
    ) = select_snapshot(
        race_date,
        race_id,
    )

    snapshot = selected[
        "data"
    ]

    snapshot_path = selected[
        "path"
    ]

    result_data = (
        collect_result()
    )

    result_race_id = (
        normalize_race_id(
            result_data.get(
                "target_race_id"
            )
        )
    )

    if result_race_id != race_id:
        raise ValueError(
            "result race_id mismatch: "
            f"{result_race_id} "
            f"!= {race_id}"
        )

    target_result = (
        find_target_result(
            result_data,
            race_id,
        )
    )

    (
        horses,
        unmatched,
    ) = (
        build_horse_verifications(
            snapshot,
            target_result,
        )
    )

    summary = (
        build_race_summary(
            horses
        )
    )

    timing = snapshot.get(
        "timing",
        {}
    )

    evaluation_eligible = (
        timing.get(
            "evaluation_eligible"
        )
        is True
    )

    official_status = (
        "official_evaluation"
        if evaluation_eligible
        else "diagnostic_only"
    )

    analysis = snapshot.get(
        "analysis",
        {}
    )

    race_scenario = analysis.get(
        "race_scenario",
        {}
    )

    day_bias = analysis.get(
        "day_bias",
        {}
    )

    verification = {
        "schema_version":
            SCHEMA_VERSION,

        "verification_kind":
            "prediction_vs_result",

        "created_at":
            now_jst(),

        "race_id":
            race_id,

        "race_date":
            race_date,

        "track":
            normalize_text(
                race.get(
                    "track"
                )
                or race.get(
                    "racecourse"
                )
            ),

        "race_name":
            normalize_text(
                target_result.get(
                    "race_name"
                )
                or race.get(
                    "race_name"
                )
            ),

        "surface":
            normalize_text(
                target_result.get(
                    "surface"
                )
            ),

        "distance":
            target_result.get(
                "distance"
            ),

        "actual_track_condition":
            normalize_text(
                target_result.get(
                    "track_condition"
                )
            ),

        "actual_pace":
            normalize_text(
                target_result.get(
                    "pace"
                )
            ),

        "actual_laps":
            target_result.get(
                "laps",
                []
            ),

        "actual_corner_orders":
            target_result.get(
                "corner_orders",
                {}
            ),

        "prediction_snapshot": {
            "snapshot_id":
                normalize_text(
                    snapshot.get(
                        "snapshot_id"
                    )
                ),

            "path":
                snapshot_path.as_posix(),

            "prediction_saved_at":
                normalize_text(
                    snapshot.get(
                        "prediction_saved_at"
                    )
                ),

            "timing_status":
                normalize_text(
                    timing.get(
                        "status"
                    )
                ),

            "evaluation_eligible":
                evaluation_eligible,

            "selection_reason":
                selection_reason,

            "candidate_snapshot_count":
                candidate_count,

            "eligible_snapshot_count":
                eligible_count,
        },

        "evaluation_status":
            official_status,

        "aggregate_eligible":
            evaluation_eligible,

        "aggregate_exclusion_reason": (
            ""
            if evaluation_eligible
            else (
                "発走前に保存された"
                "evaluation_eligible=trueの"
                "予想ではないため、"
                "正式な的中率・精度集計には"
                "使用しない"
            )
        ),

        "predicted_race_context": {
            "analysis_mode":
                normalize_text(
                    snapshot.get(
                        "analysis_mode"
                    )
                ),

            "base_pace":
                normalize_text(
                    race_scenario.get(
                        "base_pace"
                    )
                ),

            "leader_candidate_count":
                to_int(
                    race_scenario.get(
                        "leader_candidate_count"
                    )
                ),

            "front_candidate_count":
                to_int(
                    race_scenario.get(
                        "front_candidate_count"
                    )
                ),

            "day_bias_reference_race_count":
                to_int(
                    day_bias.get(
                        "reference_race_count"
                    )
                ),

            "predicted_running_style_bias":
                normalize_text(
                    day_bias.get(
                        "running_style_bias"
                    )
                ),

            "predicted_inside_outside_bias":
                normalize_text(
                    day_bias.get(
                        "inside_outside_bias"
                    )
                ),

            "predicted_time_bias":
                normalize_text(
                    day_bias.get(
                        "time_bias"
                    )
                ),
        },

        "result_source": {
            "source":
                normalize_text(
                    target_result.get(
                        "source"
                    )
                ),

            "source_url":
                normalize_text(
                    target_result.get(
                        "source_url"
                    )
                ),

            "finisher_count":
                to_int(
                    target_result.get(
                        "finisher_count"
                    )
                ),
        },

        "summary":
            summary,

        "unmatched_predictions":
            unmatched,

        "horses":
            horses,

        "method": {
            "prediction_is_frozen_snapshot":
                True,

            "result_collected_after_race":
                True,

            "horse_match_prefers_horse_id":
                True,

            "horse_number_is_fallback":
                True,

            "post_race_snapshot_excluded_from_aggregate":
                True,

            "error_category_is_diagnostic_candidate_only":
                True,

            "error_category_is_not_causal_proof":
                True,

            "popularity_does_not_modify_prediction":
                True,

            "actual_result_does_not_rewrite_prediction":
                True,
        },
    }

    return verification


def verification_path(
    verification,
):
    race_id = verification[
        "race_id"
    ]

    race_date = verification[
        "race_date"
    ]

    snapshot_id = (
        verification[
            "prediction_snapshot"
        ][
            "snapshot_id"
        ]
    )

    safe_snapshot_id = re.sub(
        r"[^0-9A-Za-z_+\-]",
        "_",
        snapshot_id,
    )

    return (
        VERIFICATION_ROOT
        / race_date
        / race_id
        / (
            "verification_"
            + safe_snapshot_id
            + ".json"
        )
    )


# ============================================================
# CLI
# ============================================================

def main():
    parser = argparse.ArgumentParser()

    parser.parse_args()

    verification = (
        build_verification()
    )

    output_path = (
        verification_path(
            verification
        )
    )

    save_json(
        output_path,
        verification,
    )

    summary = verification[
        "summary"
    ]

    snapshot_info = verification[
        "prediction_snapshot"
    ]

    print()
    print(
        "===== RACE VERIFICATION ====="
    )

    print(
        "race_id:",
        verification[
            "race_id"
        ]
    )

    print(
        "snapshot:",
        snapshot_info[
            "snapshot_id"
        ]
    )

    print(
        "evaluation_status:",
        verification[
            "evaluation_status"
        ]
    )

    print(
        "aggregate_eligible:",
        verification[
            "aggregate_eligible"
        ]
    )

    print(
        "matched horses:",
        summary[
            "matched_horse_count"
        ]
    )

    print(
        "winner:",
        summary[
            "winner"
        ]
    )

    print(
        "predicted first:",
        summary[
            "predicted_first"
        ]
    )

    print(
        "top3 coverage @3:",
        summary[
            "top3_coverage_at_3"
        ]
    )

    print(
        "top3 coverage @5:",
        summary[
            "top3_coverage_at_5"
        ]
    )

    print(
        "MAE:",
        summary[
            "mean_absolute_rank_error"
        ]
    )

    print(
        "major misses:",
        summary[
            "major_miss_count"
        ]
    )

    print(
        "actual pace:",
        verification[
            "actual_pace"
        ]
    )

    print(
        "saved:",
        output_path.as_posix()
    )

    print(
        "RACE VERIFICATION OK"
    )

    print(
        "============================="
    )


if __name__ == "__main__":
    main()
