import json
import math
from datetime import datetime, timezone


RACE_FILE = "race.json"
PEDIGREE_FILE = "pedigree.json"
STATS_FILE = "bloodline_stats.json"
OUTPUT_FILE = "race_bloodline_score.json"

# 祖先統計を評価対象にする最低出走数
MIN_STARTS = 5

# 極端な少数サンプルの影響を抑える上限
MAX_OVERPERFORMANCE = 3.0


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def clean_text(value):
    if value is None:
        return ""
    return " ".join(str(value).split())


def ancestor_key(ancestor_id, ancestor_name):
    ancestor_id = clean_text(ancestor_id)
    ancestor_name = clean_text(ancestor_name)

    if ancestor_id:
        return "id:" + ancestor_id

    return "name:" + ancestor_name


def extract_runners(race_data):
    """
    race.json の構造差に対応。
    """
    candidates = []

    if isinstance(race_data, list):
        candidates = race_data

    elif isinstance(race_data, dict):
        for key in [
            "horses",
            "runners",
            "entries",
            "results",
        ]:
            value = race_data.get(key)
            if isinstance(value, list):
                candidates = value
                break

        if not candidates:
            race = race_data.get("race")
            if isinstance(race, dict):
                for key in [
                    "horses",
                    "runners",
                    "entries",
                    "results",
                ]:
                    value = race.get(key)
                    if isinstance(value, list):
                        candidates = value
                        break

    runners = []

    for row in candidates:
        if not isinstance(row, dict):
            continue

        horse_id = clean_text(
            row.get("horse_id")
            or row.get("id")
        )

        horse_name = clean_text(
            row.get("horse_name")
            or row.get("name")
        )

        horse_number = clean_text(
            row.get("horse_number")
            or row.get("number")
            or row.get("umaban")
        )

        if not horse_id and not horse_name:
            continue

        runners.append({
            "horse_id": horse_id,
            "horse_name": horse_name,
            "horse_number": horse_number,
        })

    return runners


def build_pedigree_map(pedigree_data):
    """
    pedigree.json の構造差に対応。
    """
    pedigree_map = {}

    if isinstance(pedigree_data, list):
        horses = pedigree_data

    elif isinstance(pedigree_data, dict):
        horses = pedigree_data.get(
            "horses",
            pedigree_data.get(
                "pedigrees",
                []
            )
        )
    else:
        horses = []

    for horse in horses:
        if not isinstance(horse, dict):
            continue

        horse_id = clean_text(
            horse.get("horse_id")
        )

        horse_name = clean_text(
            horse.get("horse_name")
        )

        key = horse_id or horse_name

        if key:
            pedigree_map[key] = horse

    return pedigree_map


def build_stats_map(stats_data):
    result = {}

    for row in stats_data.get(
        "ancestors",
        []
    ):
        key = clean_text(
            row.get("ancestor_key")
        )

        if key:
            result[key] = row

    return result


def get_horse_pedigree(
    runner,
    pedigree_map
):
    horse_id = runner["horse_id"]
    horse_name = runner["horse_name"]

    if horse_id in pedigree_map:
        return pedigree_map[horse_id]

    if horse_name in pedigree_map:
        return pedigree_map[horse_name]

    # ID/名前のどちらで格納されていても照合
    for pedigree in pedigree_map.values():
        if (
            horse_id
            and clean_text(
                pedigree.get("horse_id")
            ) == horse_id
        ):
            return pedigree

        if (
            horse_name
            and clean_text(
                pedigree.get("horse_name")
            ) == horse_name
        ):
            return pedigree

    return None


def generation_weight(generation):
    """
    近い世代ほど少し重くする。
    血統そのものを能力加点する目的ではなく、
    条件適性との接続強度として使用。
    """
    weights = {
        1: 1.00,
        2: 0.90,
        3: 0.80,
        4: 0.70,
        5: 0.60,
    }

    try:
        return weights.get(
            int(generation),
            0.60
        )
    except (TypeError, ValueError):
        return 0.60


def confidence_weight(starts):
    """
    出走母数が増えるほど信頼度を上げる。
    5頭程度の祖先が過大評価されないようにする。
    """
    if starts <= 0:
        return 0

    return min(
        1.0,
        math.sqrt(starts / 20.0)
    )


def score_one_ancestor(stat, generation):
    starts = int(
        stat.get("starts", 0)
    )

    if starts < MIN_STARTS:
        return None

    top3_over = float(
        stat.get(
            "top3_overperformance",
            0
        )
    )

    win_over = float(
        stat.get(
            "win_overperformance",
            0
        )
    )

    top3_rate = float(
        stat.get(
            "top3_rate",
            0
        )
    )

    # 過剰出現指数の暴走防止
    top3_over = min(
        top3_over,
        MAX_OVERPERFORMANCE
    )

    win_over = min(
        win_over,
        MAX_OVERPERFORMANCE
    )

    # 1.0を基準にプラス/マイナス化
    top3_signal = (
        top3_over - 1.0
    )

    win_signal = (
        win_over - 1.0
    )

    # 複勝側を主軸。
    raw_signal = (
        top3_signal * 0.75
        + win_signal * 0.25
    )

    gen_weight = generation_weight(
        generation
    )

    conf_weight = confidence_weight(
        starts
    )

    contribution = (
        raw_signal
        * gen_weight
        * conf_weight
    )

    return {
        "contribution": contribution,
        "starts": starts,
        "top3_rate": top3_rate,
        "top3_overperformance":
            top3_over,
        "win_overperformance":
            win_over,
        "generation_weight":
            gen_weight,
        "confidence_weight":
            conf_weight,
    }


def evaluate_horse(
    runner,
    pedigree,
    stats_map
):
    # 同一祖先のクロスで単純二重加点しない。
    # 最も近い世代を代表値として採用。
    unique_ancestors = {}

    for ancestor in pedigree.get(
        "ancestors",
        []
    ):
        ancestor_id = clean_text(
            ancestor.get("ancestor_id")
        )

        ancestor_name = clean_text(
            ancestor.get("ancestor_name")
        )

        if not ancestor_name:
            continue

        key = ancestor_key(
            ancestor_id,
            ancestor_name
        )

        try:
            generation = int(
                ancestor.get(
                    "generation",
                    5
                )
            )
        except (TypeError, ValueError):
            generation = 5

        if key not in unique_ancestors:
            unique_ancestors[key] = {
                "ancestor_id":
                    ancestor_id,
                "ancestor_name":
                    ancestor_name,
                "generation":
                    generation,
                "occurrences": 1,
            }
        else:
            unique_ancestors[key][
                "occurrences"
            ] += 1

            # より近い世代を代表にする
            if (
                generation
                < unique_ancestors[key][
                    "generation"
                ]
            ):
                unique_ancestors[key][
                    "generation"
                ] = generation

    matched = []

    positive = []
    negative = []

    total_score = 0.0

    for key, ancestor in (
        unique_ancestors.items()
    ):
        stat = stats_map.get(key)

        if stat is None:
            continue

        scored = score_one_ancestor(
            stat,
            ancestor["generation"]
        )

        if scored is None:
            continue

        contribution = scored[
            "contribution"
        ]

        total_score += contribution

        detail = {
            "ancestor_key": key,
            "ancestor_id":
                ancestor[
                    "ancestor_id"
                ],
            "ancestor_name":
                ancestor[
                    "ancestor_name"
                ],
            "generation":
                ancestor[
                    "generation"
                ],
            "occurrences":
                ancestor[
                    "occurrences"
                ],
            "starts":
                scored["starts"],
            "top3_rate":
                scored["top3_rate"],
            "top3_overperformance":
                scored[
                    "top3_overperformance"
                ],
            "win_overperformance":
                scored[
                    "win_overperformance"
                ],
            "contribution":
                round(
                    contribution,
                    6
                ),
        }

        matched.append(detail)

        if contribution > 0:
            positive.append(detail)
        elif contribution < 0:
            negative.append(detail)

    positive.sort(
        key=lambda x:
            x["contribution"],
        reverse=True,
    )

    negative.sort(
        key=lambda x:
            x["contribution"]
    )

    # 多数の祖先を持つこと自体で
    # 点数が膨らまないよう平均化。
    if matched:
        normalized_score = (
            total_score
            / math.sqrt(len(matched))
        )
    else:
        normalized_score = 0.0

    return {
        "horse_number":
            runner["horse_number"],
        "horse_id":
            runner["horse_id"],
        "horse_name":
            runner["horse_name"],

        "matched_ancestor_count":
            len(matched),

        "positive_ancestor_count":
            len(positive),

        "negative_ancestor_count":
            len(negative),

        "raw_score":
            round(
                total_score,
                6
            ),

        "bloodline_score":
            round(
                normalized_score,
                6
            ),

        # 上位根拠確認用
        "top_positive_ancestors":
            positive[:10],

        # マイナス根拠確認用
        "top_negative_ancestors":
            negative[:10],
    }


def main():
    race_data = load_json(
        RACE_FILE
    )

    pedigree_data = load_json(
        PEDIGREE_FILE
    )

    stats_data = load_json(
        STATS_FILE
    )

    runners = extract_runners(
        race_data
    )

    pedigree_map = build_pedigree_map(
        pedigree_data
    )

    stats_map = build_stats_map(
        stats_data
    )

    results = []
    missing_pedigree = []

    for runner in runners:
        pedigree = get_horse_pedigree(
            runner,
            pedigree_map
        )

        if pedigree is None:
            missing_pedigree.append(
                runner
            )
            continue

        results.append(
            evaluate_horse(
                runner,
                pedigree,
                stats_map
            )
        )

    results.sort(
        key=lambda x:
            x["bloodline_score"],
        reverse=True,
    )

    for index, row in enumerate(
        results,
        start=1
    ):
        row["bloodline_rank"] = index

    output = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "condition":
            stats_data.get(
                "condition",
                {}
            ),

        "method": {
            "minimum_ancestor_starts":
                MIN_STARTS,
            "maximum_overperformance":
                MAX_OVERPERFORMANCE,
            "primary_signal":
                "top3_overperformance",
            "note":
                "血統単独の能力評価ではなく、今回条件への適性接続用スコア"
        },

        "summary": {
            "runner_count":
                len(runners),

            "scored_runner_count":
                len(results),

            "missing_pedigree_count":
                len(missing_pedigree),

            "historical_race_count":
                stats_data.get(
                    "summary",
                    {}
                ).get(
                    "race_count",
                    0
                ),

            "historical_start_records":
                stats_data.get(
                    "summary",
                    {}
                ).get(
                    "total_start_records",
                    0
                ),
        },

        "missing_pedigree":
            missing_pedigree,

        "ranking":
            results,
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
            indent=2
        )

    print(
        "========================"
    )
    print(
        "出走馬:",
        len(runners)
    )
    print(
        "採点成功:",
        len(results)
    )
    print(
        "血統未照合:",
        len(missing_pedigree)
    )
    print(
        "過去レース:",
        output[
            "summary"
        ][
            "historical_race_count"
        ]
    )
    print(
        "過去出走:",
        output[
            "summary"
        ][
            "historical_start_records"
        ]
    )

    print(
        "----- 血統ランキング -----"
    )

    for row in results:
        print(
            row["bloodline_rank"],
            row["horse_number"],
            row["horse_name"],
            row["bloodline_score"],
            "該当祖先",
            row[
                "matched_ancestor_count"
            ]
        )

    print(
        OUTPUT_FILE,
        "作成完了"
    )


if __name__ == "__main__":
    main()
