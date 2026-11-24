import argparse
import json
import os
from datetime import date
from pathlib import Path
from tempfile import NamedTemporaryFile

from jra_race_incidents import fetch_confirmed_victims, jra_result_identity


RACE_FILE = Path("race.json")
PAST_DB_FILE = Path("runner_race_db.json")
PREVIOUS_FILE = Path("previous_race_analysis.json")
FINAL_FILE = Path("final_analysis.json")
URL_FILE = Path("jra_result_urls.json")
NOTE = "前走で他馬による不利あり（JRA公式記録）・着順への影響は不明"


def read_json(path):
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path, data):
    with NamedTemporaryFile(
        mode="w", encoding="utf-8", dir=path.parent, delete=False
    ) as output:
        temporary_path = Path(output.name)
        try:
            json.dump(data, output, ensure_ascii=False, indent=2)
            output.write("\n")
            output.close()
            os.replace(temporary_path, path)
        finally:
            temporary_path.unlink(missing_ok=True)


def load_result_urls(extra_urls):
    urls = read_json(URL_FILE) if URL_FILE.exists() else []
    if not isinstance(urls, list):
        raise ValueError(f"{URL_FILE} は公式結果URLの配列で指定してください")
    result = {}
    for url in urls + extra_urls:
        try:
            key = jra_result_identity(url)
        except (ValueError, TypeError, AttributeError) as error:
            print("JRA結果URLをスキップ:", error)
            continue
        result[key] = url
    return result


def previous_key(horse, target_date):
    previous = horse.get("previous_race")
    if not previous:
        return None
    try:
        past_date = date.fromisoformat(previous["date"].replace("/", "-"))
    except (KeyError, TypeError, ValueError, AttributeError):
        return None
    if past_date >= target_date:
        return None
    return previous.get("race_id"), past_date.isoformat()


def enrich(previous, final, database, urls, target_date):
    previous_by_race = {}
    for horse in previous["horses"]:
        key = previous_key(horse, target_date)
        if key in urls:
            previous_by_race.setdefault(key, []).append(horse)

    past_races = {}
    for race in database["races"]:
        key = race["race_id"], race["race_date"]
        if key in previous_by_race:
            past_races.setdefault(key, []).append(race)

    final_by_id = {row["horse_id"]: row for row in final["ranking"]}
    changes = 0
    for key, horses in previous_by_race.items():
        candidates = past_races.get(key, [])
        if len(candidates) != 1:
            print("JRA前走照合をスキップ:", key[0], "前走DBのレースを特定できません")
            continue
        try:
            victims = fetch_confirmed_victims(urls[key], candidates[0])
        except (OSError, ValueError, KeyError, TypeError) as error:
            print("JRA前走照合をスキップ:", key[0], error)
            continue
        by_id = {record["horse_id"]: record for record in victims}
        for horse in horses:
            horse_id = horse["horse_id"]
            record = by_id.get(horse_id)
            ranked = final_by_id.get(horse_id)
            if (
                not record
                or not ranked
                or record["horse_name"] != horse["horse_name"]
                or ranked["horse_name"] != horse["horse_name"]
            ):
                continue
            detail = horse["previous_race"]
            reasons = ranked["reasons"]
            changed = detail.get("jra_interference") != record or NOTE not in reasons
            if not changed:
                continue
            detail["jra_interference"] = record
            if NOTE not in reasons:
                reasons.append(NOTE)
            changes += 1
    return changes


def main():
    parser = argparse.ArgumentParser(description="JRA公式の前走不利を最終解析に追記")
    parser.add_argument("--url", action="append", default=[], help="JRA公式結果URL")
    args = parser.parse_args()
    try:
        urls = load_result_urls(args.url)
        if not urls:
            print("JRA前走照合: 公式結果URLの登録なし")
            return
        race = read_json(RACE_FILE)
        previous = read_json(PREVIOUS_FILE)
        final = read_json(FINAL_FILE)
        database = read_json(PAST_DB_FILE)
        race_id = race["race_id"]
        if (
            previous["target_race_id"] != race_id
            or database["target_race_id"] != race_id
            or final["race_id"] != race_id
        ):
            raise ValueError("今回のレースIDが解析ファイル間で一致しません")
        if any(
            data.get("future_race_usage") is not False
            or data.get("leak_check_passed") is not True
            for data in (previous, database)
        ):
            raise ValueError("前走データの時系列を確認できません")
        target_date = date.fromisoformat(race["race_date"])
        changes = enrich(previous, final, database, urls, target_date)
    except (OSError, ValueError, KeyError, TypeError, AttributeError) as error:
        print("JRA前走照合をスキップ:", error)
        return
    if changes:
        write_json(PREVIOUS_FILE, previous)
        write_json(FINAL_FILE, final)
    print("JRA前走不利を追記した頭数:", changes)


if __name__ == "__main__":
    main()
