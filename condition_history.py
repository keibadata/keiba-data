import json
import os
from pathlib import Path


RACE_FILE = "race.json"
OUTPUT_FILE = "condition_history.json"
HISTORY_FILE = "history_db.json"


def load_json(path):
    if not os.path.exists(path):
        return {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def normalize_surface(value):
    value = str(value or "").strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_track(value):
    return str(value or "").strip()


def normalize_distance(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def get_race_condition(race):
    """
    race.json の形式差を吸収して
    競馬場・芝ダート・距離を取得する。
    """

    track = (
        race.get("track")
        or race.get("racecourse")
        or race.get("venue")
        or race.get("place")
        or ""
    )

    surface = (
        race.get("surface")
        or race.get("track_type")
        or race.get("course_type")
        or ""
    )

    distance = (
        race.get("distance")
        or race.get("distance_m")
        or 0
    )

    # race_info 内に入っている場合
    race_info = race.get("race_info", {})

    if isinstance(race_info, dict):

        if not track:
            track = (
                race_info.get("track")
                or race_info.get("racecourse")
                or race_info.get("venue")
                or race_info.get("place")
                or ""
            )

        if not surface:
            surface = (
                race_info.get("surface")
                or race_info.get("track_type")
                or race_info.get("course_type")
                or ""
            )

        if not distance:
            distance = (
                race_info.get("distance")
                or race_info.get("distance_m")
                or 0
            )

    return {
        "track": normalize_track(track),
        "surface": normalize_surface(surface),
        "distance": normalize_distance(distance),
    }


def get_history_rows(history):
    """
    history_db.json の形式差を吸収。
    """

    if isinstance(history, list):
        return history

    if not isinstance(history, dict):
        return []

    for key in (
        "races",
        "history",
        "records",
        "data",
    ):
        value = history.get(key)

        if isinstance(value, list):
            return value

    return []


def get_condition_from_history_row(row):
    if not isinstance(row, dict):
        return {
            "track": "",
            "surface": "",
            "distance": 0,
        }

    race_info = row.get("race_info", {})

    track = (
        row.get("track")
        or row.get("racecourse")
        or row.get("venue")
        or row.get("place")
        or ""
    )

    surface = (
        row.get("surface")
        or row.get("track_type")
        or row.get("course_type")
        or ""
    )

    distance = (
        row.get("distance")
        or row.get("distance_m")
        or 0
    )

    if isinstance(race_info, dict):

        if not track:
            track = (
                race_info.get("track")
                or race_info.get("racecourse")
                or race_info.get("venue")
                or race_info.get("place")
                or ""
            )

        if not surface:
            surface = (
                race_info.get("surface")
                or race_info.get("track_type")
                or race_info.get("course_type")
                or ""
            )

        if not distance:
            distance = (
                race_info.get("distance")
                or race_info.get("distance_m")
                or 0
            )

    return {
        "track": normalize_track(track),
        "surface": normalize_surface(surface),
        "distance": normalize_distance(distance),
    }


race = load_json(RACE_FILE)
history = load_json(HISTORY_FILE)

target = get_race_condition(race)
history_rows = get_history_rows(history)

matched = []

for row in history_rows:

    condition = get_condition_from_history_row(row)

    if (
        condition["track"] == target["track"]
        and condition["surface"] == target["surface"]
        and condition["distance"] == target["distance"]
    ):
        matched.append(row)


output = {
    "race_id": str(race.get("race_id", "")),
    "target_condition": target,
    "history_source": HISTORY_FILE,
    "history_total_count": len(history_rows),
    "matched_history_count": len(matched),
    "matched_history": matched,
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


print("===== CONDITION HISTORY =====")
print("race_id:", output["race_id"])
print(
    "condition:",
    target["track"],
    target["surface"],
    target["distance"]
)
print(
    "matched:",
    len(matched),
    "/",
    len(history_rows)
)


# 安全装置
if not target["track"]:
    raise RuntimeError(
        "race.jsonから競馬場を取得できません"
    )

if not target["surface"]:
    raise RuntimeError(
        "race.jsonから芝・ダートを取得できません"
    )

if target["distance"] <= 0:
    raise RuntimeError(
        "race.jsonから距離を取得できません"
    )

if len(matched) == 0:
    print(
        "WARNING: "
        "現在のhistory_db.jsonには"
        "この条件の過去レースがありません。"
        "新規収集が必要です。"
    )
