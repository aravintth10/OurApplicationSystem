#!/usr/bin/env python3
"""
Candidate ranking pipeline.
Usage: python rank.py --candidates candidates.jsonl --out submission.csv
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from honeypot_detector import is_honeypot
from scorer import score_candidate

load_dotenv()


def load_candidates(path: Path) -> List[Dict[str, Any]]:
    with open(path, "r", encoding="utf-8") as f:
        first_char = f.read(1)
        f.seek(0)
        if first_char == "[":
            return json.load(f)
        
        candidates = []
        for i, line in enumerate(f):
            line = line.strip()
            if not line:
                continue
            try:
                candidates.append(json.loads(line))
            except json.JSONDecodeError as e:
                print(f"  [WARN] Skipping malformed line {i+1}: {e}", file=sys.stderr)
        return candidates


def rank_candidates(
    candidates: List[Dict[str, Any]],
    verbose: bool = False,
    top_n: int = 100,
) -> List[Tuple[str, int, float, str]]:
    t0 = time.time()
    scored: List[Tuple[float, str, str]] = []
    honeypot_count = 0
    n = len(candidates)

    print(f"Scoring {n:,} candidates...", flush=True)

    for i, candidate in enumerate(candidates):
        if verbose and i % 10000 == 0:
            elapsed = time.time() - t0
            pct = i / n * 100
            eta = (elapsed / max(i, 1)) * (n - i)
            print(
                f"  [{pct:5.1f}%] {i:>6}/{n}  "
                f"elapsed={elapsed:.1f}s  eta={eta:.0f}s",
                flush=True,
            )

        cid = candidate.get("candidate_id", f"UNKNOWN_{i}")

        flagged, hp_reason = is_honeypot(candidate)
        if flagged:
            honeypot_count += 1
            if verbose:
                print(f"  [HONEYPOT] {cid}: {hp_reason}", file=sys.stderr)
            scored.append((-9.0, cid, f"EXCLUDED: {hp_reason[:80]}"))
            continue

        score, reasoning = score_candidate(candidate)
        scored.append((score, cid, reasoning))

    elapsed = time.time() - t0
    print(f"Scoring complete in {elapsed:.1f}s  |  honeypots detected: {honeypot_count}", flush=True)

    # Sort by score (desc), then ID (asc)
    scored.sort(key=lambda x: (-x[0], x[1]))
    top100 = scored[:top_n]

    # Normalize scores to [0.20, 0.99]
    max_score = top100[0][0] if top100 else 1.0
    min_score_100 = top100[-1][0] if top100 else 0.0
    score_range = max_score - min_score_100 if max_score > min_score_100 else 1.0

    norm_rows: List[Tuple[float, float, str, str]] = []
    for raw_score, cid, reasoning in top100:
        norm_score = 0.20 + 0.79 * (raw_score - min_score_100) / score_range
        norm_score = round(max(0.0, min(1.0, norm_score)), 4)
        norm_rows.append((norm_score, raw_score, cid, reasoning))

    norm_rows.sort(key=lambda x: (-x[0], x[2]))

    # Enforce non-increasing scores
    for i in range(1, len(norm_rows)):
        if norm_rows[i][0] > norm_rows[i - 1][0]:
            ns, rs, cid, rsn = norm_rows[i]
            norm_rows[i] = (norm_rows[i - 1][0], rs, cid, rsn)

    result: List[Tuple[str, int, float, str]] = [
        (cid, rank_idx + 1, ns, reasoning)
        for rank_idx, (ns, _, cid, reasoning) in enumerate(norm_rows)
    ]

    return result


def write_submission(
    rows: List[Tuple[str, int, float, str]],
    out_path: Path,
) -> None:
    with open(out_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f, quoting=csv.QUOTE_MINIMAL)
        writer.writerow(["candidate_id", "rank", "score", "reasoning"])
        for cid, rank, score, reasoning in rows:
            safe_reasoning = reasoning.replace("\n", " ").replace("\r", " ")
            writer.writerow([cid, rank, score, safe_reasoning])
    print(f"Submission written to: {out_path}  ({len(rows)} rows)", flush=True)


def print_preview(rows: List[Tuple[str, int, float, str]], n: int = 15) -> None:
    print(f"\n{'-'*90}")
    print(f"{'#':>3}  {'Candidate ID':<14}  {'Score':>6}  Reasoning")
    print(f"{'-'*90}")
    for cid, rank, score, reasoning in rows[:n]:
        print(f"{rank:>3}  {cid:<14}  {score:>6.4f}  {reasoning[:60]}")
    print(f"{'-'*90}\n")


def main():
    parser = argparse.ArgumentParser(description="Rank candidates for Senior AI Engineer JD.")
    candidates_env = os.getenv("CANDIDATES_FILE")
    parser.add_argument(
        "--candidates",
        type=Path,
        default=Path(candidates_env) if candidates_env else None,
        required=candidates_env is None,
        help="Path to candidates.jsonl or candidates.json",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=Path(os.getenv("OUTPUT_FILE", "submission.csv")),
        help="Output CSV path",
    )
    parser.add_argument(
        "--top",
        type=int,
        default=int(os.getenv("TOP_N", "100")),
        help="Number of candidates to rank",
    )
    parser.add_argument(
        "--verbose",
        action="store_true",
        help="Print progress information",
    )
    parser.add_argument(
        "--preview",
        action="store_true",
        help="Print preview of top results",
    )
    args = parser.parse_args()

    if not args.candidates.exists():
        print(f"ERROR: file not found: {args.candidates}", file=sys.stderr)
        sys.exit(1)

    t_start = time.time()

    candidates = load_candidates(args.candidates)
    rows = rank_candidates(candidates, verbose=args.verbose, top_n=args.top)

    if args.preview:
        print_preview(rows)

    write_submission(rows, args.out)
    print(f"Total time: {time.time() - t_start:.1f}s")


if __name__ == "__main__":
    main()
