# Fix PostgreSQL parameter handling to prevent 'dict is not a sequence' errors

## Summary
- Fixed PostgreSQL parameter handling bug that caused "dict is not a sequence" errors
- Added comprehensive unit tests for parameter handling
- Included CI/CD improvements for version conflict detection

## Problem
The ff_storage PostgreSQL implementation incorrectly passed empty dictionaries `{}` to psycopg2's cursor.execute() when params were None. This caused psycopg2 to interpret the empty dict as named parameters and throw errors when the SQL query didn't contain named placeholders.

## Solution
- Removed the `params or {}` pattern from three methods in postgres.py
- Now passes `params` directly (which can be None) to cursor.execute()
- psycopg2 correctly handles None params for queries without parameters

## Changes
1. **ff-storage/src/ff_storage/db/postgres.py**:
   - Fixed `read_query()` method (line 39)
   - Fixed `execute()` method (line 58)  
   - Fixed `execute_query()` method (line 81)

2. **ff-storage/tests/test_postgres_params.py**:
   - Added 10 comprehensive unit tests
   - Tests cover None params, missing params, and dict params
   - Includes specific test for "dict is not a sequence" error prevention

3. **CI/CD Improvements** (included in this commit):
   - Enhanced pipeline with version conflict detection
   - Added manual version bump jobs for conflict resolution
   - Added check_version_exists.sh script
   - Updated detect_changes.sh for conflict detection

## Test Plan
✅ All unit tests pass (10 new tests added)
✅ Verified parameter handling with None, missing, and dict params
✅ No "dict is not a sequence" errors occur