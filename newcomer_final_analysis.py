import json
import os
from datetime import datetime, timezone, timedelta


RACE_FILE = "race.json"
BLOODLINE_FILE = "race_bloodline_score.json"
FINAL_FILE = "final_analysis.json"


# =========================================================
# 共通
# =========================================================

def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {}


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def clean_text(value):
    if value is None:
        return ""

    return " ".join(
        str(value).split()
    )


def get_horse_id(data):
    if not isinstance(data, dict):
        return ""

    return clean_text(
        data.get("horse_id")
        or data.get("id")
        or ""
    )


def get_horse_name(data):
    if not isinstance(data, dict):
        return ""

    return clean_text(
        data.get("horse_name")
        or data.get("name")
        or ""
    )


def get_horse_number(data):
    if not isinstance(data, dict):
        return ""

    return clean_text(
        data.get("horse_number")
        or data.get("number")
        or data.get("umaban")
        or ""
    )


def horse_number_sort_value(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 9999


def get_optional_float(data, key):
    if not isinstance(data, dict):
        return None

    value = data.get(key)

    if value in (None, ""):
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


# =========================================================
# 新馬判定
# =========================================================

def is_debut_race(race):
    if not isinstance(race, dict):
        return False

    if race.get("is_debut") is True:
        return True

    race_class = clean_text(
        race.get("race_class")
    )

    race_name = clean_text(
        race.get("race_name")
    )

    if race_class == "新馬":
        return True

    if "新馬" in race_name:
        return True

    if "メイクデビュー" in race_name:
        return True

    return False


# =========================================================
# 出走馬取得
# =========================================================

def extract_runners(race):
    if not isinstance(race, dict):
        return []

    for key in (
        "horses",
        "runners",
        "entries",
    ):
        value = race.get(key)

        if isinstance(value, list):
            return [
                row
                for row in value
                if isinstance(row, dict)
            ]

    return []


# =========================================================
# 血統ランキングIndex
# =========================================================

def build_bloodline_index(bloodline_data):
    by_id = {}
    by_name = {}
    by_number = {}

    ranking = bloodline_data.get(
        "ranking",
        []
    )

    if not isinstance(ranking, list):
        ranking = []

    for row in ranking:
        if not isinstance(row, dict):
            continue

        horse_id = get_horse_id(row)
        horse_name = get_horse_name(row)
        horse_number = get_horse_number(row)

        if horse_id:
            by_id[horse_id] = row

        if horse_name:
            by_name[horse_name] = row

        if horse_number:
            by_number[horse_number] = row

    return {
        "id": by_id,
        "name": by_name,
        "number": by_number,
    }


def find_bloodline(index, runner):
    horse_id = get_horse_id(runner)
    horse_name = get_horse_name(runner)
    horse_number = get_horse_number(runner)

    if horse_id and horse_id in index["id"]:
        return index["id"][horse_id]

    if (
        horse_name
        and horse_name in index["name"]
    ):
        return index["name"][horse_name]

    if (
        horse_number
        and horse_number in index["number"]
    ):
        return index["number"][horse_number]

    return {}


# =========================================================
# 根拠作成
# =========================================================

def build_ancestor_reason(prefix, ancestors):
    reasons = []

    if not isinstance(ancestors, list):
        return reasons

    for row in ancestors[:3]:
        if not isinstance(row, dict):
            continue

        ancestor_name = clean_text(
            row.get("ancestor_name")
        )

        contribution = get_optional_float(
            row,
            "contribution"
        )

        starts = row.get(
            "starts",
            0
        )

        if not ancestor_name:
            continue

        text = (
            prefix
            + ":"
            + ancestor_name
        )

        if contribution is not None:
            text += (
                " "
                + format(
                    contribution,
                    "+.3f"
                )
            )

        text += (
            " "
            + str(starts)
            + "走"
        )

        reasons.append(text)

    return reasons


# =========================================================
# 判定ラベル
# =========================================================

def judgement_from_rank(rank):
    if rank is None:
        return "血統データ不明"

    if rank <= 2:
        return "血統最上位"

    if rank <= 4:
        return "血統上位"

    if rank <= 7:
        return "血統相手候補"

    return "血統比較下位"


# =========================================================
# メイン
# =========================================================

def main():
    race = load_json(
        RACE_FILE
    )

    bloodline_data = load_json(
        BLOODLINE_FILE
    )

    # -----------------------------------------------------
    # 新馬戦以外では何もしない
    #
    # 通常戦の final_analysis.json を絶対に変更しない。
    # -----------------------------------------------------

    if not is_debut_race(race):
        print(
            "===== NEWCOMER FINAL ANALYSIS ====="
        )
        print(
            "not debut race: skipped"
        )
        return

    race_id = clean_text(
        race.get("race_id")
    )

    runners = extract_runners(
        race
    )

    if not runners:
        raise RuntimeError(
            "新馬戦ですが出走馬を取得できません"
        )

    bloodline_index = build_bloodline_index(
        bloodline_data
    )

    bloodline_ranking = bloodline_data.get(
        "ranking",
        []
    )

    if not isinstance(
        bloodline_ranking,
        list
    ):
        bloodline_ranking = []

    if not bloodline_ranking:
        raise RuntimeError(
            "新馬戦ですがrace_bloodline_score.jsonの"
            "血統ランキングが空です"
        )

    results = []

    # -----------------------------------------------------
    # 血統だけで各馬を作成
    # -----------------------------------------------------

    for runner in runners:
        blood = find_bloodline(
            bloodline_index,
            runner
        )

        horse_id = get_horse_id(
            runner
        )

        horse_name = get_horse_name(
            runner
        )

        horse_number = get_horse_number(
            runner
        )

        if not blood:
            results.append({
                "horse_id":
                    horse_id,

                "horse_number":
                    horse_number,

                "horse_name":
                    horse_name,

                "analysis_mode":
                    "newcomer_pedigree_only",

                "pedigree_available":
                    False,

                "ability_known":
                    False,

                "ability_score":
                    None,

                "original_performance_rate":
                    None,

                "performance_rate":
                    None,

                "base_performance":
                    None,

                "condition_fit_score":
                    None,

                "condition_adjustment":
                    0.0,

                "previous_positive_count":
                    0,

                "previous_issue_count":
                    0,

                "overcoming_material_count":
                    0,

                "previous_race_adjustment":
                    0.0,

                "pace_adjustment":
                    0.0,

                "running_style":
                    "評価対象外",

                "track_performance_rate_adjustment":
                    0.0,

                "time_fit_performance_rate_adjustment":
                    0.0,

                "time_fit_label":
                    "評価対象外",

                "time_fit_evaluated_race_count":
                    0,

                "time_fit_median":
                    None,

                "body_weight_performance_rate_adjustment":
                    0.0,

                "body_weight_issue_adjustment":
                    0.0,

                "body_weight":
                    None,

                "body_weight_change":
                    None,

                "carried_weight":
                    None,

                "weight_body_ratio":
                    None,

                "body_weight_source":
                    "",

                "bloodline_score":
                    None,

                "bloodline_adjustment":
                    0.0,

                "bloodline_support_applied":
                    False,

                "matched_ancestor_count":
                    0,

                "positive_ancestor_count":
                    0,

                "negative_ancestor_count":
                    0,

                "bloodline_rank":
                    None,

                "final_score":
                    None,

                "unknown":
                    True,

                "noise_flags":
                    [],

                "reasons": [
                    "新馬戦・血統専用評価",
                    "血統データ未照合",
                    "前走・能力・展開・調教・騎手・枠・馬体重・人気・当日バイアスは採点対象外",
                ],

                "rank":
                    None,

                "judgement":
                    "血統データ不明",
            })

            continue

        bloodline_score = get_optional_float(
            blood,
            "bloodline_score"
        )

        matched_count = int(
            blood.get(
                "matched_ancestor_count",
                0
            ) or 0
        )

        positive_count = int(
            blood.get(
                "positive_ancestor_count",
                0
            ) or 0
        )

        negative_count = int(
            blood.get(
                "negative_ancestor_count",
                0
            ) or 0
        )

        source_bloodline_rank = blood.get(
            "bloodline_rank"
        )

        reasons = [
            "新馬戦・血統専用評価",
        ]

        if bloodline_score is not None:
            reasons.append(
                "血統スコア:"
                + format(
                    bloodline_score,
                    ".6f"
                )
            )

        reasons.append(
            "該当祖先:"
            + str(matched_count)
        )

        reasons.append(
            "プラス祖先:"
            + str(positive_count)
        )

        reasons.append(
            "マイナス祖先:"
            + str(negative_count)
        )

        reasons.extend(
            build_ancestor_reason(
                "プラス血統",
                blood.get(
                    "top_positive_ancestors",
                    []
                )
            )
        )

        reasons.extend(
            build_ancestor_reason(
                "マイナス血統",
                blood.get(
                    "top_negative_ancestors",
                    []
                )
            )
        )

        reasons.append(
            "前走・能力・展開・調教・騎手・枠・馬体重・人気・当日バイアスは採点対象外"
        )

        results.append({
            "horse_id":
                horse_id,

            "horse_number":
                horse_number,

            "horse_name":
                horse_name,

            "analysis_mode":
                "newcomer_pedigree_only",

            "pedigree_available":
                True,

            # 新馬戦では既存能力を使用しない
            "ability_known":
                False,

            "ability_score":
                None,

            "original_performance_rate":
                None,

            "performance_rate":
                None,

            "base_performance":
                None,

            "condition_fit_score":
                None,

            "condition_adjustment":
                0.0,

            # 前走関連は完全不使用
            "previous_positive_count":
                0,

            "previous_issue_count":
                0,

            "overcoming_material_count":
                0,

            "previous_race_adjustment":
                0.0,

            # 展開不使用
            "pace_adjustment":
                0.0,

            "running_style":
                "評価対象外",

            # 馬場不使用
            "track_performance_rate_adjustment":
                0.0,

            # 時計不使用
            "time_fit_performance_rate_adjustment":
                0.0,

            "time_fit_label":
                "評価対象外",

            "time_fit_evaluated_race_count":
                0,

            "time_fit_median":
                None,

            # 馬体・斤量不使用
            "body_weight_performance_rate_adjustment":
                0.0,

            "body_weight_issue_adjustment":
                0.0,

            "body_weight":
                None,

            "body_weight_change":
                None,

            "carried_weight":
                None,

            "weight_body_ratio":
                None,

            "body_weight_source":
                "",

            # 新馬戦ではこれが唯一の採点値
            "bloodline_score":
                (
                    round(
                        bloodline_score,
                        6
                    )
                    if bloodline_score is not None
                    else None
                ),

            "bloodline_adjustment":
                0.0,

            "bloodline_support_applied":
                False,

            "matched_ancestor_count":
                matched_count,

            "positive_ancestor_count":
                positive_count,

            "negative_ancestor_count":
                negative_count,

            "bloodline_rank":
                source_bloodline_rank,

            # 最終点 = 血統スコア
            "final_score":
                (
                    round(
                        bloodline_score,
                        6
                    )
                    if bloodline_score is not None
                    else None
                ),

            "unknown":
                bloodline_score is None,

            "noise_flags":
                [],

            "reasons":
                reasons,

            "rank":
                None,

            "judgement":
                "",
        })

    # -----------------------------------------------------
    # ランキング
    #
    # 血統スコアが存在する馬だけ順位付け。
    # -----------------------------------------------------

    ranked_results = [
        horse
        for horse in results
        if horse["final_score"] is not None
    ]

    unranked_results = [
        horse
        for horse in results
        if horse["final_score"] is None
    ]

    ranked_results.sort(
        key=lambda x: (
            x["final_score"],
            -horse_number_sort_value(
                x["horse_number"]
            ),
        ),
        reverse=True
    )

    for rank, horse in enumerate(
        ranked_results,
        start=1
    ):
        horse["rank"] = rank
        horse["judgement"] = (
            judgement_from_rank(rank)
        )

    unranked_results.sort(
        key=lambda x: (
            horse_number_sort_value(
                x["horse_number"]
            ),
            x["horse_name"],
        )
    )

    for horse in unranked_results:
        horse["rank"] = None
        horse["judgement"] = (
            "血統データ不明"
        )

    results = (
        ranked_results
        + unranked_results
    )

    # -----------------------------------------------------
    # 血統条件情報
    # -----------------------------------------------------

    blood_condition = bloodline_data.get(
        "condition",
        {}
    )

    blood_summary = bloodline_data.get(
        "summary",
        {}
    )

    blood_method = bloodline_data.get(
        "method",
        {}
    )

    scored_count = len(
        ranked_results
    )

    missing_count = len(
        unranked_results
    )

    # -----------------------------------------------------
    # 出力
    # -----------------------------------------------------

    output = {
        "updated_at":
            now_jst(),

        "race_id":
            race_id,

        "analysis_mode":
            "newcomer_pedigree_only",

        "is_debut":
            True,

        "race_name":
            race.get(
                "race_name",
                ""
            ),

        "race_class":
            race.get(
                "race_class",
                ""
            ),

        "age_condition":
            race.get(
                "age_condition",
                ""
            ),

        "track":
            (
                race.get("track")
                or race.get("racecourse")
                or ""
            ),

        "surface":
            race.get(
                "surface",
                ""
            ),

        "distance":
            race.get(
                "distance"
            ),

        "pedigree_condition":
            blood_condition,

        "method": {
            "mode":
                "newcomer_pedigree_only",

            "pedigree_only":
                True,

            "final_score_source":
                "race_bloodline_score.bloodline_score",

            "ability_used":
                False,

            "previous_race_used":
                False,

            "pace_used":
                False,

            "training_used":
                False,

            "jockey_used":
                False,

            "draw_used":
                False,

            "body_weight_used":
                False,

            "popularity_used":
                False,

            "track_bias_used":
                False,

            "time_fit_used":
                False,

            "unknown_pedigree_not_imputed":
                True,

            "bloodline_method":
                blood_method,
        },

        # UI互換用。
        # 新馬戦ではすべて採点対象外。
        "track_condition": {
            "source_available":
                False,

            "race_id_matched":
                False,

            "source_race_id":
                "",

            "applied":
                False,

            "track_condition":
                "",

            "cushion_value":
                None,

            "moisture_4corner":
                None,

            "moisture_finish":
                None,
        },

        "day_bias": {
            "source_available":
                False,

            "source_race_id":
                "",

            "race_id_matched":
                False,

            "future_race_usage":
                None,

            "future_safe":
                True,

            "status":
                "not_used_in_newcomer_pedigree_only",

            "applied":
                False,

            "reference_race_count":
                0,

            "reference_race_numbers":
                [],

            "corner_connected_race_count":
                0,

            "top3_sample_count":
                0,

            "confidence":
                None,

            "time_bias":
                "",

            "inside_outside_bias":
                "",

            "running_style_bias":
                "",
        },

        "runner_time_fit": {
            "source_available":
                False,

            "source_race_id":
                "",

            "race_id_matched":
                False,

            "future_safe":
                True,

            "leak_check_passed":
                True,

            "applied":
                False,

            "scoring_applied":
                False,

            "current_time_bias":
                "",

            "connected_horse_count":
                0,

            "connected_past_race_count":
                0,
        },

        "body_weight_source": {
            "primary_source":
                "",

            "fallback_source":
                "",

            "fallback_source_available":
                False,

            "fallback_race_id_matched":
                False,

            "fallback_source_race_id":
                "",
        },

        "race_scenario": {
            "base_pace":
                "評価対象外",

            "leader_candidate_count":
                0,

            "front_candidate_count":
                0,
        },

        "summary": {
            "runner_count":
                len(results),

            "ranked_count":
                scored_count,

            "unranked_unknown_count":
                missing_count,

            "pedigree_scored_count":
                scored_count,

            "pedigree_missing_count":
                missing_count,

            "bloodline_connected_count":
                scored_count,

            "historical_race_count":
                blood_summary.get(
                    "historical_race_count",
                    0
                ),

            "historical_start_records":
                blood_summary.get(
                    "historical_start_records",
                    0
                ),

            # 通常解析項目は新馬戦では不使用
            "ability_record_connected_count":
                0,

            "ability_known_count":
                0,

            "ability_unknown_count":
                len(results),

            "previous_connected_count":
                0,

            "pace_connected_count":
                0,

            "bloodline_effective_count":
                scored_count,

            "bloodline_blocked_unknown_condition_count":
                0,

            "time_fit_record_connected_count":
                0,

            "time_fit_evaluable_count":
                0,

            "time_fit_effective_count":
                0,

            "body_weight_connected_count":
                0,

            "race_json_body_weight_connected_count":
                0,

            "previous_effective_count":
                0,

            "track_source_available":
                False,

            "track_race_id_matched":
                False,

            "track_applied":
                False,

            "day_bias_source_available":
                False,

            "day_bias_race_id_matched":
                False,

            "day_bias_future_safe":
                True,

            "day_bias_applied":
                False,

            "day_bias_reference_race_count":
                0,

            "day_bias_top3_sample_count":
                0,

            "track_effective_count":
                0,

            "body_weight_effective_count":
                0,

            "training_used":
                False,
        },

        "ranking":
            results,
    }

    # -----------------------------------------------------
    # 自己検査
    # -----------------------------------------------------

    if len(results) != len(runners):
        raise RuntimeError(
            "新馬戦の出走馬数と最終解析頭数が一致しません"
        )

    if scored_count == 0:
        raise RuntimeError(
            "新馬戦ですが血統採点済み馬が0頭です"
        )

    for horse in results:
        # 血統以外の数値補正が入っていないか確認
        forbidden_adjustments = (
            horse[
                "track_performance_rate_adjustment"
            ],
            horse[
                "time_fit_performance_rate_adjustment"
            ],
            horse[
                "body_weight_performance_rate_adjustment"
            ],
            horse[
                "body_weight_issue_adjustment"
            ],
            horse[
                "condition_adjustment"
            ],
            horse[
                "previous_race_adjustment"
            ],
            horse[
                "pace_adjustment"
            ],
            horse[
                "bloodline_adjustment"
            ],
        )

        if any(
            value != 0
            for value in forbidden_adjustments
        ):
            raise RuntimeError(
                "新馬戦に血統以外の補正が混入しました: "
                + horse["horse_name"]
            )

        if (
            horse["final_score"] is not None
            and horse["bloodline_score"] is not None
            and horse["final_score"]
            != horse["bloodline_score"]
        ):
            raise RuntimeError(
                "新馬戦の最終点と血統点が一致しません: "
                + horse["horse_name"]
            )

    # 順位連続性
    actual_ranks = [
        horse["rank"]
        for horse in results
        if horse["rank"] is not None
    ]

    expected_ranks = list(
        range(
            1,
            scored_count + 1
        )
    )

    if actual_ranks != expected_ranks:
        raise RuntimeError(
            "新馬戦の血統順位が連続していません"
        )

    # -----------------------------------------------------
    # 保存
    # -----------------------------------------------------

    with open(
        FINAL_FILE,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2
        )

    # -----------------------------------------------------
    # ログ
    # -----------------------------------------------------

    print(
        "===== NEWCOMER FINAL ANALYSIS ====="
    )

    print(
        "race id:",
        race_id
    )

    print(
        "mode:",
        "newcomer_pedigree_only"
    )

    print(
        "runners:",
        len(results)
    )

    print(
        "pedigree scored:",
        scored_count
    )

    print(
        "pedigree missing:",
        missing_count
    )

    print(
        "normal factors:",
        "DISABLED"
    )

    print(
        "----- PEDIGREE ONLY RANKING -----"
    )

    for horse in results:
        print(
            (
                horse["rank"]
                if horse["rank"] is not None
                else "-"
            ),
            horse["horse_number"],
            horse["horse_name"],
            "bloodline",
            (
                horse["bloodline_score"]
                if horse["bloodline_score"] is not None
                else "UNKNOWN"
            ),
            horse["judgement"]
        )


if __name__ == "__main__":
    main()
