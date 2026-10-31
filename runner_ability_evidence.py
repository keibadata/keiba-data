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


def clock_seconds(value):
    value = unicodedata.normalize("NFKC", text(value))
    match = re.fullmatch(r"(\d+):(\d{1,2}(?:\.\d+)?)", value)
    if not match:
        return None
    minutes, seconds = int(match[1]), float(match[2])
    return minutes * 60 + seconds if 0 <= seconds < 60 else None


def numeric_position(value):
    value = finish(value)
    return value if value is not None else None


def field_evidence(past, horse_id, database, target_date, entrants=None):
    entrants = entrants or {}
    unknown = {
        "matched": False,
        "classified_finish_count": None,
        "last3f_observed_count": None,
        "last3f_rank": None,
        "winner_time_gap_seconds": None,
        "passing_4c": None,
        "current_opponents": [],
        "comparison_conflicts": [],
        "pace_label": None,
        "pace_unknown_reason": "ラップ・ペース判定データ未接続",
    }

    historical = database.get(text(past.get("race_id")))
    if historical is None:
        return unknown

    historical_date = parse_date(
        historical.get("race_date") or historical.get("date")
    )
    if (
        historical_date != parse_date(past.get("date"))
        or historical_date >= target_date
    ):
        return unknown

    rows = historical.get("results", [])
    if (
        not isinstance(rows, list)
        or any(not isinstance(r, dict) for r in rows)
    ):
        raise ValueError("Invalid historical results structure")

    own = [
        r for r in rows
        if text(r.get("horse_id")) == horse_id
    ]
    if len(own) != 1:
        return unknown

    own = own[0]
    own_finish = finish(own.get("rank"))
    history_finish = finish(past.get("rank"))

    if own_finish != history_finish:
        return dict(
            unknown,
            comparison_conflicts=[
                "過去走一覧と結果DBの着順不一致"
            ],
        )

    own_clock = clock_seconds(own.get("time"))
    history_clock = clock_seconds(past.get("time"))

    if (
        own_clock is not None
        and history_clock is not None
        and abs(own_clock - history_clock) > 0.11
    ):
        return dict(
            unknown,
            comparison_conflicts=[
                "過去走一覧と結果DBの走破時計不一致"
            ],
        )

    own_time = last3f(own.get("last3f"))
    history_closing = last3f(past.get("last3f"))

    if (
        own_time is not None
        and history_closing is not None
        and abs(own_time - history_closing) > 0.11
    ):
        return dict(
            unknown,
            comparison_conflicts=[
                "過去走一覧と結果DBの上がり不一致"
            ],
        )

    observed = [
        v for r in rows
        if (v := last3f(r.get("last3f"))) is not None
    ]
    winner_clocks = [
        v for r in rows
        if finish(r.get("rank")) == 1
        and (v := clock_seconds(r.get("time"))) is not None
    ]
    winner_clock = min(winner_clocks) if winner_clocks else None

    opponents = []
    seen = set()

    for row in rows:
        opponent_id = text(row.get("horse_id"))

        if opponent_id not in entrants or opponent_id == horse_id:
            continue

        if opponent_id in seen:
            return dict(
                unknown,
                comparison_conflicts=[
                    "結果DBの対戦馬ID重複"
                ],
            )

        seen.add(opponent_id)
        rival = entrants[opponent_id]
        opponent_finish = finish(row.get("rank"))
        opponent_clock = clock_seconds(row.get("time"))

        comparable = (
            own_finish is not None
            and opponent_finish is not None
        )
        outcome = None

        if comparable:
            if own_finish < opponent_finish:
                outcome = "先着"
            elif own_finish > opponent_finish:
                outcome = "後着"
            else:
                outcome = "同着"

        opponents.append({
            "comparison_key": "|".join(
                [text(past.get("race_id"))]
                + sorted([horse_id, opponent_id])
            ),
            "horse_id": opponent_id,
            "horse_name": rival["horse_name"],
            "current_horse_number": rival["horse_number"],
            "past_horse_number": text(row.get("horse_number")),
            "finish_raw": text(row.get("rank")),
            "finish": opponent_finish,
            "own_finish": own_finish,
            "outcome": outcome,
            "own_minus_opponent_seconds": (
                round(own_clock - opponent_clock, 2)
                if comparable
                and own_clock is not None
                and opponent_clock is not None
                else None
            ),
        })

    return {
        "matched": True,
        "classified_finish_count": sum(
            finish(r.get("rank")) is not None for r in rows
        ),
        "last3f_observed_count": len(observed),
        "last3f_rank": (
            1 + sum(v < own_time for v in observed)
            if own_time is not None
            else None
        ),
        "winner_time_gap_seconds": (
            round(own_clock - winner_clock, 2)
            if own_finish is not None
            and own_clock is not None
            and winner_clock is not None
            else None
        ),
        "passing_4c": numeric_position(own.get("passing_4c")),
        "current_opponents": opponents,
        "comparison_conflicts": [],
        "pace_label": None,
        "pace_unknown_reason": "ラップ・ペース判定データ未接続",
    }


def build(race, history, database):
    target_id = text(race.get("race_id"))
    target_date = parse_date(race.get("race_date"))

    if not target_id or target_date is None:
        raise ValueError("race.json: race_id / race_date missing")

    if text(history.get("target_race_id")) != target_id:
        raise ValueError("runner_history target race mismatch")

    if (
        history.get("future_race_usage") is not False
        or history.get("leak_check_passed") is not True
    ):
        raise ValueError("runner_history leak check failed")

    if database and (
        text(database.get("target_race_id")) != target_id
        or database.get("future_race_usage") is not False
        or database.get("leak_check_passed") is not True
    ):
        raise ValueError("runner_race_db target or leak check failed")

    race_index = {}

    for row in database.get("races", []):
        key = text(row.get("race_id"))
        if key in race_index:
            raise ValueError(f"Duplicate database race: {key}")
        if key:
            race_index[key] = row

    entrants = {}

    for horse in history.get("horses", []):
        horse_id = text(horse.get("horse_id"))

        if not horse_id or horse_id in entrants:
            raise ValueError("Missing or duplicate current horse ID")

        entrants[horse_id] = {
            "horse_name": text(horse.get("horse_name")),
            "horse_number": text(horse.get("horse_number")),
        }

    horses = []

    for horse in history.get("horses", []):
        evidence = []
        seen = set()

        for past in horse.get("past_races", []):
            past_date = parse_date(past.get("date"))
            past_id = text(past.get("race_id"))

            if (
                past_date is None
                or past_date >= target_date
                or past_id == target_id
            ):
                raise ValueError(
                    "Unknown date, same-day or future race in history"
                )

            key = (
                past_date,
                past_id or text(past.get("race_name")),
            )
            if key in seen:
                raise ValueError(
                    f"Duplicate horse history: "
                    f"{horse.get('horse_id')} {key}"
                )
            seen.add(key)

            rank = finish(past.get("rank"))
            closing = last3f(past.get("last3f"))
            flags = []

            if rank is None:
                flags.append("着順不明・取消等を0点に置換しない")
            if closing is None:
                flags.append("上がり不明を固定点に置換しない")

            evidence.append({
                "race_id": past_id,
                "date": past_date.isoformat(),
                "race_name": text(past.get("race_name")),
                "race_class": race_class(past.get("race_name")),
                "race_class_source": "race_name",
                "surface": text(past.get("surface")),
                "distance": numeric(past.get("distance")),
                "finish_raw": text(past.get("rank")),
                "finish": rank,
                "last3f": closing,
                "passing_raw": text(past.get("passing")),
                "margin_raw": text(past.get("margin")),
                "field": field_evidence(
                    past,
                    text(horse.get("horse_id")),
                    race_index,
                    target_date,
                    entrants,
                ),
                "opponent_strength": None,
                "pace_advantage": None,
                "trouble": None,
                "issue_resolution": None,
                "unknowns": [
                    "相手の実力",
                    "展開の有利不利",
                    "不利の有無",
                    "課題克服",
                ],
                "flags": flags,
            })

        evidence.sort(
            key=lambda r: r["date"],
            reverse=True,
        )
        classes = Counter(
            r["race_class"] or "不明"
            for r in evidence
        )

        horses.append({
            "horse_id": text(horse.get("horse_id")),
            "horse_number": text(horse.get("horse_number")),
            "horse_name": text(horse.get("horse_name")),
            "class_counts": dict(classes),
            "past_races": evidence,
        })

    all_rows = [
        row for horse in horses
        for row in horse["past_races"]
    ]
    comparisons = [
        opponent for row in all_rows
        for opponent in row["field"]["current_opponents"]
    ]

    return {
        "updated_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(),
        "target_race_id": target_id,
        "version": "ability_evidence_v1",
        "comparison_schema_version": "field_comparison_v1",
        "database_connected": bool(database),
        "scoring_applied": False,
        "future_race_usage": False,
        "leak_check_passed": True,
        "summary": {
            "horse_count": len(horses),
            "past_race_count": len(all_rows),
            "field_matched_count": sum(
                row["field"]["matched"] for row in all_rows
            ),
            "field_conflict_count": sum(
                bool(row["field"]["comparison_conflicts"])
                for row in all_rows
            ),
            "winner_time_gap_count": sum(
                row["field"]["winner_time_gap_seconds"] is not None
                for row in all_rows
            ),
            "direct_comparison_row_count": len(comparisons),
            "comparable_direct_row_count": sum(
                row["outcome"] is not None
                for row in comparisons
            ),
            "unique_direct_meeting_count": len({
                row["comparison_key"]
                for row in comparisons
            }),
            "unique_comparable_meeting_count": len({
                row["comparison_key"]
                for row in comparisons
                if row["outcome"] is not None
            }),
            "pace_known_count": 0,
        },
        "notes": [
            "クラスは実績の分類。クラス名だけで能力を決めない。",
            "上がり順位は同一レース内の観測値。展開有利不利は断定しない。",
            "直接対戦は両馬の記録に出る。同じ比較キーは1対戦として扱う。",
            "同一レースの着順・時計差・上がりは、独立した複数の上昇根拠と数えない。",
            "このファイルの不明は、既存の別ファイルに材料がないことを意味しない。",
        ],
        "horses": horses,
    }


def main():
    database_path = Path("runner_race_db.json")
    database = load(database_path) if database_path.exists() else {}

    result = build(
        load("race.json"),
        load("runner_history.json"),
        database,
    )

    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(
        json.dumps(
            result,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    temporary.replace(OUTPUT)

    print(
        "Ability evidence:",
        result["target_race_id"],
        len(result["horses"]),
        "horses",
    )
    print(result["summary"])

    for horse in result["horses"]:
        print(
            horse["horse_number"],
            horse["horse_name"],
            horse["class_counts"],
        )


if __name__ == "__main__":
    main()
