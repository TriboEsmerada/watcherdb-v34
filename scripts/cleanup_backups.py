#!/usr/bin/env python3
"""
Cleanup Script - Remove backup files and duplicated code from repository
This script safely removes:
- backup_limpeza_* directories
- .backup, .bak files
- Temporary cache files
- Old report files
"""

import os
import shutil
import logging
from pathlib import Path
from datetime import datetime

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Get project root
PROJECT_ROOT = Path(__file__).parent.parent


def confirm_deletion(message: str) -> bool:
    """Ask user for confirmation before deletion"""
    response = input(f"{message} (yes/no): ").lower().strip()
    return response in ['yes', 'y']


def create_deletion_report(deleted_items: list, output_file: str):
    """Create a report of deleted items"""
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    report_path = PROJECT_ROOT / "logs" / f"cleanup_report_{timestamp}.txt"

    # Ensure logs directory exists
    report_path.parent.mkdir(parents=True, exist_ok=True)

    with open(report_path, 'w') as f:
        f.write(f"WatcherDB Cleanup Report\n")
        f.write(f"Generated: {datetime.now().isoformat()}\n")
        f.write(f"{'='*80}\n\n")
        f.write(f"Total items deleted: {len(deleted_items)}\n\n")

        for item in deleted_items:
            f.write(f"- {item}\n")

    logger.info(f"Deletion report saved to: {report_path}")
    return report_path


def cleanup_backup_directories():
    """Remove backup directories (backup_limpeza_*, backup_*)"""
    deleted = []

    for item in PROJECT_ROOT.iterdir():
        if item.is_dir() and (item.name.startswith('backup_limpeza_') or
                              item.name.startswith('backup_') and item.name != 'backup'):
            try:
                logger.info(f"Deleting directory: {item.name}")
                shutil.rmtree(item)
                deleted.append(str(item.relative_to(PROJECT_ROOT)))
                logger.info(f"✓ Deleted: {item.name}")
            except Exception as e:
                logger.error(f"✗ Failed to delete {item.name}: {e}")

    return deleted


def cleanup_backup_files():
    """Remove .backup, .bak files from the project"""
    deleted = []
    patterns = ['*.backup', '*.bak', '*_backup_*.py']

    for pattern in patterns:
        for file_path in PROJECT_ROOT.rglob(pattern):
            # Skip files in .git, venv, etc.
            if any(part.startswith('.') or part == 'venv' for part in file_path.parts):
                continue

            try:
                logger.info(f"Deleting file: {file_path.relative_to(PROJECT_ROOT)}")
                file_path.unlink()
                deleted.append(str(file_path.relative_to(PROJECT_ROOT)))
                logger.info(f"✓ Deleted: {file_path.name}")
            except Exception as e:
                logger.error(f"✗ Failed to delete {file_path.name}: {e}")

    return deleted


def cleanup_cache_files():
    """Remove cache database files from root"""
    deleted = []
    cache_files = [
        PROJECT_ROOT / 'watcherdb_cache.db',
    ]

    for cache_file in cache_files:
        if cache_file.exists():
            try:
                logger.info(f"Deleting cache file: {cache_file.name}")
                cache_file.unlink()
                deleted.append(str(cache_file.relative_to(PROJECT_ROOT)))
                logger.info(f"✓ Deleted: {cache_file.name}")
            except Exception as e:
                logger.error(f"✗ Failed to delete {cache_file.name}: {e}")

    return deleted


def cleanup_old_reports():
    """Clean up old report files (optional - ask user)"""
    deleted = []
    reports_dir = PROJECT_ROOT / 'reports'

    if not reports_dir.exists():
        return deleted

    # Count report files
    report_files = list(reports_dir.glob('*'))

    if not report_files:
        logger.info("No old reports found")
        return deleted

    logger.info(f"Found {len(report_files)} files in reports/")

    if not confirm_deletion(f"Delete all {len(report_files)} old report files?"):
        logger.info("Skipping report cleanup")
        return deleted

    for report_file in report_files:
        if report_file.is_file():
            try:
                report_file.unlink()
                deleted.append(str(report_file.relative_to(PROJECT_ROOT)))
            except Exception as e:
                logger.error(f"✗ Failed to delete {report_file.name}: {e}")

    logger.info(f"✓ Deleted {len(deleted)} report files")
    return deleted


def main():
    """Main cleanup function"""
    logger.info("=" * 80)
    logger.info("WatcherDB Cleanup Script")
    logger.info("=" * 80)
    logger.info(f"Project root: {PROJECT_ROOT}")
    logger.info("")

    all_deleted = []

    # 1. Cleanup backup directories
    logger.info("Step 1: Cleaning up backup directories...")
    if confirm_deletion("Delete backup directories (backup_limpeza_*, backup_*)?"):
        deleted = cleanup_backup_directories()
        all_deleted.extend(deleted)
        logger.info(f"Deleted {len(deleted)} backup directories\n")
    else:
        logger.info("Skipped backup directories\n")

    # 2. Cleanup backup files
    logger.info("Step 2: Cleaning up .backup and .bak files...")
    if confirm_deletion("Delete all .backup, .bak, *_backup_*.py files?"):
        deleted = cleanup_backup_files()
        all_deleted.extend(deleted)
        logger.info(f"Deleted {len(deleted)} backup files\n")
    else:
        logger.info("Skipped backup files\n")

    # 3. Cleanup cache files
    logger.info("Step 3: Cleaning up cache database files...")
    if confirm_deletion("Delete cache files (watcherdb_cache.db)?"):
        deleted = cleanup_cache_files()
        all_deleted.extend(deleted)
        logger.info(f"Deleted {len(deleted)} cache files\n")
    else:
        logger.info("Skipped cache files\n")

    # 4. Cleanup old reports (optional)
    logger.info("Step 4: Cleaning up old report files...")
    deleted = cleanup_old_reports()
    all_deleted.extend(deleted)
    logger.info("")

    # Generate report
    logger.info("=" * 80)
    logger.info(f"Cleanup Complete! Total items deleted: {len(all_deleted)}")
    logger.info("=" * 80)

    if all_deleted:
        report_path = create_deletion_report(all_deleted, "cleanup_report.txt")
        logger.info(f"\nDeletion report: {report_path}")

        # Show summary
        logger.info("\nSummary of deleted items:")
        for item in all_deleted[:10]:  # Show first 10
            logger.info(f"  - {item}")

        if len(all_deleted) > 10:
            logger.info(f"  ... and {len(all_deleted) - 10} more (see report)")

    logger.info("\nRecommendations:")
    logger.info("1. Review the deletion report before committing")
    logger.info("2. Run tests to ensure nothing broke: pytest")
    logger.info("3. Update .gitignore if needed")
    logger.info("4. Commit with: git add . && git commit -m 'chore: cleanup backup files'")


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        logger.info("\n\nCleanup cancelled by user")
    except Exception as e:
        logger.error(f"\n\nCleanup failed with error: {e}")
        raise
