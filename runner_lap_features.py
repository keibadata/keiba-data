
import json
import math
import re
from datetime import datetime, timezone, timedelta
from pathlib import Path


RACE_FILE = Path("race.json")
EVIDENCE_FILE = Path("runner_ability_evidence.json")
OUTPUT_FILE = Path("runner_lap_features.json")

VERSION = "race_lap_features_v1"


def load_json(path):
    with path.open("r", encoding="utf-8") as f:
        data = json.load(f)

    if not isinstance(data, dict):
        raise ValueError(f"JSON object required: {path}")

    return data


def text(value):
    return str(value if value is not None else "").strip()


def finite_number(value):
    if type(value) not in (int, float):
        return None

    value = float(value)

    return value if math.isfinite(value) else None


def round_value(value):
    return round(value, 4) if value is not None else None


def mean(values):
    if not values:
        return None

    return sum(values) / len(values)


def weighted_mean(pairs):
    if not pairs:
        return None

    distance = sum(length for length, _ in pairs)

    if distance <= 0:
        return None

    return sum(
        seconds for _, seconds in pairs
    ) * 200.0 / distance


def validate_segments(row):
    distance = row.get("distance")
    winner = finite_number(row.get("winner_time_seconds"))
    segments = row.get("segments")

    if (
        type(distance) is not int
        or distance < 800
        or distance > 4000
        or winner is None
        or winner <= 0
        or not isinstance(segments, list)
        or not segments
    ):
        raise ValueError("Missing or invalid race lap data")

    previous_end = 0
    previous_time = 0.0
    total = 0.0
    normalized = []

    for index, segment in enumerate(segments):
        if not isinstance(segment, dict):
            raise ValueError("Invalid segment")

        end = segment.get("distance_m")
        length = segment.get("segment_distance_m")
        cumulative = finite_number(
            segment.get("cumulative_seconds")
        )
        lap = finite_number(segment.get("lap_seconds"))

        if (
            type(end) is not int
            or type(length) is not int
            or cumulative is None
            or lap is None
        ):
            raise ValueError("Invalid segment values")

        expected_length = end - previous_end

        if (
            expected_length != length
            or (
                index == 0
                and not 0 < length <= 200
            )
            or (
                index > 0
                and length != 200
            )
            or lap <= 0
            or lap >= 60
            or cumulative <= previous_time
            or abs(
                cumulative - previous_time - lap
            ) > 0.11
        ):
            raise ValueError("Segment continuity mismatch")

        normalized.append({
            "start_m": previous_end,
            "end_m": end,
            "length_m": length,
            "seconds": lap,
            "seconds_per_200m": lap * 200.0 / length,
        })

        previous_end = end
        previous_time = cumulative
        total += lap

    if (
        previous_end != distance
        or abs(previous_time - winner) > 0.11
        or abs(total - winner) > 0.11
    ):
        raise ValueError("Race distance or time mismatch")

    return normalized


def window_average(segments, start, end):
    pairs = []

    for segment in segments:
        overlap = max(
            0,
            min(end, segment["end_m"])
            - max(start, segment["start_m"])
        )

        if overlap <= 0:
            continue

        seconds = (
            segment["seconds"]
            * overlap
            / segment["length_m"]
        )

        pairs.append((overlap, seconds))

    if sum(length for length, _ in pairs) != end - start:
        return None

    return weighted_mean(pairs)


def describe_race(row):
    segments = validate_segments(row)
    distance = row["distance"]

    # 前半・中盤・後半を距離の3等分で比較する。
    first_end = distance / 3.0
    middle_end = distance * 2.0 / 3.0

    early = window_average(
        segments, 0, first_end
    )
    middle = window_average(
        segments, first_end, middle_end
    )
    late = window_average(
        segments, middle_end, distance
    )

    # 最後の600mと、その直前600mを比較する。
    final_600 = (
        window_average(
            segments, distance - 600, distance
        )
        if distance >= 1200
        else None
    )

    preceding_600 = (
        window_average(
            segments, distance - 1200, distance - 600
        )
        if distance >= 1200
        else None
    )

    normalized = [
        segment["seconds_per_200m"]
        for segment in segments
        if segment["length_m"] == 200
    ]

    # 初区間が100m等の場合は変動幅から除く。
    variation = (
        max(normalized) - min(normalized)
        if len(normalized) >= 2
        else None
    )

    # 正の値は後半が遅い（減速）。
    late_minus_early = (
        late - early
        if early is not None and late is not None
        else None
    )

    # 正の値はラスト600mが遅い（減速）。
    final_minus_preceding = (
        final_600 - preceding_600
        if final_600 is not None
        and preceding_600 is not None
        else None
    )

    return {
        "race_id": text(row.get("race_id")),
        "race_date": text(row.get("race_date")),
        "surface": text(row.get("surface")),
        "distance": distance,
        "status": "ok",
        "source_pace_code": row.get("source_pace_code"),
        "source_url": text(row.get("source_url")),
        "features": {
            "early_avg_200m": round_value(early),
            "middle_avg_200m": round_value(middle),
            "late_avg_200m": round_value(late),
            "final_600_avg_200m": round_value(final_600),
            "preceding_600_avg_200m": round_value(
                preceding_600
            ),
            "late_minus_early_seconds_per_200m":
                round_value(late_minus_early),
            "final_minus_preceding_seconds_per_200m":
                round_value(final_minus_preceding),
            "full_segment_variation_seconds_per_200m":
                round_value(variation),
            "complete_200m_segment_count":
                len(normalized),
        },
        "interpretation": {
            "late_minus_early_positive": "後半減速",
            "late_minus_early_negative": "後半加速",
            "final_minus_preceding_positive": "終盤減速",
            "final_minus_preceding_negative": "終盤加速",
            "threshold_classification_applied": False,
            "individual_horse_pace_advantage": None,
            "individual_horse_ability_adjustment": None,
        },
    }


def main():
    race = load_json(RACE_FILE)
    evidence = load_json(EVIDENCE_FILE)

    target_id = text(race.get("race_id"))
    evidence_id = text(evidence.get("target_race_id"))

    if (
        not re.fullmatch(r"\d{12}", target_id)
        or evidence_id != target_id
    ):
        raise ValueError("Target Race ID mismatch")

    if (
        evidence.get("version") != "ability_evidence_v1"
        or evidence.get("future_race_usage") is not False
        or evidence.get("leak_check_passed") is not True
        or evidence.get("scoring_applied") is not False
    ):
        raise ValueError("Evidence safety check failed")

    if (
        evidence.get("lap_connection_schema_version")
        != "race_lap_connection_v1"
        or not isinstance(evidence.get("lap_connection"), dict)
        or evidence["lap_connection"].get("status")
        != "connected"
    ):
        raise ValueError("Race lap connection is unavailable")

    race_laps = evidence.get("race_laps")

    if not isinstance(race_laps, dict):
        raise ValueError("Invalid race_laps structure")

    results = []
    errors = {}

    for race_id, row in sorted(race_laps.items()):
        if (
            not re.fullmatch(r"\d{12}", race_id)
            or not isinstance(row, dict)
            or text(row.get("race_id")) != race_id
        ):
            raise ValueError("Race lap identity mismatch")

        try:
            results.append(describe_race(row))
        except (ValueError, TypeError, KeyError) as exc:
            errors[race_id] = str(exc)
            results.append({
                "race_id": race_id,
                "status": "unknown",
                "features": None,
                "unknown_reason": str(exc),
            })

    output = {
        "version": VERSION,
        "updated_at": datetime.now(
            timezone(timedelta(hours=9))
        ).isoformat(),
        "target_race_id": target_id,
        "source": str(EVIDENCE_FILE),
        "future_race_usage": False,
        "leak_check_passed": True,
        "scoring_applied": False,
        "summary": {
            "race_count": len(results),
            "ok_count": sum(
                r["status"] == "ok" for r in results
            ),
            "unknown_count": len(errors),
        },
        "notes": [
            "レース全体のラップ特徴量であり個別馬ラップではない。",
            "前半・中盤・後半は距離の3等分。",
            "区間を跨ぐ境界では距離比例で時間を按分する。",
            "平均値は200m換算。正の差分は減速を示す。",
            "距離・馬場・コースの異なるレースを直接格付けしない。",
            "取得元のS/M/Hは参考情報であり再判定しない。",
            "展開有利不利、敗因、課題克服は判定しない。",
            "能力点・今回発揮率・最終配点には反映しない。",
            "検証不成立はunknown。0点で補完しない。",
        ],
        "errors": errors,
        "races": results,
    }

    temporary = OUTPUT_FILE.with_suffix(".json.tmp")

    temporary.write_text(
        json.dumps(
            output,
            ensure_ascii=False,
            indent=2,
            allow_nan=False,
        ),
        encoding="utf-8",
    )

    temporary.replace(OUTPUT_FILE)

    print(
        "Runner lap features:",
        target_id,
        output["summary"],
    )


if __name__ == "__main__":
    main()
