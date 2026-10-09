# Copyright (c) 2026 Martin Schoffstall. MIT License - see LICENSE in repo root.
"""Environment utilities for loading .env files."""
import os
from pathlib import Path

def load_dotenv(env_file: Path = None):
    """Load environment variables from .env file."""
    if env_file is None:
        env_file = Path(__file__).resolve().parent.parent / '.env'
    
    if not env_file.exists():
        return
    
    with open(env_file, 'r', encoding='utf-8') as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                # Remove quotes if present
                if value.startswith('"') and value.endswith('"'):
                    value = value[1:-1]
                elif value.startswith("'") and value.endswith("'"):
                    value = value[1:-1]
                os.environ[key] = value