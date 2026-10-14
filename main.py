import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

with open("race_id.txt", "r", encoding="utf-8") as f:
    RACE_ID = f.read().strip()

if not RACE_ID:
    raise ValueError("race_id.txt が空です")

print(f"Target race ID: {RACE_ID}")
URL = f"https://race.netkeiba.com/race/shutuba.html?race_id={RACE_ID}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers, timeout=20)
response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(response.text, "html.parser")

horses = []

for index, row in enumerate(soup.select(".HorseList"), start=1):

    horse = row.select_one(".HorseName a")
    if not horse:
        continue

    # 馬番
    number = row.select_one(".Umaban")
    horse_number = (
        number.get_text(strip=True)
        if number
        else str(index)
    )

    # 馬名
    horse_name = horse.get_text(strip=True)
    # 馬ID
    horse_href = horse.get("href", "")
    horse_id_match = re.search(r"/horse/(\d+)/?", horse_href)
    horse_id = horse_id_match.group(1) if horse_id_match else ""
    # 性齢
    sex_age_el = row.select_one(".Barei")
    sex_age = (
        sex_age_el.get_text(strip=True)
        if sex_age_el
        else ""
    )

    # 騎手
    jockey_el = row.select_one(".Jockey a")
    if not jockey_el:
        jockey_el = row.select_one(".Jockey")

    jockey = (
        jockey_el.get_text(strip=True)
        if jockey_el
        else ""
    )

    # 馬体重
    body_weight = ""
    body_weight_change = ""

    body_candidates = [
        row.select_one(".Weight"),
        row.select_one(".HorseWeight"),
        row.select_one(".BodyWeight")
    ]

    for element in body_candidates:
        if not element:
            continue

        text = element.get_text(" ", strip=True)

        match = re.search(
            r"(\d{3})\s*\(\s*([+\-−]?\d+)\s*\)",
            text
        )

        if match:
            body_weight = match.group(1)
            body_weight_change = (
                match.group(2)
                .replace("−", "-")
            )
            break

    # -----------------------------
    # 斤量
    # -----------------------------
    carried_weight = ""

    # まず斤量用classを探索
    weight_selectors = [
        ".JockeyInfo .Weight",
        ".JockeyInfo .Wgt",
        ".Futan",
        ".FutanWeight",
        ".BurdenWeight"
    ]

    for selector in weight_selectors:
        element = row.select_one(selector)

        if not element:
            continue

        text = element.get_text(strip=True)

        match = re.search(
            r"\b([4-6]\d(?:\.\d)?)\b",
            text
        )

        if match:
            value = float(match.group(1))

            if 40 <= value <= 69:
                carried_weight = match.group(1)
                break

    # classで取れなかった場合
    # 行全体から40～69kgの値を探索
    if not carried_weight:

        row_text = row.get_text(" ", strip=True)

        candidates = re.findall(
            r"(?<!\d)([4-6]\d(?:\.\d)?)(?!\d)",
            row_text
        )

        for candidate in candidates:
            value = float(candidate)

            # 馬体重等を除外し斤量範囲だけ採用
            if 40 <= value <= 69:
                carried_weight = candidate
                break

    horses.append({
    "horse_id": horse_id,
    "horse_number": horse_number,
    "horse_name": horse_name,
    "sex_age": sex_age,
    "carried_weight": carried_weight,
    "jockey": jockey,
    "body_weight": body_weight,
    "body_weight_change": body_weight_change
})

data = {
    "race_id": RACE_ID,
    "updated_at": datetime.now().isoformat(),
    "source": "netkeiba",
    "horse_count": len(horses),
    "horses": horses
}

with open(
    "race.json",
    "w",
    encoding="utf-8"
) as f:
    json.dump(
        data,
        f,
        ensure_ascii=False,
        indent=2
    )

print(
    json.dumps(
        data,
        ensure_ascii=False,
        indent=2
    )
)
