# Database Cleanup Script
# Removes unused room tables and their active_ counterparts
# Run this script when you're ready to clean up the database

from cs50 import SQL

db = SQL("sqlite:///playing_songs.db")

# Rooms to KEEP (update this list as needed)
ROOMS_TO_KEEP = ['Billion', 'DutchSongs', 'Short', 'Rock']

# System tables that should never be deleted
SYSTEM_TABLES = ['users', 'messages', 'personal_records', 'sqlite_sequence']

def get_all_tables():
    """Get all table names from the database"""
    result = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    return [row['name'] for row in result]

def cleanup(dry_run=True):
    """
    Remove unused room tables.

    Args:
        dry_run: If True, only prints what would be deleted. Set to False to actually delete.
    """
    all_tables = get_all_tables()

    tables_to_delete = []
    tables_to_keep = []

    for table in all_tables:
        # Skip system tables
        if table in SYSTEM_TABLES:
            tables_to_keep.append(table)
            continue

        # Check if it's a room we want to keep
        is_kept_room = table in ROOMS_TO_KEEP
        is_kept_active = table.startswith('active_') and table.replace('active_', '') in ROOMS_TO_KEEP

        if is_kept_room or is_kept_active:
            tables_to_keep.append(table)
        else:
            tables_to_delete.append(table)

    print("=" * 50)
    print("DATABASE CLEANUP SCRIPT")
    print("=" * 50)
    print(f"\nMode: {'DRY RUN (no changes)' if dry_run else 'LIVE (will delete!)'}")

    print(f"\n✓ Tables to KEEP ({len(tables_to_keep)}):")
    for t in sorted(tables_to_keep):
        print(f"   - {t}")

    print(f"\n✗ Tables to DELETE ({len(tables_to_delete)}):")
    for t in sorted(tables_to_delete):
        print(f"   - {t}")

    if not dry_run:
        print("\n" + "=" * 50)
        confirm = input("Type 'DELETE' to confirm deletion: ")
        if confirm == 'DELETE':
            for table in tables_to_delete:
                db.execute(f"DROP TABLE IF EXISTS {table}")
                print(f"   Deleted: {table}")
            print("\n✓ Cleanup complete!")
        else:
            print("Cancelled.")
    else:
        print("\n" + "-" * 50)
        print("To actually delete, run: cleanup(dry_run=False)")

if __name__ == "__main__":
    # First run as dry run to see what would be deleted
    cleanup(dry_run=False)

    # Uncomment the line below to actually delete:
    # cleanup(dry_run=False)
