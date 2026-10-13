import json
import re
import requests
from bs4 import BeautifulSoup
from datetime import datetime

RACE_ID = "202605040502"

URL = f"https://race.netkeiba.com/race/shutuba.html?race_id={RACE_ID}"

headers = {
    "User-Agent": "Mozilla/5.0"
}

response = requests.get(URL, headers=headers, timeout=20)
response.raise_for_status()

# 日本語文字化け対策
response.encoding = response.apparent_encoding

soup = BeautifulSoup(response.text, "html.parser")

horses = []

for index, row in enumerate(soup.select(".HorseList"), start=1):

    horse = row.select_one(".HorseName a")

    if not horse:
        continue

    # 馬番
    number = row.select_one(".Umaban")
    horse_number = number.get_text(strip=True) if number else str(index)

    # 馬名
    horse_name = horse.get_text(strip=True)

    # 性齢
    sex_age_el = row.select_one(".Barei")
    sex_age = sex_age_el.get_text(strip=True) if sex_age_el else ""

    # 斤量
    weight_el = row.select_one(".JockeyInfo .Weight")
    if not weight_el:
        weight_el = row.select_one(".Weight")
    weight = weight_el.get_text(strip=True) if weight_el else ""

    # 騎手
    jockey_el = row.select_one(".Jockey a")
    if not jockey_el:
        jockey_el = row.select_one(".Jockey")
    jockey = jockey_el.get_text(strip=True) if jockey_el else ""

    # 馬体重・増減
    body_weight_el = row.select_one(".Weight")
    body_weight_text = body_weight_el.get_text(" ", strip=True) if body_weight_el else ""

    body_weight = ""
    body_weight_change = ""

    match = re.search(r"(\d{3})\s*\(([+-]?\d+)\)", body_weight_text)

    if match:
        body_weight = match.group(1)
        body_weight_change = match.group(2)

    horses.append({
        "horse_number": horse_number,
        "horse_name": horse_name,
        "sex_age": sex_age,
        "carried_weight": weight,
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

with open("race.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(json.dumps(data, ensure_ascii=False, indent=2))
