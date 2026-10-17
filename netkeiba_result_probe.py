import re
import requests
from bs4 import BeautifulSoup, Tag


# =========================================================
# 設定
# =========================================================

RACE_ID = "202605040502"

URL = (
    "https://race.netkeiba.com/"
    "race/result.html"
    f"?race_id={RACE_ID}"
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


# =========================================================
# 共通
# =========================================================

def clean_text(element):
    if element is None:
        return ""

    return re.sub(
        r"\s+",
        " ",
        element.get_text(" ", strip=True)
    ).strip()


def show_element(title, element, html_limit=12000):
    print()
    print("=" * 60)
    print(title)
    print("=" * 60)

    if element is None:
        print("NONE")
        return

    print("TAG:", getattr(element, "name", None))
    print("ID:", element.get("id") if isinstance(element, Tag) else None)
    print(
        "CLASS:",
        element.get("class") if isinstance(element, Tag) else None
    )

    print()
    print("TEXT:")
    print(clean_text(element)[:5000])

    print()
    print("HTML:")
    print(str(element)[:html_limit])


def next_tag_siblings(element, limit=10):
    result = []

    sibling = element.next_sibling

    while sibling is not None and len(result) < limit:
        if isinstance(sibling, Tag):
            result.append(sibling)

        sibling = sibling.next_sibling

    return result


# =========================================================
# HTML取得
# =========================================================

response = requests.get(
    URL,
    headers=HEADERS,
    timeout=30
)

response.raise_for_status()
response.encoding = response.apparent_encoding

html = response.text

soup = BeautifulSoup(
    html,
    "html.parser"
)


print("=" * 60)
print("NETKEIBA CORNER STRUCTURE PROBE")
print("=" * 60)

print("RACE_ID:", RACE_ID)
print("URL:", URL)
print("HTML SIZE:", len(html))


# =========================================================
# 「コーナー通過順位」完全一致要素
# =========================================================

print()
print("===== EXACT CORNER HEADINGS =====")

exact_elements = []

for element in soup.find_all(True):
    text = clean_text(element)

    if text == "コーナー通過順位":
        exact_elements.append(element)


print(
    "EXACT MATCH COUNT:",
    len(exact_elements)
)


# =========================================================
# 各候補を個別調査
# =========================================================

for index, element in enumerate(
    exact_elements,
    start=1
):
    print()
    print("#" * 70)
    print(
        f"CORNER HEADING CANDIDATE {index}"
    )
    print("#" * 70)

    show_element(
        "HEADING",
        element,
        4000
    )

    # -----------------------------------------------------
    # 親
    # -----------------------------------------------------

    parent = element.parent

    show_element(
        "PARENT",
        parent,
        8000
    )

    # -----------------------------------------------------
    # 親の次兄弟
    # -----------------------------------------------------

    if parent is not None:
        siblings = next_tag_siblings(
            parent,
            10
        )

        print()
        print(
            "PARENT NEXT TAG SIBLING COUNT:",
            len(siblings)
        )

        for sibling_index, sibling in enumerate(
            siblings,
            start=1
        ):
            show_element(
                (
                    "PARENT NEXT SIBLING "
                    f"{sibling_index}"
                ),
                sibling,
                15000
            )

    # -----------------------------------------------------
    # 祖父
    # -----------------------------------------------------

    grandparent = (
        parent.parent
        if parent is not None
        else None
    )

    show_element(
        "GRANDPARENT",
        grandparent,
        15000
    )

    # -----------------------------------------------------
    # 祖父の子要素
    # -----------------------------------------------------

    if grandparent is not None:
        children = [
            child
            for child in grandparent.children
            if isinstance(child, Tag)
        ]

        print()
        print(
            "GRANDPARENT DIRECT CHILD COUNT:",
            len(children)
        )

        for child_index, child in enumerate(
            children[:20],
            start=1
        ):
            show_element(
                (
                    "GRANDPARENT CHILD "
                    f"{child_index}"
                ),
                child,
                12000
            )

    # -----------------------------------------------------
    # 祖父の次兄弟
    # -----------------------------------------------------

    if grandparent is not None:
        siblings = next_tag_siblings(
            grandparent,
            10
        )

        print()
        print(
            "GRANDPARENT NEXT TAG SIBLING COUNT:",
            len(siblings)
        )

        for sibling_index, sibling in enumerate(
            siblings,
            start=1
        ):
            show_element(
                (
                    "GRANDPARENT NEXT SIBLING "
                    f"{sibling_index}"
                ),
                sibling,
                15000
            )


# =========================================================
# corner関連classを直接調査
# =========================================================

print()
print("=" * 60)
print("CORNER CLASS SEARCH")
print("=" * 60)

corner_class_elements = []

for element in soup.find_all(True):
    classes = element.get("class", [])

    class_text = " ".join(
        str(value)
        for value in classes
    ).lower()

    if "corner" in class_text:
        corner_class_elements.append(
            element
        )


print(
    "CORNER CLASS COUNT:",
    len(corner_class_elements)
)


for index, element in enumerate(
    corner_class_elements,
    start=1
):
    show_element(
        f"CORNER CLASS ELEMENT {index}",
        element,
        10000
    )


# =========================================================
# idにもcornerがないか確認
# =========================================================

print()
print("=" * 60)
print("CORNER ID SEARCH")
print("=" * 60)

corner_id_elements = []

for element in soup.find_all(True):
    element_id = str(
        element.get("id", "")
    )

    if "corner" in element_id.lower():
        corner_id_elements.append(
            element
        )


print(
    "CORNER ID COUNT:",
    len(corner_id_elements)
)


for index, element in enumerate(
    corner_id_elements,
    start=1
):
    show_element(
        f"CORNER ID ELEMENT {index}",
        element,
        10000
    )


# =========================================================
# 完了
# =========================================================

print()
print("=" * 60)
print("PROBE COMPLETE")
print("=" * 60)
