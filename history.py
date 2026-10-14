import sys
import json
import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup


BASE_URL = "https://race.netkeiba.com/race/result.html"
HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 (KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja-JP,ja;q=0.9,en-US;q=0.8,en;q=0.7",
}


def clean_text(element):
    if element is None:
        return ""
    return element.get_text(" ", strip=True)


def first_text(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)
        if element:
            text = clean_text(element)
            if text:
                return text
    return ""


def first_href(row, selectors):
    for selector in selectors:
        element = row.select_one(selector)
        if element and element.get("href"):
            return element.get("href")
    return ""


def extract_id(url, pattern):
    if not url:
        return ""
    match = re.search(pattern, url)
    return match.group(1) if match else ""


def get_html(race_id):
    response = requests.get(
        BASE_URL,
        params={"race_id": race_id},
        headers=HEADERS,
        timeout=30,
    )
    response.raise_for_status()

    if not response.encoding or response.encoding.lower() == "iso-8859-1":
        response.encoding = response.apparent_encoding

    html = response.text

    with open("history_debug.html", "w", encoding="utf-8") as f:
        f.write(html)

    print("HTTP:", response.status_code)
    print("URL:", response.url)
    print("HTML bytes:", len(response.content))

    return html


def find_result_rows(soup):
    selectors = [
        "table.RaceTable01 tbody tr",
        ".RaceTable01 tbody tr",
        "table.Shutuba_Table tbody tr",
        "tr.HorseList",
    ]

    for selector in selectors:
        rows = soup.select(selector)
        if rows:
            print("結果行selector:", selector)
            print("結果行数:", len(rows))
            return rows

    return []


def parse_row(row):
    rank = first_text(
        row,
        [
            ".Rank",
            ".Rank_Ninki",
            "td.Result_Num",
            "td[class*='Rank']",
        ],
    )

    horse_name = first_text(
        row,
        [
            ".Horse_Name a",
            ".HorseName a",
            "td.Horse_Info a",
            "td[class*='Horse'] a",
        ],
    )

    horse_url = first_href(
        row,
        [
            ".Horse_Name a",
            ".HorseName a",
            "td.Horse_Info a",
            "td[class*='Horse'] a",
        ],
    )

    horse_id = extract_id(
        horse_url,
        r"/horse/(?:result/)?(\d+)",
    )

    horse_number = first_text(
        row,
        [
            ".Num",
            ".Umaban",
            "td.Num",
            "td[class*='Num']",
        ],
    )

    sex_age = first_text(
        row,
        [
            ".Barei",
            "td.Barei",
            "td[class*='Barei']",
        ],
    )

    weight = first_text(
        row,
        [
            ".Weight",
            "td.Weight",
            "td[class*='Weight']",
        ],
    )

    jockey = first_text(
        row,
        [
            ".Jockey a",
            "td.Jockey a",
            "td[class*='Jockey'] a",
        ],
    )

    time_text = first_text(
        row,
        [
            ".Time",
            "td.Time",
            "td[class*='Time']",
        ],
    )

    margin = first_text(
        row,
        [
            ".着差",
            ".Margin",
            "td.Margin",
            "td[class*='Margin']",
        ],
    )

    passing = first_text(
        row,
        [
            ".Passing",
            "td.Passing",
            "td[class*='Passing']",
            ".Corner",
        ],
    )

    last3f = first_text(
        row,
        [
            ".Last3F",
            "td.Last3F",
            "td[class*='Last3F']",
        ],
    )

    odds = first_text(
        row,
        [
            ".Odds",
            "td.Odds",
            "td[class*='Odds']",
        ],
    )

    popularity = first_text(
        row,
        [
            ".Popular",
            ".Ninki",
            "td.Popular",
            "td[class*='Popular']",
        ],
    )

    if not horse_name:
        links = row.select("a")
        for link in links:
            href = link.get("href", "")
            if "/horse/" in href:
                horse_name = clean_text(link)
                horse_url = href
                horse_id = extract_id(href, r"/horse/(?:result/)?(\d+)")
                break

    if not horse_name:
        return None

    return {
        "rank": rank,
        "horse_number": horse_number,
        "horse_id": horse_id,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "weight": weight,
        "jockey": jockey,
        "time": time_text,
        "margin": margin,
        "passing": passing,
        "last3f": last3f,
        "odds": odds,
        "popularity": popularity,
    }


def get_race_result(race_id):
    html = get_html(race_id)
    soup = BeautifulSoup(html, "html.parser")

    rows = find_result_rows(soup)

    results = []

    for row in rows:
        item = parse_row(row)
        if item:
            results.append(item)

    # 通常selectorで取れない場合は馬リンクを基準に最低限復旧
    if not results:
        seen = set()

        for link in soup.select('a[href*="/horse/"]'):
            horse_name = clean_text(link)
            href = link.get("href", "")

            if not horse_name:
                continue

            horse_id = extract_id(
                href,
                r"/horse/(?:result/)?(\d+)",
            )

            key = horse_id or horse_name

            if key in seen:
                continue

            seen.add(key)

            results.append(
                {
                    "rank": "",
                    "horse_number": "",
                    "horse_id": horse_id,
                    "horse_name": horse_name,
                    "sex_age": "",
                    "weight": "",
                    "jockey": "",
                    "time": "",
                    "margin": "",
                    "passing": "",
                    "last3f": "",
                    "odds": "",
                    "popularity": "",
                }
            )

    return results


def main():
    if len(sys.argv) < 2:
        raise SystemExit(
            '使い方: python history.py "202605040502"'
        )

    race_id = sys.argv[1].strip()

    if not re.fullmatch(r"\d{12}", race_id):
        raise SystemExit(
            f"race_id は12桁で指定してください: {race_id}"
        )

    print("取得開始:", race_id)

    results = get_race_result(race_id)

    data = {
        "race_id": race_id,
        "updated_at": datetime.now(timezone.utc).isoformat(),
        "source": "netkeiba",
        "result_count": len(results),
        "results": results,
    }

    with open("history.json", "w", encoding="utf-8") as f:
        json.dump(
            data,
            f,
            ensure_ascii=False,
            indent=2,
        )

    print("取得件数:", len(results))
    print(
        json.dumps(
            data,
            ensure_ascii=False,
            indent=2,
        )
    )

    if not results:
        raise RuntimeError(
            "結果を1頭も取得できませんでした。"
            " history_debug.html を確認してください。"
        )


if __name__ == "__main__":
    main()
