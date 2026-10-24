import json
from collections import defaultdict
from datetime import datetime, timezone


# 今回条件で選別済みの過去レース
HISTORY_FILE = "condition_history.json"

# 過去出走馬の5代血統DB
PEDIGREE_FILE = "history_pedigree.json"

OUTPUT_FILE = "bloodline_stats.json"


def load_json(path):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


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


def build_pedigree_map(
    pedigree_db
):
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


def normalize_surface(value):
    value = str(
        value or ""
    ).strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_condition(
    condition
):
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

        "surface":
            normalize_surface(
                condition.get(
                    "surface",
                    ""
                )
            ),

        "distance":
            distance,
    }


def get_race_condition(
    race
):
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


def validate_one_race(
    race_condition,
    target,
    selection_mode,
    selection_rule
):
    """
    condition_history.py が選択したレースが
    selection_mode / selection_rule に本当に
    合っているか再検証する。

    通常戦の exact は従来どおり完全一致。
    新馬戦のフォールバックだけ条件を広げる。
    """

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
            and surface
            == target["surface"]
            and distance
            == target["distance"]
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
            and surface
            == target["surface"]
            and distance > 0
            and abs(
                distance
                - target["distance"]
            )
            <= tolerance
        )

    if (
        selection_mode
        == "debut_same_track_surface_any_distance"
    ):
        return (
            track == target["track"]
            and surface
            == target["surface"]
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
            surface
            == target["surface"]
            and distance > 0
            and abs(
                distance
                - target["distance"]
            )
            <= tolerance
        )

    if (
        selection_mode
        == "debut_same_surface_any_distance"
    ):
        return (
            surface
            == target["surface"]
        )

    return False


def validate_selected_history(
    history_db
):
    """
    condition_history.py が選別した条件を検査。

    通常戦:
        完全一致のみ許可。

    新馬戦:
        condition_history.py が記録した
        selection_mode の範囲だけ許可。

    条件外レースが混入した場合は停止する。
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

    selection_rule = (
        history_db.get(
            "selection_rule",
            {}
        )
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

    if not races:
        raise RuntimeError(
            "血統評価に使用できる"
            "過去レースが0件です。"
        )

    # 通常戦が新馬専用モードを
    # 使用していないかチェック。
    if (
        not is_debut
        and selection_mode
        != "exact"
    ):
        raise RuntimeError(
            "通常戦で新馬用の"
            "血統条件拡張が使用されています: "
            + selection_mode
        )

    allowed_debut_modes = {
        "exact",
        (
            "debut_"
            "same_track_"
            "surface_"
            "near_distance"
        ),
        (
            "debut_"
            "same_track_"
            "surface_"
            "any_distance"
        ),
        (
            "debut_"
            "same_surface_"
            "near_distance"
        ),
        (
            "debut_"
            "same_surface_"
            "any_distance"
        ),
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

    pedigree_map = (
        build_pedigree_map(
            pedigree_db
        )
    )

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

            pedigree = (
                pedigree_map.get(
                    horse_id
                )
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

            # 同一出走内で同じ祖先が
            # 複数回出てもstartsは1回。
            runner_ancestors = {}

            for ancestor in (
                pedigree.get(
                    "ancestors",
                    []
                )
            ):

                key = make_ancestor_key(
                    ancestor
                )

                ancestor_name = (
                    clean_name(
                        ancestor.get(
                            "ancestor_name",
                            ""
                        )
                    )
                )

                if not ancestor_name:
                    continue

                generation = (
                    ancestor.get(
                        "generation"
                    )
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
                            defaultdict(
                                int
                            ),
                    }

                item = (
                    runner_ancestors[
                        key
                    ]
                )

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
                ] += (
                    occurrence_count
                )

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
            starts
            / matched_starts
            if matched_starts
            else 0
        )

        winner_prevalence = (
            wins
            / total_wins
            if total_wins
            else 0
        )

        top3_prevalence = (
            top3
            / total_top3
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
            str(g):
                s[
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

    output = {
        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source_history":
            HISTORY_FILE,

        "source_pedigree":
            PEDIGREE_FILE,

        # 今回の本来の条件。
        "condition":
            target_condition,

        # 新馬専用フォールバックを
        # 使用したか確認できるよう保存。
        "is_debut":
            is_debut,

        "selection_mode":
            selection_mode,

        "selection_rule":
            selection_rule,

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

    with open(
        OUTPUT_FILE,
        "w",
        encoding="utf-8"
    ) as f:

        json.dump(
            output,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print(
        "===== BLOODLINE STATS ====="
    )

    print(
        "condition:",
        target_condition[
            "track"
        ],
        target_condition[
            "surface"
        ],
        target_condition[
            "distance"
        ]
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

    if matched_starts == 0:
        raise RuntimeError(
            "過去レースはありますが、"
            "history_pedigree.jsonと"
            "照合できた出走馬が0件です。"
        )

    if not output_stats:
        raise RuntimeError(
            "血統統計を1件も"
            "生成できませんでした。"
        )

    print(
        "bloodline stats saved:",
        OUTPUT_FILE
    )


if __name__ == "__main__":
    main()
