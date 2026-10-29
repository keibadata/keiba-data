"""対象日より前のNAR成績表を取得しnar/past_results.jsonへ保存する。採点はしない。"""

import argparse
import hashlib
import json
import os
import re
import tempfile
import time
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

from bs4 import BeautifulSoup
from nar_collect_race import clean, fetch_html, node_text, number
from nar_normalize_history import source_identity


BASE = Path(__file__).resolve().parent
OUTPUT = BASE / "nar" / "past_results.json"
JST = timezone(timedelta(hours=9))


def require(condition, message):
    if not condition:
        raise ValueError(message)


def seconds(text):
    match = re.fullmatch(r"(\d+):([0-5]\d(?:\.\d+)?)", clean(text))
    return round(int(match[1]) * 60 + float(match[2]), 3) if match else None


def identity(url):
    day, code, race_no = source_identity(url)
    race_id = f"NAR_{day:%Y%m%d}_{code}_{race_no:02d}"
    return day, code, race_no, race_id


def canonical_url(day, code, race_no):
    return "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/RaceMarkTable?" + urlencode({
        "k_raceDate": day.strftime("%Y/%m/%d"),
        "k_babaCode": code,
        "k_raceNo": race_no,
    })


def requests_from_inputs(race_bytes, history_bytes):
    race, history = json.loads(race_bytes), json.loads(history_bytes)
    require(race.get("race_type") == "NAR" and race.get("collection_only") is True, "NAR取得専用データではありません")
    require(race.get("schema_version") == 1 and race.get("source") == "NAR", "出馬表の形式が不正です")
    require(race.get("track") == "大井" and race.get("nar_baba_code") == "20", "対象は大井に限定します")
    target_day = date.fromisoformat(race["race_date"])
    race_no = race.get("race_number")
    require(type(race_no) is int and 1 <= race_no <= 12, "対象R番号が不正です")
    require(race.get("race_id") == f"NAR_{target_day:%Y%m%d}_20_{race_no:02d}", "対象Race IDが不正です")
    require(history.get("schema_version") == 1 and history.get("normalizer_version") == "nar_history_v1", "過去走の形式が不正です")
    require(history.get("collection_only") is True and history.get("race_type") == "NAR", "過去走の区分が不正です")
    require(history.get("source_file") == "nar/race.json", "過去走の参照元が不正です")
    require(history.get("source_sha256") == hashlib.sha256(race_bytes).hexdigest(), "出馬表と過去走の版が一致しません")
    require(history.get("source_updated_at") == race.get("updated_at"), "参照元の取得日時が一致しません")
    for key in ["race_id", "race_date", "track", "race_number"]:
        require(history.get(key) == race.get(key), "対象レースが一致しません: " + key)

    horses, past_horses = race.get("horses"), history.get("horses")
    require(isinstance(horses, list) and horses and race.get("horse_count") == len(horses), "出馬表の頭数が不正です")
    require(isinstance(past_horses, list) and len(past_horses) == len(horses), "過去走の頭数が一致しません")

    requests, skipped, seen_ids = {}, [], set()

    for horse, past in zip(horses, past_horses):
        for key in ["horse_id", "horse_number", "horse_name", "horse_id_source"]:
            require(horse.get(key) == past.get(key), "馬情報が一致しません: " + key)
        require(horse.get("horse_id_source") == "NAR_k_lineageLoginCode", "NAR馬IDではありません")
        require(horse.get("horse_id") and horse["horse_id"] not in seen_ids, "馬IDが不正または重複しています")
        seen_ids.add(horse["horse_id"])

        runs, raw_runs = past.get("previous_races"), horse.get("previous_races")
        require(isinstance(runs, list) and isinstance(raw_runs, list) and len(runs) == len(raw_runs) <= 5, "過去走数が一致しません")
        seen_races = set()

        for index, (run, raw) in enumerate(zip(runs, raw_runs), 1):
            require(run.get("raw") == raw and run.get("history_index") == index, "過去走原文・順番が一致しません")
            flags = run.get("quality_flags")
            require(isinstance(flags, list) and type(run.get("eligible_as_past_race")) is bool, "過去走フラグが不正です")
            require(run["eligible_as_past_race"] == (not flags), "過去走の利用可否が一致しません")

            ref = {
                "horse_id": horse["horse_id"],
                "horse_number": horse["horse_number"],
                "horse_name": horse["horse_name"],
                "history_index": index,
            }

            if not run["eligible_as_past_race"]:
                skipped.append({**ref, "quality_flags": flags})
                continue

            require(run.get("source_url") == raw.get("source_url"), "過去走URLが一致しません")
            day, code, race_no, race_id = identity(run["source_url"])
            require(day < target_day, "対象日以降の成績は取得しません")
            require(run.get("race_id") == race_id and run.get("race_date") == day.isoformat(), "過去走の開催日・IDが一致しません")
            require(run.get("nar_baba_code") == code and run.get("race_number") == race_no, "過去走の場コード・Rが一致しません")
            require(race_id not in seen_races, "同一馬の過去走が重複しています")
            seen_races.add(race_id)

            item = requests.setdefault(
                race_id,
                {
                    "day": day,
                    "code": code,
                    "race_no": race_no,
                    "refs": [],
                },
            )
            item["refs"].append({**ref, "expected": run})

    return race, history, requests, skipped


def parse_timing(soup, distance):
    splits, race_last, warnings = None, {}, []

    for table in soup.select("section.timeTable table"):
        rows = table.find_all("tr")
        if not rows:
            continue

        headings = [
            node_text(c)
            for c in rows[0].find_all(["th", "td"], recursive=False)
        ]
        values = {}

        for row in rows[1:]:
            cells = [
                node_text(c)
                for c in row.find_all(["th", "td"], recursive=False)
            ]
            if cells:
                require(len(cells) == len(headings), "タイム表の列数が変わっています")
                values[cells[0]] = cells[1:]

        if "上がりタイム" in values:
            race_last = {
                h: number(v)
                for h, v in zip(headings[1:], values["上がりタイム"])
            }

        if "ハロンタイム" in values or "通過タイム" in values:
            require(splits is None, "ラップ表が重複しています")
            marks = [
                re.fullmatch(r"(\d+)m", h)
                for h in headings[1:]
            ]
            require(marks and all(marks), "ラップの距離見出しを取得できません")
            endpoints = [int(m[1]) for m in marks]
            require(
                endpoints == sorted(set(endpoints))
                and endpoints[0] > 0
                and endpoints[-1] == distance,
                "ラップの距離が一致しません",
            )

            lap = values.get("ハロンタイム", [None] * len(endpoints))
            cumulative = values.get("通過タイム", [None] * len(endpoints))
            splits, previous = [], 0

            for end, lap_text, total_text in zip(endpoints, lap, cumulative):
                splits.append({
                    "end_distance_m": end,
                    "segment_distance_m": end - previous,
                    "lap_seconds": number(lap_text),
                    "cumulative_seconds": number(total_text),
                })
                previous = end

            if any(
                s["lap_seconds"] is None
                or s["cumulative_seconds"] is None
                for s in splits
            ):
                warnings.append("partial_official_lap_data")

    if splits is None:
        warnings.append("official_lap_table_not_available")

    corners = []
    for row in soup.select("section.cornerPassTable tr"):
        cells = row.find_all("td", recursive=False)
        if len(cells) == 2:
            corners.append({
                "corner": node_text(cells[0]),
                "order_raw": node_text(cells[1]),
            })

    return {
        "lap_splits": splits,
        "race_last_furlong_seconds": race_last,
        "all_horses_corner_order": corners,
        "availability_notes": warnings,
    }


def parse_result(html, item):
    soup = BeautifulSoup(html, "html.parser")
    day, code, race_no = item["day"], item["code"], item["race_no"]
    found = None

    for tag in soup.find_all("h4"):
        match = re.fullmatch(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?[)）](.+?)第(\d+)競走競走成績",
            re.sub(r"\s+", "", node_text(tag)),
        )
        if match:
            found = match
            break

    require(found is not None, "成績表の開催日・競馬場・Rを取得できません")
    require(
        date(*map(int, found.group(1, 2, 3))) == day
        and int(found[5]) == race_no,
        "成績表の開催日・Rが一致しません",
    )

    track = found[4]
    require(
        all(ref["expected"]["track"] == track for ref in item["refs"]),
        "成績表の競馬場が一致しません",
    )

    info = soup.select_one("section.raceTitle .dataArea li")
    course_raw = node_text(info)
    course = re.search(
        r"(ダート|芝)\s*(\d+)\s*m\s*\(([^)]+)\)",
        course_raw,
    )
    require(course is not None, "成績表のコース情報を取得できません")
    surface, distance, layout = course[1], int(course[2]), course[3]
    condition = re.search(r"馬場[:：]\s*(\S+)", course_raw)
    weather = re.search(r"天候[:：]\s*(\S+)", course_raw)
    title = node_text(soup.select_one("section.raceTitle h3"))
    require(bool(title), "成績表のレース名を取得できません")

    table = soup.select_one("section.gradeTable table")
    require(table is not None, "全頭成績表がありません")
    headers = [
        re.sub(r"\s+", "", node_text(c))
        for c in table.find_all("tr")[0].find_all("th")
    ]
    require(
        headers == [
            "着順", "枠", "馬番", "馬名", "所属", "性齢",
            "負担重量", "騎手(所属)", "調教師", "馬体重(増減)",
            "タイム", "着差", "上がり3F", "コーナー通過順",
            "人気", "単勝オッズ",
        ],
        "全頭成績表の列構造が変わっています",
    )

    runners = []

    for row in table.select("tr.tBorder"):
        cells = row.find_all("td", recursive=False)
        require(len(cells) == 16, "全頭成績表の馬情報列数が変わっています")
        texts = [node_text(c) for c in cells]
        link = cells[3].select_one("a")
        require(link is not None, "成績表のNAR馬IDがありません")
        horse_id = parse_qs(
            urlparse(link.get("href", "")).query
        ).get("k_lineageLoginCode", [""])[0]
        horse_no = number(texts[2])
        require(
            bool(horse_id)
            and bool(texts[3])
            and type(horse_no) is int
            and horse_no > 0,
            "成績表の馬情報が不正です",
        )

        finish = re.fullmatch(r"(\d+)(降)?", texts[0])
        weight = re.fullmatch(
            r"(\d+)(?:\s*\(\s*([+-]?\d+)\s*\))?",
            texts[9],
        )
        corner = re.fullmatch(r"\d+(?:-\d+)*", texts[13])

        runners.append({
            "horse_id": horse_id,
            "horse_id_source": "NAR_k_lineageLoginCode",
            "horse_number": horse_no,
            "horse_name": texts[3],
            "frame_number": number(texts[1]),
            "finish_position": int(finish[1]) if finish else None,
            "finish_status_raw": texts[0],
            "sex_age": texts[5],
            "carried_weight": number(texts[6]),
            "jockey": texts[7],
            "trainer": texts[8],
            "body_weight": int(weight[1]) if weight else None,
            "body_weight_change": (
                int(weight[2]) if weight and weight[2] else None
            ),
            "time_seconds": seconds(texts[10]),
            "official_finish_margin_text": texts[11] or None,
            "last_3f_seconds": number(texts[12]),
            "corner_positions": (
                [int(x) for x in texts[13].split("-")]
                if corner else None
            ),
            "time_difference_to_winner_seconds": None,
            "raw_fields": dict(zip(headers[:14], texts[:14])),
        })

    require(
        runners
        and len({r["horse_id"] for r in runners}) == len(runners),
        "成績表の馬IDが重複・欠落しています",
    )
    require(
        len({r["horse_number"] for r in runners}) == len(runners),
        "成績表の馬番が重複しています",
    )

    winner_times = {
        r["time_seconds"]
        for r in runners
        if r["finish_position"] == 1
    }
    require(
        len(winner_times) == 1 and None not in winner_times,
        "勝ち馬の時計を確認できません",
    )
    winner_time = next(iter(winner_times))

    for runner in runners:
        if runner["time_seconds"] is not None:
            runner["time_difference_to_winner_seconds"] = round(
                runner["time_seconds"] - winner_time,
                3,
            )

    non_starters = {"取消", "除外", "取止"}
    starter_count = sum(
        r["finish_status_raw"] not in non_starters
        for r in runners
    )

    for ref in item["refs"]:
        past = ref["expected"]
        matched = next(
            (
                r for r in runners
                if r["horse_id"] == ref["horse_id"]
            ),
            None,
        )
        require(
            matched is not None,
            "対象馬が過去レースに見つかりません: " + ref["horse_name"],
        )
        require(
            matched["horse_number"] == past["horse_number"]
            and matched["finish_position"] == past["finish_position"],
            "過去走の馬番・着順が一致しません",
        )
        require(
            starter_count == past["field_size"]
            and distance == past["distance"],
            "過去走の出走頭数・距離が一致しません",
        )
        require(
            condition and condition[1] == past["track_condition"],
            "過去走の馬場状態が一致しません",
        )
        require(
            matched["time_seconds"] == past["time_seconds"]
            and matched["last_3f_seconds"] == past["last_3f_seconds"],
            "過去走の時計・上がりが一致しません",
        )
        require(
            matched["corner_positions"] == past["corner_positions"],
            "過去走の通過順位が一致しません",
        )

    timing = parse_timing(soup, distance)

    return {
        "race_id": f"NAR_{day:%Y%m%d}_{code}_{race_no:02d}",
        "race_date": day.isoformat(),
        "nar_baba_code": code,
        "track": track,
        "race_number": race_no,
        "race_name": title,
        "surface": surface,
        "distance": distance,
        "course_layout_raw": layout,
        "track_condition": condition[1] if condition else None,
        "weather": weather[1] if weather else None,
        "race_conditions_raw": course_raw,
        "race_class": None,
        "prize_raw": [
            node_text(li)
            for li in soup.select("section.raceTitle .dataArea li")[1:]
        ],
        "source_url": canonical_url(day, code, race_no),
        "listed_horse_count": len(runners),
        "starter_count": starter_count,
        "winner_time_seconds": winner_time,
        "timing": timing,
        "runners": runners,
        "references": [
            {
                k: v for k, v in ref.items()
                if k != "expected"
            }
            for ref in item["refs"]
        ],
    }


def collect(race_bytes, history_bytes, html_dir=None):
    race, history, requests, skipped = requests_from_inputs(
        race_bytes,
        history_bytes,
    )
    results = []

    for index, (race_id, item) in enumerate(
        sorted(requests.items()),
        1,
    ):
        if html_dir is None:
            if index > 1:
                time.sleep(0.3)
            html = fetch_html(
                canonical_url(
                    item["day"],
                    item["code"],
                    item["race_no"],
                )
            )
        else:
            html = (
                html_dir / (race_id + ".html")
            ).read_text(encoding="utf-8")

        result = parse_result(html, item)
        result["source_html_sha256"] = hashlib.sha256(
            html.encode("utf-8")
        ).hexdigest()
        results.append(result)
        print(
            f"Collected {index}/{len(requests)}: {race_id}",
            flush=True,
        )

    return {
        "schema_version": 1,
        "collector_version": "nar_past_results_v1",
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_type": "NAR",
        "race_id": race["race_id"],
        "race_date": race["race_date"],
        "track": "大井",
        "race_number": race["race_number"],
        "source_race_sha256": hashlib.sha256(race_bytes).hexdigest(),
        "source_history_sha256": hashlib.sha256(history_bytes).hexdigest(),
        "source_race_updated_at": race.get("updated_at"),
        "source_history_updated_at": history.get("updated_at"),
        "summary": {
            "horse_count": len(race["horses"]),
            "requested_race_count": len(requests),
            "collected_race_count": len(results),
            "matched_past_race_count": sum(
                len(r["references"]) for r in results
            ),
            "skipped_past_race_count": len(skipped),
            "races_with_lap_table": sum(
                r["timing"]["lap_splits"] is not None
                for r in results
            ),
        },
        "skipped_references": skipped,
        "races": results,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--html-dir",
        type=Path,
        help="検証用HTMLの保存先。指定しなければ公式サイトから取得",
    )
    args = parser.parse_args()

    result = collect(
        (BASE / "nar/race.json").read_bytes(),
        (BASE / "nar/history.json").read_bytes(),
        args.html_dir,
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

    print("NAR PAST RESULTS COLLECTION OK")
    print(json.dumps(result["summary"], ensure_ascii=False))
    print("output:", OUTPUT)


if __name__ == "__main__":
    main()
