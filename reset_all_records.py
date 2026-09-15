"""
Script to reset all records to 0
Automatically finds all tables with a 'record' column and resets them
Also clears the personal_records table
"""
from cs50 import SQL

change = False

if change is True:

    db = SQL("sqlite:///playing_songs.db")

    print("Resetting all records to 0...")
    print("=" * 50)

    # Get all table names from the database
    all_tables = db.execute("SELECT name FROM sqlite_master WHERE type='table'")
    print(f"Found {len(all_tables)} tables in database")

    # Find tables with 'record' column
    tables_with_records = []
    for table in all_tables:
        table_name = table['name']

        print(f"Checking table: {table_name}")

        # Skip system tables and personal_records (we'll handle it separately)
        if table_name.startswith('sqlite_') or table_name == 'personal_records':
            print(f"  Skipping {table_name}")
            continue

        # Try to update records - if it fails, the column doesn't exist
        try:
            # Try updating both record and player
            db.execute(f"UPDATE {table_name} SET record = 0, player = 'NaN'")
            tables_with_records.append(table_name)
            print(f"✓ Reset records in {table_name} (with player)")
        except:
            # If that fails, try just record
            try:
                db.execute(f"UPDATE {table_name} SET record = 0")
                tables_with_records.append(table_name)
                print(f"✓ Reset records in {table_name} (no player column)")
            except:
                # No record column
                print(f"  No 'record' column found")

    print()
    # Clear all personal records
    try:
        result = db.execute("DELETE FROM personal_records")
        print(f"✓ Cleared all personal records")
    except Exception as e:
        print(f"✗ Error clearing personal records: {e}")

    print("=" * 50)
    print(f"All records have been reset!")
    print(f"\nTables processed: {len(tables_with_records)}")
    for table in tables_with_records:
        print(f"  - {table}")
    print("\nWhat was reset:")
    print("  - All tables with 'record' column: record = 0, player = 'NaN'")
    print("  - personal_records table: completely cleared")

else:
    print('Set value to true')
    exit(1)