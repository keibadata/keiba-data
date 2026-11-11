import json
import os
import re
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile
from urllib.parse import parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup

from prediction_snapshot import (
    JST,
    RACE_FILE,
    build_headers,
    build_race_start_at,
    extract_start_time_from_text,
    load_json,
    normalize_race_id,
    parse_iso_datetime,
    parse_race_date,
)


ORIGIN = "https://race.netkeiba.com"
CARD_PATH = "/race/shutuba.html"
ODDS_PATH = "/api/api_get_jra_odds.html"
OUTPUT_ROOT = Path("race_market_snapshots")
HEADERS = {**build_headers(), "User-Agent": "Mozilla/5.0"}


def is_target_url(url, race_id, path):
    parsed = urlsplit(url)
    return (
        parsed.scheme == "https"
        and parsed.netloc == "race.netkeiba.com"
        and parsed.path == path
        and parse_qs(parsed.query).get("race_id") == [race_id]
    )


def scheduled_start(race_id, race_day):
    card_url = f"{ORIGIN}{CARD_PATH}?race_id={race_id}"
    response = requests.get(card_url, headers=HEADERS, timeout=10)
    response.raise_for_status()
    soup = BeautifulSoup(response.content, "html.parser")
    canonical = soup.select_one('link[rel="canonical"]')
    if (
        not is_target_url(response.url, race_id, CARD_PATH)
        or canonical is None
        or not is_target_url(canonical.get("href", ""), race_id, CARD_PATH)
    ):
        raise ValueError("出馬表のレースIDを照合できません")
    title = soup.select_one('meta[property="og:title"]')
    title_text = title.get("content", "") if title else ""
    date_match = re.search(r"(20[0-9]{2})年([0-9]{1,2})月([0-9]{1,2})日", title_text)
    if date_match is None or tuple(map(int, date_match.groups())) != (
        race_day.year, race_day.month, race_day.day
    ):
        raise ValueError("出馬表の開催日を照合できません")
    details = soup.select_one(".RaceData01")
    start_time = extract_start_time_from_text(
        details.get_text(" ", strip=True) if details else ""
    )
    start = build_race_start_at(race_day.isoformat(), start_time)
    if start is None:
        raise ValueError("出馬表の発走時刻が不明です")
    return start


def horse_number(value):
    number = str(value if value is not None else "").strip()
    if not re.fullmatch(r"[0-9]{1,2}", number) or not 1 <= int(number) <= 18:
        raise ValueError("馬番を照合できません")
    return int(number)


def race_horses(race):
    entries = race.get("horses")
    if not isinstance(entries, list) or not entries:
        raise ValueError("出走馬一覧が不明です")
    horses = {}
    horse_ids = set()
    for entry in entries:
        if not isinstance(entry, dict):
            raise ValueError("出走馬一覧の形式が不明です")
        number = horse_number(entry.get("horse_number"))
        horse_id = str(entry.get("horse_id") or "").strip()
        if not horse_id or horse_id in horse_ids or number in horses:
            raise ValueError("出走馬のIDまたは馬番に欠損・重複があります")
        horse_ids.add(horse_id)
        horses[number] = horse_id
    return horses


def parse_market(payload, horses, captured_at, race_start_at):
    if captured_at >= race_start_at:
        raise ValueError("取得時点で予定発走時刻に達しています")
    if not isinstance(payload, dict) or payload.get("status") != "middle":
        raise ValueError("発売中の実オッズが取得できません")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise ValueError("オッズのデータ形式が不明です")
    timestamp = data.get("official_datetime")
    if not isinstance(timestamp, str) or re.match(
        r"[0-9]{4}-[0-9]{2}-[0-9]{2}[ T][0-9]{2}:[0-9]{2}:[0-9]{2}", timestamp
    ) is None:
        raise ValueError("配信元の更新時刻を確認できません")
    published_at = parse_iso_datetime(timestamp)
    if published_at is None or published_at > captured_at:
        raise ValueError("配信元の更新時刻を確認できません")
    odds_by_type = data.get("odds")
    win_rows = odds_by_type.get("1") if isinstance(odds_by_type, dict) else None
    if not isinstance(win_rows, dict):
        raise ValueError("単勝オッズがありません")

    quotes = {}
    for raw_number, row in win_rows.items():
        number = horse_number(raw_number)
        if number not in horses or number in quotes:
            raise ValueError("単勝オッズの馬番が出馬表と一致しません")
        if not isinstance(row, list) or len(row) < 3:
            raise ValueError("単勝オッズの行形式が不明です")
        odds_text = str(row[0]).strip()
        rank_text = str(row[2]).strip()
        odds = None
        if re.fullmatch(r"[0-9]+(?:\.[0-9]+)?", odds_text):
            value = Decimal(odds_text)
            if value >= 1:
                odds = odds_text
        rank = None
        if odds is not None and re.fullmatch(r"[0-9]{1,2}", rank_text):
            value = int(rank_text)
            if 1 <= value <= len(horses):
                rank = value
        quotes[number] = (odds, rank)

    records = []
    for number, horse_id in sorted(horses.items()):
        odds, rank = quotes.get(number, (None, None))
        records.append({
            "horse_number": number,
            "horse_id": horse_id,
            "win_odds": odds,
            "win_popularity": rank,
            "status": "available" if odds is not None and rank is not None else "unknown",
        })
    if not any(row["status"] == "available" for row in records):
        raise ValueError("照合できる単勝人気がありません")
    return published_at, records


def collect(race):
    race_id = normalize_race_id(race.get("race_id"))
    race_day = parse_race_date(race.get("race_date"))
    if race_day is None:
        raise ValueError("開催日が不明です")
    if not 1 <= int(race_id[4:6]) <= 10 or race.get("surface") == "障害":
        raise ValueError("中央平地のレースを対象とします")
    if datetime.now(JST).date() > race_day:
        raise ValueError("開催日を過ぎています")

    horses = race_horses(race)
    start = scheduled_start(race_id, race_day)
    if datetime.now(JST) >= start:
        raise ValueError("予定発走時刻に達しています")

    headers = {
        **HEADERS,
        "Accept": "application/json",
        "Referer": f"{ORIGIN}{CARD_PATH}?race_id={race_id}",
    }
    response = requests.get(
        f"{ORIGIN}{ODDS_PATH}",
        params={
            "pid": "api_get_jra_odds",
            "race_id": race_id,
            "type": "1",
            "action": "init",
            "sort": "odds",
            "compress": "0",
            "output": "json",
        },
        headers=headers,
        timeout=10,
        allow_redirects=False,
    )
    captured_at = datetime.now(JST)
    if response.status_code != 200 or not is_target_url(response.url, race_id, ODDS_PATH):
        raise ValueError(f"単勝オッズの応答を照合できません（HTTP {response.status_code}）")
    published_at, records = parse_market(response.json(), horses, captured_at, start)
    return {
        "schema_version": 1,
        "race_id": race_id,
        "race_date": race_day.isoformat(),
        "scheduled_start_at": start.isoformat(),
        "captured_at": captured_at.isoformat(),
        "source_updated_at": published_at.isoformat(),
        "source": "netkeiba",
        "source_url": response.url,
        "source_status": "middle",
        "quoted_horse_count": sum(row["status"] == "available" for row in records),
        "horses": records,
    }


def save_snapshot(snapshot):
    captured_at = datetime.fromisoformat(snapshot["captured_at"])
    name = captured_at.strftime("%Y%m%dT%H%M%S%f%z") + ".json"
    folder = OUTPUT_ROOT / snapshot["race_date"] / snapshot["race_id"]
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / name
    temp_path = None
    try:
        with NamedTemporaryFile(
            mode="w", encoding="utf-8", dir=folder, suffix=".tmp", delete=False
        ) as handle:
            temp_path = Path(handle.name)
            json.dump(snapshot, handle, ensure_ascii=False, indent=2)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        if temp_path is not None:
            temp_path.unlink(missing_ok=True)
    return path


def main():
    try:
        race = load_json(RACE_FILE)
        if not isinstance(race, dict):
            raise ValueError("race.json が不正です")
        snapshot = collect(race)
    except (OSError, ValueError, requests.RequestException) as error:
        print(f"Market snapshot skipped: {error}")
        return
    path = save_snapshot(snapshot)
    print(f"Market snapshot saved: {path} ({snapshot['quoted_horse_count']}頭)")


if __name__ == "__main__":
    main()
