"""大井の公式出馬表を取得し、nar/race.jsonへ保存する。採点は行わない。"""

import argparse
import json
import os
import re
import tempfile
import time
import unicodedata
import urllib.request
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urljoin, urlparse

from bs4 import BeautifulSoup


BASE_DIR = Path(__file__).resolve().parent
OUTPUT = BASE_DIR / "nar" / "race.json"
JST = timezone(timedelta(hours=9))
SOURCE = "https://www.keiba.go.jp/KeibaWeb/TodayRaceInfo/DebaTable"
TRACK_CODE = "20"


def clean(value):
    return re.sub(
        r"\s+",
        " ",
        unicodedata.normalize("NFKC", str(value or "")),
    ).strip()


def node_text(node):
    return clean(node.get_text(" ", strip=True)) if node else ""


def number(value):
    match = re.fullmatch(r"[+-]?\d+(?:\.\d+)?", clean(value))
    if not match:
        return None
    value = float(match.group())
    return int(value) if value.is_integer() else value


def make_url(race_date, race_number):
    return SOURCE + "?" + urlencode({
        "k_raceDate": race_date.replace("-", "/"),
        "k_raceNo": race_number,
        "k_babaCode": TRACK_CODE,
    })


def fetch_html(url):
    for attempt in range(3):
        try:
            request = urllib.request.Request(url, headers={
                "User-Agent": "Mozilla/5.0",
                "Accept-Language": "ja,en;q=0.5",
            })
            with urllib.request.urlopen(request, timeout=25) as response:
                if urlparse(response.url).hostname != "www.keiba.go.jp":
                    raise ValueError("unexpected redirect host")
                charset = response.headers.get_content_charset() or "utf-8"
                return response.read().decode(charset)
        except Exception:
            if attempt == 2:
                raise
            time.sleep(attempt + 1)


def direct_cells(row):
    return row.find_all("td", recursive=False)


def parse_race(html, race_date, race_number, url):
    soup = BeautifulSoup(html, "html.parser")
    expected_day = date.fromisoformat(race_date)
    heading = None
    identity = None

    for tag in soup.find_all("h4"):
        text = re.sub(r"\s+", "", node_text(tag))
        match = re.search(
            r"(\d{4})年(\d{1,2})月(\d{1,2})日.*?大井第(\d{1,2})競走",
            text,
        )
        if match:
            heading, identity = text, match
            break

    if not identity:
        raise ValueError("公式ページで大井の開催日・R番号を確認できません")

    actual_day = date(*map(int, identity.group(1, 2, 3)))
    if actual_day != expected_day or int(identity.group(4)) != race_number:
        raise ValueError("取得ページと指定した開催日・R番号が一致しません")

    title = soup.select_one("section.raceTitle h3")
    info = soup.select_one("section.raceTitle .dataArea li")
    race_name = node_text(title)
    course_raw = node_text(info)
    course = re.search(r"(ダート|芝)\s*(\d+)\s*m", course_raw)

    if not race_name or not course:
        raise ValueError("レース名・距離を取得できません")

    start = re.search(r"(\d{1,2}:\d{2})発走", heading)
    layout = re.search(r"\(([^)]+)\)", course_raw)
    weather = re.search(r"天候[:：]\s*(\S+)", course_raw)
    condition = re.search(r"馬場[:：]\s*(\S+)", course_raw)

    horse_rows = [
        row
        for row in soup.select("tr.tBorder")
        if row.select_one("a.horseName")
    ]
    if not horse_rows:
        raise ValueError("出走馬を取得できません")

    horses = []
    frame_value, frame_remaining = None, 0

    for row in horse_rows:
        group = [row] + list(row.find_next_siblings("tr", limit=4))

        if len(group) != 5 or any(
            r.select_one("a.horseName") for r in group[1:]
        ):
            raise ValueError("出馬表の馬情報5行構造が変わっています")

        cells = [direct_cells(r) for r in group]
        if any(
            len(cells[i]) < count
            for i, count in [(1, 4), (2, 3), (3, 2), (4, 3)]
        ):
            raise ValueError("出馬表の列構造が変わっています")

        name_link = row.select_one("a.horseName")
        name = node_text(name_link)
        horse_number = number(node_text(row.select_one("td.horseNum")))
        query = parse_qs(urlparse(name_link.get("href", "")).query)
        horse_id = query.get("k_lineageLoginCode", [""])[0]

        if (
            not name
            or not horse_id
            or not isinstance(horse_number, int)
            or horse_number < 1
        ):
            raise ValueError("馬名・馬番・NAR馬IDを取得できません")

        # 枠セルはHTMLのrowspanで明示された範囲だけ引き継ぐ。
        frame = row.select_one("td.courseNum")
        if frame:
            frame_value = number(node_text(frame))
            frame_remaining = int(frame.get("rowspan", 1))

        horse_frame = (
            frame_value
            if frame_remaining >= len(group)
            else None
        )
        frame_remaining = max(0, frame_remaining - len(group))

        weight_raw = node_text(cells[2][2])
        weight = re.fullmatch(
            r"(\d+)\s*\(\s*([+-]?\d+)\s*\)",
            weight_raw,
        )

        # 減量記号が付く斤量も、公式に記載された数値を取得する。
        carried = re.match(
            r"(?:[▲△☆★◇]\s*)?(\d+(?:\.\d+)?)",
            node_text(cells[1][3]),
        )

        note = node_text(cells[4][2])
        previous = []
        infos = row.select("div.raceInfo")
        links = cells[1][4:]
        rider_rows = cells[2][3:]
        performances = cells[3][2:]
        margins = cells[4][3:]

        if not all(
            len(items) == 5
            for items in [
                infos,
                links,
                rider_rows,
                performances,
                margins,
            ]
        ):
            raise ValueError("過去5走欄の列構造が変わっています")

        for i in range(5):
            previous_link = links[i].select_one("a.race")

            if previous_link is None:
                if any(
                    node_text(items[i])
                    for items in [
                        infos,
                        links,
                        rider_rows,
                        performances,
                        margins,
                    ]
                ):
                    raise ValueError(
                        "過去走情報はありますが参照先を取得できません"
                    )
                continue

            previous.append({
                "race_name": node_text(previous_link),
                "source_url": urljoin(
                    url,
                    previous_link.get("href", ""),
                ),
                "race_info_raw": node_text(infos[i]),
                "jockey_weight_raw": node_text(rider_rows[i]),
                "performance_raw": node_text(performances[i]),
                "margin_raw": node_text(margins[i]),
            })

        horses.append({
            "horse_number": horse_number,
            "frame_number": horse_frame,
            "horse_id": horse_id,
            "horse_id_source": "NAR_k_lineageLoginCode",
            "horse_name": name,
            "source_url": urljoin(url, name_link.get("href", "")),
            "sex_age": node_text(cells[1][0]) or None,
            "jockey": node_text(row.select_one("a.jockeyName")) or None,
            "trainer": node_text(cells[2][1]) or None,
            "carried_weight": (
                number(carried.group(1)) if carried else None
            ),
            "body_weight": int(weight.group(1)) if weight else None,
            "body_weight_change": (
                int(weight.group(2)) if weight else None
            ),
            "body_weight_raw": weight_raw or None,
            "entry_note": note or None,
            "sire": node_text(cells[2][0]) or None,
            "dam": node_text(cells[3][0]) or None,
            "dam_sire": (
                node_text(cells[4][0]).strip("() ") or None
            ),
            "previous_races": previous,
        })

    if len({h["horse_number"] for h in horses}) != len(horses):
        raise ValueError("馬番が重複しています")

    if len({h["horse_id"] for h in horses}) != len(horses):
        raise ValueError("NAR馬IDが重複しています")

    return {
        "schema_version": 1,
        "collection_only": True,
        "updated_at": datetime.now(JST).isoformat(),
        "race_id": (
            f"NAR_{race_date.replace('-', '')}"
            f"_{TRACK_CODE}_{race_number:02d}"
        ),
        "race_id_source": "internal_date_baba_code_race_number",
        "race_type": "NAR",
        "race_date": race_date,
        "track": "大井",
        "nar_baba_code": TRACK_CODE,
        "race_number": race_number,
        "race_name": race_name,
        "race_class": None,
        "is_debut": "新馬" in race_name,
        "scheduled_start_time": start.group(1) if start else None,
        "surface": course.group(1),
        "distance": int(course.group(2)),
        "course_layout_raw": layout.group(1) if layout else None,
        "course_info_raw": course_raw,
        "weather": weather.group(1) if weather else None,
        "track_condition": condition.group(1) if condition else None,
        "horse_count": len(horses),
        "source": "NAR",
        "source_url": url,
        "horses": horses,
    }


def save_json(data):
    OUTPUT.parent.mkdir(parents=True, exist_ok=True)
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
                data,
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


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--date",
        required=True,
        help="開催日 YYYY-MM-DD",
    )
    parser.add_argument(
        "--race-number",
        required=True,
        type=int,
    )
    parser.add_argument(
        "--html",
        type=Path,
        help="検証用の保存済み公式HTML",
    )
    args = parser.parse_args()

    if date.fromisoformat(args.date).isoformat() != args.date:
        parser.error("開催日はYYYY-MM-DDで指定してください")

    if not 1 <= args.race_number <= 12:
        parser.error("R番号は1〜12で指定してください")

    url = make_url(args.date, args.race_number)
    html = (
        args.html.read_text(encoding="utf-8")
        if args.html
        else fetch_html(url)
    )
    data = parse_race(html, args.date, args.race_number, url)
    save_json(data)

    print("NAR RACE COLLECTION OK")

    for key in [
        "race_id",
        "race_date",
        "track",
        "race_number",
        "race_name",
        "distance",
        "horse_count",
    ]:
        print(f"{key}: {data[key]}")

    print(f"output: {OUTPUT}")


if __name__ == "__main__":
    main()
