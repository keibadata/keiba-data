import json
import re
from datetime import datetime, timezone, timedelta


INPUT_FILE = "runner_history.json"
RACE_FILE = "race.json"
OUTPUT_FILE = "previous_race_analysis.json"


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def load_json(filename):
    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)
    except Exception:
        return {}


def txt(v):
    if v is None:
        return ""
    return str(v).strip()


def num(v):
    s = txt(v)

    m = re.search(
        r"-?\d+(?:\.\d+)?",
        s
    )

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def rank_num(v):
    s = txt(v)

    if not re.fullmatch(
        r"\d+",
        s
    ):
        return None

    try:
        return int(s)
    except Exception:
        return None


def distance_num(v):
    x = num(v)

    if x is None:
        return None

    if 800 <= x <= 4000:
        return int(x)

    return None


def passing_positions(v):
    return [
        int(x)
        for x in re.findall(
            r"\d+",
            txt(v)
        )
    ]


def extract_weight(v):
    x = num(v)

    if x is None:
        return None

    if 250 <= x <= 700:
        return int(x)

    return None


# =========================================================
# 今回条件
#
# 固定値禁止。
# race.json を唯一の基準にする。
# =========================================================

race = load_json(
    RACE_FILE
)

TARGET_RACE_ID = txt(
    race.get("race_id")
)

TARGET_SURFACE = txt(
    race.get("surface")
)

TARGET_DISTANCE = distance_num(
    race.get("distance")
)

TARGET_TRACK = txt(
    race.get("racecourse")
    or race.get("track")
)


if not TARGET_RACE_ID:
    raise SystemExit(
        "ERROR: race.json race_id missing"
    )

if not TARGET_SURFACE:
    raise SystemExit(
        "ERROR: race.json surface missing"
    )

if TARGET_DISTANCE is None:
    raise SystemExit(
        "ERROR: race.json distance missing"
    )


# =========================================================
# runner_historyとのrace_id整合確認
# =========================================================

source = load_json(
    INPUT_FILE
)

SOURCE_RACE_ID = txt(
    source.get("target_race_id")
)

if SOURCE_RACE_ID != TARGET_RACE_ID:
    raise SystemExit(
        "ERROR: runner_history race mismatch"
    )

if source.get("future_race_usage") is not False:
    raise SystemExit(
        "ERROR: runner_history future leak"
    )

if source.get("leak_check_passed") is not True:
    raise SystemExit(
        "ERROR: runner_history leak check failed"
    )


def normalize_surface(value):
    value = txt(value)

    if value.startswith("芝"):
        return "芝"

    if (
        value.startswith("ダ")
        or "ダート" in value
    ):
        return "ダート"

    if value.startswith("障"):
        return "障害"

    return value


TARGET_SURFACE_NORMALIZED = normalize_surface(
    TARGET_SURFACE
)


def analyze_previous_race(race_row):

    rank = rank_num(
        race_row.get("rank")
    )

    surface = normalize_surface(
        race_row.get("surface")
    )

    distance = distance_num(
        race_row.get("distance")
    )

    track = txt(
        race_row.get("track_condition")
    )

    last3f = num(
        race_row.get("last3f")
    )

    margin = num(
        race_row.get("margin")
    )

    passing_raw = txt(
        race_row.get("passing")
    )

    positions = passing_positions(
        passing_raw
    )

    first_position = (
        positions[0]
        if positions
        else None
    )

    final_position = (
        positions[-1]
        if positions
        else None
    )

    horse_weight = extract_weight(
        race_row.get("horse_weight")
    )

    issues = []
    positives = []
    unknowns = []

    # =====================================================
    # 今回条件との接続
    # =====================================================

    same_surface = (
        surface
        == TARGET_SURFACE_NORMALIZED
    )

    same_distance = (
        distance
        == TARGET_DISTANCE
    )

    if same_surface:
        positives.append(
            "今回と同じ馬場種別"
        )

    elif surface:
        issues.append(
            "前走は今回と異なる馬場種別"
        )

    else:
        unknowns.append(
            "前走の芝ダート不明"
        )

    if same_distance:
        positives.append(
            f"今回と同じ{TARGET_DISTANCE}m"
        )

    elif distance is not None:

        diff = (
            distance
            - TARGET_DISTANCE
        )

        if abs(diff) <= 200:
            positives.append(
                "前走距離は今回条件に近い"
            )

        elif diff > 0:
            # 前走距離 > 今回距離
            issues.append(
                "前走から距離短縮"
            )

        else:
            # 前走距離 < 今回距離
            issues.append(
                "前走から距離延長"
            )

    else:
        unknowns.append(
            "前走距離不明"
        )

    # =====================================================
    # 着順
    #
    # 着順単独で能力判定しない。
    # =====================================================

    if rank is None:
        unknowns.append(
            "前走着順を数値評価できない"
        )

    elif rank == 1:
        positives.append(
            "前走勝利"
        )

        # 勝っていても課題を探す
        if (
            final_position is not None
            and final_position >= 8
        ):
            issues.append(
                "勝利したが後方依存"
            )

    elif rank <= 3:
        positives.append(
            "前走3着以内"
        )

    # =====================================================
    # 通過順
    # =====================================================

    if final_position is None:
        unknowns.append(
            "前走位置取り不明"
        )

    else:

        if final_position <= 3:
            positives.append(
                "前走は前方位置"
            )

        elif final_position >= 10:
            issues.append(
                "後方位置依存"
            )

        elif final_position >= 7:
            issues.append(
                "やや後方からの競馬"
            )

    # =====================================================
    # レース中の位置変化
    # =====================================================

    position_change = None

    if (
        first_position is not None
        and final_position is not None
    ):

        position_change = (
            first_position
            - final_position
        )

        if position_change >= 3:
            positives.append(
                "道中から位置を押し上げた"
            )

        elif position_change <= -3:
            issues.append(
                "道中で位置を下げた"
            )

    # =====================================================
    # 上がり
    #
    # 絶対時計は補助情報のみ。
    # 能力を単独決定しない。
    # =====================================================

    if last3f is None:
        unknowns.append(
            "前走上がり不明"
        )

    else:

        if last3f <= 34.0:
            positives.append(
                "速い上がりを記録"
            )

        elif last3f <= 35.0:
            positives.append(
                "上がりは一定水準"
            )

        elif last3f >= 37.0:
            issues.append(
                "前走上がり時計は遅め"
            )

    # =====================================================
    # 着差
    #
    # 着順単独評価ではなく、
    # 内容確認の補助材料。
    # =====================================================

    if margin is not None:

        if (
            rank is not None
            and rank > 1
        ):

            if margin <= 0.3:
                positives.append(
                    "着差は小さい"
                )

            elif margin >= 1.0:
                issues.append(
                    "着差が大きい"
                )

    # =====================================================
    # 課題克服候補
    #
    # 重要:
    # 「条件変更がある」だけで
    # 克服済みとは判定しない。
    #
    # ここでは確認材料として保持する。
    # =====================================================

    overcoming = []

    if (
        "前走から距離短縮"
        in issues
    ):
        overcoming.append(
            "距離短縮による追走・折合い変化を確認"
        )

    if (
        "前走から距離延長"
        in issues
    ):
        overcoming.append(
            "距離延長による追走負荷・持続力適性を確認"
        )

    if (
        "後方位置依存"
        in issues
        or
        "やや後方からの競馬"
        in issues
    ):
        overcoming.append(
            "今回の位置取り改善材料を確認"
        )

    if (
        "前走は今回と異なる馬場種別"
        in issues
    ):
        overcoming.append(
            "馬場種別変更への適応材料を確認"
        )

    # =====================================================
    # サマリー
    # =====================================================

    if not issues:
        issue_status = (
            "明確な課題なし"
        )
    else:
        issue_status = " / ".join(
            issues
        )

    if not positives:
        positive_status = (
            "明確なプラス材料なし"
        )
    else:
        positive_status = " / ".join(
            positives
        )

    if not overcoming:
        overcoming_status = (
            "客観データ上の明確な克服材料なし"
        )
    else:
        overcoming_status = " / ".join(
            overcoming
        )

    return {
        "race_id":
            txt(
                race_row.get("race_id")
            ),

        "date":
            txt(
                race_row.get("date")
            ),

        "meeting":
            txt(
                race_row.get("meeting")
            ),

        "race_name":
            txt(
                race_row.get("race_name")
            ),

        "rank":
            rank,

        "surface":
            surface,

        "distance":
            distance,

        "track_condition":
            track,

        "time":
            txt(
                race_row.get("time")
            ),

        "margin":
            txt(
                race_row.get("margin")
            ),

        "passing":
            passing_raw,

        "first_position":
            first_position,

        "final_position":
            final_position,

        "position_change":
            position_change,

        "last3f":
            last3f,

        "horse_weight":
            horse_weight,

        "same_surface":
            same_surface,

        "same_distance":
            same_distance,

        "positives":
            positives,

        "issues":
            issues,

        "unknowns":
            unknowns,

        "overcoming_materials":
            overcoming,

        "positive_summary":
            positive_status,

        "issue_summary":
            issue_status,

        "overcoming_summary":
            overcoming_status,
    }


def analyze_horse(horse):

    races = (
        horse.get(
            "past_races",
            []
        )
        or []
    )

    if not races:

        return {
            "horse_id":
                txt(
                    horse.get(
                        "horse_id"
                    )
                ),

            "horse_number":
                txt(
                    horse.get(
                        "horse_number"
                    )
                ),

            "horse_name":
                txt(
                    horse.get(
                        "horse_name"
                    )
                ),

            "previous_race_available":
                False,

            "previous_race":
                None,

            "previous_race_summary":
                "前走データなし",

            "positive_summary":
                "不明",

            "issue_summary":
                "不明",

            "overcoming_summary":
                "不明",

            "unknowns":
                [
                    "前走データなし"
                ],

            "unknown_is_penalized":
                False,
        }

    # runner_history は新しい順
    previous = races[0]

    analysis = analyze_previous_race(
        previous
    )

    summary_parts = []

    if analysis["rank"] is not None:
        summary_parts.append(
            "前走"
            + str(
                analysis["rank"]
            )
            + "着"
        )

    if analysis["surface"]:
        summary_parts.append(
            analysis["surface"]
        )

    if analysis["distance"]:
        summary_parts.append(
            str(
                analysis["distance"]
            )
            + "m"
        )

    if analysis["passing"]:
        summary_parts.append(
            "通過"
            + analysis["passing"]
        )

    if analysis["last3f"] is not None:
        summary_parts.append(
            "上がり"
            + str(
                analysis["last3f"]
            )
        )

    return {
        "horse_id":
            txt(
                horse.get(
                    "horse_id"
                )
            ),

        "horse_number":
            txt(
                horse.get(
                    "horse_number"
                )
            ),

        "horse_name":
            txt(
                horse.get(
                    "horse_name"
                )
            ),

        "previous_race_available":
            True,

        "previous_race":
            analysis,

        "previous_race_summary":
            " / ".join(
                summary_parts
            ),

        "positive_summary":
            analysis[
                "positive_summary"
            ],

        "issue_summary":
            analysis[
                "issue_summary"
            ],

        "overcoming_summary":
            analysis[
                "overcoming_summary"
            ],

        "unknowns":
            analysis[
                "unknowns"
            ],

        "unknown_is_penalized":
            False,
    }


def horse_number_key(horse):

    try:
        return int(
            horse[
                "horse_number"
            ]
        )
    except Exception:
        return 999


def main():

    horses = source.get(
        "horses",
        []
    )

    results = [
        analyze_horse(
            horse
        )
        for horse in horses
    ]

    results.sort(
        key=horse_number_key
    )

    output = {
        "updated_at":
            now_jst(),

        "source":
            INPUT_FILE,

        "source_race_file":
            RACE_FILE,

        "target_race_id":
            TARGET_RACE_ID,

        "target_condition": {
            "racecourse":
                TARGET_TRACK,

            "surface":
                TARGET_SURFACE_NORMALIZED,

            "distance":
                TARGET_DISTANCE,
        },

        "future_race_usage":
            False,

        "leak_check_passed":
            True,

        "rules": {
            "target_condition_from_race_json":
                True,

            "fixed_target_distance_prohibited":
                True,

            "finish_position_alone_is_not_ability":
                True,

            "winner_still_checked_for_issues":
                True,

            "unknown_is_not_penalized":
                True,

            "last3f_is_supporting_signal":
                True,

            "popularity_not_used":
                True,

            "condition_change_is_not_automatic_resolution":
                True,
        },

        "summary": {
            "horse_count":
                len(results),

            "previous_race_available_count":
                sum(
                    1
                    for x in results
                    if x[
                        "previous_race_available"
                    ]
                ),
        },

        "horses":
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
        "===== Previous Race Analysis ====="
    )

    print(
        "target race:",
        TARGET_RACE_ID
    )

    print(
        "target condition:",
        TARGET_TRACK,
        TARGET_SURFACE_NORMALIZED,
        TARGET_DISTANCE
    )

    print(
        "horses:",
        len(results)
    )

    print(
        "previous race available:",
        output[
            "summary"
        ][
            "previous_race_available_count"
        ]
    )

    for horse in results:

        print(
            horse[
                "horse_number"
            ],
            horse[
                "horse_name"
            ],
            horse[
                "previous_race_summary"
            ],
            "| 課題:",
            horse[
                "issue_summary"
            ]
        )


if __name__ == "__main__":
    main()
