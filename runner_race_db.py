import json
import os
import re
import subprocess
import sys
import time
from datetime import datetime, timezone


RUNNER_HISTORY_FILE = "runner_history.json"
OUTPUT_FILE = "runner_race_db.json"
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


def clean(value):
    return str(value or "").strip()


def valid_race_id(value):
    return bool(
        re.fullmatch(
            r"\d{12}",
            clean(value),
        )
    )


def get_existing_races(database):
    if isinstance(database, list):
        return database

    if not isinstance(database, dict):
        return []

    races = database.get(
        "races",
        [],
    )

    if isinstance(races, list):
        return races

    return []


def main():
    runner_history = load_json(
        RUNNER_HISTORY_FILE
    )

    target_race_id = clean(
        runner_history.get(
            "target_race_id"
        )
    )

    if not valid_race_id(
        target_race_id
    ):
        raise RuntimeError(
            "runner_history.json の "
            "target_race_id が不正です"
        )

    if (
        runner_history.get(
            "future_race_usage"
        )
        is not False
    ):
        raise RuntimeError(
            "runner_history.json に"
            "未来レース混入の可能性があります"
        )

    if (
        runner_history.get(
            "leak_check_passed"
        )
        is not True
    ):
        raise RuntimeError(
            "runner_history.json の "
            "leak_check_passed が "
            "true ではありません"
        )

    # ==========================================
    # 全出走馬の過去走 race_id を収集
    # ==========================================

    requested = {}

    horses = (
        runner_history.get(
            "horses",
            [],
        )
        or []
    )

    for horse in horses:
        if not isinstance(
            horse,
            dict,
        ):
            continue

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

        past_races = (
            horse.get(
                "past_races",
                [],
            )
            or []
        )

        for past in past_races:
            if not isinstance(
                past,
                dict,
            ):
                continue

            race_id = clean(
                past.get(
                    "race_id"
                )
            )

            if not valid_race_id(
                race_id
            ):
                continue

            if race_id == target_race_id:
                continue

            if race_id not in requested:
                requested[race_id] = {
                    "race_id": race_id,
                    "date": clean(
                        past.get(
                            "date"
                        )
                    ),
                    "race_name": clean(
                        past.get(
                            "race_name"
                        )
                    ),
                    "referenced_by": [],
                }

            reference = {
                "horse_id": horse_id,
                "horse_name": horse_name,
            }

            if (
                reference
                not in requested[
                    race_id
                ][
                    "referenced_by"
                ]
            ):
                requested[
                    race_id
                ][
                    "referenced_by"
                ].append(
                    reference
                )

    requested_ids = sorted(
        requested.keys()
    )

    # ==========================================
    # 既存DB
    # ==========================================

    existing_database = load_json(
        OUTPUT_FILE,
        {},
    )

    race_map = {}

    for race in get_existing_races(
        existing_database
    ):
        if not isinstance(
            race,
            dict,
        ):
            continue

        race_id = clean(
            race.get(
                "race_id"
            )
        )

        if valid_race_id(
            race_id
        ):
            race_map[
                race_id
            ] = race

    print(
        "=============================="
    )
    print(
        "出走馬過去走DB 更新開始"
    )
    print(
        "対象レース:",
        target_race_id,
    )
    print(
        "必要過去レース数:",
        len(requested_ids),
    )
    print(
        "既存DBレース数:",
        len(race_map),
    )
    print(
        "=============================="
    )

    reused_count = 0
    collected_count = 0
    errors = []

    # ==========================================
    # 必要な過去走を取得
    # ==========================================

    for index, race_id in enumerate(
        requested_ids,
        start=1,
    ):
        if race_id in race_map:
            reused_count += 1

            print(
                f"[{index}/{len(requested_ids)}] "
                f"既存結果再利用: "
                f"{race_id}"
            )

            continue

        print(
            f"[{index}/{len(requested_ids)}] "
            f"新規取得: "
            f"{race_id}"
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
                clean(
                    result.get(
                        "race_id"
                    )
                )
                != race_id
            ):
                raise RuntimeError(
                    "history.json の "
                    "race_id が一致しません"
                )

            results = result.get(
                "results",
                [],
            )

            if (
                not isinstance(
                    results,
                    list,
                )
                or not results
            ):
                raise RuntimeError(
                    "出走結果が0件です"
                )

            result[
                "runner_race_reference"
            ] = requested[
                race_id
            ]

            race_map[
                race_id
            ] = result

            collected_count += 1

            # 途中失敗しても取得済みデータを残す
            interim_races = sorted(
                race_map.values(),
                key=lambda x: clean(
                    x.get(
                        "race_id"
                    )
                ),
            )

            interim_database = {
                "updated_at":
                    datetime.now(
                        timezone.utc
                    ).isoformat(),

                "source":
                    "netkeiba",

                "database_type":
                    "runner_past_races_accumulated",

                "target_race_id":
                    target_race_id,

                "races":
                    interim_races,
            }

            save_json(
                OUTPUT_FILE,
                interim_database,
            )

            print(
                "取得成功:",
                race_id,
                "出走馬",
                len(results),
                "頭",
            )

        except Exception as e:
            print(
                "取得失敗:",
                race_id,
                str(e),
            )

            errors.append({
                "race_id":
                    race_id,

                "error":
                    str(e),
            })

        if index < len(
            requested_ids
        ):
            time.sleep(
                WAIT_SECONDS
            )

    # ==========================================
    # 最終DB
    # ==========================================

    all_races = sorted(
        race_map.values(),
        key=lambda x: clean(
            x.get(
                "race_id"
            )
        ),
    )

    connected_requested_count = sum(
        1
        for race_id in requested_ids
        if race_id in race_map
    )

    database = {
        "updated_at":
            datetime.now(
                timezone.utc
            ).isoformat(),

        "source":
            "netkeiba",

        "database_type":
            "runner_past_races_accumulated",

        "target_race_id":
            target_race_id,

        "requested_race_count":
            len(
                requested_ids
            ),

        "connected_requested_race_count":
            connected_requested_count,

        "newly_collected_count":
            collected_count,

        "existing_reused_count":
            reused_count,

        "error_count":
            len(errors),

        "errors":
            errors,

        "total_race_count":
            len(all_races),

        "races":
            all_races,
    }

    save_json(
        OUTPUT_FILE,
        database,
    )

    print(
        "=============================="
    )
    print(
        "出走馬過去走DB 更新完了"
    )
    print(
        "必要レース:",
        len(requested_ids),
    )
    print(
        "接続済み:",
        connected_requested_count,
    )
    print(
        "新規取得:",
        collected_count,
    )
    print(
        "既存再利用:",
        reused_count,
    )
    print(
        "取得失敗:",
        len(errors),
    )
    print(
        "DB総レース数:",
        len(all_races),
    )
    print(
        "=============================="
    )

    if errors:
        raise RuntimeError(
            "runner_race_db "
            f"取得失敗が "
            f"{len(errors)} 件あります"
        )

    if (
        connected_requested_count
        != len(requested_ids)
    ):
        raise RuntimeError(
            "必要な過去走を"
            "すべて接続できませんでした"
        )


if __name__ == "__main__":
    main()
