import concurrent.futures
import json
import os
import re
import subprocess
import sys
import tempfile
import time
from datetime import datetime, timezone, timedelta


RUNNER_HISTORY_FILE = "runner_history.json"
OUTPUT_FILE = "runner_race_db.json"
HISTORY_SCRIPT = "history.py"

# GitHub Actions向け高速化
MAX_WORKERS = 8
FETCH_TIMEOUT_SECONDS = 90
MAX_RETRIES = 2
RETRY_WAIT_SECONDS = 2

JST = timezone(timedelta(hours=9))


def now_iso():
    return datetime.now(JST).isoformat()


def clean(value):
    return str(value or "").strip()


def valid_race_id(value):
    return bool(re.fullmatch(r"\d{12}", clean(value)))


def load_json(path, default=None):
    if not os.path.exists(path):
        return default if default is not None else {}

    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    temp_path = f"{path}.tmp"

    with open(temp_path, "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    os.replace(temp_path, path)


def get_existing_races(db):
    races = db.get("races", [])

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


def build_existing_index(races):
    index = {}

    for race in races:
        race_id = clean(race.get("race_id"))

        if not valid_race_id(race_id):
            continue

        results = race.get("results")

        if not isinstance(results, list) or not results:
            continue

        index[race_id] = race

    return index


def collect_requested_race_ids(runner_history):
    requested = set()

    horses = runner_history.get("horses", []) or []

    if not isinstance(horses, list):
        return []

    for horse in horses:
        if not isinstance(horse, dict):
            continue

        past_races = horse.get("past_races", []) or []

        if not isinstance(past_races, list):
            continue

        for past in past_races:
            if not isinstance(past, dict):
                continue

            race_id = clean(past.get("race_id"))

            if valid_race_id(race_id):
                requested.add(race_id)

    return sorted(requested)


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
            return datetime.strptime(text[:10], fmt).date()
        except ValueError:
            pass

    try:
        return datetime.fromisoformat(
            text.replace("Z", "+00:00")
        ).date()
    except ValueError:
        return None


def get_target_date(runner_history):
    target_date = parse_race_date(
        runner_history.get("target_date")
    )

    if target_date is None:
        raise RuntimeError(
            "runner_history.json の target_date を取得できません。"
        )

    return target_date


def get_past_race_date_index(runner_history):
    result = {}

    horses = runner_history.get("horses", []) or []

    if not isinstance(horses, list):
        return result

    for horse in horses:
        if not isinstance(horse, dict):
            continue

        past_races = horse.get("past_races", []) or []

        if not isinstance(past_races, list):
            continue

        for past in past_races:
            if not isinstance(past, dict):
                continue

            race_id = clean(past.get("race_id"))

            if not valid_race_id(race_id):
                continue

            race_date = (
                past.get("race_date")
                or past.get("date")
            )

            parsed = parse_race_date(race_date)

            if parsed is not None:
                result[race_id] = parsed

    return result


def run_history_fetch(race_id):
    """
    history.py は history.json という固定ファイル名を使うため、
    並列実行時に衝突しないよう各レース専用の一時ディレクトリで実行する。
    """

    script_path = os.path.abspath(HISTORY_SCRIPT)

    if not os.path.exists(script_path):
        return {
            "race_id": race_id,
            "success": False,
            "error": f"{HISTORY_SCRIPT} が見つかりません",
        }

    last_error = ""

    for attempt in range(1, MAX_RETRIES + 1):
        try:
            with tempfile.TemporaryDirectory(
                prefix=f"runner_race_{race_id}_"
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
                    timeout=FETCH_TIMEOUT_SECONDS,
                )

                if result.returncode != 0:
                    last_error = (
                        result.stderr.strip()
                        or result.stdout.strip()
                        or f"returncode={result.returncode}"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS * attempt
                        )
                        continue

                    return {
                        "race_id": race_id,
                        "success": False,
                        "error": last_error,
                    }

                history_path = os.path.join(
                    temp_dir,
                    "history.json",
                )

                if not os.path.exists(history_path):
                    last_error = (
                        "history.py 実行後に "
                        "history.json が生成されませんでした"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS * attempt
                        )
                        continue

                    return {
                        "race_id": race_id,
                        "success": False,
                        "error": last_error,
                    }

                history = load_json(history_path)

                if not isinstance(history, dict):
                    last_error = (
                        "history.json がdictではありません"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS * attempt
                        )
                        continue

                    return {
                        "race_id": race_id,
                        "success": False,
                        "error": last_error,
                    }

                fetched_race_id = clean(
                    history.get("race_id")
                )

                if fetched_race_id != race_id:
                    last_error = (
                        "race_id不一致: "
                        f"requested={race_id}, "
                        f"fetched={fetched_race_id}"
                    )

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS * attempt
                        )
                        continue

                    return {
                        "race_id": race_id,
                        "success": False,
                        "error": last_error,
                    }

                results = history.get("results")

                if not isinstance(results, list) or not results:
                    last_error = "results が空です"

                    if attempt < MAX_RETRIES:
                        time.sleep(
                            RETRY_WAIT_SECONDS * attempt
                        )
                        continue

                    return {
                        "race_id": race_id,
                        "success": False,
                        "error": last_error,
                    }

                history["runner_race_reference"] = True

                return {
                    "race_id": race_id,
                    "success": True,
                    "race": history,
                    "attempt": attempt,
                }

        except subprocess.TimeoutExpired:
            last_error = (
                f"{FETCH_TIMEOUT_SECONDS}秒でタイムアウト"
            )

        except Exception as e:
            last_error = f"{type(e).__name__}: {e}"

        if attempt < MAX_RETRIES:
            time.sleep(
                RETRY_WAIT_SECONDS * attempt
            )

    return {
        "race_id": race_id,
        "success": False,
        "error": last_error or "unknown error",
    }


def build_output(
    runner_history,
    target_date,
    requested_ids,
    race_index,
    new_count,
    reused_count,
    errors,
    skipped_future,
):
    connected_ids = [
        race_id
        for race_id in requested_ids
        if race_id in race_index
    ]

    races = [
        race_index[race_id]
        for race_id in sorted(race_index.keys())
    ]

    return {
        "updated_at": now_iso(),
        "db_type": "runner_past_race_accumulated",
        "source": RUNNER_HISTORY_FILE,
        "target_race_id": clean(
            runner_history.get("target_race_id")
        ),
        "target_date": target_date.isoformat(),
        "future_race_usage": False,
        "leak_check_passed": True,
        "requested_race_count": len(requested_ids),
        "connected_race_count": len(connected_ids),
        "new_race_count": new_count,
        "reused_race_count": reused_count,
        "error_count": len(errors),
        "skipped_future_count": len(skipped_future),
        "missing_race_count": (
            len(requested_ids)
            - len(connected_ids)
        ),
        "errors": errors,
        "skipped_future_races": skipped_future,
        "races": races,
    }


def main():
    print("runner_race_db.py 開始")

    runner_history = load_json(
        RUNNER_HISTORY_FILE
    )

    if not isinstance(runner_history, dict):
        raise RuntimeError(
            "runner_history.json が不正です。"
        )

    target_race_id = clean(
        runner_history.get("target_race_id")
    )

    if not valid_race_id(target_race_id):
        raise RuntimeError(
            "runner_history.json の "
            "target_race_id が不正です。"
        )

    if runner_history.get("future_race_usage") is not False:
        raise RuntimeError(
            "runner_history.json の "
            "future_race_usage が false ではありません。"
        )

    if runner_history.get("leak_check_passed") is not True:
        raise RuntimeError(
            "runner_history.json の "
            "leak_check_passed が true ではありません。"
        )

    target_date = get_target_date(
        runner_history
    )

    requested_ids = collect_requested_race_ids(
        runner_history
    )

    requested_ids = [
        race_id
        for race_id in requested_ids
        if race_id != target_race_id
    ]

    print(
        f"抽出したユニーク過去レース数: "
        f"{len(requested_ids)}"
    )

    if not requested_ids:
        raise RuntimeError(
            "必要過去レース数が0件です。"
        )

    past_date_index = get_past_race_date_index(
        runner_history
    )

    skipped_future = []

    filtered_requested_ids = []

    for race_id in requested_ids:
        race_date = past_date_index.get(race_id)

        if (
            race_date is not None
            and race_date >= target_date
        ):
            skipped_future.append(
                {
                    "race_id": race_id,
                    "race_date": race_date.isoformat(),
                    "reason": (
                        "対象レース当日以降のため除外"
                    ),
                }
            )
            continue

        filtered_requested_ids.append(race_id)

    requested_ids = filtered_requested_ids

    print(
        f"未来リーク除外後の必要レース数: "
        f"{len(requested_ids)}"
    )

    if skipped_future:
        print(
            f"未来リーク除外: "
            f"{len(skipped_future)}件"
        )

    existing_db = load_json(
        OUTPUT_FILE,
        default={},
    )

    existing_races = get_existing_races(
        existing_db
    )

    race_index = build_existing_index(
        existing_races
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
        f"既存DBレース数: "
        f"{len(race_index)}"
    )

    print(
        f"再利用: "
        f"{len(reused_ids)}"
    )

    print(
        f"新規取得対象: "
        f"{len(missing_ids)}"
    )

    new_count = 0
    errors = []

    # 取得開始前にも現在状態を保存
    initial_output = build_output(
        runner_history=runner_history,
        target_date=target_date,
        requested_ids=requested_ids,
        race_index=race_index,
        new_count=new_count,
        reused_count=len(reused_ids),
        errors=errors,
        skipped_future=skipped_future,
    )

    save_json(
        OUTPUT_FILE,
        initial_output,
    )

    if missing_ids:
        print(
            f"並列取得開始: "
            f"workers={MAX_WORKERS}"
        )

        completed = 0
        total = len(missing_ids)

        with concurrent.futures.ThreadPoolExecutor(
            max_workers=MAX_WORKERS
        ) as executor:

            future_map = {
                executor.submit(
                    run_history_fetch,
                    race_id,
                ): race_id
                for race_id in missing_ids
            }

            for future in concurrent.futures.as_completed(
                future_map
            ):
                race_id = future_map[future]
                completed += 1

                try:
                    result = future.result()
                except Exception as e:
                    result = {
                        "race_id": race_id,
                        "success": False,
                        "error": (
                            f"{type(e).__name__}: {e}"
                        ),
                    }

                if result.get("success"):
                    race = result.get("race")

                    if isinstance(race, dict):
                        race_index[race_id] = race
                        new_count += 1

                        print(
                            f"[{completed}/{total}] "
                            f"OK {race_id}"
                        )

                else:
                    error = {
                        "race_id": race_id,
                        "error": clean(
                            result.get("error")
                        ),
                    }

                    errors.append(error)

                    print(
                        f"[{completed}/{total}] "
                        f"ERROR {race_id}: "
                        f"{error['error']}"
                    )

                # 1レース終了ごとに保存。
                # Actionが途中停止しても取得済みデータを残す。
                current_output = build_output(
                    runner_history=runner_history,
                    target_date=target_date,
                    requested_ids=requested_ids,
                    race_index=race_index,
                    new_count=new_count,
                    reused_count=len(reused_ids),
                    errors=errors,
                    skipped_future=skipped_future,
                )

                save_json(
                    OUTPUT_FILE,
                    current_output,
                )

    final_output = build_output(
        runner_history=runner_history,
        target_date=target_date,
        requested_ids=requested_ids,
        race_index=race_index,
        new_count=new_count,
        reused_count=len(reused_ids),
        errors=errors,
        skipped_future=skipped_future,
    )

    save_json(
        OUTPUT_FILE,
        final_output,
    )

    connected_count = (
        final_output["connected_race_count"]
    )

    requested_count = (
        final_output["requested_race_count"]
    )

    print("")
    print("===== runner_race_db 結果 =====")
    print(
        f"必要過去レース数: "
        f"{requested_count}"
    )
    print(
        f"接続成功: "
        f"{connected_count}"
    )
    print(
        f"既存再利用: "
        f"{len(reused_ids)}"
    )
    print(
        f"新規取得成功: "
        f"{new_count}"
    )
    print(
        f"取得エラー: "
        f"{len(errors)}"
    )
    print(
        f"未来リーク除外: "
        f"{len(skipped_future)}"
    )
    print(
        f"未接続: "
        f"{final_output['missing_race_count']}"
    )
    print("===============================")

    # 今回は取得エラーを明示的に失敗扱いにする。
    # NAR等の非対応レースが判明した場合は、
    # 次段階で「非対応として正常スキップ」に分離する。
    if errors:
        raise RuntimeError(
            f"過去レース取得エラーが "
            f"{len(errors)}件あります。"
        )

    if connected_count != requested_count:
        raise RuntimeError(
            "必要過去レースをすべて接続できませんでした。"
        )

    print("runner_race_db.py 完了")


if __name__ == "__main__":
    main()
