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

        if value == "":
            continue

        try:
            return float(value)

        except (
            TypeError,
            ValueError
        ):
            continue

    return None


# =====================================
# race.json
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
# 既存body_weight.json
# =====================================
# 再実行時に入力済み馬体重を保持する
# Race IDが一致する場合だけ使用
# =====================================

old_data = load_json(
    OUTPUT_FILE
)

old_race_id = str(
    old_data.get(
        "race_id",
        ""
    )
).strip()


if old_race_id == race_id:

    old_horses = (
        old_data.get(
            "horses",
            []
        )
    )

else:

    old_horses = []


# =====================================
# Index
# =====================================

old_by_id = {}
old_by_name = {}
old_by_number = {}


for horse in old_horses:

    if not isinstance(
        horse,
        dict
    ):
        continue

    horse_id = get_id(
        horse
    )

    horse_name = get_name(
        horse
    )

    horse_number = (
        get_number_string(
            horse
        )
    )

    if horse_id:
        old_by_id[
            horse_id
        ] = horse

    if horse_name:
        old_by_name[
            horse_name
        ] = horse

    if horse_number:
        old_by_number[
            horse_number
        ] = horse


def find_old(runner):

    horse_id = get_id(
        runner
    )

    horse_name = get_name(
        runner
    )

    horse_number = (
        get_number_string(
            runner
        )
    )

    if (
        horse_id
        and horse_id
        in old_by_id
    ):
        return old_by_id[
            horse_id
        ]

    if (
        horse_name
        and horse_name
        in old_by_name
    ):
        return old_by_name[
            horse_name
        ]

    if (
        horse_number
        and horse_number
        in old_by_number
    ):
        return old_by_number[
            horse_number
        ]

    return {}


# =====================================
# 馬体重データ作成
# =====================================

horses = []


for runner in runners:

    old = find_old(
        runner
    )

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
    # 斤量
    # race.jsonを優先
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

    if carried_weight is None:

        carried_weight = (
            get_optional_number(
                old,
                "carried_weight"
            )
        )

    # ---------------------------------
    # 当日馬体重
    # 既存値を保持
    # ---------------------------------

    body_weight = (
        get_optional_number(
            old,
            "body_weight"
        )
    )

    # ---------------------------------
    # 増減
    # ---------------------------------

    body_weight_change = (
        get_optional_number(
            old,
            "body_weight_change"
        )
    )

    # ---------------------------------
    # 前走馬体重
    # ---------------------------------

    previous_body_weight = (
        get_optional_number(
            old,
            "previous_body_weight"
        )
    )

    # ---------------------------------
    # 増減が不明で
    # 当日＋前走馬体重がある場合
    # 自動計算
    # ---------------------------------

    if (
        body_weight_change
        is None
        and body_weight
        is not None
        and previous_body_weight
        is not None
    ):

        body_weight_change = (
            body_weight
            - previous_body_weight
        )

    # ---------------------------------
    # 斤量体重比
    # ---------------------------------

    if (
        body_weight
        is not None
        and body_weight > 0
        and carried_weight
        is not None
        and carried_weight > 0
    ):

        weight_body_ratio = (
            carried_weight
            / body_weight
            * 100
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

    if body_weight is None:

        status = (
            "馬体重未取得"
        )

    else:

        status = (
            "馬体重取得済み"
        )

    horses.append({

        "horse_id":
            horse_id,

        "horse_number":
            horse_number,

        "horse_name":
            horse_name,

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

body_weight_count = sum(
    1
    for horse in horses
    if horse[
        "body_weight"
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


# =====================================
# 出力
# =====================================

output = {

    "updated_at":
        now_jst(),

    "race_id":
        race_id,

    "source":
        "race.json + existing body_weight.json",

    "method": {

        "body_weight_not_scored_here":
            True,

        "body_weight_change_not_scored_here":
            True,

        "weight_body_ratio_calculated":
            True,

        "race_id_checked":
            True,

        "unknown_not_penalized":
            True
    },

    "summary": {

        "runner_count":
            len(horses),

        "body_weight_count":
            body_weight_count,

        "carried_weight_count":
            carried_weight_count,

        "weight_body_ratio_count":
            ratio_count,

        "body_weight_complete":
            (
                body_weight_count
                == len(horses)
            )
    },

    "horses":
        horses
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
    "runner:",
    len(horses)
)

print(
    "body weight:",
    body_weight_count,
    "/",
    len(horses)
)

print(
    "carried weight:",
    carried_weight_count,
    "/",
    len(horses)
)

print(
    "weight/body ratio:",
    ratio_count,
    "/",
    len(horses)
)

print()


for horse in horses:

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
        horse[
            "body_weight_change"
        ],
        "斤量",
        horse[
            "carried_weight"
        ],
        "斤量体重比",
        horse[
            "weight_body_ratio"
        ],
        horse[
            "status"
        ]
    )
