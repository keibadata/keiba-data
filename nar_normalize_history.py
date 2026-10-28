"""nar/race.jsonの過去走を整理してnar/history.jsonへ保存する。採点はしない。"""

import hashlib
import json
import os
import re
import tempfile
import unicodedata
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse


BASE_DIR = Path(__file__).resolve().parent
INPUT = BASE_DIR / "nar" / "race.json"
OUTPUT = BASE_DIR / "nar" / "history.json"
JST = timezone(timedelta(hours=9))

INFO_PATTERN = re.compile(
    r"(\S+)\s+(\d{2}\.\d{2}\.\d{2})\s+"
    r"(不良|稍重|重|良)\s+(\d+)頭\s+(\S+)\s+(\S+)\s+(\d+)番"
)


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value or "")),
    ).strip()


def source_identity(url):
    """NARの成績表URLに明示された開催日・場コード・Rだけを使う。"""
    parsed = urlparse(url)

    if (
        parsed.scheme != "https"
        or parsed.netloc != "www.keiba.go.jp"
        or parsed.path != "/KeibaWeb/TodayRaceInfo/RaceMarkTable"
        or parsed.fragment
    ):
        raise ValueError("unsupported_source_url")

    query = parse_qs(parsed.query)
    values = []

    for key in ["k_raceDate", "k_babaCode", "k_raceNo"]:
        items = query.get(key, [])
        if len(items) != 1:
            raise ValueError("invalid_source_identity")
        values.append(items[0])

    day_text, code, race_no = values

    if not re.fullmatch(r"\d{4}/\d{2}/\d{2}", day_text):
        raise ValueError("invalid_source_date")

    day = date.fromisoformat(day_text.replace("/", "-"))

    if not re.fullmatch(r"\d{2}", code):
        raise ValueError("invalid_source_track_code")

    if (
        not re.fullmatch(r"\d{1,2}", race_no)
        or not 1 <= int(race_no) <= 12
    ):
        raise ValueError("invalid_source_race_number")

    return day, code, int(race_no)


def normalize_run(raw, target_day, index):
    if not isinstance(raw, dict):
        raise ValueError("過去走データがオブジェクトではありません")

    flags = []

    run = {
        "history_index": index,
        "race_name": raw.get("race_name"),
        "race_id": None,
        "race_date": None,
        "nar_baba_code": None,
        "race_number": None,
        "track": None,
        "night_race": None,
        "track_condition": None,
        "field_size": None,
        "horse_number": None,
        "finish_position": None,
        "finish_status": None,
        "course_raw": None,
        "direction": None,
        "distance": None,
        "time_seconds": None,
        "corner_positions": None,
        "last_3f_seconds": None,
        "body_weight": None,
        "jockey": None,
        "carried_weight": None,
        "margin_seconds": None,
        "margin_reference": None,
        "reference_horse_name": None,
        "days_before_target": None,
        "eligible_as_past_race": False,
        "quality_flags": flags,
        "source_url": raw.get("source_url"),
        "raw": dict(raw),
    }

    source_day = None

    try:
        source_day, code, race_no = source_identity(
            raw.get("source_url", "")
        )

        run.update({
            "race_id": (
                f"NAR_{source_day:%Y%m%d}_{code}_{race_no:02d}"
            ),
            "race_date": source_day.isoformat(),
            "nar_baba_code": code,
            "race_number": race_no,
            "days_before_target": (target_day - source_day).days,
        })

        if source_day >= target_day:
            flags.append("not_before_target_date")

    except (ValueError, TypeError) as error:
        flags.append(str(error))

    info = INFO_PATTERN.fullmatch(
        clean(raw.get("race_info_raw"))
    )

    if info:
        (
            finish,
            day_text,
            condition,
            count,
            track,
            course,
            horse_no,
        ) = info.groups()

        run.update({
            "track": (
                track[:-1] if track.endswith("ナ") else track
            ),
            "night_race": track.endswith("ナ"),
            "track_condition": condition,
            "field_size": int(count),
            "horse_number": int(horse_no),
            "course_raw": course,
        })

        if (
            source_day
            and day_text != source_day.strftime("%y.%m.%d")
        ):
            flags.append("source_and_display_date_mismatch")

        known_track = {
            "20": "大井",
            "36": "門別",
        }.get(run["nar_baba_code"])

        if known_track and run["track"] != known_track:
            flags.append("source_and_display_track_mismatch")

        position = re.fullmatch(r"(\d+)(降)?", finish)

        if (
            position
            and 1 <= int(position.group(1)) <= int(count)
        ):
            run["finish_position"] = int(position.group(1))
            run["finish_status"] = (
                "降着" if position.group(2) else "完走"
            )
        else:
            run["finish_status"] = finish
            flags.append("no_valid_finish_position")

        course_match = re.fullmatch(
            r"(芝|ダート)?(右|左|直線)(\d+)",
            course,
        )

        if course_match and int(course_match.group(3)) > 0:
            run["direction"] = course_match.group(2)
            run["distance"] = int(course_match.group(3))
        else:
            flags.append("unparsed_course")

        if int(horse_no) < 1 or int(horse_no) > int(count):
            flags.append("invalid_past_horse_number")

    else:
        flags.append("unparsed_race_info")

    performance = re.fullmatch(
        r"(\d+):([0-5]\d\.\d+)\s+"
        r"(\d+(?:-\d+)*)\s+(\d+\.\d+)",
        clean(raw.get("performance_raw")),
    )

    if performance:
        minutes, seconds, corners, last_3f = performance.groups()
        positions = [
            int(value) for value in corners.split("-")
        ]

        run["time_seconds"] = round(
            int(minutes) * 60 + float(seconds),
            3,
        )
        run["last_3f_seconds"] = float(last_3f)

        if all(
            value > 0
            and (
                run["field_size"] is None
                or value <= run["field_size"]
            )
            for value in positions
        ):
            run["corner_positions"] = positions
        else:
            flags.append("invalid_corner_positions")

        if (
            run["last_3f_seconds"] <= 0
            or run["time_seconds"] <= 0
        ):
            flags.append("invalid_time")

    else:
        flags.append("unparsed_performance")

    rider = re.fullmatch(
        r"\d+人\s+(\d+|計不)\s+(.+?)\s+(\d+(?:\.\d+)?)",
        clean(raw.get("jockey_weight_raw")),
    )

    if rider:
        body_weight, jockey, carried = rider.groups()

        run["body_weight"] = (
            int(body_weight) if body_weight.isdigit() else None
        )
        run["jockey"] = jockey
        run["carried_weight"] = float(carried)

        if run["body_weight"] == 0:
            run["body_weight"] = None
            flags.append("invalid_body_weight")

        if run["carried_weight"] <= 0:
            run["carried_weight"] = None
            flags.append("invalid_carried_weight")

    else:
        flags.append("unparsed_jockey_weight")

    margin = re.fullmatch(
        r"([+-]?\d+(?:\.\d+)?)\s+(.+)",
        clean(raw.get("margin_raw")),
    )

    if margin and run["finish_position"] is not None:
        run["margin_seconds"] = float(margin.group(1))
        run["margin_reference"] = (
            "runner_up"
            if run["finish_position"] == 1
            else "winner"
        )
        run["reference_horse_name"] = margin.group(2)
    else:
        flags.append("unparsed_margin")

    run["eligible_as_past_race"] = not flags

    return run


def build_history(data, input_sha256):
    if (
        not isinstance(data, dict)
        or data.get("schema_version") != 1
        or data.get("collection_only") is not True
        or data.get("race_type") != "NAR"
        or data.get("source") != "NAR"
        or data.get("track") != "大井"
        or data.get("nar_baba_code") != "20"
    ):
        raise ValueError(
            "入力は大井の取得専用nar/race.jsonに限定します"
        )

    target_day = date.fromisoformat(data["race_date"])
    race_no = data.get("race_number")

    if type(race_no) is not int or not 1 <= race_no <= 12:
        raise ValueError("対象レースのR番号が不正です")

    expected_id = f"NAR_{target_day:%Y%m%d}_20_{race_no:02d}"

    if data.get("race_id") != expected_id:
        raise ValueError(
            "対象レースのIDが開催日・R番号と一致しません"
        )

    horses = data.get("horses")

    if (
        not isinstance(horses, list)
        or not horses
        or data.get("horse_count") != len(horses)
    ):
        raise ValueError("対象レースの頭数が一致しません")

    output_horses = []
    numbers, horse_ids = set(), set()

    for horse in horses:
        if not isinstance(horse, dict):
            raise ValueError("馬データがオブジェクトではありません")

        number = horse.get("horse_number")
        horse_id = horse.get("horse_id")

        if (
            type(number) is not int
            or number < 1
            or number in numbers
            or not isinstance(horse_id, str)
            or not horse_id
            or horse_id in horse_ids
            or not horse.get("horse_name")
            or horse.get("horse_id_source")
            != "NAR_k_lineageLoginCode"
        ):
            raise ValueError(
                "馬番・馬名・NAR馬IDが不正または重複しています"
            )

        numbers.add(number)
        horse_ids.add(horse_id)

        previous = horse.get("previous_races")

        if (
            not isinstance(previous, list)
            or len(previous) > 5
        ):
            raise ValueError(
                "過去走は0〜5走の配列で指定してください"
            )

        runs = [
            normalize_run(raw, target_day, i + 1)
            for i, raw in enumerate(previous)
        ]

        seen = set()

        for run in runs:
            if run["race_id"]:
                if run["race_id"] in seen:
                    run["quality_flags"].append(
                        "duplicate_past_race"
                    )
                    run["eligible_as_past_race"] = False

                seen.add(run["race_id"])

        output_horses.append({
            "horse_number": number,
            "horse_id": horse_id,
            "horse_id_source": horse["horse_id_source"],
            "horse_name": horse["horse_name"],
            "previous_races": runs,
        })

    all_runs = [
        run
        for horse in output_horses
        for run in horse["previous_races"]
    ]

    return {
        "schema_version": 1,
        "normalizer_version": "nar_history_v1",
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_type": "NAR",
        "race_id": expected_id,
        "race_date": data["race_date"],
        "track": "大井",
        "race_number": race_no,
        "source_file": "nar/race.json",
        "source_updated_at": data.get("updated_at"),
        "source_sha256": input_sha256,
        "summary": {
            "horse_count": len(output_horses),
            "past_race_count": len(all_runs),
            "eligible_past_race_count": sum(
                r["eligible_as_past_race"] for r in all_runs
            ),
            "flagged_past_race_count": sum(
                bool(r["quality_flags"]) for r in all_runs
            ),
            "horses_without_history": sum(
                not h["previous_races"] for h in output_horses
            ),
        },
        "horses": output_horses,
    }


def main():
    source_bytes = INPUT.read_bytes()

    result = build_history(
        json.loads(source_bytes),
        hashlib.sha256(source_bytes).hexdigest(),
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

    print("NAR HISTORY NORMALIZATION OK")
    print("race_id:", result["race_id"])
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("output:", OUTPUT)


if __name__ == "__main__":
    main()
