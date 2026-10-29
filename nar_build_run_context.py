"""各馬の過去走に公式成績表の比較材料を結び付ける。採点はしない。"""

import hashlib
import json
import math
import os
import statistics
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from nar_collect_past_results import requests_from_inputs, require


BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "nar" / "run_context.json"
JST = timezone(timedelta(hours=9))


def positive(value):
    return value if type(value) in (int, float) and math.isfinite(value) and value > 0 else None


def match(current, previous):
    if current is None or current == "" or previous is None or previous == "":
        return None
    return current == previous


def runner_context(target, past_race, runner):
    finishers = [
        r for r in past_race["runners"]
        if type(r.get("finish_position")) is int
        and r["finish_position"] > 0
    ]
    values = [
        positive(r.get("last_3f_seconds"))
        for r in finishers
    ]
    values = [v for v in values if v is not None]
    own = positive(runner.get("last_3f_seconds"))
    recorded_finisher = any(
        r["horse_id"] == runner["horse_id"]
        for r in finishers
    )
    usable_own = own if recorded_finisher else None

    timing = past_race["timing"]
    splits = timing.get("lap_splits")
    first_600 = next(
        (
            s.get("cumulative_seconds")
            for s in (splits or [])
            if s.get("end_distance_m") == 600
        ),
        None,
    )

    comparisons = {
        "same_track": match(
            target.get("nar_baba_code"),
            past_race.get("nar_baba_code"),
        ),
        "same_surface": match(
            target.get("surface"),
            past_race.get("surface"),
        ),
        "same_distance": match(
            positive(target.get("distance")),
            positive(past_race.get("distance")),
        ),
        "same_layout_label": match(
            target.get("course_layout_raw"),
            past_race.get("course_layout_raw"),
        ),
        "same_track_condition": match(
            target.get("track_condition"),
            past_race.get("track_condition"),
        ),
    }

    course_values = [
        comparisons[k]
        for k in [
            "same_track",
            "same_surface",
            "same_distance",
            "same_layout_label",
        ]
    ]
    comparisons["same_course"] = (
        None
        if any(v is None for v in course_values)
        else all(course_values)
    )

    finish = runner.get("finish_position")
    corners = runner.get("corner_positions")
    position_change = None

    if (
        type(finish) is int
        and finish > 0
        and isinstance(corners, list)
        and corners
    ):
        if type(corners[-1]) is int and corners[-1] > 0:
            position_change = corners[-1] - finish

    return {
        "race_conditions": {
            key: past_race.get(key)
            for key in [
                "track",
                "nar_baba_code",
                "race_name",
                "surface",
                "distance",
                "course_layout_raw",
                "track_condition",
                "race_conditions_raw",
                "race_class",
            ]
        },
        "runner_result": {
            key: runner.get(key)
            for key in [
                "horse_id",
                "horse_number",
                "horse_name",
                "finish_position",
                "finish_status_raw",
                "time_seconds",
                "last_3f_seconds",
                "corner_positions",
                "carried_weight",
                "body_weight",
                "official_finish_margin_text",
                "time_difference_to_winner_seconds",
            ]
        },
        "within_race_comparison": {
            "listed_horse_count": past_race["listed_horse_count"],
            "starter_count": past_race["starter_count"],
            "ranked_finisher_count": len(finishers),
            "recorded_finisher_last_3f_count": len(values),
            "last_3f_rank_among_recorded_finishers": (
                1 + sum(v < usable_own for v in values)
                if usable_own is not None
                else None
            ),
            "last_3f_equal_time_count": (
                sum(v == usable_own for v in values)
                if usable_own is not None
                else None
            ),
            "fastest_recorded_finisher_last_3f_seconds": (
                min(values) if values else None
            ),
            "median_recorded_finisher_last_3f_seconds": (
                round(statistics.median(values), 3)
                if values else None
            ),
            "last_3f_difference_from_fastest_seconds": (
                round(usable_own - min(values), 3)
                if usable_own is not None and values
                else None
            ),
            "last_corner_to_finish_position_change": position_change,
        },
        "race_timing": {
            "lap_splits": splits,
            "first_600m_seconds": positive(first_600),
            "race_last_600m_seconds": positive(
                timing.get("race_last_furlong_seconds", {}).get("3F")
            ),
            "all_horses_corner_order": timing.get(
                "all_horses_corner_order",
                [],
            ),
            "availability_notes": timing.get(
                "availability_notes",
                [],
            ),
        },
        "comparison_to_target": comparisons,
    }


def build_context(race_bytes, history_bytes, past_bytes):
    target, history, requests, skipped = requests_from_inputs(
        race_bytes,
        history_bytes,
    )
    past = json.loads(past_bytes)

    require(
        past.get("schema_version") == 1
        and past.get("collector_version") == "nar_past_results_v1",
        "過去成績表の形式が不正です",
    )
    require(
        past.get("collection_only") is True
        and past.get("race_type") == "NAR",
        "NAR取得専用データではありません",
    )
    require(
        past.get("source_race_sha256")
        == hashlib.sha256(race_bytes).hexdigest(),
        "過去成績表の出馬表参照が古くなっています",
    )
    require(
        past.get("source_history_sha256")
        == hashlib.sha256(history_bytes).hexdigest(),
        "過去成績表の過去走参照が古くなっています",
    )

    for key in ["race_id", "race_date", "track", "race_number"]:
        require(
            past.get(key) == target.get(key),
            "対象レースが一致しません: " + key,
        )

    races = past.get("races")
    require(
        isinstance(races, list) and len(races) == len(requests),
        "過去成績表のレース数が一致しません",
    )
    lookup = {r["race_id"]: r for r in races}
    require(
        set(lookup) == set(requests),
        "過去成績表に不足または重複があります",
    )
    target_day = date.fromisoformat(target["race_date"])

    for race_id, result in lookup.items():
        require(
            date.fromisoformat(result["race_date"]) < target_day,
            "対象日以降の成績が混入しています",
        )
        expected = requests[race_id]
        require(
            result["race_date"] == expected["day"].isoformat()
            and result["nar_baba_code"] == expected["code"]
            and result["race_number"] == expected["race_no"],
            "過去レース識別情報が一致しません",
        )

        runners = result.get("runners")
        require(
            isinstance(runners, list) and bool(runners),
            "全頭成績がありません",
        )
        require(
            len({r["horse_id"] for r in runners}) == len(runners),
            "成績表の馬IDが重複しています",
        )
        require(
            result.get("listed_horse_count") == len(runners),
            "成績表の掲載頭数が一致しません",
        )
        require(
            isinstance(result.get("timing"), dict),
            "レースタイム情報が不正です",
        )

    horses, linked_count = [], 0

    for horse in history["horses"]:
        runs = []

        for run in horse["previous_races"]:
            item = {
                "history_index": run["history_index"],
                "race_id": run.get("race_id"),
                "race_date": run.get("race_date"),
                "source_url": run.get("source_url"),
                "linked": False,
                "quality_flags": list(run["quality_flags"]),
                "context": None,
            }

            if run["eligible_as_past_race"]:
                result = lookup[run["race_id"]]
                runner = next(
                    (
                        r for r in result["runners"]
                        if r["horse_id"] == horse["horse_id"]
                    ),
                    None,
                )
                require(
                    runner is not None,
                    "過去成績表に対象馬が見つかりません",
                )

                for key in [
                    "horse_number",
                    "finish_position",
                    "time_seconds",
                    "last_3f_seconds",
                    "corner_positions",
                ]:
                    require(
                        runner.get(key) == run.get(key),
                        "過去走の馬情報が一致しません: " + key,
                    )

                require(
                    result.get("distance") == run.get("distance")
                    and result.get("track") == run.get("track"),
                    "過去走の距離・競馬場が一致しません",
                )
                require(
                    result.get("track_condition")
                    == run.get("track_condition")
                    and result.get("starter_count")
                    == run.get("field_size"),
                    "過去走の馬場・頭数が一致しません",
                )

                winner = positive(result.get("winner_time_seconds"))
                own = positive(runner.get("time_seconds"))
                require(
                    winner is not None and own is not None,
                    "勝ち馬・対象馬の時計がありません",
                )
                require(
                    runner.get("time_difference_to_winner_seconds")
                    == round(own - winner, 3),
                    "勝ち馬との時計差が一致しません",
                )

                item["linked"] = True
                item["context"] = runner_context(
                    target,
                    result,
                    runner,
                )
                linked_count += 1

            runs.append(item)

        horses.append({
            "horse_number": horse["horse_number"],
            "horse_id": horse["horse_id"],
            "horse_name": horse["horse_name"],
            "previous_race": runs[0] if runs else None,
            "runs": runs,
        })

    return {
        "schema_version": 1,
        "context_version": "nar_run_context_v1",
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_type": "NAR",
        "race_id": target["race_id"],
        "race_date": target["race_date"],
        "track": "大井",
        "race_number": target["race_number"],
        "source_race_sha256": hashlib.sha256(race_bytes).hexdigest(),
        "source_history_sha256": hashlib.sha256(history_bytes).hexdigest(),
        "source_past_results_sha256": hashlib.sha256(past_bytes).hexdigest(),
        "summary": {
            "horse_count": len(horses),
            "past_race_count": sum(len(h["runs"]) for h in horses),
            "linked_past_race_count": linked_count,
            "unlinked_past_race_count": len(skipped),
        },
        "limitations": [
            "上がり順位は同一レースの記録がある完走馬内での順位。能力順位ではない",
            "同タイムは同順位とし、同タイム頭数と記録頭数を併記する",
            "順位の変化だけで不利・敗因・スタミナを断定しない",
            "ラップ未掲載は未取得のまま保持し、ペース区分を推測しない",
            "レース全体の上がりと各馬の上がりを区別する",
            "能力・発揮率・課題克服度は未評価",
        ],
        "horses": horses,
    }


def main():
    result = build_context(
        (BASE / "nar/race.json").read_bytes(),
        (BASE / "nar/history.json").read_bytes(),
        (BASE / "nar/past_results.json").read_bytes(),
    )

    temporary = None

    try:
        with tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=OUTPUT.parent,
            delete=False,
        ) as handle:
            temporary = Path(handle.name)
            json.dump(
                result,
                handle,
                ensure_ascii=False,
                indent=2,
                allow_nan=False,
            )
            handle.write("\n")

        os.replace(temporary, OUTPUT)

    finally:
        if temporary is not None and temporary.exists():
            temporary.unlink()

    print("NAR RUN CONTEXT OK")
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("output:", OUTPUT)


if __name__ == "__main__":
    main()
