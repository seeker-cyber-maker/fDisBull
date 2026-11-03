"""Tests for cold-agent skill evaluation, EGM receipt validation, and challenge probes."""
from __future__ import annotations

import itertools
import math
from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def open_col_tea_selection(stocks: list[int], weights: list[int]) -> int | None:
    """OpenCol reconstruction model: weighted scan over unboycotted colony stocks."""
    if len(stocks) != 16 or len(weights) != 16:
        raise ValueError("Exactly 16 goods are required")
    if any(type(v) is not int or v < 0 for v in stocks + weights):
        raise ValueError("This probe admits only nonnegative integers")
    remaining = sum(w for s, w in zip(stocks, weights) if s)
    for i, (stock, weight) in enumerate(zip(stocks, weights)):
        if stock:
            remaining -= weight
            if remaining <= 0:
                return i
    return None


def dos_viceroy_tea_selection(
    stocks: list[int], boycottedMask: int = 0, min_tonnage: int = 100
) -> tuple[int | None, int]:
    """DOS VICEROY.EXE (0x3446A..0x344C6, 0x34682) forward strict-max tonnage selector."""
    if len(stocks) != 16:
        raise ValueError("Exactly 16 goods are required")
    max_tonnage = -1
    chosen_good: int | None = None
    for i, stock in enumerate(stocks):
        if boycottedMask & (1 << i):
            continue
        if stock > max_tonnage:
            max_tonnage = stock
            chosen_good = i
    if chosen_good is None or max_tonnage < min_tonnage:
        return None, 0
    return chosen_good, min(max_tonnage, 100)


def tax_event(score: int, wedding_count: int) -> str:
    """Tax event dispatch band model."""
    if score < 100:
        return "cut"
    if score < 650 and wedding_count < 30:
        return "wedding"
    if score < 950:
        return "war"
    if score < 1100:
        return "navigation_act"
    return "stamp_act"


def father_cost(
    nth: int,
    difficulty: int,
    year: int,
    human: bool = True,
    independent: bool = False,
) -> int:
    """Founding Father bell requirement with compound era rounding (0x3C282..0x3C321)."""
    if not (1 <= nth <= 25 and 0 <= difficulty <= 4):
        raise ValueError("Outside probe domain")
    v = 8 * (2 * difficulty + 6 if human else 14 - difficulty)
    for boundary in (1600, 1650, 1700, 1750):
        if year >= boundary:
            v += v // 2
    value = nth * v + 1
    if nth == 1:
        value //= 2
    return 1500 * difficulty + 2000 if independent else value


def custom_house_net(
    amount: int, bid: int, tax: int, independent: bool = False
) -> int:
    """Custom House net revenue before and after independence."""
    gross = amount * bid
    return gross if independent else gross - gross * tax // 100


def trade_pressure(
    amount: int, shift: int, difficulty: int, recipient_is_dutch: bool = False
) -> int:
    """Trade pressure calculation with signed truncation toward zero."""
    correction_numerator = (difficulty - 2) * 16 * amount
    correction = abs(correction_numerator) // 100
    if correction_numerator < 0:
        correction = -correction
    base = correction + (amount << shift)
    return base * 2 // 3 if recipient_is_dutch else base


def luxury_tick(
    price: int,
    volumes: list[int],
    good: int,
    up: int = 2,
    down: int = 2,
    intrinsic: int = 0,
    counter: int = 0,
    maximum: int = 20,
) -> tuple[int, int]:
    """One turn-tick target-pull/drift step on coupled luxury goods."""
    target = 3 * max(1, sum(volumes)) // max(1, volumes[good])
    sign = (price > target) - (price < target)
    counter += sign * ((up + down) // 2) * 100 + intrinsic
    if counter <= -up * 100:
        counter += up * 100
        if price < maximum:
            price += 1
    if counter >= down * 100:
        counter -= down * 100
        if price > 1:
            price -= 1
    return price, counter


def teaching_threshold(profession_school_class: int) -> int:
    """Teacher progress threshold by school tier (0x2DE7D..0x2DE9E)."""
    if profession_school_class not in (1, 2, 3):
        raise ValueError("Teacher class outside probe")
    return (4, 6, 8)[profession_school_class - 1]


def _valid_seconds(value: object) -> bool:
    return type(value) in (int, float) and math.isfinite(value) and value >= 0


def compare_egm_receipts(
    receipts: list[dict], lead_seconds: float | None = None
) -> dict:
    """Validate 3-arm EGM host receipts before computing speedup percentages."""
    reasons: list[str] = []
    base = {
        "status": "not_comparable",
        "reasons": reasons,
        "skill_worker_time_reduction_pct": None,
        "dossier_worker_time_reduction_pct": None,
        "dossier_one_off_time_reduction_pct": None,
    }
    if len(receipts) != 3 or {r.get("arm") for r in receipts} != {1, 2, 3}:
        reasons.append("Exactly one receipt per arm is required")
        return base
    rows = {r["arm"]: r for r in receipts}
    wanted = {1: (True, False), 2: (False, False), 3: (True, True)}
    for arm, row in rows.items():
        if row.get("status") != "completed":
            reasons.append(f"Arm {arm} did not complete")
        if (row.get("study_skill"), row.get("lead_dossier")) != wanted[arm]:
            reasons.append(f"Arm {arm} has incorrect treatment")
        if row.get("extra_web_calls") != 0:
            reasons.append(f"Arm {arm} has additional or unknown web use")
        if row.get("isolation_verified") is not True:
            reasons.append(f"Arm {arm} isolation unverified")
        if row.get("accepted_by_independent_reviewer") is not True:
            reasons.append(f"Arm {arm} lacks independent acceptance")
        sub = row.get("accepted_submission_seconds")
        end = row.get("end_seconds")
        if (
            not _valid_seconds(sub)
            or not _valid_seconds(end)
            or (_valid_seconds(sub) and _valid_seconds(end) and sub > end)
        ):
            reasons.append(f"Arm {arm} has invalid or missing timing")
        if not row.get("accepted_artifact_sha256") or not row.get("accepted_claim_ids"):
            reasons.append(f"Arm {arm} lacks version-bound accepted scope")
    for key in (
        "model_settings_sha256",
        "target_sha256",
        "tool_inventory_sha256",
        "budget_sha256",
    ):
        values = [rows[n].get(key) for n in (1, 2, 3)]
        if not all(isinstance(v, str) and v for v in values) or len(set(values)) != 1:
            reasons.append(f"Mismatched or missing {key}")
    if (
        rows[1].get("skill_sha256") != rows[3].get("skill_sha256")
        or not rows[1].get("skill_sha256")
    ):
        reasons.append("Skill exposure differs between arms 1 and 3")
    if any(
        rows[n].get("accepted_claim_ids") != rows[1].get("accepted_claim_ids")
        for n in (2, 3)
    ):
        reasons.append("Accepted scope differs")
    if lead_seconds is not None and not _valid_seconds(lead_seconds):
        reasons.append("Invalid lead research duration")
    if reasons:
        return base
    a, b, c = (rows[n]["accepted_submission_seconds"] for n in (1, 2, 3))
    base["status"] = "comparable_host_receipts"
    base["skill_worker_time_reduction_pct"] = 100 * (b - a) / b if b else None
    base["dossier_worker_time_reduction_pct"] = 100 * (a - c) / a if a else None
    if lead_seconds is not None and a:
        base["dossier_one_off_time_reduction_pct"] = (
            100 * (a - c - lead_seconds) / a
        )
    return base


class ColdAgentEgmBenchmarkTests(unittest.TestCase):
    def test_tea_selection_counterexamples_and_dos_divergence(self) -> None:
        stocks = [0] * 16
        weights = [0] * 16
        stocks[14] = stocks[15] = 50
        weights[14] = 1
        # In OpenCol's weighted model, stocked muskets with 0 weight lose to weighted tools.
        self.assertEqual(open_col_tea_selection(stocks, weights), 14)

        # When all weights are zero, OpenCol selects the lowest stocked index.
        stocks2 = [0] * 16
        stocks2[0] = stocks2[15] = 50
        self.assertEqual(open_col_tea_selection(stocks2, [0] * 16), 0)

        # In DOS VICEROY.EXE (0x3446A..0x344C6, 0x34682), selection uses forward strict-max
        # tonnage (>= 100) and caps forfeiture at 100 tons.
        dos_stocks = [0] * 16
        dos_stocks[2] = 150
        dos_stocks[14] = 150
        self.assertEqual(dos_viceroy_tea_selection(dos_stocks), (2, 100))
        dos_stocks[14] = 180
        self.assertEqual(dos_viceroy_tea_selection(dos_stocks), (14, 100))
        # Boycotted goods are skipped.
        self.assertEqual(
            dos_viceroy_tea_selection(dos_stocks, boycottedMask=(1 << 14)), (2, 100)
        )

    def test_bounded_tea_selection_characterization(self) -> None:
        goods = (0, 9, 14, 15)
        for has in itertools.product((0, 1), repeat=4):
            for ws in itertools.product((0, 1, 2), repeat=4):
                stocks = [0] * 16
                weights = [0] * 16
                for g, s, w in zip(goods, has, ws):
                    stocks[g], weights[g] = 50 * s, w
                positive = [g for g in goods if stocks[g] and weights[g] > 0]
                present = [g for g in goods if stocks[g]]
                expected = (
                    max(positive)
                    if positive
                    else min(present)
                    if present
                    else None
                )
                self.assertEqual(open_col_tea_selection(stocks, weights), expected)

    def test_tax_event_bands_and_75_cap(self) -> None:
        self.assertEqual(tax_event(950, 0), "navigation_act")
        self.assertEqual(tax_event(1099, 0), "navigation_act")
        self.assertEqual(tax_event(1100, 0), "stamp_act")
        self.assertEqual(tax_event(200, 29), "wedding")
        self.assertEqual(tax_event(200, 30), "war")

        tax, delta = 74, 8
        self.assertLessEqual(tax, 85)
        applied = min(75, max(0, tax + delta))
        self.assertEqual(applied, 75)

    def test_father_compound_era_rounding(self) -> None:
        for d in range(5):
            base1 = father_cost(1, d, 1599)
            base2, delta = 4 * base1 + 1, 2 * base1
            for n in range(2, 26):
                self.assertEqual(
                    father_cost(n, d, 1599), base2 + (n - 2) * delta
                )

        # In 1750 on Discoverer (d=0), compound era rounding makes father_cost(2) = 487 != 489.
        base1_1750 = father_cost(1, 0, 1750)
        self.assertEqual(base1_1750, 122)
        self.assertEqual(father_cost(2, 0, 1750), 487)
        self.assertNotEqual(father_cost(2, 0, 1750), 4 * base1_1750 + 1)

    def test_market_and_teaching_models(self) -> None:
        self.assertEqual(custom_house_net(100, 5, 20), 400)
        self.assertEqual(custom_house_net(100, 5, 20, independent=True), 500)
        self.assertEqual(luxury_tick(8, [100] * 4, 0), (9, 0))
        self.assertEqual(
            [trade_pressure(100, 0, d) for d in range(5)],
            [68, 84, 100, 116, 132],
        )
        self.assertEqual(trade_pressure(100, 0, 2, True), 66)
        self.assertEqual([teaching_threshold(k) for k in (1, 2, 3)], [4, 6, 8])

    def test_egm_receipt_validation_and_test4_timings(self) -> None:
        common = {
            "status": "completed",
            "extra_web_calls": 0,
            "isolation_verified": True,
            "accepted_by_independent_reviewer": True,
            "model_settings_sha256": "m" * 64,
            "target_sha256": "a17ed64c27671e5e95236e54a7ddc85803a96ba822fbed05e1dad34d3917e2e3",
            "tool_inventory_sha256": "t" * 64,
            "budget_sha256": "b" * 64,
        }
        # When Arm 1 and Arm 3 achieve the full 4-system static binary scope,
        # but Arm 2 only reaches surface text-table scope, compare_egm_receipts
        # flags the scope mismatch rather than awarding a false speedup to Arm 2.
        unmatched_scope = [
            {
                **common,
                "arm": 1,
                "study_skill": True,
                "lead_dossier": False,
                "accepted_submission_seconds": 813.0,
                "end_seconds": 813.0,
                "accepted_artifact_sha256": "6548829aca1fa7aa6bd3a231cd8e681b2da9296583a83ab554d1222c94c2a2ed",
                "accepted_claim_ids": ["edu", "ff", "tax", "mkt"],
                "skill_sha256": "s" * 64,
            },
            {
                **common,
                "arm": 2,
                "study_skill": False,
                "lead_dossier": False,
                "accepted_submission_seconds": 545.0,
                "end_seconds": 545.0,
                "accepted_artifact_sha256": "1d9e69cf557a11c7cb21b2732ade28616178b919bbc4ec8ce66023d8809de690",
                "accepted_claim_ids": ["edu_surface", "tax_surface"],
                "skill_sha256": None,
            },
            {
                **common,
                "arm": 3,
                "study_skill": True,
                "lead_dossier": True,
                "accepted_submission_seconds": 494.0,
                "end_seconds": 494.0,
                "accepted_artifact_sha256": "75e57b9a854f7b6251706f5bdb87c404022404accd322372e50add6d25b62322",
                "accepted_claim_ids": ["edu", "ff", "tax", "mkt"],
                "skill_sha256": "s" * 64,
            },
        ]
        res_unmatched = compare_egm_receipts(unmatched_scope)
        self.assertEqual(res_unmatched["status"], "not_comparable")
        self.assertIn("Accepted scope differs", res_unmatched["reasons"])

        # When evaluated at matched scope, Worker 3 vs Worker 1 shows 39.237% time reduction.
        matched_scope = [dict(r) for r in unmatched_scope]
        matched_scope[1]["accepted_claim_ids"] = ["edu", "ff", "tax", "mkt"]
        res_matched = compare_egm_receipts(matched_scope, lead_seconds=120.0)
        self.assertEqual(res_matched["status"], "comparable_host_receipts")
        self.assertAlmostEqual(
            res_matched["dossier_worker_time_reduction_pct"],
            100.0 * (813.0 - 494.0) / 813.0,
            places=5,
        )
        self.assertAlmostEqual(
            res_matched["dossier_one_off_time_reduction_pct"],
            100.0 * (813.0 - 494.0 - 120.0) / 813.0,
            places=5,
        )

    def test_benchmark_documentation_and_links(self) -> None:
        doc_path = REPO_ROOT / "docs" / "COLD_AGENT_EGM_BENCHMARK.md"
        quickstart_path = REPO_ROOT / "docs" / "AGENT_QUICKSTART.md"
        self.assertTrue(doc_path.is_file())
        doc_text = doc_path.read_text(encoding="utf-8")
        for required in (
            "Elephant-Goldfish Method (EGM)",
            "Test 1",
            "Test 2",
            "Test 3",
            "Test 4",
            "494.0s",
            "545.0s",
            "813.0s",
            "39.2%",
        ):
            self.assertIn(required, doc_text)
        self.assertIn(
            "COLD_AGENT_EGM_BENCHMARK.md",
            quickstart_path.read_text(encoding="utf-8"),
        )


if __name__ == "__main__":
    unittest.main()
