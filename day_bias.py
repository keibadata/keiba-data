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
# コーナー文字列正規化
# ============================================================

def normalize_corner_text(value):
    text = clean_text(
        value
    )

    if not text:
        return ""

    text = text.replace(
        "（",
        "("
    )

    text = text.replace(
        "）",
        ")"
    )

    text = text.replace(
        "，",
        ","
    )

    text = re.sub(
        r"\s+",
        "",
        text
    )

    return text


# ============================================================
# コーナー隊列を馬番順に展開
#
# 例:
#
# (*8,12)(5,11)(1,7,10)(2,3)(6,4)9
#
# ↓
#
# [8,12,5,11,1,7,10,2,3,6,4,9]
#
# ()内で並走していても、
# 「前のグループ→後ろのグループ」という順序は保持する。
#
# * は先頭表示なので除去。
# - = 等は隊列の間隔を示す記号として扱い、
# 馬番抽出時には無視する。
# ============================================================

def parse_corner_order(value):
    text = normalize_corner_text(
        value
    )

    if not text:
        return []

    numbers = re.findall(
        r"\d+",
        text
    )

    order = []

    seen = set()

    for number in numbers:

        try:
            horse_number = int(
                number
            )
        except ValueError:
            continue

        if not (
            1
            <= horse_number
            <= 18
        ):
            continue

        if horse_number in seen:
            continue

        seen.add(
            horse_number
        )

        order.append(
            horse_number
        )

    return order


# ============================================================
# 各馬のコーナー順位
#
# 返り値:
#
# {
#   8: 1,
#   12: 2,
#   5: 3,
#   ...
# }
#
# 同一グループ内の厳密な前後は判定できないため、
# HTML上に記載された順番を位置番号として利用。
#
# バイアス判定では絶対順位より
# 「前方・中団・後方」の大分類を重視する。
# ============================================================

def build_corner_position_map(
    value
):
    order = parse_corner_order(
        value
    )

    output = {}

    for index, horse_number in enumerate(
        order,
        start=1
    ):
        output[
            horse_number
        ] = index

    return output


# ============================================================
# 使用するコーナーを選択
#
# 原則:
# 4角 → 3角 → 2角 → 1角
#
# 東京芝1400/1600などでは
# 3角・4角が取得されているため4角を優先。
#
# 直線競走等でコーナーが無い場合は空。
# ============================================================

def select_reference_corner(
    corner_positions
):
    if not isinstance(
        corner_positions,
        dict
    ):
        return (
            "",
            ""
        )

    for corner_number in [
        "4",
        "3",
        "2",
        "1",
    ]:

        value = clean_text(
            corner_positions.get(
                corner_number
            )
        )

        if value:
            return (
                corner_number,
                value
            )

    return (
        "",
        ""
    )


# ============================================================
# 脚質分類
#
# 「馬番」ではなく、
# 実際のコーナー隊列内の位置から分類する。
#
# 逃げ:
#   コーナー隊列の先頭
#
# 先行:
#   上位約1/3
#
# 中団:
#   中央約1/3
#
# 後方:
#   後ろ約1/3
#
# ただし逃げは必ず先頭1頭を独立。
#
# ※これは当日バイアス検出用の脚質分類であり、
# 各馬の恒常的な脚質を決めるものではない。
# ============================================================

def classify_running_style(
    horse_number,
    position_map
):
    if horse_number is None:
        return ""

    if not position_map:
        return ""

    position = position_map.get(
        horse_number
    )

    if position is None:
        return ""

    field_size = len(
        position_map
    )

    if field_size <= 0:
        return ""

    if position == 1:
        return "逃げ"

    position_rate = (
        position
        / field_size
    )

    if position_rate <= 0.35:
        return "先行"

    if position_rate <= 0.70:
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

corner_connected_race_count = 0

corner_missing_race_numbers = []

reference_corner_numbers = {}


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


    # ========================================================
    # 未来レース混入チェック
    # ========================================================

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


    # ========================================================
    # 同一馬場のみ使用
    #
    # 芝 → 芝
    # ダート → ダート
    #
    # 障害は芝とは別扱い。
    # ========================================================

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

        item_race_no = safe_int(
            item.get(
                "race_number"
            )
        )

        results = (
            item.get(
                "results",
                []
            )
            or []
        )


        # ----------------------------------------------------
        # レース単位のcorner_positionsから
        # 使用するコーナーを選択
        # ----------------------------------------------------

        corner_positions = (
            item.get(
                "corner_positions",
                {}
            )
            or {}
        )

        (
            reference_corner_number,
            reference_corner_text
        ) = select_reference_corner(
            corner_positions
        )


        if reference_corner_text:

            position_map = (
                build_corner_position_map(
                    reference_corner_text
                )
            )

        else:

            position_map = {}


        if position_map:

            corner_connected_race_count += 1

            if item_race_no is not None:

                reference_corner_numbers[
                    str(item_race_no)
                ] = (
                    reference_corner_number
                )

        else:

            if item_race_no is not None:

                corner_missing_race_numbers.append(
                    item_race_no
                )


        valid_results = []


        # ====================================================
        # 各馬
        # ====================================================

        for result in results:

            finish = safe_int(
                result.get(
                    "finish"
                )
            )

            if finish is None:
                continue


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


            # ------------------------------------------------
            # 修正点
            #
            # 旧:
            # result.get("corner")
            #
            # 新:
            # race単位のcorner_positionsから
            # horse_numberに対応する位置を復元
            # ------------------------------------------------

            style = classify_running_style(
                horse_number,
                position_map
            )


            corner_position = None

            if (
                horse_number is not None
                and position_map
            ):

                corner_position = (
                    position_map.get(
                        horse_number
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

                "corner_number":
                    reference_corner_number,

                "corner_position":
                    corner_position,
            }


            valid_results.append(
                record
            )


            if style in style_counts:

                style_counts[
                    style
                ] += 1


        # ====================================================
        # 上位3頭
        # ====================================================

        top3 = [
            x
            for x in valid_results
            if (
                1
                <= x[
                    "finish"
                ]
                <= 3
            )
        ]


        for result in top3:

            style = result[
                "style"
            ]


            # ------------------------------------------------
            # 脚質サンプルは
            # 実際に位置を取得できた馬だけ加算
            # ------------------------------------------------

            if style in top3_style_counts:

                top3_style_counts[
                    style
                ] += 1

                top3_samples += 1


            # ------------------------------------------------
            # 馬番による内・中・外
            #
            # 当日傾向の補助。
            # 能力評価には直接使用しない。
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


            # ------------------------------------------------
            # 上がり
            # ------------------------------------------------

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
    #
    # 逃げ＋先行 vs 中団＋後方
    #
    # サンプル不足時は無理に判定しない。
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
    # 基準時計未接続なので、
    # 上がりだけから高速・低速を断定しない。
    # ========================================================

    time_bias = ""


    # ========================================================
    # 信頼度
    #
    # 同一馬場の参考レース数を基本とする。
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
            f"通過順位接続"
            f"{corner_connected_race_count}/"
            f"{reference_race_count}件。"
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

    "corner_connected_race_count":
        corner_connected_race_count,

    "corner_missing_race_numbers":
        corner_missing_race_numbers,

    "reference_corner_numbers":
        reference_corner_numbers,

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
    "corner connected:",
    corner_connected_race_count,
    "/",
    reference_race_count
)

print(
    "reference corners:",
    reference_corner_numbers
)

print(
    "corner missing races:",
    corner_missing_race_numbers
)

print(
    "top3 sample count:",
    top3_samples
)

print(
    "style counts:",
    style_counts
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
    "average winner last3f:",
    average_winner_last3f
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
