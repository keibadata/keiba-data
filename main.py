import json
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

soup = BeautifulSoup(response.content, "html.parser")

horses = []

for row in soup.select(".HorseList"):
    horse = row.select_one(".HorseName a")

    if not horse:
        continue

    number = row.select_one(".Umaban")

    horses.append({
        "horse_number": number.get_text(strip=True) if number else "",
        "horse_name": horse.get_text(strip=True)
    })

data = {
    "race_id": RACE_ID,
    "updated_at": datetime.now().isoformat(),
    "source": "netkeiba",
    "horses": horses
}

with open("race.json", "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(json.dumps(data, ensure_ascii=False, indent=2))
