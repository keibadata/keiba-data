import json
import os
import re
from datetime import datetime, timezone, timedelta


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
TRACK_FILE = "track_condition.json"
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


# ============================================================
# race_idからR番号取得
#
# JRA/netkeiba形式
# YYYY JJ KK DD RR
# 最後2桁 = race number
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
# 入力
# ============================================================

race = load_json(
    RACE_FILE
)

track_condition = load_json(
    TRACK_FILE
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


surface = clean_text(
    race.get(
        "surface"
    )
)


distance = race.get(
    "distance"
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


if track_condition and not track_matched:

    raise SystemExit(
        "ERROR: track_condition.json race_id mismatch"
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
# 1R特例
#
# 前のレースが存在しないため、
# 当日実レース由来のバイアス判定は禁止。
# ============================================================

if race_no == 1:

    status = (
        "no_previous_races"
    )

    reference_race_count = 0

    time_bias = ""
    inside_outside_bias = ""
    running_style_bias = ""

    confidence = 0.0

    reason = (
        "対象が1Rのため、対象レース以前の"
        "同日実レースが存在しない。"
        "未来レースを使用しないため"
        "当日バイアス判定は行わない。"
    )

else:

    # --------------------------------------------------------
    # 次段階でここに実レース収集を接続する。
    #
    # 現時点では、未取得データを推測で埋めない。
    # --------------------------------------------------------

    status = (
        "waiting_for_previous_race_collection"
    )

    reference_race_count = 0

    time_bias = ""
    inside_outside_bias = ""
    running_style_bias = ""

    confidence = 0.0

    reason = (
        "対象レースより前のRは存在するが、"
        "実レース結果収集は未接続。"
        "推測によるバイアス判定は行わない。"
    )


# ============================================================
# 出力
# ============================================================

output = {
    "race_id": race_id,
    "race_date": race_date,

    "racecourse": racecourse,
    "surface": surface,
    "distance": distance,

    "race_number": race_no,

    "eligible_previous_race_numbers": (
        previous_race_numbers
    ),

    "future_race_usage": False,

    "status": status,

    "reference_race_count": (
        reference_race_count
    ),

    "time_bias": (
        time_bias
    ),

    "inside_outside_bias": (
        inside_outside_bias
    ),

    "running_style_bias": (
        running_style_bias
    ),

    "confidence": confidence,

    "reason": reason,

    "track_condition_connected": (
        track_matched
    ),

    "moisture_finish": (
        track_condition.get(
            "moisture_finish"
        )
        if track_matched
        else None
    ),

    "moisture_4corner": (
        track_condition.get(
            "moisture_4corner"
        )
        if track_matched
        else None
    ),

    "cushion_value": (
        track_condition.get(
            "cushion_value"
        )
        if track_matched
        else None
    ),

    "updated_at": now_jst(),
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
    "track condition connected:",
    track_matched
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
    "status:",
    status
)

print(
    "reference race count:",
    reference_race_count
)

print(
    "running style bias:",
    running_style_bias
)

print(
    "inside outside bias:",
    inside_outside_bias
)

print(
    "time bias:",
    time_bias
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
