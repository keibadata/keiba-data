"""過去走の観測事実・課題候補・今回の変更を分離して保存する。採点はしない。"""

import hashlib
import json
import math
import os
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path


BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "nar" / "previous_race_evidence.json"
JST = timezone(timedelta(hours=9))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def numeric(value):
    return type(value) in (int, float) and math.isfinite(value)


def describe_run(run, comparison):
    observations, candidates, changes = [], [], []
    context = run.get("context")

    if run["linked"]:
        result = context["runner_result"]
        within = context["within_race_comparison"]
        group = run["race_id"]

        def observe(code, text, values):
            item = {
                "code": code,
                "text": text,
                "evidence_group_id": group,
                "values": values,
            }
            observations.append(item)
            return item

        if result.get("finish_position") == 1:
            observe(
                "won",
                "過去レースで1着",
                {"finish_position": 1},
            )

        if within.get("last_3f_rank_among_recorded_finishers") == 1:
            observe(
                "fastest_recorded_last3f",
                "記録のある完走馬内で上がり最速（同順位を含む）",
                {
                    "last_3f_seconds": result.get("last_3f_seconds"),
                    "recorded_count": within.get(
                        "recorded_finisher_last_3f_count"
                    ),
                    "ranked_finisher_count": within.get(
                        "ranked_finisher_count"
                    ),
                    "equal_time_count": within.get(
                        "last_3f_equal_time_count"
                    ),
                },
            )

        change = within.get("last_corner_to_finish_position_change")
        finish = result.get("finish_position")
        status = result.get("finish_status_raw")

        if numeric(change) and change != 0 and status == str(finish):
            code = (
                "late_position_gain"
                if change > 0
                else "late_position_loss"
            )
            text = (
                "最終コーナーから着順上昇"
                if change > 0
                else "最終コーナーから着順後退"
            )
            observed = observe(
                code,
                text,
                {
                    "position_change": change,
                    "finish_position": finish,
                    "corner_positions": result.get("corner_positions"),
                },
            )

            if change < 0:
                candidates.append({
                    "code": "late_position_loss_review",
                    "text": "終盤の順位後退について原因確認が必要",
                    "observation_code": observed["code"],
                    "evidence_group_id": group,
                    "confirmation_status": "unconfirmed",
                    "cause": None,
                })

        facts = comparison["comparison"]

        for field, label, unit in [
            ("distance_change_m", "距離変更", "m"),
            ("carried_weight_change_kg", "斤量変更", "kg"),
            ("body_weight_change_kg", "過去走からの馬体重変化", "kg"),
        ]:
            value = facts.get(field)
            if numeric(value) and value != 0:
                changes.append({
                    "field": field,
                    "text": label,
                    "difference": value,
                    "unit": unit,
                })

        for field, label in [
            ("same_track", "競馬場変更"),
            ("same_surface", "芝・ダート変更"),
            ("same_layout_label", "内外回り等の表記変更"),
            ("same_track_condition", "馬場状態変更"),
        ]:
            if context["comparison_to_target"].get(field) is False:
                changes.append({
                    "field": field,
                    "text": label,
                })

    strengths = [
        o for o in observations
        if o["code"] in {
            "won",
            "fastest_recorded_last3f",
            "late_position_gain",
        }
    ]

    return {
        "history_index": run["history_index"],
        "race_id": run.get("race_id"),
        "race_date": run.get("race_date"),
        "source_url": run.get("source_url"),
        "data_available": run["linked"],
        "quality_flags": list(run["quality_flags"]),
        "observations": observations,
        "strength_materials": strengths,
        "issue_candidates": candidates,
        "issue_review_complete": False,
        "confirmed_issues": None,
        "condition_changes_for_review": changes,
        "overcoming_assessment": {
            "status": "unconfirmed",
            "confirmed_connections": None,
            "reason": "条件変更だけでは前走敗因・課題克服を確定しない",
        },
    }


def build_evidence(race_bytes, context_bytes, condition_bytes):
    race, context, condition = [
        json.loads(b)
        for b in [race_bytes, context_bytes, condition_bytes]
    ]

    require(
        race.get("race_type") == "NAR"
        and race.get("track") == "大井"
        and race.get("collection_only") is True,
        "対象は大井の取得専用データに限定します",
    )
    require(
        race.get("schema_version") == 1
        and race.get("nar_baba_code") == "20",
        "出馬表の形式が不正です",
    )

    target_day = date.fromisoformat(race["race_date"])
    race_no = race.get("race_number")

    require(
        type(race_no) is int and 1 <= race_no <= 12,
        "対象R番号が不正です",
    )
    require(
        race.get("race_id")
        == f"NAR_{target_day:%Y%m%d}_20_{race_no:02d}",
        "対象Race IDが不正です",
    )
    require(
        context.get("context_version") == "nar_run_context_v1"
        and condition.get("evidence_version")
        == "nar_condition_evidence_v1",
        "入力のバージョンが不正です",
    )

    for source in [context, condition]:
        require(
            source.get("schema_version") == 1
            and source.get("collection_only") is True
            and source.get("race_type") == "NAR",
            "入力の形式が不正です",
        )
        require(
            source.get("source_race_sha256")
            == hashlib.sha256(race_bytes).hexdigest(),
            "出馬表の参照が古くなっています",
        )
        for key in ["race_id", "race_date", "track", "race_number"]:
            require(
                source.get(key) == race.get(key),
                "対象レースが一致しません: " + key,
            )

    require(
        bool(context.get("source_history_sha256"))
        and context["source_history_sha256"]
        == condition.get("source_history_sha256"),
        "過去走の参照元が一致しません",
    )

    horses = race.get("horses")
    contexts = context.get("horses")
    conditions = condition.get("horses")

    require(
        isinstance(horses, list)
        and bool(horses)
        and race.get("horse_count") == len(horses),
        "出馬表の頭数が不正です",
    )
    require(
        isinstance(contexts, list)
        and isinstance(conditions, list)
        and len(horses) == len(contexts) == len(conditions),
        "入力の頭数が一致しません",
    )

    output = []

    for horse, ctx_horse, cond_horse in zip(
        horses,
        contexts,
        conditions,
    ):
        for key in ["horse_number", "horse_id", "horse_name"]:
            require(
                horse.get(key)
                == ctx_horse.get(key)
                == cond_horse.get(key),
                "馬情報が一致しません: " + key,
            )

        runs = ctx_horse.get("runs")
        comparisons = cond_horse.get("comparisons")

        require(
            isinstance(runs, list)
            and isinstance(comparisons, list)
            and len(runs)
            == len(comparisons)
            == len(horse["previous_races"]),
            "過去走数が一致しません",
        )

        described = []

        for index, (run, comp) in enumerate(
            zip(runs, comparisons),
            1,
        ):
            require(
                run.get("history_index")
                == comp.get("history_index")
                == index,
                "過去走の順番が一致しません",
            )
            for key in [
                "race_id",
                "race_date",
                "source_url",
                "quality_flags",
            ]:
                require(
                    run.get(key) == comp.get(key),
                    "過去走の参照が一致しません: " + key,
                )

            require(
                type(run.get("linked")) is bool
                and run["linked"]
                == comp.get("available_for_comparison"),
                "過去走の利用可否が一致しません",
            )

            if run["linked"]:
                require(
                    date.fromisoformat(run["race_date"]) < target_day,
                    "対象日以降の成績が混入しています",
                )
                require(
                    run["context"]["runner_result"]["horse_id"]
                    == horse["horse_id"],
                    "結合先の馬IDが一致しません",
                )

            described.append(describe_run(run, comp))

        occurrences = {}

        for item in described:
            for obs in item["observations"]:
                occurrences.setdefault(
                    obs["code"],
                    set(),
                ).add(obs["evidence_group_id"])

        output.append({
            "horse_number": horse["horse_number"],
            "horse_id": horse["horse_id"],
            "horse_name": horse["horse_name"],
            "previous_race": described[0] if described else None,
            "runs": described,
            "observation_race_ids_by_code": {
                code: sorted(ids)
                for code, ids in occurrences.items()
            },
            "unassessed_items": [
                "前走敗因",
                "課題確定",
                "課題克服度",
                "クラス比較",
                "不利の有無",
                "ペース適否",
                "能力",
                "今回発揮率",
            ],
        })

    return {
        "schema_version": 1,
        "evidence_version": "nar_previous_evidence_v1",
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_type": "NAR",
        "race_id": race["race_id"],
        "race_date": race["race_date"],
        "track": "大井",
        "race_number": race_no,
        "source_race_sha256": hashlib.sha256(race_bytes).hexdigest(),
        "source_run_context_sha256": hashlib.sha256(
            context_bytes
        ).hexdigest(),
        "source_condition_evidence_sha256": hashlib.sha256(
            condition_bytes
        ).hexdigest(),
        "summary": {
            "horse_count": len(output),
            "past_race_count": sum(
                len(h["runs"]) for h in output
            ),
        },
        "rules": [
            "観測事実・課題候補・今回条件変更を分離し、自動加減点しない",
            "同じレース内の複数観測は同一グループとし、独立上昇根拠の個数にしない",
            "順位後退だけで距離不適・スタミナ不足・能力不足を確定しない",
            "距離短縮等の変更だけで課題克服を確定しない",
            "勝利していても課題の確認完了とはしない",
            "未確認の課題・克服は0や空配列で確定扱いにしない",
        ],
        "horses": output,
    }


def main():
    names = ["race", "run_context", "condition_evidence"]
    result = build_evidence(
        *[
            (BASE / f"nar/{name}.json").read_bytes()
            for name in names
        ]
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

    print("NAR PREVIOUS EVIDENCE OK")
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("output:", OUTPUT)


if __name__ == "__main__":
    main()
