import re
import requests
from urllib.parse import urljoin


# =========================================================
# 設定
# =========================================================

BASE_URL = "https://www.jra.go.jp"
BABA_URL = "https://www.jra.go.jp/keiba/baba/index.html"

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
# HTTP取得
# =========================================================

def get_text(url):

    response = requests.get(
        url,
        headers=HEADERS,
        timeout=30
    )

    response.raise_for_status()

    response.encoding = (
        response.apparent_encoding
        or "utf-8"
    )

    return response.text


# =========================================================
# JavaScript URL取得
# =========================================================

def extract_script_urls(html):

    scripts = re.findall(
        r'<script[^>]+src=["\']([^"\']+)["\']',
        html,
        flags=re.IGNORECASE
    )

    urls = []

    for src in scripts:

        full_url = urljoin(
            BABA_URL,
            src
        )

        if full_url not in urls:
            urls.append(
                full_url
            )

    return urls


# =========================================================
# 関数本体抽出
# =========================================================

def extract_function(
    javascript,
    function_name
):

    patterns = [
        rf"function\s+{re.escape(function_name)}\s*\([^)]*\)\s*\{{",
        rf"{re.escape(function_name)}\s*=\s*function\s*\([^)]*\)\s*\{{",
    ]

    match = None

    for pattern in patterns:

        match = re.search(
            pattern,
            javascript
        )

        if match:
            break

    if not match:
        return ""

    start = match.start()

    brace_start = javascript.find(
        "{",
        match.start()
    )

    if brace_start == -1:
        return ""

    depth = 0

    in_single = False
    in_double = False
    in_template = False
    escaped = False

    for index in range(
        brace_start,
        len(javascript)
    ):

        char = javascript[index]

        if escaped:
            escaped = False
            continue

        if char == "\\":
            escaped = True
            continue

        if (
            char == "'"
            and not in_double
            and not in_template
        ):
            in_single = not in_single
            continue

        if (
            char == '"'
            and not in_single
            and not in_template
        ):
            in_double = not in_double
            continue

        if (
            char == "`"
            and not in_single
            and not in_double
        ):
            in_template = not in_template
            continue

        if (
            in_single
            or in_double
            or in_template
        ):
            continue

        if char == "{":
            depth += 1

        elif char == "}":

            depth -= 1

            if depth == 0:

                return javascript[
                    start:index + 1
                ]

    return ""


# =========================================================
# 関数周辺抽出
# =========================================================

def extract_context(
    javascript,
    keyword,
    before=1200,
    after=3000
):

    position = javascript.find(
        keyword
    )

    if position == -1:
        return ""

    start = max(
        0,
        position - before
    )

    end = min(
        len(javascript),
        position + after
    )

    return javascript[
        start:end
    ]


# =========================================================
# 通信処理候補抽出
# =========================================================

def extract_network_candidates(text):

    patterns = [
        r"\$\.ajax\s*\([^;]{0,3000}",
        r"\$\.getJSON\s*\([^;]{0,2000}",
        r"\$\.get\s*\([^;]{0,2000}",
        r"\$\.post\s*\([^;]{0,2000}",
        r"fetch\s*\([^;]{0,2000}",
        r"url\s*:\s*[^,\n]+",
        r"""["'][^"']+\.(?:json|php|html|xml|csv)(?:\?[^"']*)?["']""",
    ]

    results = []

    for pattern in patterns:

        for match in re.finditer(
            pattern,
            text,
            flags=re.IGNORECASE
        ):

            value = match.group(0)

            if value not in results:
                results.append(
                    value
                )

    return results


# =========================================================
# 実行
# =========================================================

print(
    "========================================"
)

print(
    "JRA TRACK NETWORK PROBE"
)

print(
    "========================================"
)

print(
    "PAGE:",
    BABA_URL
)


html = get_text(
    BABA_URL
)


script_urls = extract_script_urls(
    html
)


print(
    "\n===== JAVASCRIPT FILES ====="
)

print(
    "COUNT:",
    len(script_urls)
)


matched_count = 0


for number, script_url in enumerate(
    script_urls,
    start=1
):

    try:

        javascript = get_text(
            script_url
        )

    except Exception as exc:

        print(
            "\nJS ERROR:",
            script_url,
            exc
        )

        continue


    keywords = [
        "get_cushion_data",
        "set_cushion_data",
        "cushion_list",
        "cushion_data",
    ]


    if not any(
        keyword in javascript
        for keyword in keywords
    ):
        continue


    matched_count += 1


    print(
        "\n========================================"
    )

    print(
        "MATCHED JS #",
        matched_count
    )

    print(
        "URL:",
        script_url
    )

    print(
        "SIZE:",
        len(javascript)
    )

    print(
        "========================================"
    )


    # -----------------------------------------------------
    # get_cushion_data()
    # -----------------------------------------------------

    function_text = extract_function(
        javascript,
        "get_cushion_data"
    )


    print(
        "\n===== FUNCTION: get_cushion_data ====="
    )


    if function_text:

        print(
            function_text
        )

    else:

        print(
            "FUNCTION NOT FOUND"
        )


    # -----------------------------------------------------
    # set_cushion_data()
    # -----------------------------------------------------

    set_function_text = extract_function(
        javascript,
        "set_cushion_data"
    )


    print(
        "\n===== FUNCTION: set_cushion_data ====="
    )


    if set_function_text:

        print(
            set_function_text
        )

    else:

        print(
            "FUNCTION NOT FOUND"
        )


    # -----------------------------------------------------
    # get_cushion_data 周辺
    # -----------------------------------------------------

    context = extract_context(
        javascript,
        "get_cushion_data",
        before=2000,
        after=5000
    )


    print(
        "\n===== GET CUSHION CONTEXT ====="
    )


    if context:

        print(
            context
        )

    else:

        print(
            "CONTEXT NOT FOUND"
        )


    # -----------------------------------------------------
    # 通信候補
    # -----------------------------------------------------

    network_candidates = (
        extract_network_candidates(
            context
            if context
            else javascript
        )
    )


    print(
        "\n===== NETWORK CANDIDATES ====="
    )


    if network_candidates:

        for index, candidate in enumerate(
            network_candidates,
            start=1
        ):

            print(
                "\nNETWORK #",
                index
            )

            print(
                candidate
            )

    else:

        print(
            "NETWORK CANDIDATE NOT FOUND"
        )


    # -----------------------------------------------------
    # cushion_list 周辺
    # -----------------------------------------------------

    cushion_list_context = (
        extract_context(
            javascript,
            "cushion_list",
            before=1500,
            after=3500
        )
    )


    print(
        "\n===== CUSHION_LIST CONTEXT ====="
    )


    if cushion_list_context:

        print(
            cushion_list_context
        )

    else:

        print(
            "CUSHION_LIST NOT FOUND"
        )


print(
    "\n========================================"
)

print(
    "MATCHED SCRIPT COUNT:",
    matched_count
)

print(
    "JRA TRACK NETWORK PROBE FINISHED"
)

print(
    "========================================"
)
