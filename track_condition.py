import json
import os
from datetime import datetime, timezone, timedelta

RACE_FILE = "race.json"
OLD_TRACK_FILE = "track_condition.json"
OUTPUT_FILE = "track_condition.json"


def load_json(filename):
    if not os.path.exists(filename):
        return {}

    try:
        with open(filename, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def now_jst():
    return datetime.now(
        timezone(timedelta(hours=9))
    ).isoformat()


race = load_json(RACE_FILE)
old_track = load_json(OLD_TRACK_FILE)

race_id = str(
    race.get("race_id", "")
).strip()

race_date = str(
    race.get("race_date", "")
).strip()

track = str(
    race.get("track")
    or race.get("racecourse")
    or ""
).strip()

surface = str(
    race.get("surface", "")
).strip()

distance = race.get("distance")

race_track_condition = str(
    race.get("track_condition", "")
).strip()


# =====================================
# 旧データを引き継げるか
# =====================================

old_race_id = str(
    old_track.get("race_id", "")
).strip()

old_race_date = str(
    old_track.get("race_date", "")
).strip()

old_track_name = str(
    old_track.get("track", "")
).strip()

old_surface = str(
    old_track.get("surface", "")
).strip()


same_race = (
    bool(race_id)
    and race_id == old_race_id
)

same_condition_group = (
    bool(track)
    and bool(surface)
    and track == old_track_name
    and surface == old_surface
    and (
        not race_date
        or not old_race_date
        or race_date == old_race_date
    )
)


# =====================================
# 初期値
# =====================================

track_condition = race_track_condition

cushion_value = None
moisture_4corner = None
moisture_finish = None

time_bias = ""
inside_outside_bias = ""
running_style_bias = ""

reference_race_count = 0
memo = ""


# =====================================
# 同一レース
# または同日・同場・同馬場のみ引継ぎ
# =====================================

if same_race or same_condition_group:

    if not track_condition:
        track_condition = str(
            old_track.get(
                "track_condition",
                ""
            )
        ).strip()

    time_bias = str(
        old_track.get(
            "time_bias",
            ""
        )
    ).strip()

    inside_outside_bias = str(
        old_track.get(
            "inside_outside_bias",
            ""
        )
    ).strip()

    running_style_bias = str(
        old_track.get(
            "running_style_bias",
            ""
        )
    ).strip()

    reference_race_count = int(
        old_track.get(
            "reference_race_count",
            0
        ) or 0
    )

    memo = str(
        old_track.get(
            "memo",
            ""
        )
    ).strip()

    # 芝のみクッション値
    if surface == "芝":
        cushion_value = old_track.get(
            "cushion_value"
        )

    # 含水率は芝・ダートそれぞれ
    # 同じsurfaceの時だけ引継ぐ
    moisture_4corner = old_track.get(
        "moisture_4corner"
    )

    moisture_finish = old_track.get(
        "moisture_finish"
    )


# =====================================
# surface別安全処理
# =====================================

if surface == "ダート":
    # ダートにクッション値を混ぜない
    cushion_value = None

elif surface == "芝":
    pass

else:
    # surface不明なら数値情報を流用しない
    cushion_value = None
    moisture_4corner = None
    moisture_finish = None
    time_bias = ""
    inside_outside_bias = ""
    running_style_bias = ""
    reference_race_count = 0


# =====================================
# 出力
# =====================================

output = {
    "race_id": race_id,
    "race_date": race_date,

    "track": track,
    "surface": surface,
    "distance": distance,

    "track_condition": track_condition,

    "cushion_value": cushion_value,

    "moisture_4corner": moisture_4corner,
    "moisture_finish": moisture_finish,

    "time_bias": time_bias,

    "inside_outside_bias":
        inside_outside_bias,

    "running_style_bias":
        running_style_bias,

    "reference_race_count":
        reference_race_count,

    "memo": memo,

    "source": (
        "previous_track_condition"
        if same_race or same_condition_group
        else "race.json"
    ),

    "match_status": {
        "same_race": same_race,
        "same_date_track_surface":
            same_condition_group
    },

    "updated_at": now_jst()
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


print("===== TRACK CONDITION =====")
print("race id:", race_id)
print("date:", race_date)
print("track:", track)
print("surface:", surface)
print("distance:", distance)
print("condition:", track_condition)
print("same race:", same_race)
print(
    "same date/track/surface:",
    same_condition_group
)
print(
    "running style bias:",
    running_style_bias
)
print(
    "reference races:",
    reference_race_count
)
