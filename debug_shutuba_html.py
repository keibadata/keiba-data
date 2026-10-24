import os
import re
import requests
from bs4 import BeautifulSoup


def load_race_id():
    race_id = os.environ.get("RACE_ID", "").strip()

    if race_id:
        return race_id

    if os.path.exists("race_id.txt"):
        with open("race_id.txt", "r", encoding="utf-8") as f:
            race_id = f.read().strip()

        if race_id:
            return race_id

    raise RuntimeError("RACE_ID が取得できません。")


RACE_ID = load_race_id()

URL = (
    "https://race.netkeiba.com/"
    f"race/shutuba.html?race_id={RACE_ID}"
)

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 "
        "(iPhone; CPU iPhone OS 18_0 like Mac OS X) "
        "AppleWebKit/605.1.15 "
        "(KHTML, like Gecko) "
        "Version/18.0 Mobile/15E148 Safari/604.1"
    ),
    "Accept-Language": "ja,en-US;q=0.9,en;q=0.8",
}


response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30,
)

response.raise_for_status()
response.encoding = response.apparent_encoding

soup = BeautifulSoup(
    response.text,
    "html.parser",
)


rows = soup.select("tr.HorseList")

if not rows:
    rows = soup.select(".HorseList")


print("=" * 80)
print("SHUTUBA HTML DEBUG")
print("=" * 80)

print("race_id:", RACE_ID)
print("url:", URL)
print("horse_rows:", len(rows))
print()


for index, row in enumerate(rows, start=1):

    horse_link = None

    for link in row.select('a[href*="/horse/"]'):
        href = str(link.get("href", ""))

        if re.search(r"/horse/\d+", href):
            horse_link = link
            break

    horse_id = ""

    if horse_link:
        href = str(
            horse_link.get(
                "href",
                "",
            )
        )

        match = re.search(
            r"/horse/(\d+)",
            href,
        )

        if match:
            horse_id = match.group(1)

    horse_name = ""

    if horse_link:
        horse_name = horse_link.get_text(
            " ",
            strip=True,
        )

    print()
    print("#" * 80)
    print(f"ROW INDEX: {index}")
    print("#" * 80)

    print("HORSE ID:")
    print(horse_id)

    print()
    print("HORSE LINK TEXT:")
    print(horse_name)

    print()
    print("ROW TAG:")
    print(row.name)

    print()
    print("ROW CLASSES:")
    print(row.get("class", []))

    print()
    print("ROW ATTRIBUTES:")
    print(dict(row.attrs))

    print()
    print("ROW TEXT:")
    print(
        row.get_text(
            " | ",
            strip=True,
        )
    )

    print()
    print("--- TD / DIV / SPAN STRUCTURE ---")

    elements = row.find_all(
        ["td", "div", "span"],
        recursive=True,
    )

    for element_index, element in enumerate(
        elements,
        start=1,
    ):
        text = element.get_text(
            " ",
            strip=True,
        )

        classes = element.get(
            "class",
            [],
        )

        attrs = dict(
            element.attrs
        )

        print()
        print(
            f"[ELEMENT {element_index}] "
            f"<{element.name}>"
        )

        print(
            "classes:",
            classes,
        )

        print(
            "attrs:",
            attrs,
        )

        print(
            "text:",
            repr(text),
        )

    print()
    print("--- LINKS ---")

    for link_index, link in enumerate(
        row.find_all("a"),
        start=1,
    ):
        print()
        print(
            f"[LINK {link_index}]"
        )

        print(
            "classes:",
            link.get(
                "class",
                [],
            ),
        )

        print(
            "attrs:",
            dict(link.attrs),
        )

        print(
            "href:",
            link.get(
                "href",
                "",
            ),
        )

        print(
            "text:",
            repr(
                link.get_text(
                    " ",
                    strip=True,
                )
            ),
        )


print()
print("=" * 80)
print("DEBUG FINISHED")
print("=" * 80)
