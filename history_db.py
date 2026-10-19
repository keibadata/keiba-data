import json
import os
import subprocess
import sys
import time
from datetime import datetime, timezone


RACE_LIST_FILE = "history_races.json"
OUTPUT_FILE = "history_db.json"
TEMP_FILE = "history.json"

WAIT_SECONDS = 2


# =========================================================
# JSON
# =========================================================

def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )


# =========================================================
# 条件正規化
# =========================================================

def normalize_surface(value):
    value = str(value or "").strip()

    if "芝" in value:
        return "芝"

    if "ダ" in value:
        return "ダート"

    return value


def normalize_distance(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


def normalize_condition(data):
    if not isinstance(data, dict):
        data = {}

    return {
        "racecourse": str(
            data.get("racecourse")
            or data.get("track")
            or ""
        ).strip(),

        "surface": normalize_surface(
            data.get("surface", "")
        ),

        "distance": normalize_distance(
            data.get("distance", 0)
        ),
    }


def race_condition(race):
    if not isinstance(race, dict):
        return normalize_condition({})

    return normalize_condition({
        "racecourse": (
            race.get("racecourse")
            or race.get("track")
            or ""
        ),
        "surface": race.get("surface", ""),
        "distance": race.get("distance", 0),
    })


def condition_key(condition):
    c = normalize_condition(condition)

    return (
        c["racecourse"],
        c["surface"],
        c["distance"],
    )


# =========================================================
# 既存DB
# =========================================================

def get_existing_races(database):
    if isinstance(database, list):
        return database

    if not isinstance(database, dict):
        return []

    races = database.get(
        "races",
        []
    )

    if isinstance(races, list):
        return races

    return []


def validate_target_condition(condition):
    if not condition["racecourse"]:
        raise RuntimeError(
            "history_races.json の競馬場がありません"
        )

    if not condition["surface"]:
        raise RuntimeError(
            "history_races.json の芝・ダートがありません"
        )

    if condition["distance"] <= 0:
        raise RuntimeError(
            "history_races.json の距離がありません"
        )


# =========================================================
# レースmetadata
# =========================================================

def extract_metadata(race):
    """
    history_races.json から
    history_db.json に永続保存するmetadataを抽出。
    """

    if not isinstance(race, dict):
        return {}

    return {
        "race_date": str(
            race.get("race_date", "")
        ).strip(),

        "race_number": str(
            race.get("race_number", "")
        ).strip(),

        "track_condition": str(
            race.get("track_condition", "")
        ).strip(),

        "race_name": str(
            race.get("race_name", "")
        ).strip(),

        "race_info_text": str(
            race.get("race_info_text", "")
        ).strip(),

        "race_class": str(
            race.get("race_class", "")
        ).strip(),

        "age_condition": str(
            race.get("age_condition", "")
        ).strip(),
    }


def apply_metadata(
    target,
    source_race,
    requested_condition,
):
    """
    history_races.json の確定情報を
    history_db.json のレースへ接続。

    空値では既存値を消さない。
    """

    if not isinstance(target, dict):
        target = {}

    target["racecourse"] = (
        requested_condition["racecourse"]
    )

    target["surface"] = (
        requested_condition["surface"]
    )

    target["distance"] = (
        requested_condition["distance"]
    )

    metadata = extract_metadata(
        source_race
    )

    for key, value in metadata.items():
        if value not in ("", None):
            target[key] = value

    return target


def metadata_complete(race):
    """
    時計基準作成に必要なmetadata。

    track_condition は取得できないケースがあるため
    完全判定の必須項目にはしない。
    """

    if not isinstance(race, dict):
        return False

    required = (
        "race_name",
        "race_info_text",
        "race_class",
        "age_condition",
    )

    return all(
        str(
            race.get(key, "")
        ).strip()
        for key in required
    )


# =========================================================
# MAIN
# =========================================================

def main():
    race_list = load_json(
        RACE_LIST_FILE
    )

    races = race_list.get(
        "races",
        []
    )

    if (
        not isinstance(races, list)
        or not races
    ):
        raise RuntimeError(
            "history_races.json に races がありません"
        )

    target_condition = normalize_condition(
        race_list.get(
            "condition",
            {}
        )
    )

    validate_target_condition(
        target_condition
    )

    target_key = condition_key(
        target_condition
    )

    print("==============================")
    print("条件別履歴DB 更新開始")

    print(
        "対象条件:",
        target_condition["racecourse"],
        target_condition["surface"],
        target_condition["distance"],
    )

    print(
        "対象レース数:",
        len(races)
    )

    print("==============================")


    # =====================================================
    # 既存 history_db.json 読み込み
    # =====================================================

    existing_database = load_json(
        OUTPUT_FILE,
        {}
    )

    existing_races = get_existing_races(
        existing_database
    )

    race_map = {}

    for race in existing_races:
        if not isinstance(
            race,
            dict
        ):
            continue

        race_id = str(
            race.get(
                "race_id",
                ""
            )
        ).strip()

        if not race_id:
            continue

        race_map[race_id] = race

    print(
        "既存DBレース数:",
        len(race_map)
    )


    # =====================================================
    # 更新カウンター
    # =====================================================

    collected_count = 0
    reused_count = 0
    metadata_updated_count = 0

    errors = []


    # =====================================================
    # history_races.json の各レースを処理
    # =====================================================

    for index, race in enumerate(
        races,
        start=1,
    ):
        race_id = str(
            race.get(
                "race_id",
                ""
            )
        ).strip()

        if not race_id:
            errors.append({
                "race_id": "",
                "error": "race_idが空です",
            })
            continue

        requested_condition = (
            race_condition(race)
        )

        if (
            condition_key(
                requested_condition
            )
            != target_key
        ):
            errors.append({
                "race_id": race_id,
                "error": (
                    "history_races.json内の"
                    "レース条件が対象条件と一致しません"
                ),
            })
            continue


        # =================================================
        # 既存レース
        #
        # 全頭結果は取り直さない。
        # metadataだけ更新する。
        # =================================================

        if race_id in race_map:
            before = json.dumps(
                race_map[race_id],
                ensure_ascii=False,
                sort_keys=True,
            )

            race_map[race_id] = (
                apply_metadata(
                    race_map[race_id],
                    race,
                    requested_condition,
                )
            )

            after = json.dumps(
                race_map[race_id],
                ensure_ascii=False,
                sort_keys=True,
            )

            reused_count += 1

            if before != after:
                metadata_updated_count += 1

                print(
                    f"[{index}/{len(races)}] "
                    f"既存結果再利用＋metadata更新: "
                    f"{race_id}"
                )

            else:
                print(
                    f"[{index}/{len(races)}] "
                    f"既存結果再利用: "
                    f"{race_id}"
                )

            continue


        # =================================================
        # DBに存在しないレースのみ新規取得
        # =================================================

        print(
            f"[{index}/{len(races)}] "
            f"新規取得: {race_id}"
        )

        try:
            subprocess.run(
                [
                    sys.executable,
                    "history.py",
                    race_id,
                ],
                check=True,
            )

            result = load_json(
                TEMP_FILE
            )

            if (
                str(
                    result.get(
                        "race_id",
                        ""
                    )
                ).strip()
                != race_id
            ):
                raise RuntimeError(
                    "history.json のrace_idが一致しません"
                )

            result = apply_metadata(
                result,
                race,
                requested_condition,
            )

            result_count = len(
                result.get(
                    "results",
                    []
                )
            )

            if result_count <= 0:
                raise RuntimeError(
                    "出走結果が0件です"
                )

            race_map[race_id] = result

            collected_count += 1

            print(
                "取得成功:",
                race_id,
                "出走馬",
                result_count,
                "頭"
            )

        except Exception as e:
            print(
                "取得失敗:",
                race_id,
                str(e)
            )

            errors.append({
                "race_id": race_id,
                "error": str(e),
            })

        if index < len(races):
            time.sleep(
                WAIT_SECONDS
            )


    # =====================================================
    # DB全体再構築
    # =====================================================

    all_races = list(
        race_map.values()
    )

    all_races.sort(
        key=lambda x: str(
            x.get(
                "race_id",
                ""
            )
        )
    )

    total_horses = sum(
        len(
            race.get(
                "results",
                []
            )
        )
        for race in all_races
    )


    # =====================================================
    # 条件別件数
    # =====================================================

    condition_counts = {}

    for race in all_races:
        c = race_condition(
            race
        )

        key = (
            f'{c["racecourse"]}|'
            f'{c["surface"]}|'
            f'{c["distance"]}'
        )

        condition_counts[key] = (
            condition_counts.get(
                key,
                0
            )
            + 1
        )


    # =====================================================
    # 今回条件だけ抽出
    # =====================================================

    target_races_in_db = [
        race
        for race in all_races
        if (
            condition_key(
                race_condition(race)
            )
            == target_key
        )
    ]


    # =====================================================
    # metadata完全数
    # =====================================================

    metadata_complete_count = sum(
        1
        for race in target_races_in_db
        if metadata_complete(race)
    )


    # =====================================================
    # クラス・年齢・馬場状態集計
    # =====================================================

    race_class_counts = {}
    age_condition_counts = {}
    track_condition_counts = {}

    for race in target_races_in_db:

        race_class = str(
            race.get(
                "race_class",
                ""
            )
        ).strip() or "不明"

        age_condition = str(
            race.get(
                "age_condition",
                ""
            )
        ).strip() or "不明"

        track_condition = str(
            race.get(
                "track_condition",
                ""
            )
        ).strip() or "不明"


        race_class_counts[
            race_class
        ] = (
            race_class_counts.get(
                race_class,
                0
            )
            + 1
        )


        age_condition_counts[
            age_condition
        ] = (
            age_condition_counts.get(
                age_condition,
                0
            )
            + 1
        )


        track_condition_counts[
            track_condition
        ] = (
            track_condition_counts.get(
                track_condition,
                0
            )
            + 1
        )


    # =====================================================
    # history_db.json
    # =====================================================

    database = {
        "updated_at": datetime.now(
            timezone.utc
        ).isoformat(),

        "source": "netkeiba",

        "database_type": (
            "multi_condition_accumulated"
        ),

        "latest_condition": (
            target_condition
        ),

        "total_race_count": len(
            all_races
        ),

        "total_horse_count": (
            total_horses
        ),

        "condition_counts": (
            condition_counts
        ),

        "latest_update": {

            "requested_race_count": len(
                races
            ),

            "newly_collected_count": (
                collected_count
            ),

            "existing_reused_count": (
                reused_count
            ),

            "metadata_updated_count": (
                metadata_updated_count
            ),

            "metadata_complete_count": (
                metadata_complete_count
            ),

            "target_condition_race_count": (
                len(target_races_in_db)
            ),

            "race_class_counts": (
                race_class_counts
            ),

            "age_condition_counts": (
                age_condition_counts
            ),

            "track_condition_counts": (
                track_condition_counts
            ),

            "error_count": len(
                errors
            ),

            "errors": errors,
        },

        "races": all_races,
    }


    save_json(
        OUTPUT_FILE,
        database
    )


    # =====================================================
    # 最終確認
    # =====================================================

    print("")
    print("==============================")
    print("history_db.json 更新完了")

    print(
        "DB総レース数:",
        len(all_races)
    )

    print(
        "DB総出走数:",
        total_horses
    )

    print(
        "今回新規取得:",
        collected_count
    )

    print(
        "既存結果再利用:",
        reused_count
    )

    print(
        "metadata更新:",
        metadata_updated_count
    )

    print(
        "今回条件DBレース:",
        len(target_races_in_db)
    )

    print(
        "metadata完全:",
        metadata_complete_count,
        "/",
        len(target_races_in_db)
    )

    print(
        "クラス内訳:",
        race_class_counts
    )

    print(
        "年齢条件内訳:",
        age_condition_counts
    )

    print(
        "馬場状態内訳:",
        track_condition_counts
    )

    print(
        "取得失敗:",
        len(errors)
    )

    print("==============================")


    if not target_races_in_db:
        raise RuntimeError(
            "今回条件の過去レースがDBに1件もありません"
        )

    if metadata_complete_count == 0:
        raise RuntimeError(
            "時計基準に必要なレースmetadataが"
            "1件も接続されていません"
        )


if __name__ == "__main__":
    main()
