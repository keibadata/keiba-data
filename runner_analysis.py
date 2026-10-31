import json
import re
from datetime import datetime, timezone, timedelta


INPUT_FILE = "runner_history.json"
RACE_FILE = "race.json"
OUTPUT_FILE = "runner_analysis.json"


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


def text(v):
    if v is None:
        return ""
    return str(v).strip()


def number(v):
    s = text(v)

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


def rank_number(v):
    s = text(v)

    if not re.fullmatch(
        r"\d+",
        s
    ):
        return None

    try:
        return int(s)
    except Exception:
        return None


def parse_last3f(v):
    x = number(v)

    if x is None:
        return None

    if 25 <= x <= 50:
        return x

    return None


def parse_distance(v):
    x = number(v)

    if x is None:
        return None

    if 800 <= x <= 4000:
        return int(x)

    return None


def parse_margin(v):
    s = text(v)

    if not s:
        return None

    try:
        return float(s)
    except Exception:
        return None


def passing_position(v):
    s = text(v)

    nums = re.findall(
        r"\d+",
        s
    )

    if not nums:
        return None

    try:
        return int(nums[-1])
    except Exception:
        return None


# =========================================================
# 今回条件
# race.jsonを唯一の基準にする
# =========================================================

race = load_json(
    RACE_FILE
)

TARGET_RACE_ID = text(
    race.get("race_id")
)

TARGET_SURFACE = text(
    race.get("surface")
)

TARGET_DISTANCE = parse_distance(
    race.get("distance")
)

TARGET_TRACK = text(
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


def surface_match(race_row):
    return (
        text(
            race_row.get("surface")
        )
        == TARGET_SURFACE
    )


def distance_score(distance):
    """
    今回距離への近似度。

    距離そのものを能力評価にはしない。
    今回条件との接続度として使用。
    """

    if distance is None:
        return 0.0

    diff = abs(
        distance
        - TARGET_DISTANCE
    )

    if diff == 0:
        return 1.0

    if diff <= 200:
        return 0.75

    if diff <= 400:
        return 0.45

    if diff <= 600:
        return 0.20

    return 0.0


def finish_score(rank):
    """
    着順単独では能力を決めない。
    複合評価の一要素として使用。
    """

    if rank is None:
        return 0.0

    table = {
        1: 1.00,
        2: 0.88,
        3: 0.78,
        4: 0.67,
        5: 0.58,
        6: 0.48,
        7: 0.39,
        8: 0.31,
        9: 0.24,
        10: 0.18,
    }

    return table.get(
        rank,
        0.10
    )


def last3f_score(last3f):
    """
    上がり絶対値だけで能力を決めない。
    補助評価として使用。
    """

    if last3f is None:
        return 0.50

    if last3f <= 33.5:
        return 1.00

    if last3f <= 34.0:
        return 0.92

    if last3f <= 34.5:
        return 0.84

    if last3f <= 35.0:
        return 0.74

    if last3f <= 35.5:
        return 0.64

    if last3f <= 36.0:
        return 0.55

    if last3f <= 37.0:
        return 0.45

    return 0.35


def position_score(position):
    """
    脚質自体を優劣化しない。

    極端な後方依存のみ、
    発揮率リスク確認用として扱う。
    """

    if position is None:
        return 0.50

    if position <= 3:
        return 0.72

    if position <= 6:
        return 0.68

    if position <= 9:
        return 0.58

    return 0.48


def recency_weights(n):
    base = [
        1.00,
        0.82,
        0.67,
        0.55,
        0.45,
    ]

    result = []

    for i in range(n):
        if i < len(base):
            result.append(
                base[i]
            )
        else:
            result.append(
                0.35
            )

    return result


def analyze_race(race_row):
    rank = rank_number(
        race_row.get("rank")
    )

    distance = parse_distance(
        race_row.get("distance")
    )

    last3f = parse_last3f(
        race_row.get("last3f")
    )

    position = passing_position(
        race_row.get("passing")
    )

    margin = parse_margin(
        race_row.get("margin")
    )

    same_surface = surface_match(
        race_row
    )

    d_score = distance_score(
        distance
    )

    f_score = finish_score(
        rank
    )

    l_score = last3f_score(
        last3f
    )

    p_score = position_score(
        position
    )

    # ---------------------------------
    # 能力評価
    #
    # 距離適性は能力そのものではないので
    # 以前よりウェイトを下げる。
    # ---------------------------------

    performance = (
        f_score * 0.60
        + l_score * 0.25
        + p_score * 0.15
    )

    # ---------------------------------
    # 今回条件適性
    # ---------------------------------

    condition = 0.0

    if same_surface:
        condition += 0.55

    condition += (
        d_score * 0.45
    )

    return {
        "race_id":
            text(
                race_row.get(
                    "race_id"
                )
            ),

        "date":
            text(
                race_row.get(
                    "date"
                )
            ),

        "meeting":
            text(
                race_row.get(
                    "meeting"
                )
            ),

        "race_name":
            text(
                race_row.get(
                    "race_name"
                )
            ),

        "rank":
            rank,

        "surface":
            text(
                race_row.get(
                    "surface"
                )
            ),

        "distance":
            distance,

        "track_condition":
            text(
                race_row.get(
                    "track_condition"
                )
            ),

        "time":
            text(
                race_row.get(
                    "time"
                )
            ),

        "margin":
            text(
                race_row.get(
                    "margin"
                )
            ),

        "passing":
            text(
                race_row.get(
                    "passing"
                )
            ),

        "last3f":
            last3f,

        "horse_weight":
            text(
                race_row.get(
                    "horse_weight"
                )
            ),

        "same_surface":
            same_surface,

        "distance_fit":
            round(
                d_score,
                4
            ),

        "finish_score":
            round(
                f_score,
                4
            ),

        "last3f_score":
            round(
                l_score,
                4
            ),

        "position_score":
            round(
                p_score,
                4
            ),

        "performance_score":
            round(
                performance,
                4
            ),

        "condition_score":
            round(
                condition,
                4
            ),
    }


def weighted_average(
    values,
    weights
):
    valid = [
        (v, w)
        for v, w in zip(
            values,
            weights
        )
        if v is not None
    ]

    if not valid:
        return None

    total_weight = sum(
        w
        for _, w in valid
    )

    if total_weight == 0:
        return None

    return (
        sum(
            v * w
            for v, w in valid
        )
        / total_weight
    )


def classify(value):
    if value is None:
        return "UNKNOWN"

    if value >= 80:
        return "A"

    if value >= 70:
        return "B+"

    if value >= 60:
        return "B"

    if value >= 50:
        return "C+"

    if value >= 40:
        return "C"

    return "D"


def analyze_horse(horse):
    races = (
        horse.get(
            "past_races",
            []
        )
        or []
    )

    analyzed = [
        analyze_race(
            race_row
        )
        for race_row in races
    ]

    # ---------------------------------
    # 過去走なし
    #
    # 架空の能力値を作らない。
    # UNKNOWNのまま保持。
    # ---------------------------------

    if not analyzed:
        return {
            "horse_id":
                text(
                    horse.get(
                        "horse_id"
                    )
                ),

            "horse_number":
                text(
                    horse.get(
                        "horse_number"
                    )
                ),

            "horse_name":
                text(
                    horse.get(
                        "horse_name"
                    )
                ),

            "past_race_count":
                0,

            "ability_score":
                None,

            "ability_grade":
                "UNKNOWN",

            "condition_fit_score":
                None,

            "performance_rate":
                None,

            "unknown":
                True,

            "noise_flags":
                [],

            "analysis":
                [],
        }

    weights = recency_weights(
        len(analyzed)
    )

    performance_values = [
        row[
            "performance_score"
        ]
        for row in analyzed
    ]

    condition_values = [
        row[
            "condition_score"
        ]
        for row in analyzed
    ]

    ability_raw = weighted_average(
        performance_values,
        weights
    )

    condition_raw = weighted_average(
        condition_values,
        weights
    )

    if ability_raw is None:
        ability_score = None
    else:
        ability_score = round(
            max(
                0,
                min(
                    100,
                    ability_raw * 100
                )
            ),
            1
        )

    if condition_raw is None:
        condition_fit_score = None
    else:
        condition_fit_score = round(
            max(
                0,
                min(
                    100,
                    condition_raw * 100
                )
            ),
            1
        )

    if condition_raw is None:
        performance_rate = None
    else:
        performance_rate = round(
            max(
                35,
                min(
                    100,
                    45
                    + condition_raw * 55
                )
            ),
            1
        )

    noise_flags = []

    if len(analyzed) == 1:
        noise_flags.append(
            "過去1走のみ"
        )

    same_surface_count = sum(
        1
        for row in analyzed
        if row[
            "same_surface"
        ]
    )

    exact_distance_count = sum(
        1
        for row in analyzed
        if (
            row["distance"]
            == TARGET_DISTANCE
        )
    )

    # 実績なし＝能力マイナスではない。
    # 情報不足フラグとしてのみ保持。

    if same_surface_count == 0:
        noise_flags.append(
            TARGET_SURFACE
            + "実績なし"
        )

    if exact_distance_count == 0:
        noise_flags.append(
            str(
                TARGET_DISTANCE
            )
            + "m実績なし"
        )

    positions = [
        passing_position(
            row.get(
                "passing"
            )
        )
        for row in races
    ]

    valid_positions = [
        x
        for x in positions
        if x is not None
    ]

    if valid_positions:
        avg_pos = (
            sum(
                valid_positions
            )
            / len(
                valid_positions
            )
        )

        if avg_pos >= 10:
            noise_flags.append(
                "後方位置依存注意"
            )

    last3fs = [
        row["last3f"]
        for row in analyzed
        if row[
            "last3f"
        ] is not None
    ]

    best_last3f = (
        min(last3fs)
        if last3fs
        else None
    )

    return {
        "horse_id":
            text(
                horse.get(
                    "horse_id"
                )
            ),

        "horse_number":
            text(
                horse.get(
                    "horse_number"
                )
            ),

        "horse_name":
            text(
                horse.get(
                    "horse_name"
                )
            ),

        "past_race_count":
            len(analyzed),

        "ability_score":
            ability_score,

        "ability_grade":
            classify(
                ability_score
            ),

        "condition_fit_score":
            condition_fit_score,

        "performance_rate":
            performance_rate,

        "same_surface_count":
            same_surface_count,

        "target_distance_count":
            exact_distance_count,

        "best_last3f":
            best_last3f,

        "unknown":
            False,

        "noise_flags":
            noise_flags,

        "analysis":
            analyzed,
    }


def main():
    source = load_json(
        INPUT_FILE
    )

    if not source:
        raise SystemExit(
            "ERROR: runner_history.json missing"
        )

    source_target_race_id = text(
        source.get(
            "target_race_id"
        )
    )

    if (
        source_target_race_id
        and source_target_race_id
        != TARGET_RACE_ID
    ):
        raise SystemExit(
            "ERROR: runner_history target race mismatch"
        )

    if (
        source.get(
            "future_race_usage"
        )
        is not False
    ):
        raise SystemExit(
            "ERROR: runner_history future race usage"
        )

    if (
        source.get(
            "leak_check_passed"
        )
        is not True
    ):
        raise SystemExit(
            "ERROR: runner_history leak check failed"
        )

    horses = (
        source.get(
            "horses",
            []
        )
        or []
    )

    results = [
        analyze_horse(
            horse
        )
        for horse in horses
    ]

    ability_sorted = sorted(
        [
            x
            for x in results
            if x[
                "ability_score"
            ] is not None
        ],
        key=lambda x:
            x[
                "ability_score"
            ],
        reverse=True,
    )

    for i, horse in enumerate(
        ability_sorted,
        start=1
    ):
        horse[
            "ability_rank"
        ] = i

    performance_sorted = sorted(
        [
            x
            for x in results
            if x[
                "performance_rate"
            ] is not None
        ],
        key=lambda x:
            x[
                "performance_rate"
            ],
        reverse=True,
    )

    for i, horse in enumerate(
        performance_sorted,
        start=1
    ):
        horse[
            "performance_rank"
        ] = i

    def horse_number_key(x):
        try:
            return int(
                x[
                    "horse_number"
                ]
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

        "target_race_id":
            TARGET_RACE_ID,

        "target_condition": {
            "track":
                TARGET_TRACK,

            "surface":
                TARGET_SURFACE,

            "distance":
                TARGET_DISTANCE,
        },

        "method": {
            "target_condition_from_race_json":
                True,

            "hardcoded_target_distance":
                False,

            "ability_and_performance_rate_separated":
                True,

            "unknown_is_not_penalized":
                True,

            "unknown_ability_not_imputed":
                True,

            "last3f_is_supporting_signal":
                True,

            "finish_position_is_not_used_alone":
                True,

            "distance_fit_not_used_as_ability":
                True,

            "popularity_not_used":
                True,

            "bloodline_not_used_here":
                True,
        },

        "summary": {
            "horse_count":
                len(results),

            "source_past_race_count":
                source.get(
                    "total_past_race_count",
                    0
                ),

            "ability_known_count":
                sum(
                    1
                    for horse in results
                    if horse[
                        "ability_score"
                    ] is not None
                ),

            "ability_unknown_count":
                sum(
                    1
                    for horse in results
                    if horse[
                        "ability_score"
                    ] is None
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
        "===== Runner Analysis ====="
    )

    print(
        "target race:",
        TARGET_RACE_ID
    )

    print(
        "target condition:",
        TARGET_TRACK,
        TARGET_SURFACE,
        TARGET_DISTANCE
    )

    print(
        "horses:",
        len(results)
    )

    print(
        "past races:",
        source.get(
            "total_past_race_count",
            0
        )
    )

    print(
        "ability known:",
        sum(
            1
            for horse in results
            if horse[
                "ability_score"
            ] is not None
        )
    )

    print(
        "ability unknown:",
        sum(
            1
            for horse in results
            if horse[
                "ability_score"
            ] is None
        )
    )

    print("")

    print(
        "ABILITY RANKING"
    )

    if not ability_sorted:
        print(
            "no known ability data"
        )

    for horse in ability_sorted:
        print(
            horse[
                "ability_rank"
            ],
            horse[
                "horse_number"
            ],
            horse[
                "horse_name"
            ],
            horse[
                "ability_score"
            ],
            horse[
                "performance_rate"
            ],
        )


if __name__ == "__main__":
    main()
