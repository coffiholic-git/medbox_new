"""
Benchmarking Harness for Pharmaceutical EXP Date Detection.

MedBox tracks expiry dates only. MFG/MFD/PKD dates that appear on packaging are
deliberately ignored by the extractor, so this harness scores EXP accuracy, the
validity flag, and whether the rescan gate fires when it should.

Enables evaluation of extraction accuracy, precision, recall, and confidence
calibration on Kaggle datasets or built-in pharmaceutical benchmark test suites.

Usage:
  python -m backend.tests.benchmark_dates
  python -m backend.tests.benchmark_dates --dataset-dir <path_to_kaggle_dataset>
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, List, Optional

from backend.perception.date_extractor import (
    DATE_CONFIDENCE_THRESHOLD,
    DateExtractionResult,
    extract_mfg_and_exp_dates,
)
from backend.perception.ocr import OCRResult


# ==============================================================================
# BENCHMARK TEST SUITE (Synthesized from Real-world Packaging & Kaggle Formats)
# ==============================================================================

BUILTIN_BENCHMARK_CASES = [
    # 1. Standard inline MM/YYYY
    {
        "id": "CASE_01_INLINE_MM_YYYY",
        "description": "Clear inline MM/YYYY with standard MFG & EXP",
        "input": ["MFG: 05/2023", "EXP: 05/2026", "CIPLA LTD."],
        "expected_exp": "05/2026",
        "should_be_valid": True,
    },
    # 2. 2-digit years MM/YY
    {
        "id": "CASE_02_TWO_DIGIT_YEARS",
        "description": "Two digit year notation e.g. 04/23 -> 04/2023",
        "input": ["MFD: 04/23", "EXP: 04/26"],
        "expected_exp": "04/2026",
        "should_be_valid": True,
    },
    # 3. Textual month format
    {
        "id": "CASE_03_TEXTUAL_MONTH",
        "description": "Textual 3-letter month format",
        "input": ["MANUFACTURED: JAN 2024", "BEST BEFORE: DEC 2026"],
        "expected_exp": "12/2026",
        "should_be_valid": True,
    },
    # 4. Spaced and hyphenated separators
    {
        "id": "CASE_04_SPACED_DELIMITERS",
        "description": "OCR artifact with spaced hyphens and dots",
        "input": ["MFG . 08 - 2023", "EXP . 08 - 2025"],
        "expected_exp": "08/2025",
        "should_be_valid": True,
    },
    # 5. Letter 'O' confusion in numeric date tokens
    {
        "id": "CASE_05_LETTER_O_TYPO",
        "description": "Common OCR confusion: 'O' instead of '0'",
        "input": ["MFG: O2/2O24", "EXP: O2/2O27"],
        "expected_exp": "02/2027",
        "should_be_valid": True,
    },
    # 6. Spatial bounding box layout: horizontal adjacent
    {
        "id": "CASE_06_HORIZONTAL_BBOX",
        "description": "Separate bounding boxes arranged horizontally",
        "input": [
            OCRResult(text="MFG DATE:", confidence=0.96, bbox=[[10, 20], [80, 20], [80, 40], [10, 40]]),
            OCRResult(text="03/2023", confidence=0.94, bbox=[[85, 20], [140, 20], [140, 40], [85, 40]]),
            OCRResult(text="EXPIRY DATE:", confidence=0.96, bbox=[[10, 50], [90, 50], [90, 70], [10, 70]]),
            OCRResult(text="09/2025", confidence=0.93, bbox=[[95, 50], [150, 50], [150, 70], [95, 70]]),
        ],
        "expected_exp": "09/2025",
        "should_be_valid": True,
    },
    # 7. Spatial bounding box layout: vertically stacked columns
    {
        "id": "CASE_07_VERTICAL_STACKED_BBOX",
        "description": "Keyword header with date value directly below in vertical column",
        "input": [
            OCRResult(text="MFD", confidence=0.95, bbox=[[10, 10], [50, 10], [50, 30], [10, 30]]),
            OCRResult(text="EXP", confidence=0.95, bbox=[[80, 10], [120, 10], [120, 30], [80, 30]]),
            OCRResult(text="11/2023", confidence=0.92, bbox=[[10, 35], [50, 35], [50, 55], [10, 55]]),
            OCRResult(text="11/2026", confidence=0.92, bbox=[[80, 35], [120, 35], [120, 55], [80, 55]]),
        ],
        "expected_exp": "11/2026",
        "should_be_valid": True,
    },
    # 8. Full day/month/year format (DD/MM/YYYY)
    {
        "id": "CASE_08_FULL_DMY",
        "description": "Day-Month-Year pharmaceutical format",
        "input": ["MFG: 15/06/2023", "EXP: 14/06/2026"],
        "expected_exp": "14/06/2026",
        "should_be_valid": True,
    },
    # 9. Alternate keywords: PKD & USE BEFORE
    {
        "id": "CASE_09_ALT_KEYWORDS",
        "description": "PKD (packed date) and USE BEFORE",
        "input": ["PKD: 07/2023", "USE BEFORE: 07/2025"],
        "expected_exp": "07/2025",
        "should_be_valid": True,
    },
    # 10. Fuzzy keyword typo: EXF instead of EXP
    {
        "id": "CASE_10_FUZZY_KEYWORD",
        "description": "Fuzzy keyword typo recovery",
        "input": ["MFG: 10/2023", "EXF: 10/2026"],
        "expected_exp": "10/2026",
        "should_be_valid": True,
    },
    # 11. EXP keyword unreadable, MFG printed first (the original mislabelling bug).
    #     Must report the LATER date and force a rescan rather than trust the guess.
    {
        "id": "CASE_11_MFG_FIRST_NO_EXP_KEYWORD",
        "description": "No EXP keyword read; earlier (MFG) date must not be chosen",
        "input": ["BATCH A1", "05/2023", "05/2026"],
        "expected_exp": "05/2026",
        "should_be_valid": True,
        "expected_needs_rescan": True,
    },
    # 12. Only EXP date present
    {
        "id": "CASE_12_ONLY_EXP_PRESENT",
        "description": "Medicine blister containing only EXP date",
        "input": ["EXP DATE: 03/2027", "BATCH: TX-991"],
        "expected_exp": "03/2027",
        "should_be_valid": True,
    },
    # 13. Dot separators in date e.g. 05.2026
    {
        "id": "CASE_13_DOT_SEPARATORS",
        "description": "Dot delimiters in date",
        "input": ["MFD 01.2024", "EXP 01.2027"],
        "expected_exp": "01/2027",
        "should_be_valid": True,
    },
    # 14. Complex surrounding clutter
    {
        "id": "CASE_14_CLUTTERED_LABEL",
        "description": "Packaging text with dosage, barcode numbers, batch and composition",
        "input": [
            "PARACETAMOL IP 500mg",
            "B.NO. G88392",
            "MFG. LIC. NO. 25/UA/2018",
            "MFD. 06/2023",
            "EXP. 05/2026",
            "M.R.P. RS. 35.50 PER 10 TABS",
            "INCL. OF ALL TAXES",
        ],
        "expected_exp": "05/2026",
        "should_be_valid": True,
    },
    # 15. Degraded OCR with low confidence
    {
        "id": "CASE_15_LOW_CONFIDENCE_GATE",
        "description": "Low OCR confidence triggering rescan gate",
        "input": [
            OCRResult(text="EXP: 05/2026", confidence=0.30, bbox=[[0, 0], [50, 0], [50, 20], [0, 20]]),
        ],
        "expected_exp": "05/2026",
        "should_be_valid": True,
        "expected_needs_rescan": True,
    },
    # 16. MFG labelled, EXP label garbled beyond recognition
    {
        "id": "CASE_16_MFG_LABELLED_EXP_GARBLED",
        "description": "MFG is labelled but EXP label is unreadable; still gated for rescan",
        "input": ["MFG: 05/2023", "XQZ 05/2026"],
        "expected_exp": "05/2026",
        "should_be_valid": True,
        "expected_needs_rescan": True,
    },
    # 17. EXP printed before MFG (reverse layout) must still be read via its keyword
    {
        "id": "CASE_17_EXP_BEFORE_MFG",
        "description": "EXP line precedes MFG line",
        "input": ["EXP: 05/2026", "MFG: 05/2023"],
        "expected_exp": "05/2026",
        "should_be_valid": True,
        "expected_needs_rescan": False,
    },
]


# ==============================================================================
# BENCHMARK EVALUATOR
# ==============================================================================

@dataclass
class BenchmarkMetrics:
    total_cases: int = 0
    exp_exact_matches: int = 0
    validity_matches: int = 0
    rescan_cases: int = 0
    rescan_matches: int = 0
    high_conf_total: int = 0
    high_conf_accurate: int = 0
    low_conf_gated: int = 0
    avg_confidence: float = 0.0

    @property
    def exp_accuracy(self) -> float:
        return (self.exp_exact_matches / self.total_cases) * 100.0 if self.total_cases else 0.0

    @property
    def rescan_gate_accuracy(self) -> float:
        """Share of cases with an expected gate outcome where needs_rescan matched."""
        return (self.rescan_matches / self.rescan_cases) * 100.0 if self.rescan_cases else 100.0

    @property
    def high_conf_precision(self) -> float:
        return (self.high_conf_accurate / self.high_conf_total) * 100.0 if self.high_conf_total else 0.0


def run_benchmark(cases: list[dict[str, Any]]) -> tuple[BenchmarkMetrics, list[dict[str, Any]]]:
    """Execute the benchmark over a collection of test cases."""
    metrics = BenchmarkMetrics(total_cases=len(cases))
    results_detail: list[dict[str, Any]] = []
    conf_sum = 0.0

    for case in cases:
        case_id = case["id"]
        inp = case["input"]
        exp_exp = case.get("expected_exp")
        exp_valid = case.get("should_be_valid", True)
        exp_needs_rescan = case.get("expected_needs_rescan")

        # Run pipeline
        res: DateExtractionResult = extract_mfg_and_exp_dates(inp)
        conf_sum += res.overall_confidence

        exp_hit = (res.exp_date == exp_exp)
        validity_hit = (res.is_valid == exp_valid)

        if exp_hit:
            metrics.exp_exact_matches += 1
        if validity_hit:
            metrics.validity_matches += 1

        if exp_needs_rescan is not None:
            metrics.rescan_cases += 1
            if res.needs_rescan == exp_needs_rescan:
                metrics.rescan_matches += 1

        is_high_conf = res.overall_confidence >= DATE_CONFIDENCE_THRESHOLD
        if is_high_conf:
            metrics.high_conf_total += 1
            if exp_hit and validity_hit:
                metrics.high_conf_accurate += 1

        if res.needs_rescan:
            metrics.low_conf_gated += 1

        results_detail.append({
            "id": case_id,
            "description": case.get("description", ""),
            "exp_pred": res.exp_date,
            "exp_exp": exp_exp,
            "exp_match": exp_hit,
            "confidence": res.overall_confidence,
            "is_valid": res.is_valid,
            "needs_rescan": res.needs_rescan,
        })

    metrics.avg_confidence = round(conf_sum / len(cases), 1) if cases else 0.0
    return metrics, results_detail


def print_report(metrics: BenchmarkMetrics, details: list[dict[str, Any]]) -> None:
    """Print an ASCII / Markdown performance summary report."""
    print("=" * 80)
    print("           MEDBOX PHARMACEUTICAL DATE EXTRACTION BENCHMARK REPORT           ")
    print("=" * 80)
    print(f"Total Test Cases Evaluated : {metrics.total_cases}")
    print(f"EXP Extraction Accuracy    : {metrics.exp_accuracy:.1f}% ({metrics.exp_exact_matches}/{metrics.total_cases})")
    print(f"Rescan Gate Accuracy       : {metrics.rescan_gate_accuracy:.1f}% ({metrics.rescan_matches}/{metrics.rescan_cases})")
    print(f"Date Validation Accuracy   : {(metrics.validity_matches / metrics.total_cases) * 100:.1f}%")
    print(f"High-Confidence Precision  : {metrics.high_conf_precision:.1f}% (when confidence >= 80%)")
    print(f"Low-Confidence Gated Cases : {metrics.low_conf_gated} cases flagged for confirmation/rescan")
    print(f"Average Confidence Score   : {metrics.avg_confidence}%")
    print("-" * 80)
    print(f"{'CASE ID':<36} | {'EXP MATCH':<10} | {'CONF':<6} | {'STATUS':<10}")
    print("-" * 80)
    for d in details:
        e_icon = "[OK]" if d["exp_match"] else "[X]"
        gate = "CONFIRM" if not d["needs_rescan"] else "RESCAN"
        print(f"{d['id']:<36} | {e_icon:<10} | {d['confidence']:<6.1f} | {gate:<10}")
    print("=" * 80)


def load_external_kaggle_dataset(dataset_dir: str | Path) -> list[dict[str, Any]]:
    """Load an external Kaggle dataset directory if provided."""
    path = Path(dataset_dir)
    if not path.exists():
        print(f"[Warning] Kaggle dataset directory not found: {path}. Using built-in benchmark.")
        return BUILTIN_BENCHMARK_CASES

    cases: list[dict[str, Any]] = []
    # Look for annotations.json or labels.json
    for json_file in path.glob("*.json"):
        try:
            with open(json_file, encoding="utf-8") as f:
                data = json.load(f)
                if isinstance(data, list):
                    for item in data:
                        if "input" in item:
                            cases.append(item)
        except Exception as e:
            print(f"Error reading {json_file}: {e}")

    if not cases:
        print(f"No valid JSON annotation file found in {dataset_dir}. Using built-in benchmark.")
        return BUILTIN_BENCHMARK_CASES

    return cases


def main():
    parser = argparse.ArgumentParser(description="MedBox Date Detection Benchmark Harness")
    parser.add_argument("--dataset-dir", type=str, default="", help="Path to external Kaggle dataset directory")
    args = parser.parse_args()

    if args.dataset_dir:
        cases = load_external_kaggle_dataset(args.dataset_dir)
    else:
        cases = BUILTIN_BENCHMARK_CASES

    metrics, details = run_benchmark(cases)
    print_report(metrics, details)

    # Fail if EXP accuracy or rescan-gate behaviour drops below 80%
    if metrics.exp_accuracy < 80.0 or metrics.rescan_gate_accuracy < 80.0:
        sys.exit(1)


if __name__ == "__main__":
    main()
