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
    #
