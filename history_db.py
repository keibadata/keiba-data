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


def get_existing_races(database):
    if isinstance(database, list):
        return database

    if not isinstance(database, dict):
        return []

    races = database.get("races", [])

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


def main():
    race_list = load_json(
        RACE_LIST_FILE
    )

    races = race_list.get("races", [])

    if not isinstance(races, list) or not races:
        raise RuntimeError(
            "history_races.json に races がありません"
        )

    target_condition = normalize_condition(
        race_list.get("condition", {})
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
    print("対象レース数:", len(races))
    print("==============================")

    # -----------------------------------------
    # 既存DBを読み込む
    # -----------------------------------------

    existing_database = load_json(
        OUTPUT_FILE,
        {}
    )

    existing_races = get_existing_races(
        existing_database
    )

    # race_id単位で保持。
    # 既存データは消さない。
    race_map = {}

    for race in existing_races:
        if not isinstance(race, dict):
            continue

        race_id = str(
            race.get("race_id", "")
        ).strip()

        if not race_id:
            continue

        race_map[race_id] = race

    existing_count = len(race_map)

    print(
        "既存DBレース数:",
        existing_count
    )

    # -----------------------------------------
    # 今回条件の既存レースID
    # -----------------------------------------

    existing_target_ids = set()

    for race_id, race in race_map.items():
        if condition_key(
            race_condition(race)
        ) == target_key:
            existing_target_ids.add(
                race_id
            )

    print(
        "今回条件の既存レース:",
        len(existing_target_ids)
    )

    collected_count = 0
    skipped_count = 0
    errors = []

    # -----------------------------------------
    # 必要なレースだけ新規取得
    # -----------------------------------------

    for index, race in enumerate(
        races,
        start=1
    ):
        race_id = str(
            race.get("race_id", "")
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
            condition_key(requested_condition)
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

        # すでに同じrace_idがDBにあれば再取得しない
        if race_id in race_map:
            print(
                f"[{index}/{len(races)}] "
                f"既存データ使用: {race_id}"
            )

            skipped_count += 1
            continue

        print("")
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

            # history.py側で条件が欠ける場合に備えて
            # history_races.jsonの確定条件を接続
            result["racecourse"] = (
                requested_condition[
                    "racecourse"
                ]
            )

            result["surface"] = (
                requested_condition[
                    "surface"
                ]
            )

            result["distance"] = (
                requested_condition[
                    "distance"
                ]
            )

            if race.get("race_date"):
                result["race_date"] = (
                    race["race_date"]
                )

            if race.get("race_number"):
                result["race_number"] = (
                    race["race_number"]
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

    # -----------------------------------------
    # DB全体を再構築
    # -----------------------------------------

    all_races = list(
        race_map.values()
    )

    # race_idで安定ソート
    all_races.sort(
        key=lambda x: str(
            x.get("race_id", "")
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

    # 条件別件数
    condition_counts = {}

    for race in all_races:
        c = race_condition(race)

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
                skipped_count
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

    # -----------------------------------------
    # 最終安全確認
    # -----------------------------------------

    target_races_in_db = [
        race
        for race in all_races
        if condition_key(
            race_condition(race)
        ) == target_key
    ]

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
        "既存再利用:",
        skipped_count
    )
    print(
        "今回条件DBレース:",
        len(target_races_in_db)
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


if __name__ == "__main__":
    main()
