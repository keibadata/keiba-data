import json
import os


RACE_FILE = "race.json"
OUTPUT_FILE = "condition_history.json"
HISTORY_FILE = "history_db.json"

# 新馬戦の血統専用評価で、
# 完全一致条件がない場合に許容する距離差。
DEBUT_NEAR_DISTANCE = 200


def load_json(path):
    if not os.path.exists(path):
        return {}

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def normalize_surface(value):
    value = str(
        value or ""
    ).strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_track(value):
    return str(
        value or ""
    ).strip()


def normalize_distance(value):
    try:
        return int(value)

    except (
        TypeError,
        ValueError
    ):
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

    race_info = race.get(
        "race_info",
        {}
    )

    if isinstance(
        race_info,
        dict
    ):

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
        "track": normalize_track(
            track
        ),
        "surface": normalize_surface(
            surface
        ),
        "distance": normalize_distance(
            distance
        ),
    }


def get_history_rows(history):
    """
    history_db.json の形式差を吸収。
    """

    if isinstance(
        history,
        list
    ):
        return history

    if not isinstance(
        history,
        dict
    ):
        return []

    for key in (
        "races",
        "history",
        "records",
        "data",
    ):
        value = history.get(
            key
        )

        if isinstance(
            value,
            list
        ):
            return value

    return []


def get_condition_from_history_row(row):
    if not isinstance(
        row,
        dict
    ):
        return {
            "track": "",
            "surface": "",
            "distance": 0,
        }

    race_info = row.get(
        "race_info",
        {}
    )

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

    if isinstance(
        race_info,
        dict
    ):

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
        "track": normalize_track(
            track
        ),
        "surface": normalize_surface(
            surface
        ),
        "distance": normalize_distance(
            distance
        ),
    }


def is_debut_race(race):
    """
    新馬戦判定。

    過去走0件では判定しない。
    race.json の明示情報だけを使用。
    """

    if race.get(
        "is_debut"
    ) is True:
        return True

    race_class = str(
        race.get(
            "race_class",
            ""
        )
    ).strip()

    race_name = str(
        race.get(
            "race_name",
            ""
        )
    ).strip()

    if race_class == "新馬":
        return True

    if "新馬" in race_name:
        return True

    if "メイクデビュー" in race_name:
        return True

    return False


def select_history(
    history_rows,
    target,
    debut
):
    """
    通常戦:
        完全一致のみ。

    新馬戦:
        完全一致がなければ
        血統評価用に段階的フォールバック。
    """

    prepared = []

    for row in history_rows:

        condition = (
            get_condition_from_history_row(
                row
            )
        )

        prepared.append(
            (
                row,
                condition
            )
        )

    # =====================================================
    # 1. 完全一致
    # =====================================================

    exact = [
        row
        for row, condition
        in prepared
        if (
            condition["track"]
            == target["track"]
            and condition["surface"]
            == target["surface"]
            and condition["distance"]
            == target["distance"]
        )
    ]

    if exact:
        return (
            exact,
            "exact",
            {
                "track_required": True,
                "surface_required": True,
                "distance_rule": "exact",
                "distance_tolerance": 0,
            }
        )

    # =====================================================
    # 通常戦
    #
    # 完全一致がなければ終了。
    # 条件を勝手に広げない。
    # =====================================================

    if not debut:
        return (
            [],
            "exact_no_match",
            {
                "track_required": True,
                "surface_required": True,
                "distance_rule": "exact",
                "distance_tolerance": 0,
            }
        )

    # =====================================================
    # 以下は新馬戦専用
    # =====================================================

    # -----------------------------------------------------
    # 2. 同競馬場
    #    ＋同芝ダ
    #    ＋±200m
    # -----------------------------------------------------

    near_distance = [
        row
        for row, condition
        in prepared
        if (
            condition["track"]
            == target["track"]
            and condition["surface"]
            == target["surface"]
            and condition["distance"] > 0
            and abs(
                condition["distance"]
                - target["distance"]
            )
            <= DEBUT_NEAR_DISTANCE
        )
    ]

    if near_distance:
        return (
            near_distance,
            (
                "debut_"
                "same_track_"
                "surface_"
                "near_distance"
            ),
            {
                "track_required": True,
                "surface_required": True,
                "distance_rule":
                    "within_tolerance",
                "distance_tolerance":
                    DEBUT_NEAR_DISTANCE,
            }
        )

    # -----------------------------------------------------
    # 3. 同競馬場
    #    ＋同芝ダ
    #    距離不問
    # -----------------------------------------------------

    same_track_surface = [
        row
        for row, condition
        in prepared
        if (
            condition["track"]
            == target["track"]
            and condition["surface"]
            == target["surface"]
        )
    ]

    if same_track_surface:
        return (
            same_track_surface,
            (
                "debut_"
                "same_track_"
                "surface_"
                "any_distance"
            ),
            {
                "track_required": True,
                "surface_required": True,
                "distance_rule": "any",
                "distance_tolerance": None,
            }
        )

    # -----------------------------------------------------
    # 4. 同芝ダ
    #    ＋±200m
    #
    # 同競馬場に1件もない場合だけ
    # 競馬場を広げる。
    # -----------------------------------------------------

    same_surface_near_distance = [
        row
        for row, condition
        in prepared
        if (
            condition["surface"]
            == target["surface"]
            and condition["distance"] > 0
            and abs(
                condition["distance"]
                - target["distance"]
            )
            <= DEBUT_NEAR_DISTANCE
        )
    ]

    if same_surface_near_distance:
        return (
            same_surface_near_distance,
            (
                "debut_"
                "same_surface_"
                "near_distance"
            ),
            {
                "track_required": False,
                "surface_required": True,
                "distance_rule":
                    "within_tolerance",
                "distance_tolerance":
                    DEBUT_NEAR_DISTANCE,
            }
        )

    # -----------------------------------------------------
    # 5. 同芝ダ
    #    距離不問
    #
    # 新馬戦血統評価の最終フォールバック。
    # -----------------------------------------------------

    same_surface = [
        row
        for row, condition
        in prepared
        if (
            condition["surface"]
            == target["surface"]
        )
    ]

    if same_surface:
        return (
            same_surface,
            (
                "debut_"
                "same_surface_"
                "any_distance"
            ),
            {
                "track_required": False,
                "surface_required": True,
                "distance_rule": "any",
                "distance_tolerance": None,
            }
        )

    return (
        [],
        "debut_no_match",
        {
            "track_required": False,
            "surface_required": True,
            "distance_rule": "any",
            "distance_tolerance": None,
        }
    )


# =========================================================
# MAIN
# =========================================================

race = load_json(
    RACE_FILE
)

history = load_json(
    HISTORY_FILE
)

target = get_race_condition(
    race
)

history_rows = get_history_rows(
    history
)

debut = is_debut_race(
    race
)

(
    matched,
    selection_mode,
    selection_rule
) = select_history(
    history_rows,
    target,
    debut
)


# =========================================================
# OUTPUT
# =========================================================

output = {
    "race_id": str(
        race.get(
            "race_id",
            ""
        )
    ),

    "is_debut":
        debut,

    "target_condition":
        target,

    "history_source":
        HISTORY_FILE,

    "history_total_count":
        len(
            history_rows
        ),

    "selection_mode":
        selection_mode,

    "selection_rule":
        selection_rule,

    "matched_history_count":
        len(
            matched
        ),

    "matched_history":
        matched,
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


# =========================================================
# LOG
# =========================================================

print(
    "===== CONDITION HISTORY ====="
)

print(
    "race_id:",
    output["race_id"]
)

print(
    "is_debut:",
    debut
)

print(
    "condition:",
    target["track"],
    target["surface"],
    target["distance"]
)

print(
    "selection_mode:",
    selection_mode
)

print(
    "matched:",
    len(matched),
    "/",
    len(history_rows)
)


# =========================================================
# 安全装置
# =========================================================

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

    if debut:
        print(
            "WARNING: "
            "新馬戦の血統評価用フォールバックでも"
            "利用可能な過去レースがありません。"
        )

    else:
        print(
            "WARNING: "
            "現在のhistory_db.jsonには"
            "この条件の過去レースがありません。"
            "通常戦では条件を広げません。"
        )
