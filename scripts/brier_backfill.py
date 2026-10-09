# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Backfill Brier ledgers for existing predictions.

Usage:
    python scripts/brier_backfill.py --dry-run    # Preview changes
    python scripts/brier_backfill.py              # Actually backfill
    python scripts/brier_backfill.py --calibrate  # Generate calibration files
"""
import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from src.brier import backfill_brier_ledgers, generate_all_calibration_files


def main():
    parser = argparse.ArgumentParser(description="Brier Ledger backfill utility")
    parser.add_argument("--dry-run", action="store_true", help="Preview changes without writing")
    parser.add_argument("--calibrate", action="store_true", help="Generate calibration files after backfill")
    args = parser.parse_args()

    print("=" * 60)
    print("BRIER LEDGER BACKFILL")
    print("=" * 60)
    
    stats = backfill_brier_ledgers(dry_run=args.dry_run)
    
    print(f"\nResults:")
    print(f"  Predictions checked:      {stats['checked']}")
    print(f"  Already have ledger:      {stats['already_has_ledger']}")
    print(f"  Backfilled:               {stats['backfilled']}")
    print(f"  Skipped (no data):        {stats['no_data']}")
    
    if args.dry_run:
        print("\n[DRY RUN - no changes written]")
        print("Run without --dry-run to apply changes.")
    else:
        print("\n[Changes written to predictions.json]")
    
    if args.calibrate and not args.dry_run:
        print("\n" + "=" * 60)
        print("GENERATING CALIBRATION FILES")
        print("=" * 60)
        files = generate_all_calibration_files()
        print(f"Generated {len(files)} calibration file(s):")
        for f in files:
            print(f"  - {f}")


if __name__ == "__main__":
    main()
