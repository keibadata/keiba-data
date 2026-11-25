import argparse
import json
import re
from decimal import Decimal, InvalidOperation
from itertools import combinations
from pathlib import Path
from urllib.parse import urljoin


STRATEGY = "trio_partner_same_condition_v1"
UNIT_YEN = 100


def number(value):
    if type(value) is int and value > 0:
        return value
    if isinstance(value, str) and re.fullmatch(r"[1-9][0-9]*", value):
        return int(value)
    return None


def score(value):
    if not isinstance(value, (int, float, str)) or isinstance(value, bool):
        return None
    try:
        parsed = Decimal(str(value))
    except InvalidOperation:
        return None
    return parsed if parsed.is_finite() else None


def eligible(snapshot):
    return (
        snapshot.get("snapshot_kind") == "prediction"
        and snapshot.get("analysis_mode") == "normal"
        and not snapshot["race"].get("is_debut")
        and snapshot["race"].get("surface") in {"芝", "ダート"}
        and snapshot["timing"].get("evaluation_eligible") is True
        and snapshot["timing"].get("status") in {
            "before_race_date", "same_day_before_start"
        }
    )


def build_side(axis, partners):
    return {
        "partners": partners,
        "tickets": sorted(sorted((axis, left, right)) for left, right in combinations(partners, 2)),
    }


def build_partner_comparison(snapshot):
    if not eligible(snapshot):
        return None

    ranked = {}
    by_number = {}
    for horse in snapshot["analysis"]["ranking"]:
        rank = number(horse.get("rank"))
        if rank is None:
            continue
        horse_number = number(horse.get("horse_number"))
        ability = score(horse.get("ability_score"))
        if rank in ranked or horse_number in by_number or horse_number is None or ability is None:
            return None
        if horse.get("ability_known") is False or horse.get("unknown") is True:
            return None
        ranked[rank] = horse_number
        by_number[horse_number] = horse

    if len(ranked) < 6 or set(ranked) != set(range(1, len(ranked) + 1)):
        return None

    ability_order = sorted(by_number, key=lambda n: (-score(by_number[n]["ability_score"]), n))
    axis = ranked[1]
    gap = score(by_number[ability_order[0]]["ability_score"]) - score(
        by_number[ability_order[1]]["ability_score"]
    )
    sixth = ranked[6]
    sixth_support = score(by_number[sixth].get("reproducibility_support"))
    outside = {ranked[rank] for rank in range(7, min(10, len(ranked)) + 1)}
    replacement = None
    for ability_rank, candidate in enumerate(ability_order[:5], start=1):
        if candidate not in outside or sixth_support is None:
            continue
        horse = by_number[candidate]
        good_count = number(horse.get("condition_good_direct_count"))
        support = score(horse.get("reproducibility_support"))
        if good_count and support is not None and support > sixth_support:
            replacement = {
                "horse_number": candidate,
                "horse_name": horse.get("horse_name"),
                "ability_rank": ability_rank,
                "app_rank": number(horse["rank"]),
                "condition_good_direct_count": good_count,
                "reproducibility_support": float(support),
                "replaced_horse_reproducibility_support": float(sixth_support),
            }
            break

    core = [ranked[rank] for rank in range(2, 6)]
    return {
        "strategy": STRATEGY,
        "axis_horse_number": axis,
        "axis_confidence_high": axis == ability_order[0] and gap >= 8,
        "ability_first_second_gap": float(gap),
        "unit_yen": UNIT_YEN,
        "removed_horse_number": sixth if replacement else None,
        "replacement": replacement,
        "original": build_side(axis, core + [sixth]),
        "trial": build_side(axis, core + [replacement["horse_number"] if replacement else sixth]),
    }


def parse_jra_result(raw, url, race):
    from bs4 import BeautifulSoup
    from jra_race_incidents import JRA_ORIGIN, jra_result_identity

    expected = (str(race["race_id"]), race["race_date"])
    if jra_result_identity(url) != expected:
        raise ValueError("JRA公式結果URLの日付・レースIDが保存予想と一致しません")
    page = BeautifulSoup(raw, "html.parser", from_encoding="cp932")
    current = page.select_one("ul.race-num li.current a[href]")
    if not current or jra_result_identity(urljoin(JRA_ORIGIN, current["href"])) != expected:
        raise ValueError("JRA公式結果ページの日付・レースIDを確認できません")

    finishers = {}
    withdrawals = set()
    appeared = set()
    for row in page.select("#race_result .race_result_unit table tbody tr"):
        place = row.select_one("td.place")
        entry = row.select_one("td.num")
        if not place or not entry:
            continue
        horse_number = number(entry.get_text(strip=True))
        rank = place.get_text(strip=True)
        if horse_number is None or horse_number in appeared:
            raise ValueError("JRA公式結果の馬番が不足または重複しています")
        appeared.add(horse_number)
        if number(rank) is not None:
            finishers[horse_number] = number(rank)
        elif rank in {"取消", "除外"}:
            withdrawals.add(horse_number)
        elif rank not in {"中止", "失格", "降着"}:
            raise ValueError(f"JRA公式結果の着順欄を判定できません: {rank}")

    payouts = {}
    for line in page.select(".refund_area li.trio .line"):
        combination = line.select_one(".num")
        amount = line.select_one(".yen")
        if not combination or not amount:
            raise ValueError("JRA公式の3連複払戻欄を確認できません")
        horses = tuple(sorted(map(int, re.findall(r"[0-9]+", combination.get_text(" ", strip=True)))))
        yen = number(amount.get_text(strip=True).removesuffix("円").replace(",", ""))
        if (len(set(horses)) != 3 or len(horses) != 3 or horses in payouts or yen is None
                or any(finishers.get(horse, 99) > 3 for horse in horses)):
            raise ValueError("JRA公式の3連複払戻が着順と一致しません")
        payouts[horses] = yen
    if not payouts:
        raise ValueError("JRA公式の3連複払戻は不明です")
    return payouts, withdrawals, appeared


def settle(snapshot, url, raw):
    saved = snapshot.get("partner_comparison")
    if not saved or saved != build_partner_comparison(snapshot):
        raise ValueError("発走前に保存された照合可能な相手比較データがありません")
    payouts, withdrawals, appeared = parse_jra_result(raw, url, snapshot["race"])
    result = {
        "snapshot_id": snapshot["snapshot_id"],
        "race_id": snapshot["race"]["race_id"],
        "strategy": saved["strategy"],
        "axis_confidence_high": saved["axis_confidence_high"],
        "changed": saved["replacement"] is not None,
        "result_url": url,
    }
    for key in ("original", "trial"):
        tickets = [tuple(ticket) for ticket in saved[key]["tickets"]]
        if any(not set(ticket) <= appeared for ticket in tickets):
            raise ValueError("保存された買い目の馬番がJRA公式結果で確認できません")
        stake = len(tickets) * UNIT_YEN
        payout = sum(payouts.get(ticket, 0) for ticket in tickets)
        refund = UNIT_YEN * sum(bool(set(ticket) & withdrawals) for ticket in tickets)
        result[key] = {
            "hit": payout > 0,
            "stake_yen": stake,
            "payout_yen": payout,
            "refund_yen": refund,
            "net_yen": payout + refund - stake,
        }
    return result


def main():
    from jra_race_incidents import jra_result_identity
    from previous_race_jra_notes import load_result_page

    parser = argparse.ArgumentParser(description="発走前に保存した3連複2案をJRA公式結果と照合")
    parser.add_argument("snapshot", type=Path)
    parser.add_argument("jra_result_url")
    args = parser.parse_args()

    try:
        snapshot = json.loads(args.snapshot.read_text(encoding="utf-8"))
        race = snapshot["race"]
        if jra_result_identity(args.jra_result_url) != (str(race["race_id"]), race["race_date"]):
            raise ValueError("JRA公式結果URLの日付・レースIDが保存予想と一致しません")
        raw = load_result_page(args.jra_result_url, {})
        result = settle(snapshot, args.jra_result_url, raw)
    except (OSError, ValueError, KeyError) as error:
        parser.exit(1, f"照合できません: {error}\n")
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
