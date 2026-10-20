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

STRONG_THRESHOLD = 1.50
MILD_THRESHOLD = 0.75


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

    text = (
        text
        .replace("年", "/")
        .replace("月", "/")
        .replace("日", "")
        .replace("-", "/")
        .replace(".", "/")
    )

    match = re.search(
        r"(\d{4})/(\d{1,2})/(\d{1,2})",
        text
    )

    if not match:
        return None

    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3))
        ).date()

    except Exception:
        return None


def now_jst():
    return datetime.now(
        JST
    ).isoformat(timespec="seconds")


def normalize_surface(value):
    text = clean(value)

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


def normalize_class(value):
    text = clean(value)

    if not text:
        return ""

    upper = text.upper()

    if "G1" in upper or "Ｇ１" in text:
        return "G1"

    if "G2" in upper or "Ｇ２" in text:
        return "G2"

    if "G3" in upper or "Ｇ３" in text:
        return "G3"

    if (
        "OPEN" in upper
        or text == "OP"
        or "オープン" in text
    ):
        return "OP"

    if (
        "3勝" in text
        or "1600万" in text
    ):
        return "3勝クラス"

    if (
        "2勝" in text
        or "1000万" in text
    ):
        return "2勝クラス"

    if (
        "1勝" in text
        or "500万" in text
    ):
        return "1勝クラス"

    if "未勝利" in text:
        return "未勝利"

    if "新馬" in text:
        return "新馬"

    return text


def normalize_age(value):
    text = clean(value)

    if not text:
        return ""

    if "2歳" in text:
        return "2歳"

    if "3歳" in text:
        return "3歳"

    if (
        "4歳以上" in text
        or "4才以上" in text
    ):
        return "4歳以上"

    if (
        "3歳以上" in text
        or "3才以上" in text
    ):
        return "3歳以上"

    return text


def get_history_races(history_db):
    races = history_db.get(
        "races",
        []
    )

    if isinstance(races, list):
        return races

    return []


def get_winner_time(race):
    results = (
        race.get("results", [])
        or []
    )

    for result in results:
        rank = clean(
            result.get("rank")
            or result.get("finish")
        )

        rank_match = re.search(
            r"\d+",
            rank
        )

        if (
            not rank_match
            or int(rank_match.group()) != 1
        ):
            continue

        value = (
            result.get("time")
            or result.get("race_time")
        )

        seconds = parse_time(
            value
        )

        if seconds is not None:
            return seconds

    return None


def build_race_index(
    history_races,
    target_date
):
    index = {}

    for race in history_races:
        if not isinstance(
            race,
            dict
        ):
            continue

        race_id = clean(
            race.get("race_id")
        )

        if not race_id:
            continue

        race_date = parse_date(
            race.get("race_date")
            or race.get("date")
        )

        if race_date is None:
            continue

        # 対象日以降は絶対使用しない
        if race_date >= target_date:
            continue

        index[race_id] = race

    return index


def baseline_key(
    racecourse,
    surface,
    distance,
    race_class,
    age_condition
):
    return (
        clean(racecourse),
        normalize_surface(surface),
        safe_int(distance),
        normalize_class(race_class),
        normalize_age(age_condition),
    )


def build_baselines(
    history_races,
    target_date
):
    pools = {}

    for race in history_races:
        if not isinstance(
            race,
            dict
        ):
            continue

        race_date = parse_date(
            race.get("race_date")
            or race.get("date")
        )

        if race_date is None:
            continue

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

        race_class = normalize_class(
            race.get("race_class")
        )

        age_condition = normalize_age(
            race.get("age_condition")
        )

        winner_time = get_winner_time(
            race
        )

        if (
            not racecourse
            or not surface
            or distance is None
            or not race_class
            or not age_condition
            or winner_time is None
        ):
            continue

        key = baseline_key(
            racecourse,
            surface,
            distance,
            race_class,
            age_condition
        )

        pools.setdefault(
            key,
            []
        ).append({
            "race_id":
                clean(
                    race.get("race_id")
                ),

            "race_date":
                race_date.isoformat(),

            "winner_time_seconds":
                winner_time,
        })

    baselines = {}

    for key, rows in pools.items():
        times = [
            row[
                "winner_time_seconds"
            ]
            for row in rows
        ]

        if (
            len(times)
            < MIN_BASELINE_SAMPLE
        ):
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
            "sample_count":
                len(times),

            "median_seconds":
                round(
                    median,
                    3
                ),

            "mad_seconds":
                round(
                    mad,
                    3
                ),

            "race_ids": [
                row["race_id"]
                for row in rows
            ],
        }

    return baselines


def classify_environment(
    robust_z
):
    if robust_z <= -STRONG_THRESHOLD:
        return "高速"

    if robust_z <= -MILD_THRESHOLD:
        return "やや高速"

    if robust_z >= STRONG_THRESHOLD:
        return "低速"

    if robust_z >= MILD_THRESHOLD:
        return "やや低速"

    return "標準"


def environment_fit(
    historical_environment,
    current_environment
):
    if (
        not historical_environment
        or not current_environment
    ):
        return None

    scale = {
        "高速": -2,
        "やや高速": -1,
        "標準": 0,
        "やや低速": 1,
        "低速": 2,
    }

    if (
        historical_environment
        not in scale
        or current_environment
        not in scale
    ):
        return None

    difference = abs(
        scale[
            historical_environment
        ]
        - scale[
            current_environment
        ]
    )

    if difference == 0:
        return 1.0

    if difference == 1:
        return 0.7

    if difference == 2:
        return 0.3

    return 0.0


def classify_fit(
    values
):
    if not values:
        return "未知数"

    median_fit = statistics.median(
        values
    )

    if median_fit >= 0.7:
        return "同系統時計環境の経験あり"

    if median_fit >= 0.3:
        return "中間"

    return "異なる時計環境の経験中心"


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
        "ERROR: target date missing"
    )


if (
    clean(
        runner_history.get(
            "target_race_id"
        )
    )
    != race_id
):
    raise SystemExit(
        "ERROR: runner_history race mismatch"
    )


if (
    runner_history.get(
        "future_race_usage"
    )
    is not False
):
    raise SystemExit(
        "ERROR: runner_history future leak"
    )


if (
    runner_history.get(
        "leak_check_passed"
    )
    is not True
):
    raise SystemExit(
        "ERROR: runner_history leak check failed"
    )


day_bias_valid = (
    clean(
        day_bias.get("race_id")
    )
    == race_id
    and day_bias.get(
        "future_race_usage"
    )
    is False
    and clean(
        day_bias.get("status")
    )
    == "analyzed"
)


if day_bias_valid:
    current_time_bias = clean(
        day_bias.get(
            "time_bias"
        )
    )
else:
    current_time_bias = ""


history_races = get_history_races(
    history_db
)

race_index = build_race_index(
    history_races,
    target_date
)

baselines = build_baselines(
    history_races,
    target_date
)


horses_output = []

connected_horse_count = 0
connected_past_race_count = 0

missing_race_id_count = 0
race_not_in_history_db_count = 0
baseline_missing_count = 0


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
                "reason":
                    "過去走日付不明"
            })
            continue

        if past_date >= target_date:
            skipped.append({
                "date":
                    past_date.isoformat(),

                "reason":
                    "対象日以降のため除外"
            })
            continue

        past_race_id = clean(
            past.get("race_id")
        )

        if not past_race_id:
            missing_race_id_count += 1

            skipped.append({
                "date":
                    past_date.isoformat(),

                "race_name":
                    clean(
                        past.get(
                            "race_name"
                        )
                    ),

                "reason":
                    "race_idなし"
            })
            continue

        historical_race = (
            race_index.get(
                past_race_id
            )
        )

        if not historical_race:
            race_not_in_history_db_count += 1

            skipped.append({
                "race_id":
                    past_race_id,

                "date":
                    past_date.isoformat(),

                "reason":
                    "history_dbに同一レースなし"
            })
            continue

        racecourse = clean(
            historical_race.get(
                "racecourse"
            )
        )

        surface = normalize_surface(
            historical_race.get(
                "surface"
            )
        )

        distance = safe_int(
            historical_race.get(
                "distance"
            )
        )

        race_class = normalize_class(
            historical_race.get(
                "race_class"
            )
        )

        age_condition = normalize_age(
            historical_race.get(
                "age_condition"
            )
        )

        track_condition = clean(
            historical_race.get(
                "track_condition"
            )
        )

        winner_time = get_winner_time(
            historical_race
        )

        if (
            not racecourse
            or not surface
            or distance is None
            or not race_class
            or not age_condition
            or winner_time is None
        ):
            skipped.append({
                "race_id":
                    past_race_id,

                "reason":
                    "過去レース情報不足"
            })
            continue

        key = baseline_key(
            racecourse,
            surface,
            distance,
            race_class,
            age_condition
        )

        baseline = baselines.get(
            key
        )

        if not baseline:
            baseline_missing_count += 1

            skipped.append({
                "race_id":
                    past_race_id,

                "racecourse":
                    racecourse,

                "surface":
                    surface,

                "distance":
                    distance,

                "race_class":
                    race_class,

                "age_condition":
                    age_condition,

                "reason":
                    "同条件・同クラス・同年齢の基準時計不足"
            })
            continue

        # 自分自身のレースを基準サンプルから除外
        baseline_race_ids = (
            baseline.get(
                "race_ids",
                []
            )
            or []
        )

        comparison_times = []

        for comparison_race_id in (
            baseline_race_ids
        ):
            if (
                comparison_race_id
                == past_race_id
            ):
                continue

            comparison_race = (
                race_index.get(
                    comparison_race_id
                )
            )

            if not comparison_race:
                continue

            comparison_time = (
                get_winner_time(
                    comparison_race
                )
            )

            if (
                comparison_time
                is not None
            ):
                comparison_times.append(
                    comparison_time
                )

        if (
            len(comparison_times)
            < MIN_BASELINE_SAMPLE
        ):
            baseline_missing_count += 1

            skipped.append({
                "race_id":
                    past_race_id,

                "reason":
                    "自己レース除外後の基準時計サンプル不足",

                "comparison_sample_count":
                    len(
                        comparison_times
                    ),
            })
            continue

        median = statistics.median(
            comparison_times
        )

        deviations = [
            abs(value - median)
            for value in comparison_times
        ]

        mad = statistics.median(
            deviations
        )

        scaled_dispersion = max(
            MAD_SCALE * mad,
            MIN_SCALED_DISPERSION_SECONDS
        )

        delta = (
            winner_time
            - median
        )

        robust_z = (
            delta
            / scaled_dispersion
        )

        environment = (
            classify_environment(
                robust_z
            )
        )

        fit = environment_fit(
            environment,
            current_time_bias
        )

        evaluated.append({
            "race_id":
                past_race_id,

            "date":
                past_date.isoformat(),

            "race_name":
                clean(
                    historical_race.get(
                        "race_name"
                    )
                    or past.get(
                        "race_name"
                    )
                ),

            "racecourse":
                racecourse,

            "surface":
                surface,

            "distance":
                distance,

            "race_class":
                race_class,

            "age_condition":
                age_condition,

            "track_condition":
                track_condition,

            # ここで使うのは馬自身の時計ではなく
            # そのレースの勝ち時計
            "race_winner_time_seconds":
                round(
                    winner_time,
                    3
                ),

            "baseline_sample_count":
                len(
                    comparison_times
                ),

            "baseline_median_seconds":
                round(
                    median,
                    3
                ),

            "baseline_mad_seconds":
                round(
                    mad,
                    3
                ),

            "time_delta_seconds":
                round(
                    delta,
                    3
                ),

            "robust_z":
                round(
                    robust_z,
                    3
                ),

            "historical_time_environment":
                environment,

            "current_time_bias":
                current_time_bias,

            "current_bias_fit":
                (
                    round(
                        fit,
                        3
                    )
                    if fit is not None
                    else None
                ),

            # 馬自身の着順は保持するが
            # 時計環境判定には使用しない
            "horse_rank":
                clean(
                    past.get("rank")
                ),
        })

        connected_past_race_count += 1

    fit_values = [
        row["current_bias_fit"]
        for row in evaluated
        if row.get(
            "current_bias_fit"
        )
        is not None
    ]

    if evaluated:
        connected_horse_count += 1

    if fit_values:
        median_fit = (
            statistics.median(
                fit_values
            )
        )

        fit_label = classify_fit(
            fit_values
        )

        matching_count = sum(
            1
            for value in fit_values
            if value >= 0.7
        )

        middle_count = sum(
            1
            for value in fit_values
            if 0.3 <= value < 0.7
        )

        mismatch_count = sum(
            1
            for value in fit_values
            if value < 0.3
        )

    else:
        median_fit = None
        fit_label = "未知数"

        matching_count = 0
        middle_count = 0
        mismatch_count = 0

    horses_output.append({
        "horse_id":
            horse_id,

        "horse_name":
            horse_name,

        "horse_number":
            horse_number,

        "current_time_bias":
            current_time_bias,

        "evaluated_past_race_count":
            len(evaluated),

        "matching_count":
            matching_count,

        "middle_count":
            middle_count,

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
            not bool(
                fit_values
            ),
    })


future_race_usage = False

for horse in horses_output:
    for row in horse.get(
        "evaluated_races",
        []
    ):
        row_date = parse_date(
            row.get("date")
        )

        if (
            row_date is None
            or row_date >= target_date
        ):
            future_race_usage = True


output = {
    "updated_at":
        now_jst(),

    "target_race_id":
        race_id,

    "target_date":
        target_date.isoformat(),

    "current_time_bias":
        current_time_bias,

    "future_race_usage":
        future_race_usage,

    "leak_check_passed":
        not future_race_usage,

    "method":
        (
            "過去走race_idからhistory_dbの同一レースを接続し、"
            "馬自身の走破時計ではなく当該レースの勝ち時計を使用。"
            "競馬場・芝ダート・距離・クラス・年齢条件が一致する"
            "過去レース群の中央値/MADと比較して時計環境を判定。"
            "対象レース当日以降は使用せず、"
            "未知数は減点しない。"
        ),

    "target_horse_count":
        len(horses_output),

    "connected_horse_count":
        connected_horse_count,

    "connected_past_race_count":
        connected_past_race_count,

    "baseline_condition_count":
        len(baselines),

    "missing_race_id_count":
        missing_race_id_count,

    "race_not_in_history_db_count":
        race_not_in_history_db_count,

    "baseline_missing_count":
        baseline_missing_count,

    "horses":
        horses_output,
}


if future_race_usage:
    raise SystemExit(
        "ERROR: future race leakage detected"
    )


save_json(
    OUTPUT_FILE,
    output
)


print("")
print(
    "===== Runner Time Fit ====="
)

print(
    "target race:",
    race_id
)

print(
    "target date:",
    target_date.isoformat()
)

print(
    "current time bias:",
    current_time_bias or "不明"
)

print(
    "baseline conditions:",
    len(baselines)
)

print(
    "connected horses:",
    f"{connected_horse_count}/{len(horses_output)}"
)

print(
    "connected past races:",
    connected_past_race_count
)

print(
    "missing race ids:",
    missing_race_id_count
)

print(
    "race not in history db:",
    race_not_in_history_db_count
)

print(
    "baseline missing:",
    baseline_missing_count
)

print(
    "future race usage:",
    future_race_usage
)

print(
    "leak check passed:",
    not future_race_usage
)

print("")
