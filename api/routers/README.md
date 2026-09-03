# ⚠️ DEPRECATED - DO NOT USE

**This directory is DEPRECATED and will be removed in version 2.0.0**

## Migration Status

All routers in this directory are being migrated to `watcherdb/api/routers/`.

| File | Status | New Location | Notes |
|------|--------|--------------|-------|
| `alwayson.py` | 🔴 DEPRECATED | `watcherdb/api/routers/alwayson.py` | Use new version |
| `diagnostics_overview.py` | 🟡 MIGRATING | `watcherdb/api/routers/monitoring.py` | Being integrated |
| `oracle_kpis.py` | 🟡 MIGRATING | `watcherdb/api/routers/oracle.py` | Being migrated |
| `service_status.py` | 🟡 MIGRATING | `watcherdb/api/routers/monitoring.py` | Being integrated |
| `sql_queries.py` | 🔴 DEPRECATED | `watcherdb/api/routers/queries.py` | Use new version |

## Why?

This directory was the original location for API routers. We've refactored to a cleaner architecture:

**Old structure:**
```
api/routers/
  alwayson.py       # Monolithic, no separation of concerns
  oracle_kpis.py    # 73 KB! Too large, mixed responsibilities
```

**New structure:**
```
watcherdb/
  api/routers/      # Clean, modular routers
  services/         # Business logic layer
  models/           # Data models
  core/             # Core functionality (auth, cache)
```

## Timeline

- **2025-11-14:** Marked as deprecated
- **2025-11-20:** Migration to new structure complete
- **2025-12-01:** This directory will be removed

## For Developers

**DO NOT** add new code to this directory.
**DO NOT** fix bugs here - fix them in `watcherdb/api/routers/` instead.

If you need to use these endpoints, import from the new location:

```python
# ❌ OLD - Don't do this
from api.routers.alwayson import router

# ✅ NEW - Do this instead
from watcherdb.api.routers.alwayson import router
```

## Need Help?

See:
- [STRUCTURE_ANALYSIS_AND_IMPROVEMENTS.md](../../STRUCTURE_ANALYSIS_AND_IMPROVEMENTS.md) - Full analysis
- [MIGRATION_GUIDE.md](../../MIGRATION_GUIDE.md) - Migration guide
- [REFACTORING_COMPLETE.md](../../REFACTORING_COMPLETE.md) - Refactoring details

## Questions?

Contact: WatcherDB Team
