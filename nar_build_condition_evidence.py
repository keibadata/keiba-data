"""大井の今回条件と過去走を比較し、事実だけを保存する。採点はしない。"""

import hashlib
import json
import math
import os
import re
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
RACE_FILE = BASE_DIR / "nar" / "race.json"
HISTORY_FILE = BASE_DIR / "nar" / "history.json"
OUTPUT = BASE_DIR / "nar" / "condition_evidence.json"
JST = timezone(timedelta(hours=9))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def positive_number(value):
    if type(value) not in (int, float):
        return None
    return value if math.isfinite(value) and value > 0 else None


def difference(current, previous):
    current = positive_number(current)
    previous = positive_number(previous)
    if current is None or previous is None:
        return None
    return round(current - previous, 3)


def match_value(current, previous):
    if current is None or current == "" or previous is None or previous == "":
        return None
    return current == previous


def weight_ratio(carried, body):
    carried = positive_number(carried)
    body = positive_number(body)
    if carried is None or body is None:
        return None
    return round(carried / body * 100, 3)


def compare_run(race, horse, run, target_direction):
    available = run["eligible_as_past_race"]
    distance_change = difference(race.get("distance"), run.get("distance")) if available else None
    distance_relation = None
    if distance_change is not None:
        distance_relation = "extension" if distance_change > 0 else "shortening" if distance_change < 0 else "same"

    return {
        "history_index": run["history_index"],
        "race_id": run.get("race_id"),
        "race_date": run.get("race_date"),
        "race_name": run.get("race_name"),
        "available_for_comparison": available,
        "quality_flags": list(run["quality_flags"]),
        "source_url": run.get("source_url"),
        "days_before_target": run.get("days_before_target"),
        "previous_conditions": {
            "track": run.get("track"),
            "distance": run.get("distance"),
            "direction": run.get("direction"),
            "track_condition": run.get("track_condition"),
            "course_raw": run.get("course_raw"),
            "carried_weight": run.get("carried_weight"),
            "body_weight": run.get("body_weight"),
        },
        "previous_result": {
            key: run.get(key)
            for key in [
                "finish_position", "finish_status", "field_size",
                "time_seconds", "corner_positions", "last_3f_seconds",
                "margin_seconds", "margin_reference", "reference_horse_name",
            ]
        },
        "comparison": {
            "same_track": match_value(race.get("track"), run.get("track")) if available else None,
            "same_distance": distance_change == 0 if distance_change is not None else None,
            "distance_change_m": distance_change,
            "distance_relation": distance_relation,
            "same_direction": match_value(target_direction, run.get("direction")) if available else None,
            "same_track_condition": match_value(race.get("track_condition"), run.get("track_condition")) if available else None,
            "same_surface": None,
            "same_course_layout": None,
            "carried_weight_change_kg": difference(horse.get("carried_weight"), run.get("carried_weight")) if available else None,
            "body_weight_change_kg": difference(horse.get("body_weight"), run.get("body_weight")) if available else None,
        },
    }


def build_evidence(race_bytes, history_bytes):
    race = json.loads(race_bytes)
    history = json.loads(history_bytes)
    require(isinstance(race, dict) and isinstance(history, dict), "入力JSONが不正です")
    require(
        race.get("schema_version") == 1
        and race.get("collection_only") is True
        and race.get("race_type") == "NAR"
        and race.get("source") == "NAR"
        and race.get("track") == "大井"
        and race.get("nar_baba_code") == "20",
        "入力は大井の取得専用データに限定します",
    )
    target_day = date.fromisoformat(race["race_date"])
    race_no = race.get("race_number")
    require(type(race_no) is int and 1 <= race_no <= 12, "対象R番号が不正です")
    expected_id = f"NAR_{target_day:%Y%m%d}_20_{race_no:02d}"
    require(race.get("race_id") == expected_id, "対象Race IDが一致しません")
    require(
        history.get("schema_version") == 1
        and history.get("normalizer_version") == "nar_history_v1"
        and history.get("collection_only") is True
        and history.get("race_type") == "NAR",
        "過去走データの形式が不正です",
    )
    for key in ["race_id", "race_date", "track", "race_number"]:
        require(history.get(key) == race.get(key), "出馬表と過去走が一致しません: " + key)
    require(history.get("source_file") == "nar/race.json", "過去走の参照元が不正です")
    require(history.get("source_sha256") == hashlib.sha256(race_bytes).hexdigest(), "出馬表更新後に過去走が再生成されていません")
    require(history.get("source_updated_at") == race.get("updated_at"), "参照元の取得日時が一致しません")

    horses = race.get("horses")
    past_horses = history.get("horses")
    require(isinstance(horses, list) and bool(horses), "出走馬がありません")
    require(isinstance(past_horses, list) and len(past_horses) == len(horses), "過去走の頭数が一致しません")
    require(race.get("horse_count") == len(horses), "出馬表の頭数が一致しません")
    layout = str(race.get("course_layout_raw") or "")
    directions = re.findall(r"直線|右|左", layout)
    target_direction = directions[0] if len(directions) == 1 else None
    output_horses = []
    seen_numbers, seen_ids = set(), set()

    for horse, past_horse in zip(horses, past_horses):
        require(isinstance(horse, dict) and isinstance(past_horse, dict), "馬データが不正です")
        for key in ["horse_number", "horse_id", "horse_id_source", "horse_name"]:
            require(horse.get(key) == past_horse.get(key), "馬データが一致しません: " + key)
        number, horse_id = horse.get("horse_number"), horse.get("horse_id")
        require(type(number) is int and number > 0 and number not in seen_numbers, "馬番が不正または重複しています")
        require(isinstance(horse_id, str) and bool(horse_id) and horse_id not in seen_ids, "馬IDが不正または重複しています")
        require(horse.get("horse_id_source") == "NAR_k_lineageLoginCode" and bool(horse.get("horse_name")), "NAR馬情報が不正です")
        seen_numbers.add(number)
        seen_ids.add(horse_id)
        raw_runs = horse.get("previous_races")
        runs = past_horse.get("previous_races")
        require(isinstance(raw_runs, list) and isinstance(runs, list) and len(raw_runs) == len(runs) <= 5, "過去走数が一致しません")
        comparisons = []
        for index, (raw, run) in enumerate(zip(raw_runs, runs), 1):
            require(isinstance(run, dict), "過去走レコードが不正です")
            require(run.get("raw") == raw and run.get("history_index") == index, "過去走の原文または順番が一致しません")
            flags = run.get("quality_flags")
            require(isinstance(flags, list) and all(isinstance(f, str) for f in flags), "品質フラグが不正です")
            require(type(run.get("eligible_as_past_race")) is bool and run["eligible_as_past_race"] == (not flags), "過去走の利用可否が不正です")
            if run["eligible_as_past_race"]:
                require(date.fromisoformat(run["race_date"]) < target_day, "対象日以降の成績が混入しています")
            comparisons.append(compare_run(race, horse, run, target_direction))

        usable = [item["comparison"] for item in comparisons if item["available_for_comparison"]]
        output_horses.append({
            "horse_number": number,
            "horse_id": horse_id,
            "horse_name": horse["horse_name"],
            "current_weight": {
                "carried_weight": positive_number(horse.get("carried_weight")),
                "body_weight": positive_number(horse.get("body_weight")),
                "reported_body_weight_change": horse.get("body_weight_change"),
                "weight_body_ratio_percent": weight_ratio(horse.get("carried_weight"), horse.get("body_weight")),
            },
            "previous_race": comparisons[0] if comparisons else None,
            "comparisons": comparisons,
            "summary": {
                "listed_past_race_count": len(comparisons),
                "comparable_past_race_count": len(usable),
                "same_track_count": sum(c["same_track"] is True for c in usable),
                "same_distance_count": sum(c["same_distance"] is True for c in usable),
                "same_track_and_distance_count": sum(c["same_track"] is True and c["same_distance"] is True for c in usable),
            },
            "unassessed_items": [
                "前走敗因", "前走課題", "課題克服度", "クラス比較",
                "能力", "今回発揮率", "展開別評価",
            ],
        })

    return {
        "schema_version": 1,
        "evidence_version": "nar_condition_evidence_v1",
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_type": "NAR",
        "race_id": expected_id,
        "race_date": race["race_date"],
        "track": "大井",
        "race_number": race_no,
        "race_name": race.get("race_name"),
        "source_race_updated_at": race.get("updated_at"),
        "source_history_updated_at": history.get("updated_at"),
        "source_race_sha256": hashlib.sha256(race_bytes).hexdigest(),
        "source_history_sha256": hashlib.sha256(history_bytes).hexdigest(),
        "target_conditions": {
            "surface": race.get("surface"),
            "distance": positive_number(race.get("distance")),
            "direction": target_direction,
            "course_layout_raw": race.get("course_layout_raw"),
            "track_condition": race.get("track_condition"),
            "race_class": race.get("race_class"),
        },
        "limitations": [
            "条件変更や馬体重増減を、プラス・マイナス評価へ変換しない",
            "過去走の芝・ダート区分と内外回りは未確定のため一致判定しない",
            "未知・未取得の数値を0で補完しない",
            "時計や上がりを異なる条件間で直接順位付けしない",
            "過去走が欠けても別の過去走を前走として繰り上げない",
        ],
        "summary": {
            "horse_count": len(output_horses),
            "past_race_count": sum(len(h["comparisons"]) for h in output_horses),
            "comparable_past_race_count": sum(h["summary"]["comparable_past_race_count"] for h in output_horses),
        },
        "horses": output_horses,
    }


def main():
    result = build_evidence(RACE_FILE.read_bytes(), HISTORY_FILE.read_bytes())
    temporary = None
    try:
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", dir=OUTPUT.parent, delete=False) as handle:
            temporary = Path(handle.name)
            json.dump(result, handle, ensure_ascii=False, indent=2, allow_nan=False)
            handle.write("\n")
        os.replace(temporary, OUTPUT)
    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()
    print("NAR CONDITION EVIDENCE OK")
    print("race_id:", result["race_id"])
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("output:", OUTPUT)


if __name__ == "__main__":
    main()
