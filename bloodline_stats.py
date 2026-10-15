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
        return "id:" + ancestor_id

    return "name:" + ancestor_name


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


def normalize_condition(
    condition
):
    return {
        "track": str(
            condition.get(
                "track",
                ""
            )
        ).strip(),

        "surface": str(
            condition.get(
                "surface",
                ""
            )
        ).strip(),

        "distance": int(
            condition.get(
                "distance",
                0
            ) or 0
        ),
    }


def validate_selected_history(
    history_db
):
    """
    condition_history.py が選別した条件を検査。
    別条件のレースが混ざっていたら停止する。
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
            "今回条件に一致する過去レースが0件です。"
            "血統評価を続行しません。"
        )

    for race in races:

        race_track = str(
            race.get(
                "racecourse",
                race.get(
                    "track",
                    ""
                )
            )
        ).strip()

        race_surface = str(
            race.get(
                "surface",
                ""
            )
        ).strip()

        try:
            race_distance = int(
                race.get(
                    "distance",
                    0
                ) or 0
            )
        except (
            TypeError,
            ValueError
        ):
            race_distance = 0

        if (
            race_track
            != target["track"]
            or race_surface
            != target["surface"]
            or race_distance
            != target["distance"]
        ):
            raise RuntimeError(
                "条件不一致レース混入: "
                + str(
                    race.get(
                        "race_id",
                        ""
                    )
                )
            )

    return target, races


def main():
    history_db = load_json(
        HISTORY_FILE
    )

    pedigree_db = load_json(
        PEDIGREE_FILE
    )

    target_condition, races = (
        validate_selected_history(
            history_db
        )
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

                s["starts"] += 1

                if rank == 1:
                    s["wins"] += 1

                if (
                    rank is not None
                    and rank <= 3
                ):
                    s["top3"] += 1

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
                    ][generation] += count

    output_stats = []

    for key, s in stats.items():

        starts = s["starts"]
        wins = s["wins"]
        top3 = s["top3"]

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

        # race.jsonから選ばれた
        # 今回の実条件
        "condition":
            target_condition,

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
                "この祖先を5代内に持つ馬の出走レコード数。同一馬内のクロスは1回として数える。",

            "wins":
                "startsのうち1着になった回数。",

            "top3":
                "startsのうち3着以内になった回数。",

            "all_runner_prevalence":
                "全血統照合済み出走レコードに対する、この祖先を持つ馬の割合。",

            "winner_prevalence":
                "全勝ち馬に対する、この祖先を持つ勝ち馬の割合。",

            "top3_prevalence":
                "全3着以内馬に対する、この祖先を持つ好走馬の割合。",

            "win_overperformance":
                "winner_prevalence ÷ all_runner_prevalence。1超で勝ち馬に過剰出現。",

            "top3_overperformance":
                "top3_prevalence ÷ all_runner_prevalence。1超で3着以内馬に過剰出現。",

            "pedigree_occurrences":
                "クロスを含めた5代血統表内での祖先総出現回数。",

            "cross_runner_count":
                "同じ祖先が同一馬の5代内に2回以上出現した出走レコード数。"
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
        OUTPUT_FILE,
        "作成完了"
    )


if __name__ == "__main__":
    main()
