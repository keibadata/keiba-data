import json
import os
from datetime import datetime, timezone, timedelta


RACE_FILE = "race.json"
OUTPUT_FILE = "body_weight.json"


# =====================================
# 共通
# =====================================

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
        timezone(
            timedelta(hours=9)
        )
    ).isoformat()


def get_name(data):

    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_name")
        or data.get("name")
        or ""
    ).strip()


def get_id(data):

    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_id")
        or ""
    ).strip()


def get_number_string(data):

    if not isinstance(data, dict):
        return ""

    return str(
        data.get("horse_number")
        or data.get("number")
        or data.get("umaban")
        or ""
    ).strip()


def get_optional_number(
    data,
    *keys
):

    if not isinstance(data, dict):
        return None

    for key in keys:

        value = data.get(key)

        if value is None:
            continue

        value = str(value).strip()

        if not value:
            continue

        # +8 等にも対応
        value = value.replace(
            "kg",
            ""
        ).strip()

        try:
            return float(value)

        except (
            TypeError,
            ValueError
        ):
            continue

    return None


# =====================================
# race.json 読み込み
# =====================================

race = load_json(
    RACE_FILE
)


if not race:

    raise RuntimeError(
        "race.jsonを読み込めません"
    )


race_id = str(
    race.get(
        "race_id",
        ""
    )
).strip()


if not race_id:

    raise RuntimeError(
        "race.jsonにrace_idがありません"
    )


runners = (
    race.get("horses")
    or race.get("runners")
    or race.get("entries")
    or []
)


if not runners:

    raise RuntimeError(
        "race.jsonに出走馬がありません"
    )


# =====================================
# Race情報
# =====================================

race_date = str(
    race.get(
        "race_date",
        ""
    )
).strip()


track = str(
    race.get("track")
    or race.get("racecourse")
    or ""
).strip()


surface = str(
    race.get(
        "surface",
        ""
    )
).strip()


distance = get_optional_number(
    race,
    "distance"
)


source = str(
    race.get(
        "source",
        ""
    )
).strip()


source_url = str(
    race.get(
        "source_url",
        ""
    )
).strip()


# =====================================
# 馬体重データ生成
# =====================================

horses = []

warnings = []


for runner in runners:

    horse_id = get_id(
        runner
    )

    horse_number = (
        get_number_string(
            runner
        )
    )

    horse_name = get_name(
        runner
    )

    # ---------------------------------
    # 当日馬体重
    # race.jsonを直接使用
    # ---------------------------------

    body_weight = (
        get_optional_number(
            runner,
            "body_weight",
            "weight"
        )
    )

    # ---------------------------------
    # 馬体重増減
    # ---------------------------------

    body_weight_change = (
        get_optional_number(
            runner,
            "body_weight_change",
            "weight_change",
            "change"
        )
    )

    # ---------------------------------
    # 斤量
    # ---------------------------------

    carried_weight = (
        get_optional_number(
            runner,
            "carried_weight",
            "burden_weight",
            "weight_carried",
            "jockey_weight"
        )
    )

    # ---------------------------------
    # 前走馬体重
    #
    # 当日馬体重と増減があれば
    # 逆算可能
    # ---------------------------------

    if (
        body_weight is not None
        and body_weight_change is not None
    ):

        previous_body_weight = (
            body_weight
            - body_weight_change
        )

    else:

        previous_body_weight = None

    # ---------------------------------
    # 斤量体重比
    # ---------------------------------

    if (
        body_weight is not None
        and body_weight > 0
        and carried_weight is not None
        and carried_weight > 0
    ):

        weight_body_ratio = (
            carried_weight
            / body_weight
            * 100.0
        )

        weight_body_ratio = round(
            weight_body_ratio,
            3
        )

    else:

        weight_body_ratio = None

    # ---------------------------------
    # 状態
    # ---------------------------------

    missing = []

    if body_weight is None:
        missing.append(
            "馬体重"
        )

    if body_weight_change is None:
        missing.append(
            "増減"
        )

    if carried_weight is None:
        missing.append(
            "斤量"
        )

    if missing:

        status = (
            "一部不明:"
            + ",".join(missing)
        )

        warnings.append(
            horse_number
            + " "
            + horse_name
            + " "
            + status
        )

    else:

        status = "取得済み"

    # ---------------------------------
    # 出力
    # ---------------------------------

    horses.append({

        "horse_id":
            horse_id,

        "horse_number":
            horse_number,

        "horse_name":
            horse_name,

        "sex_age":
            str(
                runner.get(
                    "sex_age",
                    ""
                )
            ).strip(),

        "jockey":
            str(
                runner.get(
                    "jockey",
                    ""
                )
            ).strip(),

        "body_weight":
            (
                round(
                    body_weight,
                    1
                )
                if body_weight
                is not None
                else None
            ),

        "body_weight_change":
            (
                round(
                    body_weight_change,
                    1
                )
                if body_weight_change
                is not None
                else None
            ),

        "previous_body_weight":
            (
                round(
                    previous_body_weight,
                    1
                )
                if previous_body_weight
                is not None
                else None
            ),

        "carried_weight":
            (
                round(
                    carried_weight,
                    1
                )
                if carried_weight
                is not None
                else None
            ),

        "weight_body_ratio":
            weight_body_ratio,

        "status":
            status
    })


# =====================================
# 集計
# =====================================

runner_count = len(
    horses
)


body_weight_count = sum(
    1
    for horse in horses
    if horse[
        "body_weight"
    ] is not None
)


change_count = sum(
    1
    for horse in horses
    if horse[
        "body_weight_change"
    ] is not None
)


carried_weight_count = sum(
    1
    for horse in horses
    if horse[
        "carried_weight"
    ] is not None
)


ratio_count = sum(
    1
    for horse in horses
    if horse[
        "weight_body_ratio"
    ] is not None
)


complete_count = sum(
    1
    for horse in horses
    if (
        horse["body_weight"]
        is not None
        and horse[
            "body_weight_change"
        ] is not None
        and horse[
            "carried_weight"
        ] is not None
    )
)


# =====================================
# 出力
# =====================================

output = {

    "updated_at":
        now_jst(),

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

    "source":
        source,

    "source_url":
        source_url,

    "method": {

        "source_is_race_json":
            True,

        "body_weight_from_race_json":
            True,

        "body_weight_change_from_race_json":
            True,

        "carried_weight_from_race_json":
            True,

        "previous_body_weight_reconstructed":
            True,

        "weight_body_ratio_calculated":
            True,

        "body_weight_not_scored_here":
            True,

        "body_weight_change_not_scored_here":
            True,

        "unknown_not_penalized":
            True
    },

    "summary": {

        "runner_count":
            runner_count,

        "body_weight_count":
            body_weight_count,

        "body_weight_change_count":
            change_count,

        "carried_weight_count":
            carried_weight_count,

        "weight_body_ratio_count":
            ratio_count,

        "complete_count":
            complete_count,

        "complete":
            (
                complete_count
                == runner_count
            )
    },

    "warnings":
        warnings,

    "horses":
        horses
}


# =====================================
# JSON保存
# =====================================

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


# =====================================
# ログ
# =====================================

print(
    "===== BODY WEIGHT ====="
)

print(
    "race id:",
    race_id
)

print(
    "race:",
    track,
    surface,
    distance
)

print(
    "runner:",
    runner_count
)

print(
    "body weight:",
    body_weight_count,
    "/",
    runner_count
)

print(
    "change:",
    change_count,
    "/",
    runner_count
)

print(
    "carried weight:",
    carried_weight_count,
    "/",
    runner_count
)

print(
    "weight/body ratio:",
    ratio_count,
    "/",
    runner_count
)

print(
    "complete:",
    complete_count,
    "/",
    runner_count
)

print()


for horse in horses:

    ratio = (
        format(
            horse[
                "weight_body_ratio"
            ],
            ".2f"
        )
        + "%"
        if horse[
            "weight_body_ratio"
        ] is not None
        else "不明"
    )

    change = (
        format(
            horse[
                "body_weight_change"
            ],
            "+.0f"
        )
        if horse[
            "body_weight_change"
        ] is not None
        else "不明"
    )

    print(
        horse[
            "horse_number"
        ],
        horse[
            "horse_name"
        ],
        "馬体重",
        horse[
            "body_weight"
        ],
        "増減",
        change,
        "斤量",
        horse[
            "carried_weight"
        ],
        "斤量比",
        ratio,
        horse[
            "status"
        ]
    )


if warnings:

    print()
    print(
        "===== WARNINGS ====="
    )

    for warning in warnings:
        print(
            warning
        )
