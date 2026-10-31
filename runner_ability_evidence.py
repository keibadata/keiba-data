import json
import math
import re
import unicodedata
from collections import Counter
from datetime import date, datetime, timezone, timedelta
from pathlib import Path


OUTPUT = Path("runner_ability_evidence.json")


def load(path):
    with open(path, encoding="utf-8") as f:
        data = json.load(f)
    if not isinstance(data, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return data


def text(value):
    return str(value if value is not None else "").strip()


def parse_date(value):
    value = text(value).replace("/", "-")
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def numeric(value):
    try:
        number = float(value)
        return number if math.isfinite(number) else None
    except (ValueError, TypeError):
        return None


def finish(value):
    value = unicodedata.normalize("NFKC", text(value))
    return int(value) if re.fullmatch(r"[1-9]\d*", value) else None


def last3f(value):
    value = numeric(value)
    return value if value is not None and 25 <= value <= 50 else None


def race_class(name):
    # race_class既存値にはGI/GII/GIIIの誤判定があり得るため、名称から抽出。
    name = unicodedata.normalize("NFKC", text(name)).upper()
    for token in re.findall(r"\(([^()]*)\)", name):
        token = re.sub(r"\s+", "", token)
        grades = {"GI": "G1", "G1": "G1", "GII": "G2",
                  "G2": "G2", "GIII": "G3", "G3": "G3"}
        if token in grades:
            return grades[token]
        if token == "L":
            return "L"
    for token, label in [("3勝", "3勝クラス"), ("1600万", "3勝クラス"),
                         ("2勝", "2勝クラス"), ("1000万", "2勝クラス"),
                         ("1勝", "1勝クラス"), ("500万", "1勝クラス"),
                         ("未勝利", "未勝利"), ("新馬", "新馬"),
                         ("オープン", "OP")]:
        if token in name:
            return label
    if re.search(r"\(OP\)", name):
        return "OP"
    return None


def field_evidence(past, horse_id, database, target_date):
    unknown = {"matched": False, "classified_finish_count": None,
               "last3f_observed_count": None, "last3f_rank": None}
    historical = database.get(text(past.get("race_id")))
    if historical is None:
        return unknown
    historical_date = parse_date(historical.get("race_date") or historical.get("date"))
    if historical_date != parse_date(past.get("date")) or historical_date >= target_date:
        return unknown
    rows = historical.get("results", [])
    own = [r for r in rows if text(r.get("horse_id")) == horse_id]
    if len(own) != 1:
        return unknown
    own_time = last3f(own[0].get("last3f"))
    observed = [v for r in rows if (v := last3f(r.get("last3f"))) is not None]
    return {
        "matched": True,
        "classified_finish_count": sum(finish(r.get("rank")) is not None for r in rows),
        "last3f_observed_count": len(observed),
        "last3f_rank": 1 + sum(v < own_time for v in observed) if own_time is not None else None,
    }


def build(race, history, database):
    target_id = text(race.get("race_id"))
    target_date = parse_date(race.get("race_date"))
    if not target_id or target_date is None:
        raise ValueError("race.json: race_id / race_date missing")
    if text(history.get("target_race_id")) != target_id:
        raise ValueError("runner_history target race mismatch")
    if history.get("future_race_usage") is not False or history.get("leak_check_passed") is not True:
        raise ValueError("runner_history leak check failed")
    race_index = {}
    for row in database.get("races", []):
        key = text(row.get("race_id"))
        if key in race_index:
            raise ValueError(f"Duplicate database race: {key}")
        if key:
            race_index[key] = row
    horses = []
    for horse in history.get("horses", []):
        evidence = []
        seen = set()
        for past in horse.get("past_races", []):
            past_date = parse_date(past.get("date"))
            past_id = text(past.get("race_id"))
            if past_date is None or past_date >= target_date or past_id == target_id:
                raise ValueError("Unknown date, same-day or future race in history")
            key = (past_date, past_id or text(past.get("race_name")))
            if key in seen:
                raise ValueError(f"Duplicate horse history: {horse.get('horse_id')} {key}")
            seen.add(key)
            rank = finish(past.get("rank"))
            closing = last3f(past.get("last3f"))
            flags = []
            if rank is None:
                flags.append("着順不明・取消等を0点に置換しない")
            if closing is None:
                flags.append("上がり不明を固定点に置換しない")
            evidence.append({
                "race_id": past_id, "date": past_date.isoformat(),
                "race_name": text(past.get("race_name")),
                "race_class": race_class(past.get("race_name")),
                "race_class_source": "race_name",
                "surface": text(past.get("surface")),
                "distance": numeric(past.get("distance")),
                "finish_raw": text(past.get("rank")), "finish": rank,
                "last3f": closing, "passing_raw": text(past.get("passing")),
                "margin_raw": text(past.get("margin")),
                "field": field_evidence(past, text(horse.get("horse_id")), race_index, target_date),
                "opponent_strength": None, "pace_advantage": None,
                "trouble": None, "issue_resolution": None,
                "unknowns": ["相手の実力", "展開の有利不利", "不利の有無", "課題克服"],
                "flags": flags,
            })
        evidence.sort(key=lambda r: r["date"], reverse=True)
        classes = Counter(r["race_class"] or "不明" for r in evidence)
        horses.append({
            "horse_id": text(horse.get("horse_id")),
            "horse_number": text(horse.get("horse_number")),
            "horse_name": text(horse.get("horse_name")),
            "class_counts": dict(classes), "past_races": evidence,
        })
    return {
        "updated_at": datetime.now(timezone(timedelta(hours=9))).isoformat(),
        "target_race_id": target_id, "version": "ability_evidence_v1",
        "scoring_applied": False, "future_race_usage": False,
        "leak_check_passed": True,
        "notes": ["クラスは実績の分類。クラス名だけで能力を決めない。",
                  "上がり順位は同一レース内の観測値。展開有利不利は断定しない。",
                  "このファイルの不明は、既存の別ファイルに材料がないことを意味しない。"],
        "horses": horses,
    }


def main():
    database_path = Path("runner_race_db.json")
    database = load(database_path) if database_path.exists() else {}
    result = build(load("race.json"), load("runner_history.json"), database)
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(OUTPUT)
    print("Ability evidence:", result["target_race_id"], len(result["horses"]), "horses")
    for horse in result["horses"]:
        print(horse["horse_number"], horse["horse_name"], horse["class_counts"])


if __name__ == "__main__":
    main()
