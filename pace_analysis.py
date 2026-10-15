import json
import re
from datetime import datetime, timezone, timedelta

INPUT_FILE = "runner_history.json"
OUTPUT_FILE = "pace_analysis.json"


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def text(value):
    if value is None:
        return ""
    return str(value).strip()


def passing_positions(value):
    return [
        int(x)
        for x in re.findall(
            r"\d+",
            text(value)
        )
    ]


def classify_position(position):
    if position is None:
        return "不明"

    if position == 1:
        return "逃げ"

    if position <= 4:
        return "先行"

    if position <= 8:
        return "中団"

    return "後方"


def analyze_horse(horse):

    races = horse.get("past_races", [])

    usable = []

    for race in races:

        positions = passing_positions(
            race.get("passing")
        )

        if not positions:
            continue

        first = positions[0]
        final = positions[-1]

        usable.append({
            "date": text(race.get("date")),
            "race_name": text(
                race.get("race_name")
            ),
            "passing": text(
                race.get("passing")
            ),
            "first_position": first,
            "final_position": final,
            "style": classify_position(
                final
            )
        })

    if not usable:

        return {
            "horse_id":
                text(horse.get("horse_id")),

            "horse_number":
                text(horse.get("horse_number")),

            "horse_name":
                text(horse.get("horse_name")),

            "usable_race_count": 0,

            "running_style": "不明",

            "front_rate": None,
            "escape_rate": None,
            "back_rate": None,

            "likely_leader": False,

            "pace_dependency":
                "不明",

            "high_pace":
                "不明",

            "middle_pace":
                "不明",

            "slow_pace":
                "不明",

            "noise_flag":
                "未知数・減点しない",

            "race_details": []
        }

    count = len(usable)

    escape_count = sum(
        1
        for x in usable
        if x["final_position"] == 1
    )

    front_count = sum(
        1
        for x in usable
        if x["final_position"] <= 4
    )

    back_count = sum(
        1
        for x in usable
        if x["final_position"] >= 9
    )

    average_final_position = (
        sum(
            x["final_position"]
            for x in usable
        )
        / count
    )

    escape_rate = (
        escape_count / count
    )

    front_rate = (
        front_count / count
    )

    back_rate = (
        back_count / count
    )

    # ----------------------------
    # 基本脚質
    # ----------------------------

    if escape_rate >= 0.5:
        running_style = "逃げ"

    elif front_rate >= 0.6:
        running_style = "先行"

    elif back_rate >= 0.5:
        running_style = "後方"

    elif average_final_position <= 6:
        running_style = "中団前"

    else:
        running_style = "中団後"


    # ----------------------------
    # ハナ候補
    #
    # 単に前走逃げただけでは
    # ハナ候補確定にしない。
    # ----------------------------

    likely_leader = (
        escape_count >= 2
        or
        (
            escape_count >= 1
            and escape_rate >= 0.5
        )
    )


    # ----------------------------
    # 展開依存度
    # ----------------------------

    if back_rate >= 0.67:

        pace_dependency = (
            "前崩れ依存度高め"
        )

    elif escape_rate >= 0.67:

        pace_dependency = (
            "逃げ成立への依存度高め"
        )

    elif front_rate >= 0.67:

        pace_dependency = (
            "前目の位置を取れるかが重要"
        )

    else:

        pace_dependency = (
            "位置取りの自由度あり"
        )


    # ----------------------------
    # ペース別評価
    #
    # ここでは能力点を直接変更しない。
    # 脚質構成による適合度だけ作る。
    # ----------------------------

    if running_style == "逃げ":

        slow_pace = "プラス"
        middle_pace = "標準"
        high_pace = "注意"

    elif running_style == "先行":

        slow_pace = "プラス"
        middle_pace = "プラス"
        high_pace = "標準"

    elif running_style == "中団前":

        slow_pace = "標準"
        middle_pace = "プラス"
        high_pace = "プラス"

    elif running_style == "中団後":

        slow_pace = "注意"
        middle_pace = "標準"
        high_pace = "プラス"

    elif running_style == "後方":

        slow_pace = "注意"
        middle_pace = "標準"
        high_pace = "プラス"

    else:

        slow_pace = "不明"
        middle_pace = "不明"
        high_pace = "不明"


    return {
        "horse_id":
            text(horse.get("horse_id")),

        "horse_number":
            text(horse.get("horse_number")),

        "horse_name":
            text(horse.get("horse_name")),

        "usable_race_count":
            count,

        "running_style":
            running_style,

        "average_final_position":
            round(
                average_final_position,
                2
            ),

        "escape_count":
            escape_count,

        "escape_rate":
            round(
                escape_rate,
                3
            ),

        "front_count":
            front_count,

        "front_rate":
            round(
                front_rate,
                3
            ),

        "back_count":
            back_count,

        "back_rate":
            round(
                back_rate,
                3
            ),

        "likely_leader":
            likely_leader,

        "pace_dependency":
            pace_dependency,

        "slow_pace":
            slow_pace,

        "middle_pace":
            middle_pace,

        "high_pace":
            high_pace,

        "noise_flag":
            "",

        "race_details":
            usable
    }


def build_race_scenario(horses):

    leaders = [
        x
        for x in horses
        if x["likely_leader"]
    ]

    front_horses = [
        x
        for x in horses
        if x["running_style"]
        in ("逃げ", "先行")
    ]

    leader_count = len(leaders)
    front_count = len(front_horses)

    # ----------------------------
    # 基本ペース想定
    # ----------------------------

    if leader_count >= 3:

        base_pace = "ハイ"

        reason = (
            "明確な逃げ候補が3頭以上。"
            "ハナ争い激化の可能性"
        )

    elif leader_count == 2:

        base_pace = "ミドル〜ハイ"

        reason = (
            "逃げ候補2頭。"
            "競り合えばハイまで上昇"
        )

    elif (
        leader_count == 1
        and front_count <= 4
    ):

        base_pace = "スロー〜ミドル"

        reason = (
            "逃げ候補1頭で"
            "単騎逃げの可能性"
        )

    elif front_count >= 7:

        base_pace = "ミドル〜ハイ"

        reason = (
            "先行候補が多く"
            "序盤の位置取り争いが強い"
        )

    else:

        base_pace = "ミドル"

        reason = (
            "逃げ・先行構成に"
            "極端な偏りなし"
        )


    return {
        "base_pace":
            base_pace,

        "reason":
            reason,

        "leader_candidate_count":
            leader_count,

        "front_candidate_count":
            front_count,

        "leader_candidates": [
            {
                "horse_number":
                    x["horse_number"],

                "horse_name":
                    x["horse_name"]
            }
            for x in leaders
        ],

        # 決め打ちしない
        "scenario_slow":
            "逃げ馬が主張せず隊列が早期に決まる",

        "scenario_middle":
            "標準的な先行争い",

        "scenario_high":
            "複数馬がハナ・好位を主張し前半加速",

        "front_collapse_scenario":
            "ハイペース化した場合は前潰れまで考慮"
    }


def main():

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:
        source = json.load(f)

    source_horses = source.get(
        "horses",
        []
    )

    horses = [
        analyze_horse(horse)
        for horse in source_horses
    ]

    horses.sort(
        key=lambda x:
        int(x["horse_number"])
        if x["horse_number"].isdigit()
        else 999
    )

    race_scenario = (
        build_race_scenario(horses)
    )

    output = {
        "updated_at":
            now_jst(),

        "source":
            INPUT_FILE,

        "rules": {
            "multiple_races_used":
                True,

            "escape_checked":
                True,

            "leader_battle_checked":
                True,

            "slow_middle_high_all_kept":
                True,

            "front_collapse_kept":
                True,

            "unknown_not_penalized":
                True,

            "pace_not_scored_as_independent_ability":
                True
        },

        "summary": {
            "horse_count":
                len(horses),

            "usable_horse_count":
                sum(
                    1
                    for x in horses
                    if x[
                        "usable_race_count"
                    ] > 0
                )
        },

        "race_scenario":
            race_scenario,

        "horses":
            horses
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

    print("===== Pace Analysis =====")
    print(
        "horses:",
        len(horses)
    )

    print(
        "base pace:",
        race_scenario[
            "base_pace"
        ]
    )

    print(
        "leaders:",
        race_scenario[
            "leader_candidate_count"
        ]
    )

    for horse in horses:
        print(
            horse["horse_number"],
            horse["horse_name"],
            horse["running_style"],
            "| 逃げ率",
            horse["escape_rate"],
            "| 先行率",
            horse["front_rate"],
            "|",
            horse["pace_dependency"]
        )


if __name__ == "__main__":
    main()
