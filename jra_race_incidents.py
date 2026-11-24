import argparse
import json
import re
import unicodedata
from datetime import datetime
from pathlib import Path
from urllib.parse import parse_qs, urljoin, urlsplit

import requests
from bs4 import BeautifulSoup


JRA_ORIGIN = "https://www.jra.go.jp"
RESULT_PATH = "/JRADB/accessS.html"
RESULT_KEY = re.compile(r"pw01sde(?:01|10)(\d{2})(\d{4})(\d{6})(\d{8})/[0-9A-F]{2}")
HORSE_KEY = re.compile(r"pw01dud(?:01|10)(\d{10})/[0-9A-F]{2}")
VICTIM_LIST = re.compile(r"\(被害馬:\s*(\d+番(?:\s*[・、,]\s*\d+番)*)\s*\)")


def jra_result_identity(url):
    parsed = urlsplit(url)
    if (parsed.scheme, parsed.netloc, parsed.path) != (
        "https", "www.jra.go.jp", RESULT_PATH
    ):
        raise ValueError("JRA公式のレース結果URLを指定してください")
    keys = parse_qs(parsed.query).get("CNAME", [])
    match = RESULT_KEY.fullmatch(keys[0]) if len(keys) == 1 else None
    if not match:
        raise ValueError("JRAレース結果URLの識別子を確認できません")
    course, year, meeting_day_race, compact_date = match.groups()
    race_date = datetime.strptime(compact_date, "%Y%m%d").date().isoformat()
    if not "01" <= course <= "10" or race_date[:4] != year:
        raise ValueError("JRAの開催場または年が一致しません")
    return year + course + meeting_day_race, race_date


def confirmed_victims(html, source_url, past_race):
    race_id, race_date = jra_result_identity(source_url)
    if (str(past_race["race_id"]), past_race["race_date"]) != (race_id, race_date):
        raise ValueError("前走データとJRA公式URLのレースID・日付が一致しません")

    page = BeautifulSoup(html, "html.parser", from_encoding="cp932")
    selected_race = page.select_one("ul.race-num li.current a[href]")
    result_table = page.select_one("#race_result .race_result_unit table")
    if not selected_race or not result_table:
        raise ValueError("JRA公式ページでレース結果を確認できません")
    current_url = urljoin(JRA_ORIGIN, selected_race["href"])
    if jra_result_identity(current_url) != (race_id, race_date):
        raise ValueError("取得したJRA公式ページが指定レースと一致しません")

    past_runners = {}
    for runner in past_race["results"]:
        number = int(runner["horse_number"])
        if number in past_runners:
            raise ValueError("前走データに同じ馬番が複数あります")
        past_runners[number] = (str(runner["horse_id"]), runner["horse_name"])

    matched_runners = {}
    seen_numbers = set()
    for row in result_table.select("tbody tr"):
        num_cell = row.select_one("td.num")
        horse_link = row.select_one("td.horse a[href]")
        if not num_cell or not horse_link:
            continue
        number = int(num_cell.get_text(strip=True))
        if number in seen_numbers:
            raise ValueError("JRA公式結果に同じ馬番が複数あります")
        seen_numbers.add(number)
        keys = parse_qs(urlsplit(horse_link["href"]).query).get("CNAME", [])
        key = HORSE_KEY.fullmatch(keys[0]) if len(keys) == 1 else None
        name = horse_link.get_text(strip=True)
        if key and past_runners.get(number) == (key[1], name):
            matched_runners[number] = (key[1], name)
    if not matched_runners:
        raise ValueError("JRA公式結果と前走DBで同じ馬を確認できません")

    victims = {}
    for panel in page.select(".race_info_area .panel"):
        heading = panel.select_one("h3")
        if not heading or heading.get_text(strip=True) != "競走中の出来事等":
            continue
        for item in panel.select(".dot_list li .txt"):
            official_text = item.get_text(" ", strip=True)
            normalized = unicodedata.normalize("NFKC", official_text)
            for match in VICTIM_LIST.finditer(normalized):
                for value in re.findall(r"(\d+)番", match[1]):
                    number = int(value)
                    if number not in matched_runners:
                        continue
                    victims.setdefault(number, [])
                    if official_text not in victims[number]:
                        victims[number].append(official_text)

    return [
        {
            "race_id": race_id,
            "race_date": race_date,
            "horse_number": number,
            "horse_id": matched_runners[number][0],
            "horse_name": matched_runners[number][1],
            "source_url": source_url,
            "official_notes": notes,
        }
        for number, notes in sorted(victims.items())
    ]


def fetch_confirmed_victims(source_url, past_race):
    if jra_result_identity(source_url) != (
        str(past_race["race_id"]), past_race["race_date"]
    ):
        raise ValueError("前走データとJRA公式URLのレースID・日付が一致しません")
    response = requests.get(source_url, timeout=8, allow_redirects=False)
    response.raise_for_status()
    if response.status_code != 200:
        raise ValueError("JRA公式結果ページを取得できません")
    return confirmed_victims(response.content, source_url, past_race)


def main():
    parser = argparse.ArgumentParser(description="JRA公式結果の被害馬を前走DBと照合")
    parser.add_argument("url", help="JRA公式のレース結果URL")
    parser.add_argument("--db", type=Path, default=Path("runner_race_db.json"))
    args = parser.parse_args()
    try:
        race_id, race_date = jra_result_identity(args.url)
        database = json.loads(args.db.read_text(encoding="utf-8"))
        races = [
            row for row in database["races"]
            if (str(row["race_id"]), row["race_date"]) == (race_id, race_date)
        ]
        if len(races) != 1:
            raise ValueError("前走DBで該当レースを一意に確認できません")
        result = fetch_confirmed_victims(args.url, races[0])
    except (OSError, ValueError, KeyError, TypeError) as error:
        parser.exit(1, f"照合不能: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
