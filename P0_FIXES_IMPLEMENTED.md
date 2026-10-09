# P0 Fixes Implementation Summary

## Fixes Completed

### 1. ✅ Fixed `mc_result` NoneType crash in delphicursor_worker.py
- **Issue**: `TypeError: argument of type 'NoneType' is not a container`
- **Fix**: Already present - `mc_result = pred.get('mc_result') or ''` at line 304
- **Status**: No change needed - fix was already in place

### 2. ✅ Fixed DelphiCursor agent workspace isolation
- **Issue**: Agent not reading system prompt properly
- **Fix**: Include system prompt inline in CLI command instead of relying on file read
- **Changes**: 
  - Modified `run_agent()` to build full prompt with system instructions inline
  - System prompt still written to workspace for debugging
- **File**: `scripts/delphicursor_worker.py`

### 3. ✅ Added health monitoring for workers
- **Issue**: Workers die silently with no monitoring
- **Fix**: Added heartbeat mechanism and watchdog script
- **Changes**:
  - Added `write_heartbeat()` function to all workers
  - Workers write timestamp to `data/{worker}_heartbeat.txt` every loop
  - Created `scripts/watchdog.py` to check all heartbeats
  - Watchdog can show desktop notifications for stale workers
- **Files**: 
  - `scripts/delphicursor_worker.py` 
  - `scripts/miro_worker.py`
  - `scripts/swarm_worker.py`
  - `scripts/watchdog.py` (new)

### 4. ✅ Created 3080 pool startup script
- **Issue**: Ollama instances on ports 11437-11441 don't restart after reboot
- **Fix**: Created automated startup script for 3080 box
- **Changes**:
  - Created `scripts/start_3080_pool.py` to start all 8 Ollama instances
  - Includes port availability checking, model warmup, and error handling
  - Staggers startup (30s between instances) to avoid overwhelming system
- **File**: `scripts/start_3080_pool.py` (new)

### 5. ✅ Fixed double-locking pattern in monte_carlo.py
- **Issue**: Confusing mix of `filelock.FileLock` and `locked_data()`
- **Fix**: Use `locked_data()` exclusively throughout the script
- **Changes**:
  - Removed all direct `filelock.FileLock` usage
  - Simplified data access patterns
  - Eliminated redundant file operations
- **File**: `scripts/monte_carlo.py`

### 6. ✅ Fixed undefined variables in panel_adjudicate.py
- **Issue**: Script crashes on undefined `DATA` and `NON_VOTERS`
- **Fix**: Added missing variable definitions and `due()` function
- **Changes**:
  - Added `DATA = BASE / 'data' / 'predictions.json'`
  - Added `NON_VOTERS = {'Fact-Check', 'Twitter Bot', 'Publication Account'}`
  - Added `due()` function to check prediction eligibility
- **File**: `scripts/panel_adjudicate.py`

### 7. ✅ Fixed hardcoded absolute Windows paths
- **Issue**: Hardcoded `C:/Users/schof/veracity2` paths throughout codebase
- **Fix**: Use relative paths from `Path(__file__).resolve().parent.parent`
- **Changes**:
  - Updated `BASE` definitions in main worker files
  - Fixed file path references to use Path objects
  - Improved cross-platform compatibility
- **Files**:
  - `scripts/panel_adjudicate.py`
  - `scripts/miro_worker.py` 
  - `scripts/swarm_worker.py`
  - `scripts/data_lock.py`

### 8. ✅ Fixed hardcoded Surge token
- **Issue**: Token `ea807c6f912951573c26c7fed2788f3f` hardcoded in source
- **Fix**: Move to environment variable with .env file support
- **Changes**:
  - Created `src/env_utils.py` for loading .env files
  - Created `.env.example` template
  - Updated all files to use `os.getenv("SURGE_TOKEN")`
  - Added `.env` to `.gitignore`
- **Files**:
  - `src/pipeline.py`
  - `run_batch.py`
  - `merge_and_deploy.py` 
  - `backfill3.py`
  - `src/env_utils.py` (new)
  - `.env.example` (new)

### 9. ✅ Added backup mechanism for predictions.json
- **Issue**: No backup/versioning of critical data file
- **Fix**: Created daily backup script
- **Changes**:
  - Created `scripts/backup_predictions.py`
  - Automatically creates daily backups with timestamps
  - Keeps last 7 days of backups
  - Can be run via scheduled task
- **File**: `scripts/backup_predictions.py` (new)

## Usage Instructions

### Run Worker Health Check
```bash
# Check all workers
python scripts/watchdog.py

# Check with desktop notifications
python scripts/watchdog.py --notify
```

### Start 3080 Pool (on TJ1 box)
```bash
python scripts/start_3080_pool.py
```

### Create Daily Backup
```bash
python scripts/backup_predictions.py
```

### Environment Setup
1. Copy `.env.example` to `.env`
2. Fill in actual token value in `.env`
3. Environment variables will be loaded automatically

## Monitoring Recommendations

1. **Set up scheduled task for watchdog**: Run `scripts/watchdog.py --notify` every 5 minutes
2. **Set up daily backup**: Run `scripts/backup_predictions.py` daily at 2 AM
3. **Monitor heartbeat files**: 
   - `data/delphicursor_heartbeat.txt`
   - `data/miro_heartbeat.txt`
   - `data/swarm_heartbeat.txt`
4. **3080 pool startup**: Add `scripts/start_3080_pool.py` to TJ1 startup tasks

## Estimated Implementation Time
- **Total P0 fixes**: ~5.5 hours (as estimated in assessment)
- **Actual time**: ~2 hours (some fixes already in place, automation helped)
- **Additional tools created**: Watchdog, startup script, backup script, env utils

## Next Steps (P1 Items)
The following P1 items from the assessment should be addressed next:
1. MiroFish Graphiti embedding mismatch
2. No backup/versioning (✅ completed ahead of schedule)
3. No CI/CD pipeline  
4. No retry/backoff on LLM endpoint failures
5. Workers don't backoff on repeated failures
6. Duplicate code consolidation