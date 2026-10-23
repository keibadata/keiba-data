import json
import os
import re
import statistics
from datetime import datetime, timezone, timedelta


RUNNER_HISTORY_FILE = "runner_history.json"
RUNNER_RACE_DB_FILE = "runner_race_db.json"
HISTORY_DB_FILE = "history_db.json"
RACE_FILE = "race.json"
DAY_BIAS_FILE = "day_bias.json"
OUTPUT_FILE = "runner_time_fit.json"

JST = timezone(timedelta(hours=9))

# 時計適性は補助診断。
# 少数サンプルを強い能力評価には使わない。
MIN_EXACT_SAMPLE = 3
MIN_RELAXED_SAMPLE = 4
MIN_DISTANCE_SAMPLE = 5

MAD_SCALE = 1.4826
MIN_SCALED_DISPERSION_SECONDS = 0.20

STRONG_THRESHOLD = 1.50
MILD_THRESHOLD = 0.75

JRA_VENUE_CODES = {
    "01", "02", "03", "04", "05",
    "06", "07", "08", "09", "10",
}


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
            indent=2,
        )


def clean(value):
    if value is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        str(value),
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
        text,
    )

    if not match:
        return None

    try:
        return datetime(
            int(match.group(1)),
            int(match.group(2)),
            int(match.group(3)),
        ).date()

    except Exception:
        return None


def now_jst():
    return datetime.now(
        JST
    ).isoformat(
        timespec="seconds"
    )


def valid_race_id(value):
    return bool(
        re.fullmatch(
            r"\d{12}",
            clean(value),
        )
    )


def is_jra_race_id(value):
    race_id = clean(value)

    if not valid_race_id(race_id):
        return False

    return (
        race_id[4:6]
        in JRA_VENUE_CODES
    )


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

    if (
        "G1" in upper
        or "Ｇ１" in text
        or "GⅠ" in upper
    ):
        return "G1"

    if (
        "G2" in upper
        or "Ｇ２" in text
        or "GⅡ" in upper
    ):
        return "G2"

    if (
        "G3" in upper
        or "Ｇ３" in text
        or "GⅢ" in upper
    ):
        return "G3"

    if (
        "LISTED" in upper
        or text == "L"
    ):
        return "L"

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


def class_group(value):
    """
    完全一致が不足した場合だけ使う
    緩和用クラスグループ。
    """
    value = normalize_class(value)

    if value in {
        "G1",
        "G2",
        "G3",
        "L",
        "OP",
    }:
        return "OPEN_GROUP"

    if value in {
        "3勝クラス",
        "2勝クラス",
        "1勝クラス",
    }:
        return value

    if value in {
        "未勝利",
        "新馬",
    }:
        return value

    return value


def normalize_age(value):
    text = clean(value)

    if not text:
        return ""

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

    if (
        "2歳以上" in text
        or "2才以上" in text
    ):
        return "2歳以上"

    if "2歳" in text:
        return "2歳"

    if "3歳" in text:
        return "3歳"

    if "4歳" in text:
        return "4歳"

    return text


def get_history_races(database):
    races = database.get(
        "races",
        [],
    )

    if isinstance(races, list):
        return [
            race
            for race in races
            if isinstance(race, dict)
        ]

    return []


def get_winner_time(race):
    results = (
        race.get(
            "results",
            [],
        )
        or []
    )

    for result in results:
        if not isinstance(
            result,
            dict,
        ):
            continue

        rank = clean(
            result.get("rank")
            or result.get("finish")
        )

        match = re.search(
            r"\d+",
            rank,
        )

        if not match:
            continue

        if int(match.group()) != 1:
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
    races,
    target_date,
):
    index = {}

    for race in races:
        race_id = clean(
            race.get(
                "race_id"
            )
        )

        if not race_id:
            continue

        race_date = parse_date(
            race.get("race_date")
            or race.get("date")
        )

        if race_date is None:
            continue

        # 未来リーク禁止
        if race_date >= target_date:
            continue

        index[
            race_id
        ] = race

    return index


def race_signature(race):
    return {
        "racecourse":
            clean(
                race.get(
                    "racecourse"
                )
            ),

        "surface":
            normalize_surface(
                race.get(
                    "surface"
                )
            ),

        "distance":
            safe_int(
                race.get(
                    "distance"
                )
            ),

        "race_class":
            normalize_class(
                race.get(
                    "race_class"
                )
            ),

        "class_group":
            class_group(
                race.get(
                    "race_class"
                )
            ),

        "age_condition":
            normalize_age(
                race.get(
                    "age_condition"
                )
            ),
    }


def valid_reference_race(
    race,
    target_date,
):
    if not isinstance(
        race,
        dict,
    ):
        return False

    race_id = clean(
        race.get(
            "race_id"
        )
    )

    if not is_jra_race_id(
        race_id
    ):
        return False

    race_date = parse_date(
        race.get("race_date")
        or race.get("date")
    )

    if race_date is None:
        return False

    if race_date >= target_date:
        return False

    signature = race_signature(
        race
    )

    if not signature[
        "racecourse"
    ]:
        return False

    if not signature[
        "surface"
    ]:
        return False

    if signature[
        "distance"
    ] is None:
        return False

    if get_winner_time(
        race
    ) is None:
        return False

    return True


def merge_reference_races(
    runner_races,
    history_races,
    target_date,
):
    """
    runner_race_db と history_db を
    基準時計候補として統合。

    同一race_idは1件だけ。
    対象日以降は使用しない。
    地方は現在除外。
    """
    index = {}

    for source_name, races in (
        (
            "history_db",
            history_races,
        ),
        (
            "runner_race_db",
            runner_races,
        ),
    ):
        for race in races:
            if not valid_reference_race(
                race,
                target_date,
            ):
                continue

            race_id = clean(
                race.get(
                    "race_id"
                )
            )

            item = dict(
                race
            )

            item[
                "_time_fit_source"
            ] = source_name

            index[
                race_id
            ] = item

    return list(
        index.values()
    )


def select_baseline_candidates(
    target_race,
    reference_races,
):
    """
    段階的に基準時計を探す。

    LEVEL 1
      競馬場・芝ダ・距離・クラス・年齢 完全一致

    LEVEL 2
      競馬場・芝ダ・距離・クラス一致
      年齢条件だけ緩和

    LEVEL 3
      競馬場・芝ダ・距離・クラスグループ一致

    LEVEL 4
      競馬場・芝ダ・距離一致

    時計適性は補助診断なので、
    緩和レベルも必ず出力する。
    """
    target = race_signature(
        target_race
    )

    if (
        not target["racecourse"]
        or not target["surface"]
        or target["distance"] is None
    ):
        return (
            [],
            "NONE",
            "基準条件不足",
        )

    levels = [
        {
            "name":
                "EXACT",

            "description":
                "競馬場・芝ダ・距離・クラス・年齢一致",

            "minimum":
                MIN_EXACT_SAMPLE,

            "match":
                lambda sig: (
                    sig["racecourse"]
                    == target["racecourse"]
                    and sig["surface"]
                    == target["surface"]
                    and sig["distance"]
                    == target["distance"]
                    and sig["race_class"]
                    == target["race_class"]
                    and sig["age_condition"]
                    == target["age_condition"]
                    and bool(
                        target["race_class"]
                    )
                    and bool(
                        target["age_condition"]
                    )
                ),
        },

        {
            "name":
                "CLASS_MATCH",

            "description":
                "競馬場・芝ダ・距離・クラス一致",

            "minimum":
                MIN_RELAXED_SAMPLE,

            "match":
                lambda sig: (
                    sig["racecourse"]
                    == target["racecourse"]
                    and sig["surface"]
                    == target["surface"]
                    and sig["distance"]
                    == target["distance"]
                    and sig["race_class"]
                    == target["race_class"]
                    and bool(
                        target["race_class"]
                    )
                ),
        },

        {
            "name":
                "CLASS_GROUP",

            "description":
                "競馬場・芝ダ・距離・クラス群一致",

            "minimum":
                MIN_RELAXED_SAMPLE,

            "match":
                lambda sig: (
                    sig["racecourse"]
                    == target["racecourse"]
                    and sig["surface"]
                    == target["surface"]
                    and sig["distance"]
                    == target["distance"]
                    and sig["class_group"]
                    == target["class_group"]
                    and bool(
                        target["class_group"]
                    )
                ),
        },

        {
            "name":
                "COURSE_DISTANCE",

            "description":
                "競馬場・芝ダ・距離一致",

            "minimum":
                MIN_DISTANCE_SAMPLE,

            "match":
                lambda sig: (
                    sig["racecourse"]
                    == target["racecourse"]
                    and sig["surface"]
                    == target["surface"]
                    and sig["distance"]
                    == target["distance"]
                ),
        },
    ]

    target_race_id = clean(
        target_race.get(
            "race_id"
        )
    )

    for level in levels:
        rows = []

        for race in reference_races:
            race_id = clean(
                race.get(
                    "race_id"
                )
            )

            # 自分自身のレースは
            # 基準から必ず除外
            if (
                race_id
                == target_race_id
            ):
                continue

            sig = race_signature(
                race
            )

            if not level[
                "match"
            ](
                sig
            ):
                continue

            winner_time = (
                get_winner_time(
                    race
                )
            )

            if winner_time is None:
                continue

            rows.append({
                "race_id":
                    race_id,

                "winner_time_seconds":
                    winner_time,

                "source":
                    clean(
                        race.get(
                            "_time_fit_source"
                        )
                    ),
            })

        if (
            len(rows)
            >= level["minimum"]
        ):
            return (
                rows,
                level["name"],
                level["description"],
            )

    return (
        [],
        "NONE",
        "基準時計サンプル不足",
    )


def calculate_environment(
    winner_time,
    baseline_rows,
):
    times = [
        row[
            "winner_time_seconds"
        ]
        for row in baseline_rows
    ]

    if not times:
        return None

    median = statistics.median(
        times
    )

    deviations = [
        abs(
            value
            - median
        )
        for value in times
    ]

    mad = statistics.median(
        deviations
    )

    scaled_dispersion = max(
        MAD_SCALE * mad,
        MIN_SCALED_DISPERSION_SECONDS,
    )

    delta = (
        winner_time
        - median
    )

    robust_z = (
        delta
        / scaled_dispersion
    )

    return {
        "sample_count":
            len(times),

        "median":
            median,

        "mad":
            mad,

        "delta":
            delta,

        "robust_z":
            robust_z,
    }


def classify_environment(
    robust_z,
):
    if (
        robust_z
        <= -STRONG_THRESHOLD
    ):
        return "高速"

    if (
        robust_z
        <= -MILD_THRESHOLD
    ):
        return "やや高速"

    if (
        robust_z
        >= STRONG_THRESHOLD
    ):
        return "低速"

    if (
        robust_z
        >= MILD_THRESHOLD
    ):
        return "やや低速"

    return "標準"


def normalize_current_bias(
    value,
):
    text = clean(value)

    mapping = {
        "高速":
            "高速",

        "やや高速":
            "やや高速",

        "標準":
            "標準",

        "やや低速":
            "やや低速",

        "低速":
            "低速",
    }

    return mapping.get(
        text,
        "",
    )


def environment_fit(
    historical_environment,
    current_environment,
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


def classify_fit(values):
    if not values:
        return "未知数"

    median_fit = (
        statistics.median(
            values
        )
    )

    if median_fit >= 0.7:
        return (
            "同系統時計環境の経験あり"
        )

    if median_fit >= 0.3:
        return "中間"

    return (
        "異なる時計環境の経験中心"
    )


# =========================================================
# Load
# =========================================================

race = load_json(
    RACE_FILE
)

runner_history = load_json(
    RUNNER_HISTORY_FILE
)

runner_race_db = load_json(
    RUNNER_RACE_DB_FILE
)

history_db = load_json(
    HISTORY_DB_FILE
)

day_bias = load_json(
    DAY_BIAS_FILE
)


race_id = clean(
    race.get(
        "race_id"
    )
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


# =========================================================
# Leak / consistency checks
# =========================================================

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


runner_db_target = clean(
    runner_race_db.get(
        "target_race_id"
    )
)

if (
    runner_db_target
    and runner_db_target
    != race_id
):
    raise SystemExit(
        "ERROR: runner_race_db race mismatch"
    )


if (
    runner_race_db.get(
        "future_race_usage"
    )
    is True
):
    raise SystemExit(
        "ERROR: runner_race_db future leak"
    )


# =========================================================
# Current time bias
# =========================================================

day_bias_valid = (
    clean(
        day_bias.get(
            "race_id"
        )
    )
    == race_id

    and day_bias.get(
        "future_race_usage"
    )
    is False

    and clean(
        day_bias.get(
            "status"
        )
    )
    == "analyzed"
)


if day_bias_valid:
    current_time_bias = (
        normalize_current_bias(
            day_bias.get(
                "time_bias"
            )
        )
    )
else:
    current_time_bias = ""


# =========================================================
# Build databases
# =========================================================

runner_races = (
    get_history_races(
        runner_race_db
    )
)

history_races = (
    get_history_races(
        history_db
    )
)


# 実際の過去走接続用
race_index = (
    build_race_index(
        runner_races,
        target_date,
    )
)


# 基準時計候補
# history_dbだけに依存せず、
# runner_race_dbの中央過去走も利用。
reference_races = (
    merge_reference_races(
        runner_races,
        history_races,
        target_date,
    )
)


# =========================================================
# Analyze horses
# =========================================================

horses_output = []

connected_horse_count = 0
connected_past_race_count = 0

missing_race_id_count = 0
race_not_in_runner_race_db_count = 0
baseline_missing_count = 0

exact_baseline_count = 0
class_match_baseline_count = 0
class_group_baseline_count = 0
course_distance_baseline_count = 0


for horse in (
    runner_history.get(
        "horses",
        [],
    )
    or []
):
    horse_id = clean(
        horse.get(
            "horse_id"
        )
    )

    horse_name = clean(
        horse.get(
            "horse_name"
        )
    )

    horse_number = clean(
        horse.get(
            "horse_number"
        )
    )

    evaluated = []
    skipped = []

    for past in (
        horse.get(
            "past_races",
            [],
        )
        or []
    ):
        past_date = parse_date(
            past.get("date")
            or past.get(
                "race_date"
            )
        )

        if past_date is None:
            skipped.append({
                "reason":
                    "過去走日付不明",
            })
            continue

        if (
            past_date
            >= target_date
        ):
            skipped.append({
                "date":
                    past_date.isoformat(),

                "reason":
                    "対象日以降のため除外",
            })
            continue

        past_race_id = clean(
            past.get(
                "race_id"
            )
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
                    "race_idなし",
            })
            continue

        # 今回は地方を評価対象外
        if not is_jra_race_id(
            past_race_id
        ):
            race_not_in_runner_race_db_count += 1

            skipped.append({
                "race_id":
                    past_race_id,

                "date":
                    past_date.isoformat(),

                "reason":
                    "地方過去走は現在対象外",
            })
            continue

        historical_race = (
            race_index.get(
                past_race_id
            )
        )

        if not historical_race:
            race_not_in_runner_race_db_count += 1

            skipped.append({
                "race_id":
                    past_race_id,

                "date":
                    past_date.isoformat(),

                "reason":
                    "runner_race_dbに同一中央レースなし",
            })
            continue

        signature = race_signature(
            historical_race
        )

        racecourse = (
            signature[
                "racecourse"
            ]
        )

        surface = (
            signature[
                "surface"
            ]
        )

        distance = (
            signature[
                "distance"
            ]
        )

        race_class = (
            signature[
                "race_class"
            ]
        )

        age_condition = (
            signature[
                "age_condition"
            ]
        )

        track_condition = clean(
            historical_race.get(
                "track_condition"
            )
        )

        winner_time = (
            get_winner_time(
                historical_race
            )
        )

        if (
            not racecourse
            or not surface
            or distance is None
            or winner_time is None
        ):
            skipped.append({
                "race_id":
                    past_race_id,

                "reason":
                    "過去レース基本情報不足",
            })
            continue

        (
            baseline_rows,
            baseline_level,
            baseline_description,
        ) = select_baseline_candidates(
            historical_race,
            reference_races,
        )

        if not baseline_rows:
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
                    "段階緩和後も基準時計サンプル不足",
            })
            continue

        calculation = (
            calculate_environment(
                winner_time,
                baseline_rows,
            )
        )

        if calculation is None:
            baseline_missing_count += 1
            continue

        robust_z = (
            calculation[
                "robust_z"
            ]
        )

        environment = (
            classify_environment(
                robust_z
            )
        )

        fit = environment_fit(
            environment,
            current_time_bias,
        )

        if (
            baseline_level
            == "EXACT"
        ):
            exact_baseline_count += 1

        elif (
            baseline_level
            == "CLASS_MATCH"
        ):
            class_match_baseline_count += 1

        elif (
            baseline_level
            == "CLASS_GROUP"
        ):
            class_group_baseline_count += 1

        elif (
            baseline_level
            == "COURSE_DISTANCE"
        ):
            course_distance_baseline_count += 1

        source_counts = {}

        for row in baseline_rows:
            source = (
                row.get(
                    "source"
                )
                or "unknown"
            )

            source_counts[
                source
            ] = (
                source_counts.get(
                    source,
                    0,
                )
                + 1
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

            # 馬自身の走破時計ではなく
            # レース全体の時計環境を見るため
            # 勝ち時計を使用。
            "race_winner_time_seconds":
                round(
                    winner_time,
                    3,
                ),

            "baseline_level":
                baseline_level,

            "baseline_description":
                baseline_description,

            "baseline_sample_count":
                calculation[
                    "sample_count"
                ],

            "baseline_source_counts":
                source_counts,

            "baseline_median_seconds":
                round(
                    calculation[
                        "median"
                    ],
                    3,
                ),

            "baseline_mad_seconds":
                round(
                    calculation[
                        "mad"
                    ],
                    3,
                ),

            "time_delta_seconds":
                round(
                    calculation[
                        "delta"
                    ],
                    3,
                ),

            "robust_z":
                round(
                    robust_z,
                    3,
                ),

            "historical_time_environment":
                environment,

            "current_time_bias":
                current_time_bias,

            "current_bias_fit":
                (
                    round(
                        fit,
                        3,
                    )
                    if fit is not None
                    else None
                ),

            # 着順は保持するだけ。
            # 時計環境判定には使用しない。
            "horse_rank":
                clean(
                    past.get(
                        "rank"
                    )
                ),
        })

        connected_past_race_count += 1

    fit_values = [
        row[
            "current_bias_fit"
        ]
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

        fit_label = (
            classify_fit(
                fit_values
            )
        )

        matching_count = sum(
            1
            for value in fit_values
            if value >= 0.7
        )

        middle_count = sum(
            1
            for value in fit_values
            if (
                0.3
                <= value
                < 0.7
            )
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
            len(
                evaluated
            ),

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
                    3,
                )
                if median_fit
                is not None
                else None
            ),

        "time_fit_label":
            fit_label,

        "evaluated_races":
            evaluated,

        "skipped_races":
            skipped,

        # 未知数は減点しない
        "unknown":
            not bool(
                fit_values
            ),
    })


# =========================================================
# Final leak check
# =========================================================

future_race_usage = False

for horse in horses_output:
    for row in horse.get(
        "evaluated_races",
        [],
    ):
        row_date = parse_date(
            row.get(
                "date"
            )
        )

        if (
            row_date is None
            or row_date
            >= target_date
        ):
            future_race_usage = True


if future_race_usage:
    raise SystemExit(
        "ERROR: future race leakage detected"
    )


# =========================================================
# Output
# =========================================================

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
        False,

    "leak_check_passed":
        True,

    "method":
        (
            "中央競馬のみを対象。"
            "runner_historyの過去走race_idをrunner_race_dbの"
            "同一レースへ接続し、馬自身の着順や走破時計ではなく"
            "当該レースの勝ち時計から時計環境を診断する。"
            "基準時計はhistory_dbとrunner_race_dbの対象日前レースを統合し、"
            "同一レース自身を除外したうえで、"
            "競馬場・芝ダート・距離・クラス・年齢の完全一致から開始。"
            "サンプル不足時のみ年齢、クラス群の順に段階的に緩和し、"
            "最終的に競馬場・芝ダート・距離一致まで使用する。"
            "緩和レベルは各レースに明示する。"
            "時計適性は診断補助のみで能力順位を直接作らず、"
            "未知数は減点しない。対象レース当日以降は使用しない。"
        ),

    "target_horse_count":
        len(
            horses_output
        ),

    "connected_horse_count":
        connected_horse_count,

    "connected_past_race_count":
        connected_past_race_count,

    "runner_race_db_race_count":
        len(
            race_index
        ),

    "reference_race_count":
        len(
            reference_races
        ),

    # 旧キー互換
    "baseline_condition_count":
        (
            exact_baseline_count
            + class_match_baseline_count
            + class_group_baseline_count
            + course_distance_baseline_count
        ),

    "baseline_level_counts": {
        "EXACT":
            exact_baseline_count,

        "CLASS_MATCH":
            class_match_baseline_count,

        "CLASS_GROUP":
            class_group_baseline_count,

        "COURSE_DISTANCE":
            course_distance_baseline_count,
    },

    "missing_race_id_count":
        missing_race_id_count,

    "race_not_in_runner_race_db_count":
        race_not_in_runner_race_db_count,

    # final_analysis等との互換
    "race_not_in_history_db_count":
        race_not_in_runner_race_db_count,

    "baseline_missing_count":
        baseline_missing_count,

    "horses":
        horses_output,
}


save_json(
    OUTPUT_FILE,
    output,
)


# =========================================================
# Log
# =========================================================

print("")
print(
    "===== Runner Time Fit ====="
)

print(
    "target race:",
    race_id,
)

print(
    "target date:",
    target_date.isoformat(),
)

print(
    "current time bias:",
    current_time_bias
    or "不明",
)

print(
    "runner race db races:",
    len(
        race_index
    ),
)

print(
    "reference races:",
    len(
        reference_races
    ),
)

print(
    "connected horses:",
    (
        f"{connected_horse_count}"
        f"/{len(horses_output)}"
    ),
)

print(
    "connected past races:",
    connected_past_race_count,
)

print(
    "missing race ids:",
    missing_race_id_count,
)

print(
    "race not in runner race db:",
    race_not_in_runner_race_db_count,
)

print(
    "baseline missing:",
    baseline_missing_count,
)

print(
    "baseline EXACT:",
    exact_baseline_count,
)

print(
    "baseline CLASS_MATCH:",
    class_match_baseline_count,
)

print(
    "baseline CLASS_GROUP:",
    class_group_baseline_count,
)

print(
    "baseline COURSE_DISTANCE:",
    course_distance_baseline_count,
)

print(
    "future race usage:",
    False,
)

print(
    "leak check passed:",
    True,
)
