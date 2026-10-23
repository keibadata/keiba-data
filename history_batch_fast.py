import re
import time

from history_batch import (
    RACE_FILE,
    HISTORY_DB_FILE,
    OUTPUT_FILE,
    MAX_RACES,
    MIN_CACHE_RACES,
    REQUEST_WAIT,
    load_json,
    save_json,
    get_target_condition,
    get_existing_races,
    parse_race_info,
    build_output,
)


def metadata_complete(row):
    return bool(
        row.get("race_name")
        and row.get("race_info_text")
        and row.get("race_class")
        and row.get("age_condition")
    )


def merge_metadata(old, new):
    result = dict(old)

    for key in (
        "racecourse",
        "race_number",
        "surface",
        "distance",
        "track_condition",
        "race_name",
        "race_info_text",
        "race_class",
        "age_condition",
    ):
        value = new.get(key)

        if value not in (None, "", 0):
            result[key] = value

    return result


def main():
    race = load_json(RACE_FILE)
    target = get_target_condition(race)

    history_db = load_json(
        HISTORY_DB_FILE,
        {},
    )

    print("==============================")
    print("条件別 過去レース高速取得")
    print("対象Race ID:", target["race_id"])
    print(
        "条件:",
        target["racecourse"],
        target["surface"],
        target["distance"],
    )
    print("==============================")

    existing = get_existing_races(
        history_db,
        target,
    )

    existing_count = len(existing)

    print(
        "既存DB一致レース:",
        existing_count,
    )

    # =====================================================
    # 既存DBが10件以上ある場合
    # 日付探索は一切行わない
    # =====================================================

    if existing_count >= MIN_CACHE_RACES:
        selected = existing[:MAX_RACES]

        errors = []
        enriched = []

        direct_fetch_count = 0

        for row in selected:
            current = dict(row)

            # metadataが揃っているものはネット取得しない
            if metadata_complete(current):
                enriched.append(current)
                continue

            race_id = str(
                current.get("race_id", "")
            ).strip()

            if not re.fullmatch(
                r"\d{12}",
                race_id,
            ):
                enriched.append(current)
                continue

            print(
                "metadata不足のみ直接取得:",
                race_id,
            )

            try:
                info = parse_race_info(
                    race_id
                )

                current = merge_metadata(
                    current,
                    info,
                )

                direct_fetch_count += 1

                time.sleep(
                    REQUEST_WAIT
                )

            except Exception as e:
                errors.append({
                    "race_id": race_id,
                    "error": str(e),
                })

                print(
                    "metadata取得失敗:",
                    race_id,
                    str(e),
                )

            enriched.append(current)

        enriched.sort(
            key=lambda x: (
                x.get("race_date", ""),
                x.get("race_id", ""),
            ),
            reverse=True,
        )

        output = build_output(
            target=target,
            races=enriched,
            errors=errors,
            cache_used=True,
            existing_count=existing_count,
            searched=False,
            cache_reason=(
                "既存history_dbを優先使用・"
                "不足metadataのみrace_id直接取得・"
                "日付探索なし"
            ),
            class_refresh_count=(
                direct_fetch_count
            ),
            class_changed_count=0,
        )

        save_json(
            OUTPUT_FILE,
            output,
        )

        print("==============================")
        print("高速キャッシュ使用")
        print(
            "使用レース:",
            len(enriched),
        )
        print(
            "ネット直接取得:",
            direct_fetch_count,
        )
        print(
            "日付探索: 0"
        )
        print(
            "エラー:",
            len(errors),
        )
        print(
            "history_races.json 作成完了"
        )
        print("==============================")

        return

    # =====================================================
    # 10件未満
    #
    # この場合だけ従来版へフォールバックする。
    # データ不足時に解析材料を削らないため。
    # =====================================================

    print(
        "既存DBが",
        MIN_CACHE_RACES,
        "件未満のため従来探索へフォールバック",
    )

    from history_batch import main as legacy_main

    legacy_main()


if __name__ == "__main__":
    main()
