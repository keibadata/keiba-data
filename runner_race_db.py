import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta
from history import detect_race_class


RUNNER_HISTORY_FILE = "runner_history.json"
OUTPUT_FILE = "runner_race_db.json"
HISTORY_SCRIPT = "history.py"
CLASS_CACHE_VERSION = "race_class_cache_v1"

MAX_WORKERS = 8
FETCH_TIMEOUT_SECONDS = 90
MAX_RETRIES = 2
RETRY_WAIT_SECONDS = 2

JST = timezone(timedelta(hours=9))

JRA_VENUE_CODES = {
    "01",  # 札幌
    "02",  # 函館
    "03",  # 福島
    "04",  # 新潟
    "05",  # 東京
    "06",  # 中山
    "07",  # 中京
    "08",  # 京都
    "09",  # 阪神
    "10",  # 小倉
}


def now_iso():
    return datetime.now(JST).isoformat()


def clean(value):
    return str(value or "").strip()


def valid_race_id(value):
    return bool(
        re.fullmatch(
            r"\d{12}",
            clean(value),
        )
    )


def is_jra_race_id(race_id):
    race_id = clean(race_id)

    if not valid_race_id(race_id):
        return False

    return race_id[4:6] in JRA_VENUE_CODES


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}

    with open(
        path,
        "r",
        encoding="utf-8",
    ) as f:
        return json.load(f)


def save_json(path, data):
    temp_path = f"{path}.tmp"

    with open(
        temp_path,
        "w",
        encoding="utf-8",
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(
        temp_path,
        path,
    )


def parse_race_date(value):
    text = clean(value)

    if not text:
        return None

    for fmt in (
        "%Y-%m-%d",
        "%Y/%m/%d",
        "%Y%m%d",
    ):
        try:
            return datetime.strptime(
                text[:10],
                fmt,
            ).date()

        except ValueError:
            pass

    try:
        return datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00",
            )
        ).date()

    except ValueError:
        return None


def get_target_date(runner_history):
    target_date = parse_race_date(
        runner_history.get(
            "target_date"
        )
    )

    if target_date is None:
        raise RuntimeError(
            "runner_history.json の "
            "target_date を取得できません。"
        )

    return target_date


def get_existing_races(db):
    races = db.get(
        "races",
        [],
    )

    if isinstance(races, dict):
        result = []

        for race_id, race in races.items():
            if not isinstance(race, dict):
                continue

            item = dict(race)

            if not item.get("race_id"):
                item["race_id"] = race_id

            result.append(item)

        return result

    if isinstance(races, list):
        return [
            race
            for race in races
            if isinstance(race, dict)
        ]

    return []


def base_race_data_is_valid(race):
    if not isinstance(race, dict):
        return False

    race_id = clean(
        race.get("race_id")
    )

    if not valid_race_id(race_id):
        return False

    if not is_jra_race_id(race_id):
        return False

    race_date = clean(
        race.get("race_date")
        or race.get("date")
    )

    racecourse = clean(
        race.get("racecourse")
    )

    surface = clean(
        race.get("surface")
    )

    distance = race.get(
        "distance"
    )

    results = race.get(
        "results"
    )

    if not race_date:
        return False

    if not racecourse:
        return False

    if not surface:
        return False

    if distance in (
        None,
        "",
    ):
        return False

    if (
        not isinstance(results, list)
        or not results
    ):
        return False

    return True


def prepare_class_cache(races, runner_history, target_date, requested_ids):
    sources = {}
    horses = runner_history.get("horses", []) or []
    if not isinstance(horses, list):
        horses = []
    for horse in horses:
        if not isinstance(horse, dict):
            continue
        past_races = horse.get("past_races", []) or []
        if not isinstance(past_races, list):
            continue
        for past in past_races:
            if not isinstance(past, dict):
                continue
            rid = clean(past.get("race_id"))
            sources.setdefault(rid, []).append({
                "date": parse_race_date(past.get("race_date") or past.get("date")),
                "race_name": clean(past.get("race_name")),
                "race_class": detect_race_class(clean(past.get("race_name"))),
            })
    requested = set(requested_ids)
    prepared = []
    report = {"version": CLASS_CACHE_VERSION, "verified_count": 0,
              "corrected_count": 0, "rejected_count": 0,
              "corrections": [], "rejections": []}
    for cached in races:
        item = dict(cached)
        rid = clean(item.get("race_id"))
        if rid not in requested:
            prepared.append(item)
            continue
        when = parse_race_date(item.get("race_date") or item.get("date"))
        entries = sources.get(rid, [])
        labels = {e["race_class"] for e in entries if e["race_class"]}
        marker = item.get("race_class_validation")
        marker = marker if isinstance(marker, dict) else {}
        previous = clean(item.get("race_class"))
        reason, expected = "", ""
        if when is None or when >= target_date:
            reason = "キャッシュの日付が不明・対象日当日以降"
        elif any(e["date"] != when for e in entries):
            reason = "過去走一覧とキャッシュの日付が不一致"
        elif len(labels) > 1:
            reason = "同一Race IDの過去走名に異なるクラスがある"
        elif len(labels) == 1:
            expected = next(iter(labels))
            if (
                marker.get("version") == CLASS_CACHE_VERSION
                and marker.get("source") == "history.py"
                and marker.get("value") == previous
                and previous != expected
            ):
                reason = "取得済みページと過去走名のクラスが不一致"
        elif (
            marker.get("version") == CLASS_CACHE_VERSION
            and marker.get("source") == "history.py"
            and marker.get("status") in ("verified", "corrected", "fetched")
            and marker.get("value") == previous
            and marker.get("race_id") == rid
            and parse_race_date(marker.get("race_date")) == when
            and previous == detect_race_class(previous)
            and previous
        ):
            expected = previous
        else:
            reason = "クラスを確認できる過去走名・取得記録がない"
        if reason:
            report["rejected_count"] += 1
            report["rejections"].append({"race_id": rid, "reason": reason})
            item["race_class_validation"] = {
                "version": CLASS_CACHE_VERSION, "status": "unverified",
                "reason": reason,
            }
        else:
            changed = previous != expected
            source = "runner_history.race_name" if labels else "history.py"
            item["race_class"] = expected
            item["race_class_validation"] = {
                "version": CLASS_CACHE_VERSION,
                "status": "corrected" if changed else "verified",
                "source": source, "value": expected,
                "previous_value": previous, "race_id": rid,
                "race_date": when.isoformat(),
                "source_names": sorted({e["race_name"] for e in entries if e["race_class"]}),
            }
            if changed:
                report["corrected_count"] += 1
                report["corrections"].append({
                    "race_id": rid, "previous_value": previous,
                    "value": expected, "source": source,
                    "source_names": item["race_class_validation"]["source_names"],
                })
            else:
                report["verified_count"] += 1
        prepared.append(item)
    return prepared, report


def cache_has_required_fields(race):
    """
    中央専用。

    runner_time_fit で必要な
    race_class / age_condition まで
    入っているキャッシュだけ再利用する。
    """

    if not base_race_data_is_valid(
        race
    ):
        return False

    race_class = clean(
        race.get(
            "race_class"
        )
    )

    age_condition = clean(
        race.get(
            "age_condition"
        )
    )

    if not race_class:
        return False

    if not age_condition:
        return False

    marker = race.get("race_class_validation")
    if (
        not isinstance(marker, dict)
        or marker.get("version") != CLASS_CACHE_VERSION
        or marker.get("status") not in ("verified", "corrected", "fetched")
        or marker.get("source") not in ("runner_history.race_name", "history.py")
        or marker.get("value") != race_class
        or marker.get("race_id") != clean(race.get("race_id"))
        or parse_race_date(marker.get("race_date")) != parse_race_date(
            race.get("race_date") or race.get("date")
        )
    ):
        return False

    return True


def build_existing_index(
    races,
    requested_ids,
):
    requested_set = set(
        requested_ids
    )

    index = {}

    for race in races:
        race_id = clean(
            race.get(
                "race_id"
            )
        )

        if race_id not in requested_set:
            continue

        if not cache_has_required_fields(
            race
        ):
            continue

        index[
            race_id
        ] = race

    return index


def collect_requested_races(
    runner_history
):
    """
    runner_historyから
    中央レースIDだけ抽出。

    地方は今回明示的に除外する。
    """

    jra_ids = set()
    local_ids = set()

    horses = runner_history.get(
        "horses",
        [],
    ) or []

    if not isinstance(
        horses,
        list,
    ):
        return [], []

    for horse in horses:
        if not isinstance(
            horse,
            dict,
        ):
            continue

        past_races = horse.get(
            "past_races",
            [],
        ) or []

        if not isinstance(
            past_races,
            list,
        ):
            continue

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

            if is_jra_race_id(
                race_id
            ):
                jra_ids.add(
                    race_id
                )

            else:
                local_ids.add(
                    race_id
                )

    return (
        sorted(jra_ids),
        sorted(local_ids),
    )


def get_past_race_date_index(
    runner_history
):
    result = {}

    horses = runner_history.get(
        "horses",
        [],
    ) or []

    if not isinstance(
        horses,
        list,
    ):
        return result

    for horse in horses:
        if not isinstance(
            horse,
            dict,
        ):
            continue

        past_races = horse.get(
            "past_races",
            [],
        ) or []

        if not isinstance(
            past_races,
            list,
        ):
            continue

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

            race_date = (
                past.get("race_date")
                or past.get("date")
            )

            parsed = parse_race_date(
                race_date
            )

            if parsed is not None:
                result[
                    race_id
                ] = parsed

    return result


def validate_fetched_history(
    history,
    race_id,
):
    if not isinstance(
        history,
        dict,
    ):
        return (
            False,
            "history.json がdictではありません",
        )

    fetched_race_id = clean(
        history.get(
            "race_id"
        )
    )

    if fetched_race_id != race_id:
        return (
            False,
            (
                "race_id不一致: "
                f"requested={race_id}, "
                f"fetched={fetched_race_id}"
            ),
        )

    if not is_jra_race_id(
        race_id
    ):
        return (
            False,
            "地方レースは現在対象外です",
        )

    if not base_race_data_is_valid(
        history
    ):
        return (
            False,
            "中央レース基本情報またはresultsが不完全です",
        )

    race_class = detect_race_class(clean(history.get("race_class")))

    age_condition = clean(
        history.get(
            "age_condition"
        )
    )

    if not race_class:
        return (
            False,
            "中央レースのrace_classを取得できませんでした",
        )

    if not age_condition:
        return (
            False,
            "中央レースのage_conditionを取得できませんでした",
        )

    history[
        "condition_metadata_status"
    ] = "complete"

    history[
        "race_class_unknown"
    ] = False

    history[
        "age_condition_unknown"
    ] = False

    history[
        "runner_race_reference"
    ] = True
    history["race_class"] = race_class
    history["race_class_validation"] = {
        "version": CLASS_CACHE_VERSION, "status": "fetched",
        "source": "history.py", "value": race_class,
        "race_id": race_id,
        "race_date": clean(history.get("race_date") or history.get("date")),
    }

    return (
        True,
        "",
    )


def run_history_fetch(race_id):
    script_path = os.path.abspath(
        HISTORY_SCRIPT
    )

    if not os.path.exists(
        script_path
    ):
        return {
            "race_id": race_id,
            "success": False,
            "error": (
                f"{HISTORY_SCRIPT} "
                "が見つかりません"
            ),
        }

    last_error = ""

    for attempt in range(
        1,
        MAX_RETRIES + 1,
    ):
        try:
            with tempfile.TemporaryDirectory(
                prefix=(
                    f"runner_race_"
                    f"{race_id}_"
                )
            ) as temp_dir:

                result = subprocess.run(
                    [
                        sys.executable,
                        script_path,
                        race_id,
                    ],
                    cwd=temp_dir,
                    capture_output=True,
                    text=True,
                    timeout=(
                        FETCH_TIMEOUT_SECONDS
                    ),
                )

                if result.returncode != 0:
                    last_error = (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or (
                            "returncode="
                            f"{result.returncode}"
                        )
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS
                            * attempt
                        )
                        continue

                    return {
                        "race_id":
                            race_id,
                        "success":
                            False,
                        "error":
                            last_error,
                    }

                history_path = (
                    os.path.join(
                        temp_dir,
                        "history.json",
                    )
                )

                if not os.path.exists(
                    history_path
                ):
                    last_error = (
                        "history.py 実行後に "
                        "history.json が"
                        "生成されませんでした"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS
                            * attempt
                        )
                        continue

                    return {
                        "race_id":
                            race_id,
                        "success":
                            False,
                        "error":
                            last_error,
                    }

                history = load_json(
                    history_path
                )

                (
                    valid,
                    validation_error,
                ) = validate_fetched_history(
                    history,
                    race_id,
                )

                if not valid:
                    last_error = (
                        validation_error
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS
                            * attempt
                        )
                        continue

                    return {
                        "race_id":
                            race_id,
                        "success":
                            False,
                        "error":
                            last_error,
                    }

                return {
                    "race_id":
                        race_id,
                    "success":
                        True,
                    "race":
                        history,
                    "attempt":
                        attempt,
                }

        except subprocess.TimeoutExpired:
            last_error = (
                f"{FETCH_TIMEOUT_SECONDS}"
                "秒でタイムアウト"
            )

        except Exception as e:
            last_error = (
                f"{type(e).__name__}: {e}"
            )

        if attempt < MAX_RETRIES:
            time.sleep(
                RETRY_WAIT_SECONDS
                * attempt
            )

    return {
        "race_id":
            race_id,
        "success":
            False,
        "error":
            (
                last_error
                or "unknown error"
            ),
    }


def build_output(
    runner_history,
    target_date,
    requested_ids,
    excluded_local_ids,
    race_index,
    new_count,
    reused_count,
    errors,
    skipped_future,
    invalid_cache_count,
    class_cache_review=None,
):
    connected_ids = [
        race_id
        for race_id in requested_ids
        if race_id in race_index
    ]

    races = [
        race_index[
            race_id
        ]
        for race_id in sorted(
            race_index.keys()
        )
    ]

    return {
        "updated_at":
            now_iso(),

        "db_type":
            "runner_past_race_jra_only",

        "source":
            RUNNER_HISTORY_FILE,

        "target_race_id":
            clean(
                runner_history.get(
                    "target_race_id"
                )
            ),

        "target_date":
            target_date.isoformat(),

        "mode":
            "JRA_ONLY",

        "future_race_usage":
            False,

        "leak_check_passed":
            True,

        "requested_race_count":
            len(
                requested_ids
            ),

        "connected_race_count":
            len(
                connected_ids
            ),

        "new_race_count":
            new_count,

        "reused_race_count":
            reused_count,

        "invalid_cache_count":
            invalid_cache_count,
        "class_cache_review": class_cache_review or {},

        "excluded_local_race_count":
            len(
                excluded_local_ids
            ),

        "excluded_local_race_ids":
            excluded_local_ids,

        "error_count":
            len(
                errors
            ),

        "skipped_future_count":
            len(
                skipped_future
            ),

        "missing_race_count":
            (
                len(requested_ids)
                - len(connected_ids)
            ),

        "errors":
            errors,

        "skipped_future_races":
            skipped_future,

        "races":
            races,
    }


def main():
    print(
        "runner_race_db.py 開始"
    )

    print(
        "MODE: JRA ONLY"
    )

    runner_history = load_json(
        RUNNER_HISTORY_FILE
    )

    if not isinstance(
        runner_history,
        dict,
    ):
        raise RuntimeError(
            "runner_history.json が不正です。"
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
            "target_race_id が不正です。"
        )

    if (
        runner_history.get(
            "future_race_usage"
        )
        is not False
    ):
        raise RuntimeError(
            "runner_history.json の "
            "future_race_usage が "
            "false ではありません。"
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
            "true ではありません。"
        )

    target_date = get_target_date(
        runner_history
    )

    (
        requested_ids,
        excluded_local_ids,
    ) = collect_requested_races(
        runner_history
    )

    requested_ids = [
        race_id
        for race_id in requested_ids
        if race_id != target_race_id
    ]

    print(
        "中央ユニーク過去レース数: "
        f"{len(requested_ids)}"
    )

    print(
        "地方除外レース数: "
        f"{len(excluded_local_ids)}"
    )

    # 新馬戦など、全馬に過去走がないケースは正常。
    # 0件でも空DBを生成し、後続工程へ進める。
    if not requested_ids:
        print(
            "中央の必要過去レース数は0件です。"
            "新馬戦等として正常に続行します。"
        )

    past_date_index = (
        get_past_race_date_index(
            runner_history
        )
    )

    skipped_future = []
    filtered_requested_ids = []

    for race_id in requested_ids:
        race_date = (
            past_date_index.get(
                race_id
            )
        )

        if (
            race_date is not None
            and race_date >= target_date
        ):
            skipped_future.append({
                "race_id":
                    race_id,
                "race_date":
                    race_date.isoformat(),
                "reason":
                    "対象レース当日以降のため除外",
            })

            continue

        filtered_requested_ids.append(
            race_id
        )

    requested_ids = (
        filtered_requested_ids
    )

    print(
        "未来リーク除外後の中央必要レース数: "
        f"{len(requested_ids)}"
    )

    existing_db = load_json(
        OUTPUT_FILE,
        default={},
    )

    existing_races = (
        get_existing_races(
            existing_db
        )
    )

    requested_set = set(
        requested_ids
    )

    existing_races, class_cache_review = prepare_class_cache(
        existing_races, runner_history, target_date, requested_ids,
    )
    print("クラスキャッシュ再検証:", class_cache_review)

    invalid_cache_ids = []

    for race in existing_races:
        race_id = clean(
            race.get(
                "race_id"
            )
        )

        if race_id not in requested_set:
            continue

        if not cache_has_required_fields(
            race
        ):
            invalid_cache_ids.append(
                race_id
            )

    race_index = (
        build_existing_index(
            existing_races,
            requested_ids,
        )
    )

    reused_ids = [
        race_id
        for race_id in requested_ids
        if race_id in race_index
    ]

    missing_ids = [
        race_id
        for race_id in requested_ids
        if race_id not in race_index
    ]

    print(
        "既存DBレース数: "
        f"{len(existing_races)}"
    )

    print(
        "中央有効キャッシュ: "
        f"{len(reused_ids)}"
    )

    print(
        "中央旧・不完全キャッシュ: "
        f"{len(invalid_cache_ids)}"
    )

    print(
        "中央再取得対象: "
        f"{len(missing_ids)}"
    )

    new_count = 0
    errors = []

    initial_output = build_output(
        runner_history=runner_history,
        target_date=target_date,
        requested_ids=requested_ids,
        excluded_local_ids=(
            excluded_local_ids
        ),
        race_index=race_index,
        new_count=new_count,
        reused_count=len(
            reused_ids
        ),
        errors=errors,
        skipped_future=(
            skipped_future
        ),
        invalid_cache_count=len(
            invalid_cache_ids
        ),
        class_cache_review=class_cache_review,
    )

    save_json(
        OUTPUT_FILE,
        initial_output,
    )

    if missing_ids:
        print(
            "中央並列取得開始: "
            f"workers={MAX_WORKERS}"
        )

        completed = 0
        total = len(
            missing_ids
        )

        with (
            concurrent.futures
            .ThreadPoolExecutor(
                max_workers=MAX_WORKERS
            )
        ) as executor:

            future_map = {
                executor.submit(
                    run_history_fetch,
                    race_id,
                ): race_id
                for race_id in missing_ids
            }

            for future in (
                concurrent.futures
                .as_completed(
                    future_map
                )
            ):
                race_id = (
                    future_map[
                        future
                    ]
                )

                completed += 1

                try:
                    result = (
                        future.result()
                    )

                except Exception as e:
                    result = {
                        "race_id":
                            race_id,
                        "success":
                            False,
                        "error":
                            (
                                f"{type(e).__name__}: "
                                f"{e}"
                            ),
                    }

                if result.get(
                    "success"
                ):
                    race = result.get(
                        "race"
                    )

                    if isinstance(
                        race,
                        dict,
                    ):
                        race_index[
                            race_id
                        ] = race

                        new_count += 1

                        print(
                            f"[{completed}/{total}] "
                            f"OK {race_id} "
                            f"class="
                            f"{clean(race.get('race_class'))} "
                            f"age="
                            f"{clean(race.get('age_condition'))}"
                        )

                else:
                    error = {
                        "race_id":
                            race_id,
                        "error":
                            clean(
                                result.get(
                                    "error"
                                )
                            ),
                    }

                    errors.append(
                        error
                    )

                    print(
                        f"[{completed}/{total}] "
                        f"ERROR {race_id}: "
                        f"{error['error']}"
                    )

                current_output = (
                    build_output(
                        runner_history=(
                            runner_history
                        ),
                        target_date=(
                            target_date
                        ),
                        requested_ids=(
                            requested_ids
                        ),
                        excluded_local_ids=(
                            excluded_local_ids
                        ),
                        race_index=(
                            race_index
                        ),
                        new_count=(
                            new_count
                        ),
                        reused_count=len(
                            reused_ids
                        ),
                        errors=errors,
                        skipped_future=(
                            skipped_future
                        ),
                        invalid_cache_count=len(
                            invalid_cache_ids
                        ),
                        class_cache_review=class_cache_review,
                    )
                )

                save_json(
                    OUTPUT_FILE,
                    current_output,
                )

    final_output = build_output(
        runner_history=runner_history,
        target_date=target_date,
        requested_ids=requested_ids,
        excluded_local_ids=(
            excluded_local_ids
        ),
        race_index=race_index,
        new_count=new_count,
        reused_count=len(
            reused_ids
        ),
        errors=errors,
        skipped_future=(
            skipped_future
        ),
        invalid_cache_count=len(
            invalid_cache_ids
        ),
        class_cache_review=class_cache_review,
    )

    save_json(
        OUTPUT_FILE,
        final_output,
    )

    connected_count = (
        final_output[
            "connected_race_count"
        ]
    )

    requested_count = (
        final_output[
            "requested_race_count"
        ]
    )

    print("")
    print(
        "===== runner_race_db JRA結果 ====="
    )

    print(
        "中央必要過去レース数: "
        f"{requested_count}"
    )

    print(
        "中央接続成功: "
        f"{connected_count}"
    )

    print(
        "中央既存再利用: "
        f"{len(reused_ids)}"
    )

    print(
        "中央旧・不完全キャッシュ: "
        f"{len(invalid_cache_ids)}"
    )

    print(
        "中央新規取得成功: "
        f"{new_count}"
    )

    print(
        "地方除外: "
        f"{len(excluded_local_ids)}"
    )

    print(
        "取得エラー: "
        f"{len(errors)}"
    )

    print(
        "未来リーク除外: "
        f"{len(skipped_future)}"
    )

    print(
        "中央未接続: "
        f"{final_output['missing_race_count']}"
    )

    print(
        "=================================="
    )

    if errors:
        raise RuntimeError(
            "中央過去レース取得エラーが "
            f"{len(errors)}件あります。"
        )

    if (
        connected_count
        != requested_count
    ):
        raise RuntimeError(
            "中央必要過去レースを"
            "すべて接続できませんでした。"
        )

    print(
        "runner_race_db.py 完了"
    )


if __name__ == "__main__":
    main()
