import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
TRACK_FILE = "track_condition.json"
DAY_RACES_FILE = "day_races.json"
OUTPUT_FILE = "day_bias.json"

JST = timezone(
    timedelta(hours=9)
)


# ============================================================
# 基本
# ============================================================

def now_jst():
    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(
            path,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except Exception:
        return {}


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
            indent=2
        )


def clean_text(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def normalize_surface(value):
    value = clean_text(value)

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


def safe_int(value):
    try:
        return int(value)
    except (
        TypeError,
        ValueError
    ):
        return None


def safe_float(value):
    try:
        return float(value)
    except (
        TypeError,
        ValueError
    ):
        return None


# ============================================================
# race_idからR番号
# ============================================================

def get_race_number(race_id):
    race_id = clean_text(
        race_id
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        return None

    try:
        race_no = int(
            race_id[-2:]
        )
    except ValueError:
        return None

    if not 1 <= race_no <= 12:
        return None

    return race_no


# ============================================================
# 通過順位解析
#
# 例:
# 2-2
# 4-4
# 10-8
# ============================================================

def parse_corner_positions(value):
    text = clean_text(value)

    if not text:
        return []

    numbers = re.findall(
        r"\d+",
        text
    )

    result = []

    for number in numbers:
        try:
            result.append(
                int(number)
            )
        except ValueError:
            pass

    return result


# ============================================================
# 脚質推定
#
# 通過順位からのみ判定。
# 推測情報は使用しない。
# ============================================================

def classify_running_style(
    corner_text
):
    positions = parse_corner_positions(
        corner_text
    )

    if not positions:
        return ""

    first = positions[0]

    if first == 1:
        return "逃げ"

    if first <= 4:
        return "先行"

    if first <= 9:
        return "中団"

    return "後方"


# ============================================================
# 入力
# ============================================================

race = load_json(
    RACE_FILE
)

track_condition = load_json(
    TRACK_FILE
)

day_races = load_json(
    DAY_RACES_FILE
)


if not race:
    raise SystemExit(
        "ERROR: race.json がありません"
    )


race_id = clean_text(
    race.get(
        "race_id"
    )
)

race_date = clean_text(
    race.get(
        "race_date"
    )
    or race.get(
        "date"
    )
)

racecourse = clean_text(
    race.get(
        "track"
    )
    or race.get(
        "racecourse"
    )
)

surface = normalize_surface(
    race.get(
        "surface"
    )
)

distance = safe_int(
    race.get(
        "distance"
    )
)

race_no = get_race_number(
    race_id
)


if race_no is None:
    raise SystemExit(
        "ERROR: race_idからR番号を取得できません"
    )


# ============================================================
# track_condition整合性
# ============================================================

track_race_id = clean_text(
    track_condition.get(
        "race_id"
    )
)

track_matched = (
    bool(track_condition)
    and track_race_id == race_id
)

if (
    track_condition
    and not track_matched
):
    raise SystemExit(
        "ERROR: track_condition.json race_id mismatch"
    )


# ============================================================
# day_races整合性
# ============================================================

day_races_race_id = clean_text(
    day_races.get(
        "race_id"
    )
)

day_races_matched = (
    bool(day_races)
    and day_races_race_id == race_id
)

if (
    day_races
    and not day_races_matched
):
    raise SystemExit(
        "ERROR: day_races.json race_id mismatch"
    )


# ============================================================
# 対象レースより前だけ
# ============================================================

previous_race_numbers = list(
    range(
        1,
        race_no
    )
)


# ============================================================
# 初期値
# ============================================================

status = ""
reference_race_count = 0

time_bias = ""
inside_outside_bias = ""
running_style_bias = ""

confidence = 0.0
reason = ""

reference_races = []

style_counts = {
    "逃げ": 0,
    "先行": 0,
    "中団": 0,
    "後方": 0,
}

top3_style_counts = {
    "逃げ": 0,
    "先行": 0,
    "中団": 0,
    "後方": 0,
}

top3_samples = 0

winner_last3f = []
top3_last3f = []

inside_top3 = 0
outside_top3 = 0
middle_top3 = 0

future_race_detected = False


# ============================================================
# 1R
# ============================================================

if race_no == 1:

    status = "no_previous_races"

    reason = (
        "対象が1Rのため、対象レース以前の"
        "同日実レースが存在しない。"
        "未来レースを使用しないため"
        "当日バイアス判定は行わない。"
    )


# ============================================================
# day_races 未取得
# ============================================================

elif not day_races:

    status = (
        "day_races_not_found"
    )

    reason = (
        "対象レースより前のRは存在するが、"
        "day_races.json が存在しない。"
        "推測によるバイアス判定は行わない。"
    )


# ============================================================
# day_races 接続
# ============================================================

else:

    collected_races = (
        day_races.get(
            "collected_races",
            []
        )
        or []
    )

    # --------------------------------------------------------
    # 安全確認
    #
    # 対象R以降が混入していたら停止
    # --------------------------------------------------------

    for item in collected_races:

        item_race_no = safe_int(
            item.get(
                "race_number"
            )
        )

        if item_race_no is None:
            continue

        if item_race_no >= race_no:
            future_race_detected = True
            break


    if future_race_detected:

        raise SystemExit(
            "ERROR: day_races.json に"
            "対象レース以降のデータが混入しています"
        )


    # --------------------------------------------------------
    # 同一馬場のみ使用
    #
    # 芝 → 芝
    # ダート → ダート
    # --------------------------------------------------------

    for item in collected_races:

        item_race_no = safe_int(
            item.get(
                "race_number"
            )
        )

        if item_race_no is None:
            continue

        if item_race_no >= race_no:
            continue

        item_surface = normalize_surface(
            item.get(
                "surface"
            )
        )

        if item_surface != surface:
            continue

        if (
            item.get(
                "status"
            )
            not in [
                "ok",
                "condition_parse_incomplete",
            ]
        ):
            continue

        results = (
            item.get(
                "results",
                []
            )
            or []
        )

        if not results:
            continue

        reference_races.append(
            item
        )


    reference_race_count = len(
        reference_races
    )


    # ========================================================
    # 各参考レース解析
    # ========================================================

    for item in reference_races:

        results = (
            item.get(
                "results",
                []
            )
            or []
        )

        valid_results = []

        for result in results:

            finish = safe_int(
                result.get(
                    "finish"
                )
            )

            if finish is None:
                continue

            style = classify_running_style(
                result.get(
                    "corner"
                )
            )

            horse_number = safe_int(
                result.get(
                    "horse_number"
                )
            )

            last3f = safe_float(
                result.get(
                    "last3f"
                )
            )

            record = {
                "finish":
                    finish,

                "style":
                    style,

                "horse_number":
                    horse_number,

                "last3f":
                    last3f,
            }

            valid_results.append(
                record
            )

            if style in style_counts:
                style_counts[
                    style
                ] += 1


        # ----------------------------------------------------
        # 上位3頭
        # ----------------------------------------------------

        top3 = [
            x
            for x in valid_results
            if 1 <= x[
                "finish"
            ] <= 3
        ]

        for result in top3:

            style = result[
                "style"
            ]

            if style in top3_style_counts:

                top3_style_counts[
                    style
                ] += 1

                top3_samples += 1


            # ------------------------------------------------
            # 馬番を内・中・外に簡易分類
            #
            # 枠順ではなく馬番。
            # これ単独で能力評価には使わない。
            # 当日傾向の補助のみ。
            # ------------------------------------------------

            horse_number = result[
                "horse_number"
            ]

            if horse_number is not None:

                if horse_number <= 5:
                    inside_top3 += 1

                elif horse_number >= 11:
                    outside_top3 += 1

                else:
                    middle_top3 += 1


            last3f = result[
                "last3f"
            ]

            if last3f is not None:
                top3_last3f.append(
                    last3f
                )


            if (
                result[
                    "finish"
                ]
                == 1
                and last3f is not None
            ):
                winner_last3f.append(
                    last3f
                )


    # ========================================================
    # 脚質バイアス
    # ========================================================

    front_top3 = (
        top3_style_counts[
            "逃げ"
        ]
        + top3_style_counts[
            "先行"
        ]
    )

    back_top3 = (
        top3_style_counts[
            "中団"
        ]
        + top3_style_counts[
            "後方"
        ]
    )


    if top3_samples >= 3:

        front_rate = (
            front_top3
            / top3_samples
        )

        back_rate = (
            back_top3
            / top3_samples
        )

        if front_rate >= 0.67:
            running_style_bias = (
                "逃げ・先行有利"
            )

        elif back_rate >= 0.67:
            running_style_bias = (
                "差し有利"
            )

        else:
            running_style_bias = (
                "大きな偏りなし"
            )


    # ========================================================
    # 内外バイアス
    #
    # 馬番だけなので強い判定にはしない。
    # ========================================================

    position_samples = (
        inside_top3
        + middle_top3
        + outside_top3
    )

    if position_samples >= 3:

        inside_rate = (
            inside_top3
            / position_samples
        )

        outside_rate = (
            outside_top3
            / position_samples
        )

        if inside_rate >= 0.60:
            inside_outside_bias = (
                "内寄り優勢"
            )

        elif outside_rate >= 0.60:
            inside_outside_bias = (
                "外寄り優勢"
            )

        else:
            inside_outside_bias = (
                "大きな偏りなし"
            )


    # ========================================================
    # 時計バイアス
    #
    # 絶対時計との比較基準がまだないため、
    # 上がりだけで高速・低速とは断定しない。
    #
    # ここは意図的にニュートラル。
    # ========================================================

    time_bias = ""


    # ========================================================
    # 信頼度
    #
    # 同一馬場の参考レース数だけで決める。
    # ========================================================

    if reference_race_count >= 5:
        confidence = 1.0

    elif reference_race_count == 4:
        confidence = 0.8

    elif reference_race_count == 3:
        confidence = 0.6

    elif reference_race_count == 2:
        confidence = 0.4

    elif reference_race_count == 1:
        confidence = 0.2

    else:
        confidence = 0.0


    # ========================================================
    # status
    # ========================================================

    if reference_race_count == 0:

        status = (
            "no_same_surface_reference"
        )

        reason = (
            "対象レース以前の同日レースは"
            "収集済みだが、対象と同じ馬場の"
            "有効な参考レースが存在しない。"
            "推測によるバイアス判定は行わない。"
        )

    else:

        status = (
            "analyzed"
        )

        reason = (
            f"対象レース以前の同日・同競馬場・"
            f"同馬場の実レース"
            f"{reference_race_count}件を使用。"
            f"対象レース以降のデータは使用していない。"
            f"時計傾向は基準時計未接続のため"
            f"現段階では判定しない。"
        )


# ============================================================
# 平均上がり
# ============================================================

average_top3_last3f = None

if top3_last3f:
    average_top3_last3f = round(
        statistics.mean(
            top3_last3f
        ),
        2
    )


average_winner_last3f = None

if winner_last3f:
    average_winner_last3f = round(
        statistics.mean(
            winner_last3f
        ),
        2
    )


# ============================================================
# 出力
# ============================================================

output = {
    "race_id":
        race_id,

    "race_date":
        race_date,

    "racecourse":
        racecourse,

    "surface":
        surface,

    "distance":
        distance,

    "race_number":
        race_no,

    "eligible_previous_race_numbers":
        previous_race_numbers,

    "future_race_usage":
        False,

    "day_races_connected":
        day_races_matched,

    "status":
        status,

    "reference_race_count":
        reference_race_count,

    "reference_race_numbers": [
        item.get(
            "race_number"
        )
        for item in reference_races
    ],

    "time_bias":
        time_bias,

    "inside_outside_bias":
        inside_outside_bias,

    "running_style_bias":
        running_style_bias,

    "confidence":
        confidence,

    "reason":
        reason,

    "style_counts":
        style_counts,

    "top3_style_counts":
        top3_style_counts,

    "top3_sample_count":
        top3_samples,

    "inside_top3":
        inside_top3,

    "middle_top3":
        middle_top3,

    "outside_top3":
        outside_top3,

    "average_top3_last3f":
        average_top3_last3f,

    "average_winner_last3f":
        average_winner_last3f,

    "track_condition_connected":
        track_matched,

    "moisture_finish":
        (
            track_condition.get(
                "moisture_finish"
            )
            if track_matched
            else None
        ),

    "moisture_4corner":
        (
            track_condition.get(
                "moisture_4corner"
            )
            if track_matched
            else None
        ),

    "cushion_value":
        (
            track_condition.get(
                "cushion_value"
            )
            if track_matched
            else None
        ),

    "updated_at":
        now_jst(),
}


save_json(
    OUTPUT_FILE,
    output
)


# ============================================================
# ログ
# ============================================================

print()
print(
    "===== DAY BIAS ====="
)

print(
    "race id:",
    race_id
)

print(
    "date:",
    race_date
)

print(
    "racecourse:",
    racecourse
)

print(
    "surface:",
    surface
)

print(
    "race number:",
    race_no
)

print(
    "eligible previous races:",
    previous_race_numbers
)

print(
    "future race usage:",
    False
)

print(
    "day races connected:",
    day_races_matched
)

print(
    "track condition connected:",
    track_matched
)

print(
    "reference race count:",
    reference_race_count
)

print(
    "reference races:",
    output[
        "reference_race_numbers"
    ]
)

print(
    "top3 sample count:",
    top3_samples
)

print(
    "top3 style counts:",
    top3_style_counts
)

print(
    "running style bias:",
    running_style_bias
)

print(
    "inside / middle / outside:",
    inside_top3,
    middle_top3,
    outside_top3
)

print(
    "inside outside bias:",
    inside_outside_bias
)

print(
    "average top3 last3f:",
    average_top3_last3f
)

print(
    "time bias:",
    time_bias
)

print(
    "confidence:",
    confidence
)

print(
    "moisture finish:",
    output[
        "moisture_finish"
    ]
)

print(
    "moisture 4corner:",
    output[
        "moisture_4corner"
    ]
)

print(
    "cushion value:",
    output[
        "cushion_value"
    ]
)

print(
    "status:",
    status
)

print(
    "reason:",
    reason
)

print(
    "saved:",
    OUTPUT_FILE
)

print(
    "===================="
)
