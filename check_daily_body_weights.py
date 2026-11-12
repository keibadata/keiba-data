import argparse
import hashlib
import json
import re
import unicodedata
from urllib.parse import parse_qs, urlsplit

import requests
from bs4 import BeautifulSoup

from resolve_race_id import HEADERS


def parse_body_weights(html, race_id):
    soup = BeautifulSoup(html, "html.parser")
    canonical = soup.select_one('link[rel="canonical"][href]')
    og_url = soup.select_one('meta[property="og:url"][content]')
    page_urls = []
    if canonical:
        page_urls.append(canonical["href"])
    if og_url:
        page_urls.append(og_url["content"])
    if not page_urls or any(
        parse_qs(urlsplit(url).query).get("race_id") != [race_id]
        for url in page_urls
    ):
        raise ValueError(f"{race_id}: 出馬表のレースIDを照合できません。")

    rows = soup.select("table.ShutubaTable tr.HorseList")
    if not rows:
        raise ValueError(f"{race_id}: 出馬表の出走馬一覧を取得できません。")

    horses = {}
    excluded = 0
    for row in rows:
        cancel = row.select_one("td.Cancel_Txt")
        cancel_text = cancel.get_text(strip=True) if cancel else ""
        if cancel_text in {"取消", "出走取消", "除外", "競走除外", "発走除外"}:
            excluded += 1
            continue
        if cancel_text or "Cancel" in row.get("class", []):
            raise ValueError(f"{race_id}: 出走状態を確認できない馬がいます。")

        horse_link = row.select_one('.HorseName a[href*="/horse/"]')
        horse_match = (
            re.fullmatch(r"/horse/([0-9]{10})/?", urlsplit(horse_link["href"]).path)
            if horse_link else None
        )
        if not horse_match or horse_match[1] in horses:
            raise ValueError(f"{race_id}: 出走馬IDを照合できません。")

        weight_cell = row.select_one("td.Weight")
        weight_text = weight_cell.get_text(" ", strip=True) if weight_cell else ""
        weight_text = unicodedata.normalize("NFKC", weight_text).replace("−", "-")
        weight_match = re.fullmatch(
            r"([1-9][0-9]{2})(?:\s*kg)?(?:\s*\(([+-]?[0-9]+)\))?",
            weight_text,
            flags=re.IGNORECASE,
        )
        horses[horse_match[1]] = {
            "body_weight": int(weight_match[1]) if weight_match else None,
            "body_weight_change": (
                int(weight_match[2]) if weight_match and weight_match[2] else None
            ),
        }

    published = sum(horse["body_weight"] is not None for horse in horses.values())
    status = "pending"
    signature = None
    if not horses:
        status = "no_active_runners"
    elif published == len(horses):
        status = "ready"
        payload = json.dumps(horses, sort_keys=True, separators=(",", ":"))
        signature = hashlib.sha256(payload.encode("utf-8")).hexdigest()

    return {
        "race_id": race_id,
        "status": status,
        "runner_count": len(horses),
        "published_count": published,
        "excluded_count": excluded,
        "weight_signature": signature,
        "horses": horses,
    }


def fetch_body_weights(race_id):
    if not re.fullmatch(r"[0-9]{12}", race_id):
        raise ValueError("レースIDは半角数字12桁で指定してください。")

    response = requests.get(
        "https://race.netkeiba.com/race/shutuba.html",
        params={"race_id": race_id},
        headers=HEADERS,
        timeout=20,
    )
    response.raise_for_status()
    return parse_body_weights(response.content, race_id)


def main():
    parser = argparse.ArgumentParser(description="JRA出馬表の馬体重発表状況を確認")
    parser.add_argument("--race-id", required=True)
    args = parser.parse_args()
    try:
        result = fetch_body_weights(args.race_id)
    except (requests.RequestException, ValueError) as exc:
        parser.exit(1, f"{exc}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
