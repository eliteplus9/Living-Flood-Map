"""Classify a CSV locally: python -m scripts.classify_csv input.csv output.json"""

import argparse
from pathlib import Path

from src.classify import classify_tweets
from src.data import DataValidationError, load_data


def main():
    parser = argparse.ArgumentParser(
        description="Classify tweets offline; write JSON records or CSV."
    )
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--threshold", type=float, default=0.5)
    args = parser.parse_args()
    if args.input.resolve() == args.output.resolve():
        parser.error("Choose a different output path to preserve the input.")
    if args.output.exists():
        parser.error("Output already exists; choose a new filename.")
    if args.output.suffix not in (".csv", ".json"):
        parser.error("Output must end in .csv or .json.")
    try:
        result = classify_tweets(load_data(args.input), threshold=args.threshold)
    except (DataValidationError, ValueError, RuntimeError) as exc:
        parser.error(str(exc))
    if args.output.suffix == ".json":
        result.to_json(args.output, orient="records", force_ascii=False, indent=2)
    else:
        result.to_csv(args.output, index=False)
    print(
        f"{len(result):,} rows; {result.is_relevant.sum():,} relevant; {result.needs_review.sum():,} need review. Saved {args.output}"
    )


if __name__ == "__main__":
    main()
