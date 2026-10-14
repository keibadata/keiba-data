import json
from collections import defaultdict
from datetime import datetime, timezone


HISTORY_FILE = "history_db.json"
PEDIGREE_FILE = "history_pedigree.json"
OUTPUT_FILE = "bloodline_stats.json"


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_name(name):
    if not name:
        return ""

    # 現在の血統JSONでは祖先名に生年等が付く場合があるため、
    # IDがある場合はIDを主キーにする。
    return " ".join(str(name).split())


def parse_rank(value):
    try:
        return int(str(value).strip())
    except (ValueError, TypeError):
        return None


def make_ancestor_key(ancestor):
    ancestor_id = str(
        ancestor.get("ancestor_id", "")
    ).strip()

    ancestor_name = clean_name(
        ancestor.get("ancestor_name", "")
    )

    if ancestor_id:
        return "id:" + ancestor_id

    return "name:" + ancestor_name


def build_pedigree_map(pedigree_db):
    pedigree_map = {}

    for horse in pedigree_db.get("horses", []):
        horse_id = str(
            horse.get("horse_id", "")
        ).strip()

        if not horse_id:
            continue

        pedigree_map[horse_id] = horse

    return pedigree_map


def main():
    history_db = load_json(HISTORY_FILE)
    pedigree_db = load_json(PEDIGREE_FILE)

    pedigree_map = build_pedigree_map(
        pedigree_db
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
            "generation_counts": defaultdict(int),
        }
    )

    total_starts = 0
    total_wins = 0
    total_top3 = 0

    matched_starts = 0
    unmatched_starts = []

    race_count = 0

    for race in history_db.get("races", []):
        race_count += 1

        race_id = str(
            race.get("race_id", "")
        )

        for result in race.get(
            "results",
            []
        ):
            total_starts += 1

            horse_id = str(
                result.get("horse_id", "")
            ).strip()

            horse_name = str(
                result.get("horse_name", "")
            ).strip()

            rank = parse_rank(
                result.get("rank")
            )

            if rank == 1:
                total_wins += 1

            if rank is not None and rank <= 3:
                total_top3 += 1

            pedigree = pedigree_map.get(
                horse_id
            )

            if pedigree is None:
                unmatched_starts.append({
                    "race_id": race_id,
                    "horse_id": horse_id,
                    "horse_name": horse_name,
                })
                continue

            matched_starts += 1

            # この1出走について祖先別にまとめる。
            # 同じ祖先がクロスしていてもstartsは1回。
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

                if key not in runner_ancestors:
                    runner_ancestors[key] = {
                        "ancestor_id": ancestor_id,
                        "ancestor_name": ancestor_name,
                        "occurrences": 0,
                        "generation_counts":
                            defaultdict(int),
                    }

                item = runner_ancestors[key]

                item["occurrences"] += 1

                try:
                    generation_int = int(
                        generation
                    )
                    item[
                        "generation_counts"
                    ][generation_int] += 1
                except (TypeError, ValueError):
                    pass

            for key, ancestor_data in (
                runner_ancestors.items()
            ):
                s = stats[key]

                if not s["ancestor_id"]:
                    s["ancestor_id"] = (
                        ancestor_data[
                            "ancestor_id"
                        ]
                    )

                if not s["ancestor_name"]:
                    s["ancestor_name"] = (
                        ancestor_data[
                            "ancestor_name"
                        ]
                    )

                # 出走数は1出走につき1回
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

                # 同一祖先が5代内に2回以上ある出走
                if occurrence_count >= 2:
                    s[
                        "cross_runner_count"
                    ] += 1

                for generation, count in (
                    ancestor_data[
                        "generation_counts"
                    ].items()
                ):
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

        # 全出走レコード中、
        # この祖先を持つ馬の割合
        all_runner_prevalence = (
            starts / matched_starts
            if matched_starts
            else 0
        )

        # 勝ち馬の中でこの祖先を持つ割合
        winner_prevalence = (
            wins / total_wins
            if total_wins
            else 0
        )

        # 3着以内馬の中でこの祖先を持つ割合
        top3_prevalence = (
            top3 / total_top3
            if total_top3
            else 0
        )

        # 1.0 = 全出走馬と同程度
        # >1.0 = 勝ち馬で過剰出現
        win_overperformance = (
            winner_prevalence
            / all_runner_prevalence
            if all_runner_prevalence
            else 0
        )

        # 1.0 = 全出走馬と同程度
        # >1.0 = 3着以内馬で過剰出現
        top3_overperformance = (
            top3_prevalence
            / all_runner_prevalence
            if all_runner_prevalence
            else 0
        )

        generation_counts = {
            str(g): s[
                "generation_counts"
            ].get(g, 0)
            for g in range(1, 6)
        }

        output_stats.append({
            "ancestor_key": key,
            "ancestor_id": s[
                "ancestor_id"
            ],
            "ancestor_name": s[
                "ancestor_name"
            ],

            "starts": starts,
            "wins": wins,
            "top3": top3,

            "win_rate": round(
                win_rate,
                6
            ),
            "top3_rate": round(
                top3_rate,
                6
            ),

            "all_runner_prevalence": round(
                all_runner_prevalence,
                6
            ),
            "winner_prevalence": round(
                winner_prevalence,
                6
            ),
            "top3_prevalence": round(
                top3_prevalence,
                6
            ),

            "win_overperformance": round(
                win_overperformance,
                4
            ),
            "top3_overperformance": round(
                top3_overperformance,
                4
            ),

            # 血統表内での総出現回数
            "pedigree_occurrences":
                s["occurrences"],

            # 5代内クロスを持った出走数
            "cross_runner_count":
                s["cross_runner_count"],

            "generation_counts":
                generation_counts,
        })

    # 母数が大きい祖先を上へ。
    # 同数なら複勝率 → 勝率。
    output_stats.sort(
        key=lambda x: (
            x["starts"],
            x["top3_rate"],
            x["win_rate"],
        ),
        reverse=True,
    )

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source_history":
            HISTORY_FILE,

        "source_pedigree":
            PEDIGREE_FILE,

        "condition": history_db.get(
            "condition",
            {}
        ),

        "summary": {
            "race_count":
                race_count,

            "total_start_records":
                total_starts,

            "matched_start_records":
                matched_starts,

            "unmatched_start_records":
                len(unmatched_starts),

            "unique_pedigree_horses":
                len(pedigree_map),

            "total_winners":
                total_wins,

            "total_top3_finishers":
                total_top3,

            "ancestor_count":
                len(output_stats),
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
        "========================"
    )
    print(
        "レース数:",
        race_count
    )
    print(
        "全出走レコード:",
        total_starts
    )
    print(
        "血統照合成功:",
        matched_starts
    )
    print(
        "血統照合失敗:",
        len(unmatched_starts)
    )
    print(
        "祖先種類数:",
        len(output_stats)
    )
    print(
        OUTPUT_FILE,
        "作成完了"
    )


if __name__ == "__main__":
    main()
