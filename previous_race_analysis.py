import json
import re
from datetime import datetime, timezone, timedelta

INPUT_FILE = "runner_history.json"
OUTPUT_FILE = "previous_race_analysis.json"

TARGET_SURFACE = "芝"
TARGET_DISTANCE = 1400


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


def txt(v):
    if v is None:
        return ""
    return str(v).strip()


def num(v):
    s = txt(v)
    m = re.search(r"-?\d+(?:\.\d+)?", s)

    if not m:
        return None

    try:
        return float(m.group())
    except Exception:
        return None


def rank_num(v):
    s = txt(v)

    if not re.fullmatch(r"\d+", s):
        return None

    return int(s)


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
        for x in re.findall(r"\d+", txt(v))
    ]


def extract_weight(v):
    x = num(v)

    if x is None:
        return None

    if 250 <= x <= 700:
        return int(x)

    return None


def analyze_previous_race(race):

    rank = rank_num(race.get("rank"))
    surface = txt(race.get("surface"))
    distance = distance_num(race.get("distance"))
    track = txt(race.get("track_condition"))

    last3f = num(race.get("last3f"))
    margin = num(race.get("margin"))

    passing_raw = txt(race.get("passing"))
    positions = passing_positions(passing_raw)

    first_position = (
        positions[0]
        if positions else None
    )

    final_position = (
        positions[-1]
        if positions else None
    )

    horse_weight = extract_weight(
        race.get("horse_weight")
    )

    issues = []
    positives = []
    unknowns = []

    # -----------------------------
    # 今回条件との接続
    # -----------------------------

    same_surface = (
        surface == TARGET_SURFACE
    )

    same_distance = (
        distance == TARGET_DISTANCE
    )

    if same_surface:
        positives.append("今回と同じ芝")
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
            "今回と同じ1400m"
        )
    elif distance is not None:

        diff = distance - TARGET_DISTANCE

        if abs(diff) <= 200:
            positives.append(
                "前走距離は今回条件に近い"
            )
        elif diff > 0:
            issues.append(
                "前走から距離短縮"
            )
        else:
            issues.append(
                "前走から距離延長"
            )

    else:
        unknowns.append(
            "前走距離不明"
        )

    # -----------------------------
    # 着順
    # 単独では能力判定しない
    # -----------------------------

    if rank is None:
        unknowns.append(
            "前走着順を数値評価できない"
        )

    elif rank == 1:
        positives.append(
            "前走勝利"
        )

        # 勝っていても課題探索
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

    # -----------------------------
    # 通過順
    # -----------------------------

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

    # -----------------------------
    # レース中の位置変化
    # -----------------------------

    position_change = None

    if (
        first_position is not None
        and final_position is not None
    ):

        position_change = (
            first_position -
            final_position
        )

        if position_change >= 3:
            positives.append(
                "道中から位置を押し上げた"
            )

        elif position_change <= -3:
            issues.append(
                "道中で位置を下げた"
            )

    # -----------------------------
    # 上がり
    # 絶対時計だけで能力決定しない
    # -----------------------------

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

    # -----------------------------
    # 着差
    # 数値化できる場合だけ使用
    # -----------------------------

    if margin is not None:

        if rank is not None and rank > 1:

            if margin <= 0.3:
                positives.append(
                    "着差は小さい"
                )

            elif margin >= 1.0:
                issues.append(
                    "着差が大きい"
                )

    # -----------------------------
    # 課題克服候補
    # 今回条件変更から機械判定
    # -----------------------------

    overcoming = []

    if (
        "前走から距離短縮" in issues
    ):
        overcoming.append(
            "距離短縮が追走面の改善につながるか確認"
        )

    if (
        "前走から距離延長" in issues
    ):
        overcoming.append(
            "距離延長で追走負荷が軽減する可能性"
        )

    if (
        "後方位置依存" in issues
        or
        "やや後方からの競馬" in issues
    ):
        overcoming.append(
            "今回の位置取り改善が課題"
        )

    if (
        "前走は今回と異なる馬場種別"
        in issues
    ):
        overcoming.append(
            "芝替わりへの適応確認が必要"
        )

    # 不明はマイナスにしない
    if not issues:
        issue_status = "明確な課題なし"
    else:
        issue_status = " / ".join(issues)

    if not positives:
        positive_status = "明確なプラス材料なし"
    else:
        positive_status = " / ".join(positives)

    if not overcoming:
        overcoming_status = (
            "客観データ上の明確な克服材料なし"
        )
    else:
        overcoming_status = " / ".join(
            overcoming
        )

    return {
        "date": txt(race.get("date")),
        "meeting": txt(race.get("meeting")),
        "race_name": txt(race.get("race_name")),

        "rank": rank,
        "surface": surface,
        "distance": distance,
        "track_condition": track,

        "time": txt(race.get("time")),
        "margin": txt(race.get("margin")),

        "passing": passing_raw,
        "first_position": first_position,
        "final_position": final_position,
        "position_change": position_change,

        "last3f": last3f,
        "horse_weight": horse_weight,

        "same_surface": same_surface,
        "same_distance": same_distance,

        "positives": positives,
        "issues": issues,

        "unknowns": unknowns,

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

    races = horse.get(
        "past_races",
        []
    )

    if not races:

        return {
            "horse_id":
                txt(horse.get("horse_id")),

            "horse_number":
                txt(horse.get("horse_number")),

            "horse_name":
                txt(horse.get("horse_name")),

            "previous_race_available":
                False,

            "previous_race":
                None,

            "previous_race_summary":
                "前走データなし",

            "issue_summary":
                "不明",

            "overcoming_summary":
                "不明",

            "unknown_is_penalized":
                False,
        }

    # runner_historyは新しい順
    previous = races[0]

    analysis = analyze_previous_race(
        previous
    )

    summary_parts = []

    if analysis["rank"] is not None:
        summary_parts.append(
            "前走" +
            str(analysis["rank"]) +
            "着"
        )

    if analysis["surface"]:
        summary_parts.append(
            analysis["surface"]
        )

    if analysis["distance"]:
        summary_parts.append(
            str(analysis["distance"]) +
            "m"
        )

    if analysis["passing"]:
        summary_parts.append(
            "通過" +
            analysis["passing"]
        )

    if analysis["last3f"] is not None:
        summary_parts.append(
            "上がり" +
            str(analysis["last3f"])
        )

    return {
        "horse_id":
            txt(horse.get("horse_id")),

        "horse_number":
            txt(horse.get("horse_number")),

        "horse_name":
            txt(horse.get("horse_name")),

        "previous_race_available":
            True,

        "previous_race":
            analysis,

        "previous_race_summary":
            " / ".join(summary_parts),

        "positive_summary":
            analysis["positive_summary"],

        "issue_summary":
            analysis["issue_summary"],

        "overcoming_summary":
            analysis[
                "overcoming_summary"
            ],

        "unknowns":
            analysis["unknowns"],

        "unknown_is_penalized":
            False,
    }


def main():

    with open(
        INPUT_FILE,
        "r",
        encoding="utf-8"
    ) as f:

        source = json.load(f)

    horses = source.get(
        "horses",
        []
    )

    results = [
        analyze_horse(horse)
        for horse in horses
    ]

    def horse_number_key(horse):

        try:
            return int(
                horse["horse_number"]
            )
        except Exception:
            return 999

    results.sort(
        key=horse_number_key
    )

    output = {

        "updated_at":
            now_jst(),

        "source":
            INPUT_FILE,

        "target_condition": {
            "surface":
                TARGET_SURFACE,

            "distance":
                TARGET_DISTANCE,
        },

        "rules": {
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
        "horses:",
        len(results)
    )

    print(
        "previous race available:",
        output["summary"][
            "previous_race_available_count"
        ]
    )

    for horse in results:

        print(
            horse["horse_number"],
            horse["horse_name"],
            horse["previous_race_summary"],
            "| 課題:",
            horse["issue_summary"]
        )


if __name__ == "__main__":
    main()
