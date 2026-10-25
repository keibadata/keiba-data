import html
import json
import os
import re
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import requests


RACE_FILE = "race.json"
FINAL_ANALYSIS_FILE = "final_analysis.json"
OUTPUT_ROOT = Path("prediction_snapshots")

JST = timezone(timedelta(hours=9))
TIMEOUT = 20

SCHEMA_VERSION = 2


def load_json(path):
    if not os.path.exists(path):
        raise FileNotFoundError(
            f"required file is missing: {path}"
        )

    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        return json.load(f)


def save_json(path, data):
    path = Path(path)

    path.parent.mkdir(
        parents=True,
        exist_ok=True
    )

    with open(
        path,
        "w",
        encoding="utf-8"
    ) as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2
        )

        f.write("\n")


def normalize_text(value):
    value = str(
        value or ""
    )

    translation = str.maketrans(
        "０１２３４５６７８９：．－＋",
        "0123456789:.-+",
    )

    value = value.translate(
        translation
    )

    value = value.replace(
        "\u3000",
        " "
    )

    return re.sub(
        r"\s+",
        " ",
        value
    ).strip()


def normalize_race_id(value):
    race_id = normalize_text(
        value
    )

    if not re.fullmatch(
        r"\d{12}",
        race_id
    ):
        raise ValueError(
            f"invalid race_id: {race_id!r}"
        )

    return race_id


def parse_iso_datetime(value):
    text = normalize_text(
        value
    )

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace(
                "Z",
                "+00:00"
            )
        )

    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=JST
        )

    return parsed.astimezone(
        JST
    )


def parse_race_date(value):
    text = normalize_text(
        value
    )

    if not text:
        return None

    try:
        return date.fromisoformat(
            text
        )

    except ValueError:
        return None


def normalize_start_time(value):
    text = normalize_text(
        value
    )

    match = re.fullmatch(
        r"(\d{1,2}):(\d{2})",
        text
    )

    if not match:
        return ""

    hour = int(
        match.group(1)
    )

    minute = int(
        match.group(2)
    )

    if not (
        0 <= hour <= 23
        and 0 <= minute <= 59
    ):
        return ""

    return (
        f"{hour:02d}:"
        f"{minute:02d}"
    )


def build_race_start_at(
    race_date_value,
    race_start_time
):
    race_day = parse_race_date(
        race_date_value
    )

    start_time = normalize_start_time(
        race_start_time
    )

    if (
        race_day is None
        or not start_time
    ):
        return None

    hour, minute = [
        int(value)
        for value
        in start_time.split(":")
    ]

    return datetime(
        year=race_day.year,
        month=race_day.month,
        day=race_day.day,
        hour=hour,
        minute=minute,
        second=0,
        microsecond=0,
        tzinfo=JST,
    )


def safe_timestamp(
    value,
    fallback
):
    parsed = parse_iso_datetime(
        value
    )

    if parsed is None:
        parsed = fallback

    return parsed.strftime(
        "%Y%m%dT%H%M%S%f%z"
    )


def build_headers():
    return {
        "User-Agent": (
            "Mozilla/5.0 "
            "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
            "AppleWebKit/605.1.15 "
            "(KHTML, like Gecko) "
            "Version/18.0 "
            "Mobile/15E148 Safari/604.1"
        ),
        "Accept": (
            "text/html,"
            "application/xhtml+xml,"
            "application/xml;q=0.9,"
            "*/*;q=0.8"
        ),
        "Accept-Language": (
            "ja,en-US;q=0.8,en;q=0.6"
        ),
        "Cache-Control": "no-cache",
        "Pragma": "no-cache",
    }


def fetch_html(url):
    response = requests.get(
        url,
        headers=build_headers(),
        timeout=TIMEOUT,
        allow_redirects=True,
    )

    response.raise_for_status()

    if (
        not response.encoding
        or response.encoding.lower()
        in [
            "iso-8859-1",
            "ascii",
        ]
    ):
        response.encoding = (
            response.apparent_encoding
        )

    return (
        response.text,
        response.url,
    )


def html_to_text(raw_html):
    text = re.sub(
        r"(?is)<script.*?>.*?</script>",
        " ",
        raw_html,
    )

    text = re.sub(
        r"(?is)<style.*?>.*?</style>",
        " ",
        text,
    )

    text = re.sub(
        r"(?is)<[^>]+>",
        " ",
        text,
    )

    text = html.unescape(
        text
    )

    return normalize_text(
        text
    )


def extract_start_time_from_text(text):
    text = normalize_text(
        text
    )

    if not text:
        return ""

    patterns = [
        (
            r"発走(?:時刻)?"
            r"\s*[:：]?\s*"
            r"(\d{1,2})"
            r"\s*[:時]\s*"
            r"(\d{2})"
        ),
        (
            r"(\d{1,2})"
            r"\s*[:時]\s*"
            r"(\d{2})"
            r"\s*分?"
            r"\s*発走"
        ),
        (
            r"(\d{1,2})"
            r":"
            r"(\d{2})"
            r"\s+"
            r"(?:芝|ダ(?:ート)?)"
            r"\s*"
            r"\d{3,4}"
            r"\s*m"
        ),
    ]

    for pattern in patterns:
        match = re.search(
            pattern,
            text,
            re.IGNORECASE,
        )

        if not match:
            continue

        try:
            hour = int(
                match.group(1)
            )

            minute = int(
                match.group(2)
            )

        except Exception:
            continue

        if (
            7 <= hour <= 20
            and 0 <= minute <= 59
        ):
            return (
                f"{hour:02d}:"
                f"{minute:02d}"
            )

    return ""


def build_source_urls(
    race_id,
    race
):
    urls = []

    source_url = normalize_text(
        race.get(
            "source_url"
        )
    )

    if source_url:
        urls.append(
            source_url
        )

    shutuba_url = (
        "https://race.netkeiba.com/"
        "race/shutuba.html"
        f"?race_id={race_id}"
    )

    result_url = (
        "https://race.netkeiba.com/"
        "race/result.html"
        f"?race_id={race_id}"
    )

    for url in [
        shutuba_url,
        result_url,
    ]:
        if url not in urls:
            urls.append(
                url
            )

    return urls


def fetch_race_start_time(
    race_id,
    race
):
    errors = []

    for url in build_source_urls(
        race_id,
        race
    ):
        try:
            raw_html, final_url = (
                fetch_html(
                    url
                )
            )

            visible_text = html_to_text(
                raw_html
            )

            start_time = (
                extract_start_time_from_text(
                    visible_text
                )
            )

            if start_time:
                return {
                    "start_time": start_time,
                    "source": "netkeiba",
                    "requested_url": url,
                    "final_url": final_url,
                    "error": "",
                }

            errors.append(
                (
                    f"start time not found: "
                    f"{final_url}"
                )
            )

        except Exception as exc:
            errors.append(
                (
                    f"{url}: "
                    f"{type(exc).__name__}: "
                    f"{exc}"
                )
            )

    return {
        "start_time": "",
        "source": "",
        "requested_url": "",
        "final_url": "",
        "error": " | ".join(
            errors
        ),
    }


def build_timing(
    race_date_value,
    race_start_time,
    saved_at
):
    race_day = parse_race_date(
        race_date_value
    )

    if race_day is None:
        return {
            "status": (
                "race_date_unknown"
            ),
            "evaluation_eligible": None,
            "reason": (
                "race_dateを確認できないため"
                "発走前予想か判定できない"
            ),
            "race_start_at": "",
        }

    saved_at = saved_at.astimezone(
        JST
    )

    saved_day = saved_at.date()

    if saved_day < race_day:
        race_start_at = (
            build_race_start_at(
                race_date_value,
                race_start_time,
            )
        )

        return {
            "status": (
                "before_race_date"
            ),
            "evaluation_eligible": True,
            "reason": (
                "レース日前に保存された予想"
            ),
            "race_start_at": (
                race_start_at.isoformat()
                if race_start_at
                else ""
            ),
        }

    if saved_day > race_day:
        race_start_at = (
            build_race_start_at(
                race_date_value,
                race_start_time,
            )
        )

        return {
            "status": (
                "after_race_date"
            ),
            "evaluation_eligible": False,
            "reason": (
                "レース日後に保存されたため"
                "事前予想検証には使用しない"
            ),
            "race_start_at": (
                race_start_at.isoformat()
                if race_start_at
                else ""
            ),
        }

    race_start_at = (
        build_race_start_at(
            race_date_value,
            race_start_time,
        )
    )

    if race_start_at is None:
        return {
            "status": (
                "same_day_start_time_unknown"
            ),
            "evaluation_eligible": None,
            "reason": (
                "同日保存だが発走時刻を"
                "取得できないため"
                "事前予想判定を保留"
            ),
            "race_start_at": "",
        }

    if saved_at < race_start_at:
        return {
            "status": (
                "same_day_before_start"
            ),
            "evaluation_eligible": True,
            "reason": (
                "同日かつ予定発走時刻より"
                "前に保存された予想"
            ),
            "race_start_at": (
                race_start_at.isoformat()
            ),
        }

    return {
        "status": (
            "same_day_at_or_after_start"
        ),
        "evaluation_eligible": False,
        "reason": (
            "同日だが予定発走時刻以降に"
            "保存されたため"
            "事前予想検証には使用しない"
        ),
        "race_start_at": (
            race_start_at.isoformat()
        ),
    }


def validate_inputs(
    race,
    final_analysis
):
    race_id = normalize_race_id(
        race.get(
            "race_id"
        )
    )

    final_race_id = normalize_race_id(
        final_analysis.get(
            "race_id"
        )
    )

    if race_id != final_race_id:
        raise ValueError(
            "race_id mismatch: "
            f"race.json={race_id} "
            f"final_analysis.json="
            f"{final_race_id}"
        )

    ranking = final_analysis.get(
        "ranking"
    )

    if (
        not isinstance(
            ranking,
            list
        )
        or not ranking
    ):
        raise ValueError(
            "final_analysis.json "
            "has no ranking"
        )

    summary = final_analysis.get(
        "summary"
    )

    if not isinstance(
        summary,
        dict
    ):
        raise ValueError(
            "final_analysis.json "
            "summary is missing"
        )

    runner_count = int(
        summary.get(
            "runner_count",
            0
        )
        or 0
    )

    if runner_count <= 0:
        raise ValueError(
            "final_analysis "
            "runner_count is invalid"
        )

    if len(ranking) != runner_count:
        raise ValueError(
            "ranking count mismatch: "
            f"ranking={len(ranking)} "
            f"runner_count={runner_count}"
        )

    race_horse_count = int(
        race.get(
            "horse_count",
            0
        )
        or 0
    )

    if (
        race_horse_count > 0
        and race_horse_count
        != runner_count
    ):
        raise ValueError(
            "race horse_count mismatch: "
            f"race.json="
            f"{race_horse_count} "
            f"final_analysis="
            f"{runner_count}"
        )

    return race_id


def build_snapshot(
    race,
    final_analysis,
    saved_at
):
    race_id = validate_inputs(
        race,
        final_analysis
    )

    source_updated_at = normalize_text(
        final_analysis.get(
            "updated_at"
        )
    )

    start_time_info = (
        fetch_race_start_time(
            race_id,
            race,
        )
    )

    race_start_time = (
        start_time_info.get(
            "start_time",
            ""
        )
    )

    timing = build_timing(
        race.get(
            "race_date"
        ),
        race_start_time,
        saved_at,
    )

    snapshot_id = (
        race_id
        + "_"
        + safe_timestamp(
            source_updated_at,
            saved_at
        )
        + "_v2"
    )

    race_context = {
        "race_id": race_id,

        "race_date": normalize_text(
            race.get(
                "race_date"
            )
        ),

        "track": normalize_text(
            race.get(
                "track"
            )
            or race.get(
                "racecourse"
            )
        ),

        "race_name": normalize_text(
            race.get(
                "race_name"
            )
        ),

        "race_class": normalize_text(
            race.get(
                "race_class"
            )
        ),

        "age_condition": normalize_text(
            race.get(
                "age_condition"
            )
        ),

        "is_debut": bool(
            race.get(
                "is_debut",
                False
            )
        ),

        "surface": normalize_text(
            race.get(
                "surface"
            )
        ),

        "distance": race.get(
            "distance",
            0
        ),

        "track_condition": normalize_text(
            race.get(
                "track_condition"
            )
        ),

        "horse_count": int(
            race.get(
                "horse_count",
                0
            )
            or 0
        ),

        "scheduled_start_time": (
            race_start_time
        ),
    }

    return {
        "schema_version": (
            SCHEMA_VERSION
        ),

        "snapshot_id": snapshot_id,

        "prediction_saved_at": (
            saved_at.isoformat()
        ),

        "source_final_analysis_updated_at": (
            source_updated_at
        ),

        "source_race_updated_at": (
            normalize_text(
                race.get(
                    "updated_at"
                )
            )
        ),

        "snapshot_kind": "prediction",

        "provenance": {
            "github_run_id": (
                normalize_text(
                    os.environ.get(
                        "GITHUB_RUN_ID"
                    )
                )
            ),

            "github_run_number": (
                normalize_text(
                    os.environ.get(
                        "GITHUB_RUN_NUMBER"
                    )
                )
            ),

            "github_workflow": (
                normalize_text(
                    os.environ.get(
                        "GITHUB_WORKFLOW"
                    )
                )
            ),

            "github_sha": (
                normalize_text(
                    os.environ.get(
                        "GITHUB_SHA"
                    )
                )
            ),
        },

        "start_time_source": {
            "source": (
                start_time_info.get(
                    "source",
                    ""
                )
            ),
            "requested_url": (
                start_time_info.get(
                    "requested_url",
                    ""
                )
            ),
            "final_url": (
                start_time_info.get(
                    "final_url",
                    ""
                )
            ),
            "error": (
                start_time_info.get(
                    "error",
                    ""
                )
            ),
        },

        "timing": timing,

        "race": race_context,

        "analysis_mode": (
            normalize_text(
                final_analysis.get(
                    "analysis_mode"
                )
                or "normal"
            )
        ),

        "analysis": final_analysis,
    }


def snapshot_path(snapshot):
    race = snapshot[
        "race"
    ]

    race_id = race[
        "race_id"
    ]

    race_date = (
        race.get(
            "race_date"
        )
        or "date_unknown"
    )

    snapshot_id = snapshot[
        "snapshot_id"
    ]

    return (
        OUTPUT_ROOT
        / race_date
        / race_id
        / f"{snapshot_id}.json"
    )


def validate_existing_snapshot(
    path,
    snapshot
):
    with open(
        path,
        "r",
        encoding="utf-8"
    ) as f:
        existing = json.load(
            f
        )

    if (
        existing.get(
            "snapshot_id"
        )
        != snapshot.get(
            "snapshot_id"
        )
    ):
        raise ValueError(
            "existing snapshot id mismatch: "
            f"{path}"
        )

    if (
        existing.get(
            "race",
            {}
        ).get(
            "race_id"
        )
        != snapshot.get(
            "race",
            {}
        ).get(
            "race_id"
        )
    ):
        raise ValueError(
            "existing snapshot "
            "race_id mismatch: "
            f"{path}"
        )

    if (
        existing.get(
            "analysis"
        )
        != snapshot.get(
            "analysis"
        )
    ):
        raise ValueError(
            "snapshot path already exists "
            "but analysis content differs: "
            f"{path}"
        )


def run_timing_self_test(
    race_date_value,
    race_start_time
):
    race_start_at = (
        build_race_start_at(
            race_date_value,
            race_start_time,
        )
    )

    if race_start_at is None:
        raise ValueError(
            "TIMING SELF TEST FAILED: "
            "race start datetime unavailable"
        )

    before_time = (
        race_start_at
        - timedelta(
            minutes=1
        )
    )

    after_time = (
        race_start_at
        + timedelta(
            minutes=1
        )
    )

    before_result = build_timing(
        race_date_value,
        race_start_time,
        before_time,
    )

    after_result = build_timing(
        race_date_value,
        race_start_time,
        after_time,
    )

    if (
        before_result.get(
            "status"
        )
        != "same_day_before_start"
        or before_result.get(
            "evaluation_eligible"
        )
        is not True
    ):
        raise ValueError(
            "TIMING SELF TEST FAILED: "
            "before-start判定が不正"
        )

    if (
        after_result.get(
            "status"
        )
        != "same_day_at_or_after_start"
        or after_result.get(
            "evaluation_eligible"
        )
        is not False
    ):
        raise ValueError(
            "TIMING SELF TEST FAILED: "
            "after-start判定が不正"
        )

    print(
        "TIMING SELF TEST OK"
    )

    print(
        "before:",
        before_result[
            "status"
        ],
        before_result[
            "evaluation_eligible"
        ],
    )

    print(
        "after:",
        after_result[
            "status"
        ],
        after_result[
            "evaluation_eligible"
        ],
    )


def main():
    race = load_json(
        RACE_FILE
    )

    final_analysis = load_json(
        FINAL_ANALYSIS_FILE
    )

    saved_at = datetime.now(
        JST
    )

    snapshot = build_snapshot(
        race=race,
        final_analysis=final_analysis,
        saved_at=saved_at,
    )

    race_start_time = (
        snapshot.get(
            "race",
            {}
        ).get(
            "scheduled_start_time",
            ""
        )
    )

    if race_start_time:
        run_timing_self_test(
            snapshot[
                "race"
            ][
                "race_date"
            ],
            race_start_time,
        )

    output_path = snapshot_path(
        snapshot
    )

    if output_path.exists():
        validate_existing_snapshot(
            output_path,
            snapshot
        )

        print(
            "PREDICTION SNAPSHOT "
            "ALREADY EXISTS"
        )

    else:
        save_json(
            output_path,
            snapshot
        )

        print(
            "PREDICTION SNAPSHOT SAVED"
        )

    print(
        "snapshot_id:",
        snapshot[
            "snapshot_id"
        ]
    )

    print(
        "race_id:",
        snapshot[
            "race"
        ][
            "race_id"
        ]
    )

    print(
        "race_date:",
        snapshot[
            "race"
        ][
            "race_date"
        ]
    )

    print(
        "track:",
        snapshot[
            "race"
        ][
            "track"
        ]
    )

    print(
        "scheduled_start_time:",
        snapshot[
            "race"
        ][
            "scheduled_start_time"
        ]
    )

    print(
        "analysis_mode:",
        snapshot[
            "analysis_mode"
        ]
    )

    print(
        "runner_count:",
        snapshot[
            "race"
        ][
            "horse_count"
        ]
    )

    print(
        "timing_status:",
        snapshot[
            "timing"
        ][
            "status"
        ]
    )

    print(
        "evaluation_eligible:",
        snapshot[
            "timing"
        ][
            "evaluation_eligible"
        ]
    )

    print(
        "race_start_at:",
        snapshot[
            "timing"
        ][
            "race_start_at"
        ]
    )

    print(
        "output:",
        output_path.as_posix()
    )


if __name__ == "__main__":
    main()
