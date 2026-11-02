import hashlib
import json
import math
import re
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import requests
from bs4 import BeautifulSoup

from runner_ability_evidence import build, clock_seconds, finish, parse_date, text


OUTPUT = Path("runner_past_laps.json")
VERSION = "past_laps_v1"
BASE_URL = "https://race.sp.netkeiba.com/"
HEADERS = {
    "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15 Version/18.0 Mobile/15E148 Safari/604.1",
    "Accept-Language": "ja-JP,ja;q=0.9",
}


def load(path):
    with open(path, encoding="utf-8") as f:
        result = json.load(f)
    if not isinstance(result, dict):
        raise ValueError(f"Invalid JSON object: {path}")
    return result


def now_jst():
    return datetime.now(timezone(timedelta(hours=9))).isoformat()


def winner_seconds(race):
    values = [v for row in race.get("results", [])
              if finish(row.get("rank")) == 1
              and (v := clock_seconds(row.get("time"))) is not None]
    return min(values) if values else None


def validate_segments(rows, distance, winner):
    if (
        not isinstance(rows, list) or not rows
        or type(winner) not in (int, float)
        or not math.isfinite(winner) or winner <= 0
    ):
        raise ValueError("ラップまたは照合用の勝ち時計が不明")
    previous_distance = 0
    previous_time = 0.0
    lap_total = 0.0
    for index, row in enumerate(rows):
        if not isinstance(row, dict):
            raise ValueError("ラップ行が不正")
        end = row.get("distance_m")
        cumulative = row.get("cumulative_seconds")
        lap = row.get("lap_seconds")
        if type(end) is not int or end <= previous_distance:
            raise ValueError("ラップ距離が不正")
        length = end - previous_distance
        if (index == 0 and not 0 < length <= 200) or (index > 0 and length != 200):
            raise ValueError("ラップ区間長が不正")
        if (
            type(cumulative) not in (int, float)
            or type(lap) not in (int, float)
            or not math.isfinite(cumulative) or not math.isfinite(lap)
        ):
            raise ValueError("ラップ時計が不正")
        if not 0 < lap < 60 or not cumulative > previous_time:
            raise ValueError("ラップ時計の範囲が不正")
        if abs(cumulative - previous_time - lap) > 0.11:
            raise ValueError("累積時計と区間ラップが不一致")
        if row.get("segment_distance_m") != length:
            raise ValueError("保存された区間長が不一致")
        previous_distance, previous_time = end, cumulative
        lap_total += lap
    if previous_distance != distance:
        raise ValueError("最終ラップ距離とレース距離が不一致")
    if abs(previous_time - winner) > 0.11:
        raise ValueError("最終累積時計と勝ち時計が不一致")
    if abs(lap_total - winner) > 0.11:
        raise ValueError("区間ラップ合計と勝ち時計が不一致")


def parse_html(html, race):
    race_id = text(race.get("race_id"))
    soup = BeautifulSoup(html, "html.parser")
    identities = [tag.get("href") for tag in soup.select('link[rel="canonical"]')]
    identities += [tag.get("content") for tag in soup.select('meta[property="og:url"]')]
    if not identities or any(
        parse_qs(urlparse(value or "").query).get("race_id") != [race_id]
        for value in identities
    ):
        raise ValueError("取得ページのRace IDを確認できません")
    tables = soup.select("table.Race_HaronTime")
    if len(tables) != 1:
        raise ValueError("レースラップ表が存在しない、または複数あります")
    table = tables[0]
    rows = []
    headers = None
    previous_distance = 0
    for tr in table.select("tr"):
        ths = tr.find_all("th", recursive=False)
        tds = tr.find_all("td", recursive=False)
        if ths:
            if headers is not None:
                raise ValueError("ラップ表のヘッダーが連続しています")
            headers = []
            for th in ths:
                label = th.get_text(strip=True)
                if not label:
                    headers.append(None)
                    continue
                match = re.fullmatch(r"(\d+)m", label)
                if not match:
                    raise ValueError("ラップ距離ヘッダーを解析できません")
                headers.append(int(match[1]))
        elif tds:
            if headers is None or len(headers) != len(tds):
                raise ValueError("ラップの距離数と時計数が不一致")
            for end, td in zip(headers, tds):
                if end is None:
                    if td.get_text(strip=True):
                        raise ValueError("距離ヘッダーのない時計があります")
                    continue
                parts = td.get_text("|", strip=True).split("|")
                if len(parts) != 2:
                    raise ValueError("累積時計と区間時計を分離できません")
                cumulative = clock_seconds(parts[0]) if ":" in parts[0] else float(parts[0])
                lap = float(parts[1])
                rows.append({
                    "distance_m": end,
                    "segment_distance_m": end - previous_distance,
                    "cumulative_seconds": cumulative,
                    "lap_seconds": lap,
                })
                previous_distance = end
            headers = None
    if headers is not None:
        raise ValueError("ラップ表の末尾に時計がありません")
    distance = int(race["distance"])
    winner = winner_seconds(race)
    validate_segments(rows, distance, winner)
    box = table.find_parent("div", class_="Race_ResultBox")
    codes = [tag.get_text(strip=True) for tag in box.select("dl.RacePace dd")] if box else []
    code = codes[0] if len(codes) == 1 and codes[0] in ("S", "M", "H") else None
    return {
        "status": "ok", "segments": rows,
        "winner_time_seconds": winner, "source_pace_code": code,
        "source_pace_note": "取得元の表示。展開有利不利や個別馬の評価とは別。",
        "pace_advantage": None, "html_sha256": hashlib.sha256(html.encode("utf-8")).hexdigest(),
    }


def cached_result(cache, race):
    key = text(race.get("race_id"))
    row = cache.get(key)
    if not isinstance(row, dict) or row.get("status") != "ok" or row.get("version") != VERSION:
        return None
    if row.get("race_id") != key or row.get("race_date") != text(race.get("race_date") or race.get("date")):
        return None
    if row.get("distance") != int(race["distance"]) or row.get("source_url") != source_url(key):
        return None
    if row.get("surface") != text(race.get("surface")) or row.get("winner_time_seconds") != winner_seconds(race):
        return None
    if row.get("source_pace_code") not in (None, "S", "M", "H"):
        return None
    if not re.fullmatch(r"[0-9a-f]{64}", text(row.get("html_sha256"))):
        return None
    try:
        validate_segments(row.get("segments"), int(race["distance"]), winner_seconds(race))
    except (ValueError, TypeError, KeyError, AttributeError):
        return None
    return dict(row, cache_hit=True)


def source_url(race_id):
    return f"{BASE_URL}?pid=race_result&race_id={race_id}"


def collect_one(session, race):
    race_id = text(race["race_id"])
    result = {
        "version": VERSION, "race_id": race_id,
        "race_date": text(race.get("race_date") or race.get("date")),
        "distance": int(race["distance"]), "surface": text(race.get("surface")),
        "source_url": source_url(race_id), "fetched_at": now_jst(), "cache_hit": False,
    }
    error = ""
    for attempt in range(2):
        try:
            response = session.get(result["source_url"], headers=HEADERS, timeout=30)
            response.raise_for_status()
            response.encoding = response.apparent_encoding
            parsed = parse_html(response.text, race)
            return dict(result, **parsed)
        except (requests.RequestException, ValueError, TypeError, KeyError) as exc:
            error = f"{type(exc).__name__}: {exc}"
            if attempt == 0:
                time.sleep(1)
    return dict(result, status="unknown", segments=None, source_pace_code=None,
                pace_advantage=None, error=error)


def main():
    race = load("race.json")
    history = load("runner_history.json")
    database = load("runner_race_db.json")
    checked = build(race, history, database)
    target_date = parse_date(race["race_date"])
    requested = {text(row.get("race_id")) for horse in checked["horses"]
                 for row in horse["past_races"] if text(row.get("race_id"))}
    expected_dates = {}
    for horse in checked["horses"]:
        for row in horse["past_races"]:
            key = text(row.get("race_id"))
            if not key:
                continue
            when = parse_date(row["date"])
            if key in expected_dates and expected_dates[key] != when:
                raise ValueError("同一Race IDに異なる過去走日付があります")
            expected_dates[key] = when
    candidates = []
    for row in database.get("races", []):
        key = text(row.get("race_id"))
        if key not in requested:
            continue
        if not re.fullmatch(r"\d{12}", key) or key[4:6] not in {f"{i:02d}" for i in range(1, 11)}:
            continue
        when = parse_date(row.get("race_date") or row.get("date"))
        if when is None or when >= target_date:
            raise ValueError("Unknown date, same-day or future race in runner_race_db")
        if when != expected_dates[key]:
            raise ValueError("過去走一覧と結果DBの日付が不一致")
        if row.get("surface") not in ("芝", "ダート"):
            continue
        candidates.append(row)
    cache = {}
    if OUTPUT.exists():
        try:
            saved = load(OUTPUT)
            if saved.get("version") == VERSION:
                cache = {r["race_id"]: r for r in saved.get("races", [])}
        except (OSError, ValueError, TypeError, KeyError):
            cache = {}
    collected = []
    with requests.Session() as session:
        for index, row in enumerate(sorted(candidates, key=lambda r: text(r["race_id"])), 1):
            result = cached_result(cache, row)
            if result is None:
                time.sleep(1)
                result = collect_one(session, row)
            collected.append(result)
            print(index, "/", len(candidates), row["race_id"], result["status"], flush=True)
    output = {
        "version": VERSION, "updated_at": now_jst(),
        "target_race_id": race["race_id"], "target_date": race["race_date"],
        "future_race_usage": False, "leak_check_passed": True, "scoring_applied": False,
        "summary": {
            "requested_race_count": len(requested), "candidate_race_count": len(candidates),
            "ok_count": sum(r["status"] == "ok" for r in collected),
            "unknown_count": sum(r["status"] != "ok" for r in collected),
            "cache_hit_count": sum(r["cache_hit"] for r in collected),
            "unlinked_race_count": len(requested - {r["race_id"] for r in collected}),
        },
        "notes": ["レース全体のラップ。各馬の個別ラップではない。",
                  "取得元のS/M/H表示は参考値。展開有利不利は未判定。",
                  "取得・検証できないレースは不明。0点で補完しない。"],
        "races": collected,
    }
    temporary = OUTPUT.with_suffix(".json.tmp")
    temporary.write_text(json.dumps(output, ensure_ascii=False, indent=2, allow_nan=False), encoding="utf-8")
    temporary.replace(OUTPUT)
    print(output["summary"])


if __name__ == "__main__":
    main()
