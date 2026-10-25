import json
import os
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone


# ============================================================
# 設定
# ============================================================

RACE_FILE = "race.json"
OUTPUT_FILE = "day_races.json"
COLLECTOR_FILE = "day_race_collector.py"

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
            encoding="utf-8",
        ) as f:
            return json.load(f)

    except Exception as exc:
        raise RuntimeError(
            f"{path} の読み込みに失敗しました: {exc}"
        )


def save_json(path, data):
    with open(
        path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


def clean_text(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or ""),
    ).strip()


def safe_int(value):
    try:
        return int(value)

    except (
        TypeError,
        ValueError,
    ):
        return None


def normalize_surface(value):
    text = clean_text(
        value
    )

    if text.startswith("芝"):
        return "芝"

    if (
        text.startswith("ダ")
        or "ダート" in text
    ):
        return "ダート"

    if text.startswith("障"):
        return "障害"

    return text


# ============================================================
# race.json
# ============================================================

race = load_json(
    RACE_FILE
)

if not race:
    raise RuntimeError(
        "race.json がありません。"
    )


race_id = clean_text(
    race.get("race_id")
)

if not re.fullmatch(
    r"\d{12}",
    race_id,
):
    raise RuntimeError(
        "race.json の race_id が不正です。"
    )


target_race_number = int(
    race_id[-2:]
)

if not (
    1
    <= target_race_number
    <= 12
):
    raise RuntimeError(
        "対象R番号が不正です。"
    )


race_date = clean_text(
    race.get("race_date")
    or race.get("date")
)

racecourse = clean_text(
    race.get("racecourse")
    or race.get("track")
)

target_surface = normalize_surface(
    race.get("surface")
)

target_distance = safe_int(
    race.get("distance")
)


print()
print(
    "===== DAY RACES PRODUCTION BRIDGE ====="
)

print(
    "target race id:",
    race_id,
)

print(
    "date:",
    race_date,
)

print(
    "racecourse:",
    racecourse,
)

print(
    "surface:",
    target_surface,
)

print(
    "distance:",
    target_distance,
)

print(
    "target race number:",
    target_race_number,
)

print()


# ============================================================
# collector存在確認
# ============================================================

if not os.path.exists(
    COLLECTOR_FILE
):
    raise RuntimeError(
        f"{COLLECTOR_FILE} がありません。"
    )


# ============================================================
# 新しい取得エンジン実行
#
# 重要:
# --include-target は絶対に付けない。
#
# 予想時は対象Rより前の確定レースだけ取得する。
# ============================================================

command = [
    sys.executable,
    COLLECTOR_FILE,
    "--output",
    OUTPUT_FILE,
]


print(
    "run collector:",
    " ".join(command),
)

print()


completed = subprocess.run(
    command,
    check=False,
)


if completed.returncode != 0:
    raise RuntimeError(
        "day_race_collector.py が異常終了しました。"
    )


# ============================================================
# collector出力確認
# ============================================================

collector_data = load_json(
    OUTPUT_FILE
)

if not collector_data:
    raise RuntimeError(
        "day_race_collector.py の出力がありません。"
    )


collector_target_race_id = clean_text(
    collector_data.get(
        "target_race_id"
    )
)


if (
    collector_target_race_id
    != race_id
):
    raise RuntimeError(
        "day_race_collector.py の"
        "target_race_id が一致しません。"
    )


# ============================================================
# 未来情報リーク防止
# ============================================================

mode = clean_text(
    collector_data.get(
        "mode"
    )
)


if mode != "prediction":
    raise RuntimeError(
        "day_race_collector.py が"
        "prediction モードではありません。"
    )


if (
    collector_data.get(
        "include_target"
    )
    is True
):
    raise RuntimeError(
        "予想モードで対象レース結果が"
        "取得されています。"
    )


if (
    collector_data.get(
        "target_race_included"
    )
    is True
):
    raise RuntimeError(
        "対象レース自身が"
        "day_races.json に混入しています。"
    )


if (
    collector_data.get(
        "future_race_usage"
    )
    is True
):
    raise RuntimeError(
        "未来レース使用フラグが"
        "検出されました。"
    )


# ============================================================
# 新形式取得
# ============================================================

new_races = (
    collector_data.get(
        "races",
        []
    )
    or []
)


if not isinstance(
    new_races,
    list,
):
    raise RuntimeError(
        "day_race_collector.py の"
        "races が配列ではありません。"
    )


# ============================================================
# corner_orders
#   ↓
# corner_positions
#
# 新形式:
# {
#   "3_corner": "...",
#   "4_corner": "..."
# }
#
# 既存day_bias:
# {
#   "1": "",
#   "2": "",
#   "3": "...",
#   "4": "..."
# }
# ============================================================

def convert_corner_positions(
    corner_orders
):
    output = {
        "1": "",
        "2": "",
        "3": "",
        "4": "",
    }

    if not isinstance(
        corner_orders,
        dict,
    ):
        return output

    for number in [
        1,
        2,
        3,
        4,
    ]:
        value = clean_text(
            corner_orders.get(
                f"{number}_corner"
            )
            or corner_orders.get(
                str(number)
            )
        )

        output[
            str(number)
        ] = value

    return output


# ============================================================
# 1レースを既存形式へ接続
# ============================================================

def convert_race(
    item
):
    if not isinstance(
        item,
        dict,
    ):
        return None

    converted = dict(
        item
    )

    race_number = safe_int(
        item.get(
            "race_number"
        )
    )

    current_race_id = clean_text(
        item.get(
            "race_id"
        )
    )

    surface = normalize_surface(
        item.get(
            "surface"
        )
    )

    distance = safe_int(
        item.get(
            "distance"
        )
    )

    track_condition = clean_text(
        item.get(
            "track_condition"
        )
    )

    finished = bool(
        item.get(
            "finished"
        )
    )

    finishers = (
        item.get(
            "finishers",
            []
        )
        or []
    )

    if not isinstance(
        finishers,
        list,
    ):
        finishers = []

    laps = (
        item.get(
            "laps",
            []
        )
        or []
    )

    if not isinstance(
        laps,
        list,
    ):
        laps = []

    corner_positions = (
        convert_corner_positions(
            item.get(
                "corner_orders",
                {}
            )
        )
    )


    # ========================================================
    # 解析状態
    # ========================================================

    problems = []


    if not surface:
        problems.append(
            "surface"
        )


    if not distance:
        problems.append(
            "distance"
        )


    if (
        finished
        and not finishers
    ):
        problems.append(
            "results"
        )


    if (
        finished
        and distance
        and not laps
    ):
        problems.append(
            "race_laps"
        )


    if not finished:
        status = "not_finished"

    elif problems:
        status = "parse_incomplete"

    elif not track_condition:
        # 馬場状態だけ取れない場合は
        # レース結果自体は使用可能。
        status = (
            "condition_parse_incomplete"
        )

    else:
        status = "ok"


    # ========================================================
    # 旧形式互換フィールド
    # ========================================================

    converted[
        "race_id"
    ] = current_race_id

    converted[
        "race_number"
    ] = race_number

    converted[
        "surface"
    ] = surface

    converted[
        "distance"
    ] = distance

    converted[
        "track_condition"
    ] = track_condition

    converted[
        "finished"
    ] = finished

    converted[
        "race_laps"
    ] = laps

    converted[
        "corner_positions"
    ] = corner_positions

    converted[
        "result_count"
    ] = len(
        finishers
    )

    converted[
        "results"
    ] = finishers

    converted[
        "parse_problems"
    ] = problems

    converted[
        "status"
    ] = status


    return converted


# ============================================================
# 全レース変換
# ============================================================

collected_races = []


for item in new_races:
    converted = convert_race(
        item
    )

    if converted is None:
        continue

    race_number = safe_int(
        converted.get(
            "race_number"
        )
    )


    # ========================================================
    # 最重要:
    # 対象R以上は絶対に許可しない
    # ========================================================

    if race_number is None:
        raise RuntimeError(
            "取得レースのR番号が不明です。"
        )


    if (
        race_number
        >= target_race_number
    ):
        raise RuntimeError(
            "対象レース以降のデータが"
            "day_races.json に混入しています。"
        )


    collected_races.append(
        converted
    )


# ============================================================
# R番号順
# ============================================================

collected_races.sort(
    key=lambda item:
        safe_int(
            item.get(
                "race_number"
            )
        )
        or 999
)


# ============================================================
# 同一馬場
# ============================================================

same_surface_race_numbers = []


for item in collected_races:
    if (
        normalize_surface(
            item.get(
                "surface"
            )
        )
        != target_surface
    ):
        continue

    if (
        item.get(
            "finished"
        )
        is not True
    ):
        continue

    same_surface_race_numbers.append(
        item.get(
            "race_number"
        )
    )


# ============================================================
# 取得エラー
# ============================================================

collector_errors = (
    collector_data.get(
        "errors",
        []
    )
    or []
)

if not isinstance(
    collector_errors,
    list,
):
    collector_errors = []


# ============================================================
# 状態
# ============================================================

if target_race_number == 1:
    overall_status = (
        "no_previous_races"
    )

elif collector_errors:
    overall_status = (
        "collected_with_errors"
    )

elif collected_races:
    overall_status = (
        "collected"
    )

else:
    overall_status = (
        "no_previous_races"
    )


# ============================================================
# 新形式を残したまま
# 既存形式を追加
#
# これにより:
#
# 新:
#   races
#   finishers
#   laps
#   corner_orders
#
# 旧:
#   collected_races
#   results
#   race_laps
#   corner_positions
#
# の両方がday_races.jsonに残る。
# ============================================================

output = dict(
    collector_data
)


output[
    "race_id"
] = race_id

output[
    "race_date"
] = race_date

output[
    "racecourse"
] = racecourse

output[
    "surface"
] = target_surface

output[
    "distance"
] = target_distance

output[
    "target_race_number"
] = target_race_number

output[
    "future_race_usage"
] = False

output[
    "status"
] = overall_status

output[
    "same_surface_race_numbers"
] = (
    same_surface_race_numbers
)

output[
    "same_surface_race_count"
] = len(
    same_surface_race_numbers
)

output[
    "collected_race_count"
] = len(
    collected_races
)

output[
    "collected_races"
] = collected_races

output[
    "collector_error_count"
] = len(
    collector_errors
)

output[
    "compatibility_schema"
] = True

output[
    "compatibility_updated_at"
] = now_jst()


# ============================================================
# 最終安全確認
# ============================================================

for item in output[
    "collected_races"
]:
    race_number = safe_int(
        item.get(
            "race_number"
        )
    )

    if (
        race_number is None
        or race_number
        >= target_race_number
    ):
        raise RuntimeError(
            "最終未来レースチェックに"
            "失敗しました。"
        )


if (
    output.get(
        "target_race_included"
    )
    is True
):
    raise RuntimeError(
        "最終チェックで対象レース混入を"
        "検出しました。"
    )


# ============================================================
# 保存
# ============================================================

save_json(
    OUTPUT_FILE,
    output,
)


# ============================================================
# ログ
# ============================================================

print()
print(
    "===== DAY RACES BRIDGE RESULT ====="
)

print(
    "collector:",
    COLLECTOR_FILE,
)

print(
    "mode:",
    output.get(
        "mode"
    ),
)

print(
    "target race:",
    target_race_number,
)

print(
    "collected:",
    len(
        collected_races
    ),
)

print(
    "same surface:",
    same_surface_race_numbers,
)

print(
    "collector errors:",
    len(
        collector_errors
    ),
)

print(
    "future race usage:",
    output.get(
        "future_race_usage"
    ),
)

print(
    "target included:",
    output.get(
        "target_race_included"
    ),
)

print(
    "compatibility schema:",
    output.get(
        "compatibility_schema"
    ),
)

print()


for item in collected_races:
    print(
        f"{item.get('race_number')}R",
        item.get(
            "race_id"
        ),
        item.get(
            "surface"
        ),
        item.get(
            "distance"
        ),
        item.get(
            "track_condition"
        ),
        "status=",
        item.get(
            "status"
        ),
        "results=",
        item.get(
            "result_count"
        ),
        "laps=",
        len(
            item.get(
                "race_laps",
                []
            )
            or []
        ),
    )


print()
print(
    "saved:",
    OUTPUT_FILE,
)

print(
    "==================================="
)
