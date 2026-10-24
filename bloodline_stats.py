import json
from collections import defaultdict
from datetime import datetime, timezone


# ============================================================
# Files
# ============================================================

HISTORY_FILE = "condition_history.json"
PEDIGREE_FILE = "history_pedigree.json"
OUTPUT_FILE = "bloodline_stats.json"


# ============================================================
# Basic helpers
# ============================================================

def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def clean_name(name):
    if not name:
        return ""

    return " ".join(
        str(name).split()
    )


def parse_rank(value):
    try:
        return int(
            str(value).strip()
        )

    except (
        ValueError,
        TypeError
    ):
        return None


# ============================================================
# Pedigree helpers
# ============================================================

def make_ancestor_key(ancestor):
    ancestor_id = str(
        ancestor.get(
            "ancestor_id",
            ""
        )
    ).strip()

    ancestor_name = clean_name(
        ancestor.get(
            "ancestor_name",
            ""
        )
    )

    if ancestor_id:
        return (
            "id:"
            + ancestor_id
        )

    return (
        "name:"
        + ancestor_name
    )


def build_pedigree_map(pedigree_db):
    pedigree_map = {}

    for horse in pedigree_db.get(
        "horses",
        []
    ):
        horse_id = str(
            horse.get(
                "horse_id",
                ""
            )
        ).strip()

        if not horse_id:
            continue

        pedigree_map[
            horse_id
        ] = horse

    return pedigree_map


# ============================================================
# Condition helpers
# ============================================================

def normalize_surface(value):
    value = str(
        value or ""
    ).strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_condition(condition):
    try:
        distance = int(
            condition.get(
                "distance",
                0
            )
            or 0
        )

    except (
        TypeError,
        ValueError
    ):
        distance = 0

    return {
        "track": str(
            condition.get(
                "track",
                ""
            )
        ).strip(),

        "surface": normalize_surface(
            condition.get(
                "surface",
                ""
            )
        ),

        "distance": distance,
    }


def get_race_condition(race):
    race_info = race.get(
        "race_info",
        {}
    )

    track = (
        race.get("racecourse")
        or race.get("track")
        or race.get("venue")
        or race.get("place")
        or ""
    )

    surface = (
        race.get("surface")
        or race.get("track_type")
        or race.get("course_type")
        or ""
    )

    distance = (
        race.get("distance")
        or race.get("distance_m")
        or 0
    )

    if isinstance(
        race_info,
        dict
    ):
        if not track:
            track = (
                race_info.get(
                    "racecourse"
                )
                or race_info.get(
                    "track"
                )
                or race_info.get(
                    "venue"
                )
                or race_info.get(
                    "place"
                )
                or ""
            )

        if not surface:
            surface = (
                race_info.get(
                    "surface"
                )
                or race_info.get(
                    "track_type"
                )
                or race_info.get(
                    "course_type"
                )
                or ""
            )

        if not distance:
            distance = (
                race_info.get(
                    "distance"
                )
                or race_info.get(
                    "distance_m"
                )
                or 0
            )

    return normalize_condition(
        {
            "track": track,
            "surface": surface,
            "distance": distance,
        }
    )


# ============================================================
# Selected history validation
# ============================================================

def validate_one_race(
    race_condition,
    target,
    selection_mode,
    selection_rule
):
    track = race_condition[
        "track"
    ]

    surface = race_condition[
        "surface"
    ]

    distance = race_condition[
        "distance"
    ]

    if selection_mode == "exact":
        return (
            track == target["track"]
            and surface == target["surface"]
            and distance == target["distance"]
        )

    if (
        selection_mode
        == "debut_same_track_surface_near_distance"
    ):
        tolerance = selection_rule.get(
            "distance_tolerance",
            200
        )

        try:
            tolerance = int(
                tolerance
            )

        except (
            TypeError,
            ValueError
        ):
            tolerance = 200

        return (
            track == target["track"]
            and surface == target["surface"]
            and distance > 0
            and abs(
                distance
                - target["distance"]
            ) <= tolerance
        )

    if (
        selection_mode
        == "debut_same_track_surface_any_distance"
    ):
        return (
            track == target["track"]
            and surface == target["surface"]
        )

    if (
        selection_mode
        == "debut_same_surface_near_distance"
    ):
        tolerance = selection_rule.get(
            "distance_tolerance",
            200
        )

        try:
            tolerance = int(
                tolerance
            )

        except (
            TypeError,
            ValueError
        ):
            tolerance = 200

        return (
            surface == target["surface"]
            and distance > 0
            and abs(
                distance
                - target["distance"]
            ) <= tolerance
        )

    if (
        selection_mode
        == "debut_same_surface_any_distance"
    ):
        return (
            surface == target["surface"]
        )

    return False


def validate_selected_history(history_db):
    """
    通常戦:
        exactのみ。
        過去レース0件は正常。
        血統補正なしで解析を続行する。

    新馬戦:
        血統のみで最終評価するため、
        使用可能な過去レース0件はエラー。
        新馬専用フォールバックを許可する。
    """

    target = normalize_condition(
        history_db.get(
            "target_condition",
            {}
        )
    )

    races = history_db.get(
        "matched_history",
        []
    )

    if not isinstance(
        races,
        list
    ):
        races = []

    is_debut = bool(
        history_db.get(
            "is_debut",
            False
        )
    )

    selection_mode = str(
        history_db.get(
            "selection_mode",
            "exact"
        )
    ).strip()

    selection_rule = history_db.get(
        "selection_rule",
        {}
    )

    if not isinstance(
        selection_rule,
        dict
    ):
        selection_rule = {}

    if not target["track"]:
        raise RuntimeError(
            "target_condition.track がありません"
        )

    if not target["surface"]:
        raise RuntimeError(
            "target_condition.surface がありません"
        )

    if target["distance"] <= 0:
        raise RuntimeError(
            "target_condition.distance が不正です"
        )

    # --------------------------------------------------------
    # 通常戦は exact のみ
    # --------------------------------------------------------

    if (
        not is_debut
        and selection_mode != "exact"
    ):
        raise RuntimeError(
            "通常戦で新馬用の"
            "血統条件拡張が使用されています: "
            + selection_mode
        )

    # --------------------------------------------------------
    # 新馬戦で使用可能な選択モード
    # --------------------------------------------------------

    allowed_debut_modes = {
        "exact",
        "debut_same_track_surface_near_distance",
        "debut_same_track_surface_any_distance",
        "debut_same_surface_near_distance",
        "debut_same_surface_any_distance",
    }

    if (
        is_debut
        and selection_mode
        not in allowed_debut_modes
    ):
        raise RuntimeError(
            "不明な新馬用"
            "selection_modeです: "
            + selection_mode
        )

    # --------------------------------------------------------
    # 重要:
    # 新馬は血統データ必須。
    # 通常戦は0件でも正常続行。
    # --------------------------------------------------------

    if not races:
        if is_debut:
            raise RuntimeError(
                "新馬戦ですが、"
                "血統評価に使用できる"
                "過去レースが0件です。"
            )

        print(
            "通常戦の血統条件一致レースは0件です。"
        )
        print(
            "血統評価をニュートラルとして"
            "解析を続行します。"
        )

        return (
            target,
            [],
            is_debut,
            selection_mode,
            selection_rule,
        )

    # --------------------------------------------------------
    # 選択済み過去レースを再検証
    # --------------------------------------------------------

    for race in races:
        race_condition = (
            get_race_condition(
                race
            )
        )

        valid = validate_one_race(
            race_condition,
            target,
            selection_mode,
            selection_rule
        )

        if not valid:
            raise RuntimeError(
                "条件不一致レース混入: "
                + str(
                    race.get(
                        "race_id",
                        ""
                    )
                )
                + " / mode="
                + selection_mode
                + " / "
                + str(
                    race_condition
                )
            )

    return (
        target,
        races,
        is_debut,
        selection_mode,
        selection_rule,
    )


# ============================================================
# Empty / neutral output
# ============================================================

def build_output(
    target_condition,
    is_debut,
    selection_mode,
    selection_rule,
    pedigree_map,
    race_count,
    total_starts,
    matched_starts,
    total_wins,
    total_top3,
    unmatched_starts,
    output_stats,
    bloodline_available,
    neutral_reason
):
    return {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source_history":
            HISTORY_FILE,

        "source_pedigree":
            PEDIGREE_FILE,

        "condition":
            target_condition,

        "is_debut":
            is_debut,

        "selection_mode":
            selection_mode,

        "selection_rule":
            selection_rule,

        # 下流処理・デバッグ用
        "bloodline_available":
            bloodline_available,

        "neutral_reason":
            neutral_reason,

        "summary": {
            "race_count":
                race_count,

            "total_start_records":
                total_starts,

            "matched_start_records":
                matched_starts,

            "unmatched_start_records":
                len(
                    unmatched_starts
                ),

            "unique_pedigree_horses":
                len(
                    pedigree_map
                ),

            "total_winners":
                total_wins,

            "total_top3_finishers":
                total_top3,

            "ancestor_count":
                len(
                    output_stats
                ),
        },

        "definitions": {
            "starts":
                (
                    "この祖先を5代内に持つ馬の"
                    "出走レコード数。"
                    "同一馬内のクロスは"
                    "1回として数える。"
                ),

            "wins":
                (
                    "startsのうち"
                    "1着になった回数。"
                ),

            "top3":
                (
                    "startsのうち"
                    "3着以内になった回数。"
                ),

            "all_runner_prevalence":
                (
                    "全血統照合済み出走レコード"
                    "に対する、この祖先を持つ馬の割合。"
                ),

            "winner_prevalence":
                (
                    "全勝ち馬に対する、"
                    "この祖先を持つ勝ち馬の割合。"
                ),

            "top3_prevalence":
                (
                    "全3着以内馬に対する、"
                    "この祖先を持つ好走馬の割合。"
                ),

            "win_overperformance":
                (
                    "winner_prevalence ÷ "
                    "all_runner_prevalence。"
                    "1超で勝ち馬に過剰出現。"
                ),

            "top3_overperformance":
                (
                    "top3_prevalence ÷ "
                    "all_runner_prevalence。"
                    "1超で3着以内馬に過剰出現。"
                ),

            "pedigree_occurrences":
                (
                    "クロスを含めた"
                    "5代血統表内での"
                    "祖先総出現回数。"
                ),

            "cross_runner_count":
                (
                    "同じ祖先が同一馬の"
                    "5代内に2回以上出現した"
                    "出走レコード数。"
                ),
        },

        "unmatched_starts":
            unmatched_starts,

        "ancestors":
            output_stats,
    }


# ============================================================
# Main
# ============================================================

def main():
    history_db = load_json(
        HISTORY_FILE
    )

    pedigree_db = load_json(
        PEDIGREE_FILE
    )

    (
        target_condition,
        races,
        is_debut,
        selection_mode,
        selection_rule,
    ) = validate_selected_history(
        history_db
    )

    pedigree_map = build_pedigree_map(
        pedigree_db
    )

    # --------------------------------------------------------
    # 通常戦で過去条件一致レース0件
    # --------------------------------------------------------

    if (
        not is_debut
        and not races
    ):
        output = build_output(
            target_condition=
                target_condition,

            is_debut=
                is_debut,

            selection_mode=
                selection_mode,

            selection_rule=
                selection_rule,

            pedigree_map=
                pedigree_map,

            race_count=0,
            total_starts=0,
            matched_starts=0,
            total_wins=0,
            total_top3=0,
            unmatched_starts=[],
            output_stats=[],

            bloodline_available=False,

            neutral_reason=(
                "通常戦の今回条件に一致する"
                "血統統計用過去レースが0件のため、"
                "血統評価をニュートラル0として扱う。"
            ),
        )

        save_json(
            OUTPUT_FILE,
            output
        )

        print(
            "===== BLOODLINE STATS ====="
        )
        print(
            "condition:",
            target_condition["track"],
            target_condition["surface"],
            target_condition["distance"]
        )
        print(
            "is_debut:",
            is_debut
        )
        print(
            "selection_mode:",
            selection_mode
        )
        print(
            "race_count: 0"
        )
        print(
            "ancestor_count: 0"
        )
        print(
            "bloodline_available: False"
        )
        print(
            "NORMAL RACE: "
            "bloodline neutral fallback"
        )
        print(
            "bloodline stats saved:",
            OUTPUT_FILE
        )

        return

    # --------------------------------------------------------
    # Statistics
    # --------------------------------------------------------

    stats = defaultdict(
        lambda: {
            "ancestor_id": "",
            "ancestor_name": "",
            "starts": 0,
            "wins": 0,
            "top3": 0,
            "occurrences": 0,
            "cross_runner_count": 0,
            "generation_counts":
                defaultdict(int),
        }
    )

    total_starts = 0
    total_wins = 0
    total_top3 = 0

    matched_starts = 0
    unmatched_starts = []

    race_count = 0

    for race in races:
        race_count += 1

        race_id = str(
            race.get(
                "race_id",
                ""
            )
        )

        for result in race.get(
            "results",
            []
        ):
            total_starts += 1

            horse_id = str(
                result.get(
                    "horse_id",
                    ""
                )
            ).strip()

            horse_name = str(
                result.get(
                    "horse_name",
                    ""
                )
            ).strip()

            rank = parse_rank(
                result.get(
                    "rank"
                )
            )

            if rank == 1:
                total_wins += 1

            if (
                rank is not None
                and rank <= 3
            ):
                total_top3 += 1

            pedigree = pedigree_map.get(
                horse_id
            )

            if pedigree is None:
                unmatched_starts.append(
                    {
                        "race_id":
                            race_id,

                        "horse_id":
                            horse_id,

                        "horse_name":
                            horse_name,
                    }
                )
                continue

            matched_starts += 1

            # 同一出走内で同じ祖先が複数回出ても
            # startsは1回だけ数える。
            runner_ancestors = {}

            for ancestor in pedigree.get(
                "ancestors",
                []
            ):
                key = make_ancestor_key(
                    ancestor
                )

                ancestor_name = clean_name(
                    ancestor.get(
                        "ancestor_name",
                        ""
                    )
                )

                if not ancestor_name:
                    continue

                generation = ancestor.get(
                    "generation"
                )

                ancestor_id = str(
                    ancestor.get(
                        "ancestor_id",
                        ""
                    )
                ).strip()

                if (
                    key
                    not in runner_ancestors
                ):
                    runner_ancestors[
                        key
                    ] = {
                        "ancestor_id":
                            ancestor_id,

                        "ancestor_name":
                            ancestor_name,

                        "occurrences":
                            0,

                        "generation_counts":
                            defaultdict(int),
                    }

                item = runner_ancestors[
                    key
                ]

                item[
                    "occurrences"
                ] += 1

                try:
                    generation_int = int(
                        generation
                    )

                    item[
                        "generation_counts"
                    ][
                        generation_int
                    ] += 1

                except (
                    TypeError,
                    ValueError
                ):
                    pass

            for (
                key,
                ancestor_data
            ) in runner_ancestors.items():
                s = stats[key]

                if not s[
                    "ancestor_id"
                ]:
                    s[
                        "ancestor_id"
                    ] = ancestor_data[
                        "ancestor_id"
                    ]

                if not s[
                    "ancestor_name"
                ]:
                    s[
                        "ancestor_name"
                    ] = ancestor_data[
                        "ancestor_name"
                    ]

                s[
                    "starts"
                ] += 1

                if rank == 1:
                    s[
                        "wins"
                    ] += 1

                if (
                    rank is not None
                    and rank <= 3
                ):
                    s[
                        "top3"
                    ] += 1

                occurrence_count = (
                    ancestor_data[
                        "occurrences"
                    ]
                )

                s[
                    "occurrences"
                ] += occurrence_count

                if (
                    occurrence_count
                    >= 2
                ):
                    s[
                        "cross_runner_count"
                    ] += 1

                for (
                    generation,
                    count
                ) in ancestor_data[
                    "generation_counts"
                ].items():
                    s[
                        "generation_counts"
                    ][
                        generation
                    ] += count

    # --------------------------------------------------------
    # 新馬戦では血統照合0件を許可しない
    # 通常戦ではニュートラル継続
    # --------------------------------------------------------

    if matched_starts == 0:
        if is_debut:
            raise RuntimeError(
                "新馬戦ですが、"
                "過去レース出走馬と"
                "history_pedigree.jsonを"
                "照合できた馬が0件です。"
            )

        output = build_output(
            target_condition=
                target_condition,

            is_debut=
                is_debut,

            selection_mode=
                selection_mode,

            selection_rule=
                selection_rule,

            pedigree_map=
                pedigree_map,

            race_count=
                race_count,

            total_starts=
                total_starts,

            matched_starts=0,

            total_wins=
                total_wins,

            total_top3=
                total_top3,

            unmatched_starts=
                unmatched_starts,

            output_stats=[],

            bloodline_available=False,

            neutral_reason=(
                "通常戦の過去レースは存在するが、"
                "血統DBと照合できた出走馬が0件のため、"
                "血統評価をニュートラル0として扱う。"
            ),
        )

        save_json(
            OUTPUT_FILE,
            output
        )

        print(
            "===== BLOODLINE STATS ====="
        )
        print(
            "matched_start_records: 0"
        )
        print(
            "NORMAL RACE: "
            "bloodline neutral fallback"
        )
        print(
            "bloodline stats saved:",
            OUTPUT_FILE
        )

        return

    # --------------------------------------------------------
    # Ancestor statistics
    # --------------------------------------------------------

    output_stats = []

    for key, s in stats.items():
        starts = s[
            "starts"
        ]

        wins = s[
            "wins"
        ]

        top3 = s[
            "top3"
        ]

        win_rate = (
            wins / starts
            if starts
            else 0
        )

        top3_rate = (
            top3 / starts
            if starts
            else 0
        )

        all_runner_prevalence = (
            starts / matched_starts
            if matched_starts
            else 0
        )

        winner_prevalence = (
            wins / total_wins
            if total_wins
            else 0
        )

        top3_prevalence = (
            top3 / total_top3
            if total_top3
            else 0
        )

        win_overperformance = (
            winner_prevalence
            / all_runner_prevalence
            if all_runner_prevalence
            else 0
        )

        top3_overperformance = (
            top3_prevalence
            / all_runner_prevalence
            if all_runner_prevalence
            else 0
        )

        generation_counts = {
            str(g): s[
                "generation_counts"
            ].get(
                g,
                0
            )
            for g in range(
                1,
                6
            )
        }

        output_stats.append(
            {
                "ancestor_key":
                    key,

                "ancestor_id":
                    s[
                        "ancestor_id"
                    ],

                "ancestor_name":
                    s[
                        "ancestor_name"
                    ],

                "starts":
                    starts,

                "wins":
                    wins,

                "top3":
                    top3,

                "win_rate":
                    round(
                        win_rate,
                        6
                    ),

                "top3_rate":
                    round(
                        top3_rate,
                        6
                    ),

                "all_runner_prevalence":
                    round(
                        all_runner_prevalence,
                        6
                    ),

                "winner_prevalence":
                    round(
                        winner_prevalence,
                        6
                    ),

                "top3_prevalence":
                    round(
                        top3_prevalence,
                        6
                    ),

                "win_overperformance":
                    round(
                        win_overperformance,
                        4
                    ),

                "top3_overperformance":
                    round(
                        top3_overperformance,
                        4
                    ),

                "pedigree_occurrences":
                    s[
                        "occurrences"
                    ],

                "cross_runner_count":
                    s[
                        "cross_runner_count"
                    ],

                "generation_counts":
                    generation_counts,
            }
        )

    output_stats.sort(
        key=lambda x: (
            x["starts"],
            x["top3_rate"],
            x["win_rate"],
        ),
        reverse=True,
    )

    # --------------------------------------------------------
    # 血統統計が生成できない場合
    # --------------------------------------------------------

    if not output_stats:
        if is_debut:
            raise RuntimeError(
                "新馬戦ですが、"
                "血統統計を1件も"
                "生成できませんでした。"
            )

        bloodline_available = False

        neutral_reason = (
            "通常戦で血統統計を生成できなかったため、"
            "血統評価をニュートラル0として扱う。"
        )

    else:
        bloodline_available = True
        neutral_reason = ""

    # --------------------------------------------------------
    # Output
    # --------------------------------------------------------

    output = build_output(
        target_condition=
            target_condition,

        is_debut=
            is_debut,

        selection_mode=
            selection_mode,

        selection_rule=
            selection_rule,

        pedigree_map=
            pedigree_map,

        race_count=
            race_count,

        total_starts=
            total_starts,

        matched_starts=
            matched_starts,

        total_wins=
            total_wins,

        total_top3=
            total_top3,

        unmatched_starts=
            unmatched_starts,

        output_stats=
            output_stats,

        bloodline_available=
            bloodline_available,

        neutral_reason=
            neutral_reason,
    )

    save_json(
        OUTPUT_FILE,
        output
    )

    # --------------------------------------------------------
    # Log
    # --------------------------------------------------------

    print(
        "===== BLOODLINE STATS ====="
    )

    print(
        "condition:",
        target_condition["track"],
        target_condition["surface"],
        target_condition["distance"]
    )

    print(
        "is_debut:",
        is_debut
    )

    print(
        "selection_mode:",
        selection_mode
    )

    print(
        "race_count:",
        race_count
    )

    print(
        "total_start_records:",
        total_starts
    )

    print(
        "matched_start_records:",
        matched_starts
    )

    print(
        "unmatched_start_records:",
        len(
            unmatched_starts
        )
    )

    print(
        "ancestor_count:",
        len(
            output_stats
        )
    )

    print(
        "bloodline_available:",
        bloodline_available
    )

    if not bloodline_available:
        print(
            "NORMAL RACE: "
            "bloodline neutral fallback"
        )

    print(
        "bloodline stats saved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
