import json
import os
from datetime import datetime, timezone, timedelta


RACE_FILE = "race.json"
TRACK_FILE = "track_condition.json"
OUTPUT_FILE = "track_condition.json"

JST = timezone(
    timedelta(hours=9)
)


def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(
            filename,
            "r",
            encoding="utf-8"
        ) as f:
            return json.load(f)

    except (
        json.JSONDecodeError,
        OSError
    ):
        return {}


def now_jst():
    return datetime.now(
        JST
    ).isoformat()


def clean(value):
    if value is None:
        return ""

    return str(
        value
    ).strip()


# =========================================================
# race.json
# =========================================================

race = load_json(
    RACE_FILE
)

if not race:
    raise RuntimeError(
        "race.jsonを読み込めませんでした。"
    )


race_id = clean(
    race.get("race_id")
)

race_date = clean(
    race.get("race_date")
)

track = clean(
    race.get("track")
    or race.get("racecourse")
)

surface = clean(
    race.get("surface")
)

distance = race.get(
    "distance"
)

race_track_condition = clean(
    race.get("track_condition")
)


# =========================================================
# 必須項目チェック
# =========================================================

if not race_id:
    raise RuntimeError(
        "race_idがありません。"
    )

if not race_date:
    raise RuntimeError(
        "race_dateがありません。"
    )

if not track:
    raise RuntimeError(
        "trackがありません。"
    )

if surface not in (
    "芝",
    "ダート"
):
    raise RuntimeError(
        "surfaceが芝/ダートではありません。"
    )


# =========================================================
# 既存track_condition.json
# =========================================================

old = load_json(
    TRACK_FILE
)

old_race_id = clean(
    old.get("race_id")
)

old_race_date = clean(
    old.get("race_date")
)

old_track = clean(
    old.get("track")
)

old_surface = clean(
    old.get("surface")
)


# =========================================================
# 引継ぎ判定
# =========================================================
#
# 1. 完全に同じrace_id
#
# または
#
# 2. 開催日
#    競馬場
#    surface
#
# の3条件が完全一致した場合だけ許可
#
# 日付不明の旧データは絶対に共有しない
# =========================================================

same_race = (
    bool(old_race_id)
    and old_race_id == race_id
    and (
        not old_track
        or old_track == track
    )
    and (
        not old_surface
        or old_surface == surface
    )
)


same_date_track_surface = (
    bool(race_date)
    and bool(old_race_date)
    and bool(track)
    and bool(old_track)
    and bool(surface)
    and bool(old_surface)

    and race_date == old_race_date
    and track == old_track
    and surface == old_surface
)


can_reuse = (
    same_race
    or same_date_track_surface
)


# =========================================================
# 初期値
# =========================================================

track_condition = (
    race_track_condition
)

cushion_value = None

moisture_4corner = None
moisture_finish = None

time_bias = ""

inside_outside_bias = ""

running_style_bias = ""

reference_race_count = 0

memo = ""

source_race_id = ""


# =========================================================
# 安全な旧データのみ引継ぎ
# =========================================================

if can_reuse:

    source_race_id = (
        clean(
            old.get(
                "source_race_id"
            )
        )
        or old_race_id
    )

    if not track_condition:

        track_condition = clean(
            old.get(
                "track_condition"
            )
        )

    # -----------------------------------------------------
    # 芝クッション値
    # -----------------------------------------------------

    if surface == "芝":

        cushion_value = old.get(
            "cushion_value"
        )

    # -----------------------------------------------------
    # 含水率
    # -----------------------------------------------------

    moisture_4corner = old.get(
        "moisture_4corner"
    )

    moisture_finish = old.get(
        "moisture_finish"
    )

    # -----------------------------------------------------
    # 実測バイアス
    # -----------------------------------------------------

    time_bias = clean(
        old.get(
            "time_bias"
        )
    )

    inside_outside_bias = clean(
        old.get(
            "inside_outside_bias"
        )
    )

    running_style_bias = clean(
        old.get(
            "running_style_bias"
        )
    )

    try:
        reference_race_count = int(
            old.get(
                "reference_race_count",
                0
            )
            or 0
        )

    except (
        TypeError,
        ValueError
    ):
        reference_race_count = 0

    memo = clean(
        old.get(
            "memo"
        )
    )


# =========================================================
# surface安全処理
# =========================================================

if surface == "ダート":

    # ダートにクッション値は使用しない
    cushion_value = None


# =========================================================
# データ有無
# =========================================================

data_available = any(
    [
        bool(track_condition),

        (
            cushion_value
            is not None
        ),

        (
            moisture_4corner
            is not None
        ),

        (
            moisture_finish
            is not None
        ),

        bool(
            time_bias
        ),

        bool(
            inside_outside_bias
        ),

        bool(
            running_style_bias
        ),

        reference_race_count > 0,
    ]
)


# =========================================================
# 旧データ不採用理由
# =========================================================

reject_reason = ""

if old and not can_reuse:

    if (
        old_race_date
        and old_race_date != race_date
    ):

        reject_reason = (
            "race_date mismatch"
        )

    elif (
        old_track
        and old_track != track
    ):

        reject_reason = (
            "track mismatch"
        )

    elif (
        old_surface
        and old_surface != surface
    ):

        reject_reason = (
            "surface mismatch"
        )

    elif not old_race_date:

        reject_reason = (
            "old race_date missing"
        )

    else:

        reject_reason = (
            "condition group mismatch"
        )


# =========================================================
# 出力
# =========================================================

output = {
    "race_id":
        race_id,

    "race_date":
        race_date,

    "track":
        track,

    "surface":
        surface,

    "distance":
        distance,

    "track_condition":
        track_condition,

    "cushion_value":
        cushion_value,

    "moisture_4corner":
        moisture_4corner,

    "moisture_finish":
        moisture_finish,

    "time_bias":
        time_bias,

    "inside_outside_bias":
        inside_outside_bias,

    "running_style_bias":
        running_style_bias,

    "reference_race_count":
        reference_race_count,

    "data_available":
        data_available,

    "source_race_id":
        source_race_id,

    "source": (
        "previous_track_condition"
        if can_reuse
        else "race.json"
    ),

    "match_status": {
        "same_race":
            same_race,

        "same_date_track_surface":
            same_date_track_surface,

        "reused":
            can_reuse,

        "reject_reason":
            reject_reason,
    },

    "memo":
        memo,

    "updated_at":
        now_jst(),
}


# =========================================================
# 保存
# =========================================================

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


# =========================================================
# ログ
# =========================================================

print(
    "===== TRACK CONDITION ====="
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
    "track:",
    track
)

print(
    "surface:",
    surface
)

print(
    "distance:",
    distance
)

print(
    "condition:",
    track_condition
)

print(
    "same race:",
    same_race
)

print(
    "same date/track/surface:",
    same_date_track_surface
)

print(
    "reused:",
    can_reuse
)

print(
    "reject reason:",
    reject_reason
)

print(
    "cushion:",
    cushion_value
)

print(
    "moisture 4corner:",
    moisture_4corner
)

print(
    "moisture finish:",
    moisture_finish
)

print(
    "running style bias:",
    running_style_bias
)

print(
    "reference races:",
    reference_race_count
)

print(
    "data available:",
    data_available
)
