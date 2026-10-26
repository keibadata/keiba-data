import argparse
import json
import re
import subprocess
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

SNAPSHOT_ROOT = Path("prediction_snapshots")
VERIFICATION_ROOT = Path("race_verifications")
RACE_FILE = Path("race.json")
VERIFICATION_SCRIPT = Path("race_verification.py")
AGGREGATE_SCRIPT = Path("verification_aggregate.py")
AGGREGATE_FILE = Path("verification_database.json")
TEMP_RESULT_FILE = Path("verification_day_results.json")
JST = timezone(timedelta(hours=9))


def now_jst():
    return datetime.now(JST)


def load_json(path):
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
        f.write("\n")


def text(value):
    value = str(value or "").translate(
        str.maketrans(
            "０１２３４５６７８９：．－＋",
            "0123456789:.-+",
        )
    )
    return re.sub(
        r"\s+",
        " ",
        value.replace("\u3000", " "),
    ).strip()


def race_id(value):
    value = text(value)

    if not re.fullmatch(r"\d{12}", value):
        raise ValueError(
            f"invalid race_id: {value!r}"
        )

    return value


def parse_iso(value):
    value = text(value)

    if not value:
        return None

    try:
        dt = datetime.fromisoformat(
            value.replace(
                "Z",
                "+00:00",
            )
        )
    except ValueError:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(
            tzinfo=JST
        )

    return dt.astimezone(JST)


def race_day(race):
    date_text = text(
        race.get("race_date")
        or race.get("date")
    )

    if not re.fullmatch(
        r"\d{4}-\d{2}-\d{2}",
        date_text,
    ):
        return None

    try:
        return datetime.strptime(
            date_text,
            "%Y-%m-%d",
        )
    except ValueError:
        return None


def race_start(race):
    day = race_day(race)
    time_text = text(
        race.get(
            "scheduled_start_time"
        )
    )

    if day is None:
        return None

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        time_text,
    )

    if not match:
        return None

    hour, minute = map(
        int,
        match.groups(),
    )

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return None

    return datetime(
        day.year,
        day.month,
        day.day,
        hour,
        minute,
        tzinfo=JST,
    )


def verification_path(snapshot):
    race = (
        snapshot.get("race")
        or {}
    )

    rid = race_id(
        race.get("race_id")
    )

    date_text = text(
        race.get("race_date")
        or race.get("date")
    )

    sid = re.sub(
        r"[^0-9A-Za-z_+\-]",
        "_",
        text(
            snapshot.get(
                "snapshot_id"
            )
        ),
    )

    if not date_text or not sid:
        raise ValueError(
            "snapshot race_date or "
            "snapshot_id is missing"
        )

    return (
        VERIFICATION_ROOT
        / date_text
        / rid
        / f"verification_{sid}.json"
    )


def latest_eligible_snapshots():
    if not SNAPSHOT_ROOT.exists():
        return []

    grouped = {}

    for path in SNAPSHOT_ROOT.rglob(
        "*.json"
    ):
        try:
            data = load_json(path)
        except Exception:
            continue

        if (
            data.get("snapshot_kind")
            != "prediction"
        ):
            continue

        timing = (
            data.get("timing")
            or {}
        )

        if (
            timing.get(
                "evaluation_eligible"
            )
            is not True
        ):
            continue

        race = (
            data.get("race")
            or {}
        )

        try:
            rid = race_id(
                race.get("race_id")
            )
        except Exception:
            continue

        saved_at = parse_iso(
            data.get(
                "prediction_saved_at"
            )
        )

        if saved_at is None:
            continue

        old = grouped.get(rid)

        if (
            old is None
            or saved_at
            > old["saved_at"]
        ):
            grouped[rid] = {
                "path": path,
                "data": data,
                "saved_at": saved_at,
            }

    return sorted(
        grouped.values(),
        key=lambda item: (
            race_start(
                item["data"].get(
                    "race"
                )
                or {}
            )
            or datetime.max.replace(
                tzinfo=JST
            ),
            text(
                (
                    item["data"].get(
                        "race"
                    )
                    or {}
                ).get(
                    "race_id"
                )
            ),
        ),
    )


def temporary_race(snapshot):
    race = (
        snapshot.get("race")
        or {}
    )

    rid = race_id(
        race.get("race_id")
    )

    date_text = text(
        race.get("race_date")
        or race.get("date")
    )

    track = text(
        race.get("track")
        or race.get("racecourse")
    )

    if not date_text:
        raise ValueError(
            "snapshot race_date "
            "is missing"
        )

    return {
        "race_id": rid,
        "race_date": date_text,
        "date": date_text,
        "track": track,
        "racecourse": track,
        "race_name": text(
            race.get("race_name")
        ),
        "race_class": text(
            race.get("race_class")
        ),
        "age_condition": text(
            race.get("age_condition")
        ),
        "is_debut": bool(
            race.get(
                "is_debut",
                False,
            )
        ),
        "surface": text(
            race.get("surface")
        ),
        "distance": race.get(
            "distance"
        ),
        "track_condition": text(
            race.get(
                "track_condition"
            )
        ),
        "horse_count": race.get(
            "horse_count"
        ),
        "scheduled_start_time":
            text(
                race.get(
                    "scheduled_start_time"
                )
            ),
        "auto_verification_context":
            True,
        "updated_at":
            now_jst().isoformat(
                timespec="seconds"
            ),
    }


def run(command):
    result = subprocess.run(
        command,
        text=True,
        capture_output=True,
        check=False,
    )

    if result.stdout:
        print(
            result.stdout.rstrip()
        )

    if result.stderr:
        print(
            result.stderr.rstrip(),
            file=sys.stderr,
        )

    return result


def validate_verification(
    path,
    snapshot,
):
    if not path.exists():
        raise FileNotFoundError(
            "verification file was "
            f"not created: {path}"
        )

    data = load_json(path)

    selected = (
        data.get(
            "prediction_snapshot"
        )
        or {}
    )

    expected_rid = race_id(
        (
            snapshot.get("race")
            or {}
        ).get(
            "race_id"
        )
    )

    expected_sid = text(
        snapshot.get(
            "snapshot_id"
        )
    )

    if (
        text(
            data.get("race_id")
        )
        != expected_rid
    ):
        raise ValueError(
            "verification "
            "race_id mismatch"
        )

    if (
        data.get(
            "aggregate_eligible"
        )
        is not True
    ):
        raise ValueError(
            "automatic verification "
            "is not aggregate_eligible"
        )

    if (
        text(
            selected.get(
                "snapshot_id"
            )
        )
        != expected_sid
    ):
        raise ValueError(
            "verification "
            "snapshot_id mismatch"
        )

    if (
        selected.get(
            "evaluation_eligible"
        )
        is not True
    ):
        raise ValueError(
            "verification selected "
            "an ineligible snapshot"
        )


def verify_one(item):
    snapshot = item["data"]

    race = (
        snapshot.get("race")
        or {}
    )

    rid = race_id(
        race.get("race_id")
    )

    output = (
        verification_path(
            snapshot
        )
    )

    if output.exists():
        validate_verification(
            output,
            snapshot,
        )

        return {
            "race_id": rid,
            "status":
                "already_verified",
            "path": str(output),
        }

    save_json(
        RACE_FILE,
        temporary_race(
            snapshot
        ),
    )

    TEMP_RESULT_FILE.unlink(
        missing_ok=True
    )

    print()
    print(
        "AUTO VERIFY START:",
        rid,
        "/",
        snapshot.get(
            "snapshot_id"
        ),
    )

    result = run(
        [
            sys.executable,
            str(
                VERIFICATION_SCRIPT
            ),
        ]
    )

    TEMP_RESULT_FILE.unlink(
        missing_ok=True
    )

    if result.returncode != 0:
        return {
            "race_id": rid,
            "status":
                "result_not_ready_"
                "or_retryable_error",
            "returncode":
                result.returncode,
        }

    validate_verification(
        output,
        snapshot,
    )

    return {
        "race_id": rid,
        "status": "verified",
        "path": str(output),
    }


def rebuild_database():
    result = run(
        [
            sys.executable,
            str(
                AGGREGATE_SCRIPT
            ),
        ]
    )

    if result.returncode != 0:
        raise RuntimeError(
            "verification_aggregate.py "
            "failed: "
            f"{result.returncode}"
        )

    if not AGGREGATE_FILE.exists():
        raise FileNotFoundError(
            "verification_database.json "
            "was not created"
        )

    data = load_json(
        AGGREGATE_FILE
    )

    if (
        data.get(
            "database_kind"
        )
        !=
        "race_verification_aggregate"
    ):
        raise ValueError(
            "verification database "
            "kind mismatch"
        )

    return data


def main():
    parser = argparse.ArgumentParser()

    parser.add_argument(
        "--grace-minutes",
        type=int,
        default=15,
    )

    parser.add_argument(
        "--max-age-days",
        type=int,
        default=7,
    )

    args = parser.parse_args()

    if (
        args.grace_minutes < 0
        or args.max_age_days < 1
    ):
        raise SystemExit(
            "ERROR: invalid "
            "grace/max-age setting"
        )

    required = [
        VERIFICATION_SCRIPT,
        AGGREGATE_SCRIPT,
        Path(
            "day_race_collector.py"
        ),
    ]

    missing = [
        str(path)
        for path in required
        if not path.exists()
    ]

    if missing:
        raise SystemExit(
            "ERROR: missing "
            "required files: "
            + ", ".join(missing)
        )

    current = now_jst()

    snapshots = (
        latest_eligible_snapshots()
    )

    original_exists = (
        RACE_FILE.exists()
    )

    original_text = (
        RACE_FILE.read_text(
            encoding="utf-8"
        )
        if original_exists
        else None
    )

    results = []

    counts = {
        key: 0
        for key in (
            "due",
            "verified",
            "pending",
            "already",
            "future",
            "stale",
            "unknown_start",
        )
    }

    try:
        for item in snapshots:
            snapshot = item["data"]

            race = (
                snapshot.get("race")
                or {}
            )

            rid = text(
                race.get("race_id")
            )

            start = race_start(
                race
            )

            if start is None:
                day = race_day(
                    race
                )

                if day is None:
                    counts[
                        "unknown_start"
                    ] += 1

                    results.append(
                        {
                            "race_id":
                                rid,
                            "status":
                                "race_date_unknown",
                        }
                    )

                    continue

                # 発走時刻を取得できなかった
                # 発走日前snapshotは、
                # JRA全レース終了後の
                # 18:00 JSTを安全な
                # fallbackとする。
                start = datetime(
                    day.year,
                    day.month,
                    day.day,
                    18,
                    0,
                    tzinfo=JST,
                )

            due_at = (
                start
                + timedelta(
                    minutes=
                        args.grace_minutes
                )
            )

            stale_at = (
                start
                + timedelta(
                    days=
                        args.max_age_days
                )
            )

            if current < due_at:
                counts[
                    "future"
                ] += 1

                results.append(
                    {
                        "race_id": rid,
                        "status":
                            "not_due_yet",
                    }
                )

                continue

            output = (
                verification_path(
                    snapshot
                )
            )

            if output.exists():
                validate_verification(
                    output,
                    snapshot,
                )

                counts[
                    "already"
                ] += 1

                results.append(
                    {
                        "race_id": rid,
                        "status":
                            "already_verified",
                    }
                )

                continue

            if current > stale_at:
                counts[
                    "stale"
                ] += 1

                results.append(
                    {
                        "race_id": rid,
                        "status":
                            "stale_unverified",
                    }
                )

                continue

            counts["due"] += 1

            result = verify_one(
                item
            )

            results.append(
                result
            )

            if (
                result["status"]
                == "verified"
            ):
                counts[
                    "verified"
                ] += 1
            else:
                counts[
                    "pending"
                ] += 1

    finally:
        if original_exists:
            RACE_FILE.write_text(
                original_text,
                encoding="utf-8",
            )
        else:
            RACE_FILE.unlink(
                missing_ok=True
            )

        TEMP_RESULT_FILE.unlink(
            missing_ok=True
        )

    database = (
        rebuild_database()
        if counts["verified"]
        else None
    )

    print()
    print(
        "===== AUTO RACE "
        "VERIFICATION ====="
    )

    print(
        "now_jst:",
        current.isoformat(
            timespec="seconds"
        ),
    )

    print(
        "eligible latest snapshots:",
        len(snapshots),
    )

    for key, value in (
        counts.items()
    ):
        print(
            f"{key}:",
            value,
        )

    if database:
        source = (
            database.get("source")
            or {}
        )

        print(
            "formal races:",
            source.get(
                "formal_race_count"
            ),
        )

        print(
            "diagnostic races:",
            source.get(
                "diagnostic_race_count"
            ),
        )

    print(
        "AUTO RACE VERIFICATION OK"
    )

    for result in results:
        print(
            json.dumps(
                result,
                ensure_ascii=False,
            )
        )


if __name__ == "__main__":
    main()
