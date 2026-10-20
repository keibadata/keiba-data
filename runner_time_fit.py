import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta


RUNNER_HISTORY_FILE = "runner_history.json"
HISTORY_DB_FILE = "history_db.json"
RACE_FILE = "race.json"
DAY_BIAS_FILE = "day_bias.json"
OUTPUT_FILE = "runner_time_fit.json"

JST = timezone(timedelta(hours=9))

MIN_BASELINE_SAMPLE = 5
MAD_SCALE = 1.4826
MIN_SCALED_DISPERSION_SECONDS = 0.20


def load_json(path):
    if not os.path.exists(path):
        return {}

    try:
        with open(path, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )


def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value)
    ).strip()


def safe_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def safe_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def normalize_surface(value):
    value = clean(value)

    if value.startswith("芝"):
        return "芝"

    if value.startswith("ダ") or "ダート" in value:
        return "ダート"

    if value.startswith("障"):
        return "障害"

    return value


def parse_time(value):
    text = clean(value)

    if not text:
        return None

    try:
        if ":" in text:
            minute, second = text.split(":", 1)

            return (
                float(minute) * 60.0
                + float(second)
            )

        return float(text)

    except (TypeError, ValueError):
        return None


def parse_date(value):
    text = clean(value)

    if not text:
        return None

    for fmt in (
        "%Y/%m/%d",
        "%Y-%m-%d",
    ):
        try:
            return datetime.strptime(
                text,
                fmt
            ).date()
        except ValueError:
            pass

    return None


def now_jst():
    return datetime.now(
        JST
    ).isoformat(timespec="seconds")


def racecourse_from_meeting(value):
    text = clean(value)

    racecourses = (
        "札幌",
        "函館",
        "福島",
        "新潟",
        "東京",
        "中山",
        "中京",
        "京都",
        "阪神",
        "小倉",
    )

    for racecourse in racecourses:
        if racecourse in text:
            return racecourse

    return ""


def get_race_winner_time(race):
    results = race.get(
        "results",
        []
    ) or []

    for result in results:
        rank = clean(
            result.get("rank")
            or result.get("finish")
        )

        if rank != "1":
            continue

        value = (
            result.get("time")
            or result.get("race_time")
        )

        seconds = parse_time(value)

        if seconds is not None:
            return seconds

    return None


def get_history_races(history_db):
    races = history_db.get(
        "races",
        []
    )

    if isinstance(races, list):
        return races

    return []


def baseline_key(
    racecourse,
    surface,
    distance
):
    return (
        clean(racecourse),
        normalize_surface(surface),
        safe_int(distance),
    )


def build_baselines(
    history_db,
    target_date
):
    pools = {}

    for race in get_history_races(
        history_db
    ):
        if not isinstance(race, dict):
            continue

        race_date = parse_date(
            race.get("race_date")
        )

        # 日付不明は安全側で除外
        if race_date is None:
            continue

        # 対象日以降は使用禁止
        if race_date >= target_date:
            continue

        racecourse = clean(
            race.get("racecourse")
        )

        surface = normalize_surface(
            race.get("surface")
        )

        distance = safe_int(
            race.get("distance")
        )

        if (
            not racecourse
            or not surface
            or distance is None
        ):
            continue

        winner_time = get_race_winner_time(
            race
        )

        if winner_time is None:
            continue

        key = baseline_key(
            racecourse,
            surface,
            distance
        )

        pools.setdefault(
            key,
            []
        ).append({
            "race_id": clean(
                race.get("race_id")
            ),
            "race_date": race_date.isoformat(),
            "race_class": clean(
                race.get("race_class")
            ),
            "age_condition": clean(
                race.get("age_condition")
            ),
            "track_condition": clean(
                race.get("track_condition")
            ),
            "winner_time_seconds": winner_time,
        })

    baselines = {}

    for key, rows in pools.items():
        times = [
            row["winner_time_seconds"]
            for row in rows
        ]

        if len(times) < MIN_BASELINE_SAMPLE:
            continue

        median = statistics.median(
            times
        )

        deviations = [
            abs(value - median)
            for value in times
        ]

        mad = statistics.median(
            deviations
        )

        baselines[key] = {
            "sample_count": len(times),
            "median_seconds": round(
                median,
                3
            ),
            "mad_seconds": round(
                mad,
                3
            ),
            "races": rows,
        }

    return baselines


def classify_time_environment(
    robust_z
):
    if robust_z <= -1.50:
        return "高速"

    if robust_z <= -0.75:
        return "やや高速"

    if robust_z >= 1.50:
        return "低速"

    if robust_z >= 0.75:
        return "やや低速"

    return "標準"


def fit_to_current_bias(
    past_environment,
    current_bias
):
    if not current_bias:
        return 0.0

    if current_bias == "標準":
        if past_environment == "標準":
            return 1.0

        if past_environment in (
            "やや高速",
            "やや低速",
        ):
            return 0.5

        return 0.0

    if current_bias == "高速":
        if past_environment == "高速":
            return 1.0

        if past_environment == "やや高速":
            return 0.7

        if past_environment == "標準":
            return 0.2

        return 0.0

    if current_bias == "やや高速":
        if past_environment == "高速":
            return 0.7

        if past_environment == "やや高速":
            return 1.0

        if past_environment == "標準":
            return 0.5

        return 0.0

    if current_bias == "低速":
        if past_environment == "低速":
            return 1.0

        if past_environment == "やや低速":
            return 0.7

        if past_environment == "標準":
            return 0.2

        return 0.0

    if current_bias == "やや低速":
        if past_environment == "低速":
            return 0.7

        if past_environment == "やや低速":
            return 1.0

        if past_environment == "標準":
            return 0.5

        return 0.0

    return 0.0


race = load_json(
    RACE_FILE
)

runner_history = load_json(
    RUNNER_HISTORY_FILE
)

history_db = load_json(
    HISTORY_DB_FILE
)

day_bias = load_json(
    DAY_BIAS_FILE
)


race_id = clean(
    race.get("race_id")
)

target_date = parse_date(
    race.get("race_date")
    or race.get("date")
)

if not race_id:
    raise SystemExit(
        "ERROR: race_id missing"
    )

if target_date is None:
    raise SystemExit(
        "ERROR: target race date missing"
    )


day_bias_race_id = clean(
    day_bias.get("race_id")
)

day_bias_valid = (
    day_bias_race_id == race_id
    and day_bias.get(
        "future_race_usage"
    ) is False
    and clean(
        day_bias.get("status")
    ) == "analyzed"
)

if day_bias_valid:
    current_time_bias = clean(
        day_bias.get("time_bias")
    )
else:
    current_time_bias = ""


baselines = build_baselines(
    history_db,
    target_date
)


horses_output = []

connected_horse_count = 0
connected_past_race_count = 0


for horse in (
    runner_history.get(
        "horses",
        []
    )
    or []
):
    horse_id = clean(
        horse.get("horse_id")
    )

    horse_name = clean(
        horse.get("horse_name")
    )

    horse_number = clean(
        horse.get("horse_number")
    )

    evaluated = []

    skipped = []

    for past in (
        horse.get(
            "past_races",
            []
        )
        or []
    ):
        past_date = parse_date(
            past.get("date")
        )

        if past_date is None:
            skipped.append({
                "date": clean(
                    past.get("date")
                ),
                "reason": "日付不明",
            })
            continue

        # 対象レース当日・未来は禁止
        if past_date >= target_date:
            skipped.append({
                "date": past_date.isoformat(),
                "reason": "対象日以降のため除外",
            })
            continue

        racecourse = racecourse_from_meeting(
            past.get("meeting")
        )

        surface = normalize_surface(
            past.get("surface")
        )

        distance = safe_int(
            past.get("distance")
        )

        actual_time = parse_time(
            past.get("time")
        )

        if (
            not racecourse
            or not surface
            or distance is None
            or actual_time is None
        ):
            skipped.append({
                "date": past_date.isoformat(),
                "racecourse": racecourse,
                "surface": surface,
                "distance": distance,
                "reason": "時計比較に必要な情報不足",
            })
            continue

        key = baseline_key(
            racecourse,
            surface,
            distance
        )

        baseline = baselines.get(
            key
        )

        if not baseline:
            skipped.append({
                "date": past_date.isoformat(),
                "racecourse": racecourse,
                "surface": surface,
                "distance": distance,
                "reason": "完全一致する基準時計なし",
            })
            continue

        median = baseline[
            "median_seconds"
        ]

        mad = baseline[
            "mad_seconds"
        ]

        delta = (
            actual_time
            - median
        )

        scaled_dispersion = max(
            MAD_SCALE * mad,
            MIN_SCALED_DISPERSION_SECONDS
        )

        robust_z = (
            delta
            / scaled_dispersion
        )

        environment = (
            classify_time_environment(
                robust_z
            )
        )

        current_fit = fit_to_current_bias(
            environment,
            current_time_bias
        )

        evaluated.append({
            "date": past_date.isoformat(),
            "racecourse": racecourse,
            "surface": surface,
            "distance": distance,
            "race_name": clean(
                past.get("race_name")
            ),
            "rank": clean(
                past.get("rank")
            ),
            "actual_time_seconds": round(
                actual_time,
                3
            ),
            "baseline_sample_count":
                baseline["sample_count"],
            "baseline_median_seconds":
                median,
            "baseline_mad_seconds":
                mad,
            "time_delta_seconds": round(
                delta,
                3
            ),
            "robust_z": round(
                robust_z,
                3
            ),
            "time_environment":
                environment,
            "current_time_bias":
                current_time_bias,
            "current_bias_fit":
                current_fit,
        })

        connected_past_race_count += 1

    if evaluated:
        connected_horse_count += 1

        fit_values = [
            row["current_bias_fit"]
            for row in evaluated
        ]

        median_fit = statistics.median(
            fit_values
        )

        matching_count = sum(
            1
            for value in fit_values
            if value >= 0.7
        )

        neutral_count = sum(
            1
            for value in fit_values
            if 0.2 <= value < 0.7
        )

        mismatch_count = sum(
            1
            for value in fit_values
            if value < 0.2
        )

        if median_fit >= 0.7:
            fit_label = "適性根拠あり"

        elif median_fit >= 0.2:
            fit_label = "弱い適性根拠"

        else:
            fit_label = "適性根拠なし"

    else:
        median_fit = None
        matching_count = 0
        neutral_count = 0
        mismatch_count = 0
        fit_label = "未知数"

    horses_output.append({
        "horse_id": horse_id,
        "horse_name": horse_name,
        "horse_number": horse_number,

        "current_time_bias":
            current_time_bias,

        "evaluated_past_race_count":
            len(evaluated),

        "matching_count":
            matching_count,

        "neutral_count":
            neutral_count,

        "mismatch_count":
            mismatch_count,

        "median_current_bias_fit":
            (
                round(
                    median_fit,
                    3
                )
                if median_fit is not None
                else None
            ),

        "time_fit_label":
            fit_label,

        "evaluated_races":
            evaluated,

        "skipped_races":
            skipped,

        "unknown":
            len(evaluated) == 0,
    })


output = {
    "updated_at": now_jst(),

    "target_race_id":
        race_id,

    "target_race_date":
        target_date.isoformat(),

    "future_race_usage":
        False,

    "day_bias_connected":
        day_bias_valid,

    "current_time_bias":
        current_time_bias,

    "baseline_rule": {
        "racecourse_exact":
            True,

        "surface_exact":
            True,

        "distance_exact":
            True,

        "minimum_sample":
            MIN_BASELINE_SAMPLE,

        "target_date_or_future_excluded":
            True,

        "unknown_not_penalized":
            True,
    },

    "baseline_condition_count":
        len(baselines),

    "target_horse_count":
        len(
            runner_history.get(
                "horses",
                []
            )
            or []
        ),

    "connected_horse_count":
        connected_horse_count,

    "connected_past_race_count":
        connected_past_race_count,

    "horses":
        horses_output,
}


save_json(
    OUTPUT_FILE,
    output
)


print()
print(
    "===== RUNNER TIME FIT ====="
)

print(
    "target race:",
    race_id
)

print(
    "target date:",
    target_date
)

print(
    "day bias connected:",
    day_bias_valid
)

print(
    "current time bias:",
    current_time_bias
)

print(
    "baseline conditions:",
    len(baselines)
)

print(
    "horses:",
    len(horses_output)
)

print(
    "connected horses:",
    connected_horse_count
)

print(
    "connected past races:",
    connected_past_race_count
)

for horse in horses_output:
    print(
        horse["horse_number"],
        horse["horse_name"],
        "評価走",
        horse[
            "evaluated_past_race_count"
        ],
        "時計適性",
        horse[
            "time_fit_label"
        ],
        "fit",
        horse[
            "median_current_bias_fit"
        ]
    )

print(
    "saved:",
    OUTPUT_FILE
)

print(
    "==========================="
)
