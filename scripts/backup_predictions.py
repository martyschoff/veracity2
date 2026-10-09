# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Daily backup script for predictions.json.

Copies predictions.json to backups/ directory with timestamp.
Keeps last 7 days of backups.

Usage: python scripts/backup_predictions.py
"""
import datetime
import shutil
import sys
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
DATA_FILE = BASE / 'data' / 'predictions.json'
BACKUP_DIR = BASE / 'data' / 'backups'
KEEP_DAYS = 7

def main():
    # Create backup directory if it doesn't exist
    BACKUP_DIR.mkdir(exist_ok=True)
    
    # Check if source file exists
    if not DATA_FILE.exists():
        print(f"ERROR: Source file {DATA_FILE} does not exist")
        sys.exit(1)
    
    # Create backup filename with date
    today = datetime.date.today().strftime('%Y%m%d')
    backup_file = BACKUP_DIR / f'predictions_{today}.json'
    
    # Skip if backup already exists for today
    if backup_file.exists():
        print(f"Backup already exists: {backup_file}")
        return
    
    try:
        # Copy file
        shutil.copy2(DATA_FILE, backup_file)
        print(f"Backup created: {backup_file}")
        
        # Clean up old backups
        cutoff_date = datetime.date.today() - datetime.timedelta(days=KEEP_DAYS)
        
        for backup in BACKUP_DIR.glob('predictions_*.json'):
            try:
                # Extract date from filename
                date_str = backup.stem.split('_')[1]  # predictions_YYYYMMDD.json
                backup_date = datetime.datetime.strptime(date_str, '%Y%m%d').date()
                
                if backup_date < cutoff_date:
                    backup.unlink()
                    print(f"Removed old backup: {backup}")
                    
            except (ValueError, IndexError):
                # Skip files that don't match the expected pattern
                continue
                
    except Exception as e:
        print(f"ERROR: Failed to create backup: {e}")
        sys.exit(1)

if __name__ == '__main__':
    main()