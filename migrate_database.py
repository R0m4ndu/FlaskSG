# Database Migration Script
# Migrates from per-room tables to normalized structure:
# - Song_Info: central song data with global records
# - Room_Songs: links rooms to songs
# - personal_records: simplified without room dependency

from cs50 import SQL

db = SQL("sqlite:///playing_songs.db")

# Rooms to migrate
ROOMS = ['Billion', 'DutchSongs']

def migrate():
    print("Starting migration...")

    # Step 1: Create new tables
    print("\n1. Creating new tables...")

    db.execute("""
        CREATE TABLE IF NOT EXISTS Song_Info (
            song_id INTEGER PRIMARY KEY,
            artist TEXT,
            title TEXT,
            preview TEXT,
            artwork TEXT,
            year TEXT,
            record FLOAT DEFAULT 0.0,
            player TEXT DEFAULT 'NaN'
        )
    """)

    db.execute("""
        CREATE TABLE IF NOT EXISTS Room_Songs (
            room_name TEXT,
            song_id INTEGER,
            PRIMARY KEY (room_name, song_id),
            FOREIGN KEY (song_id) REFERENCES Song_Info(song_id)
        )
    """)

    print("   Tables created.")

    # Step 2: Migrate songs to Song_Info (handle duplicates - keep best record)
    print("\n2. Migrating songs to Song_Info...")

    songs_migrated = 0
    songs_updated = 0

    for room in ROOMS:
        print(f"   Processing {room}...")
        try:
            songs = db.execute(f"SELECT * FROM {room}")
            for song in songs:
                song_id = song['ID']

                # Check if song already exists in Song_Info
                existing = db.execute("SELECT * FROM Song_Info WHERE song_id = ?", song_id)

                if existing:
                    # Song exists - check if this record is better
                    old_record = existing[0]['record'] or 0
                    new_record = song['record'] or 0

                    if new_record > 0 and (old_record == 0 or new_record < old_record):
                        db.execute("""
                            UPDATE Song_Info
                            SET record = ?, player = ?
                            WHERE song_id = ?
                        """, new_record, song['player'], song_id)
                        songs_updated += 1
                else:
                    # Insert new song
                    year = song.get('year', None)
                    db.execute("""
                        INSERT INTO Song_Info (song_id, artist, title, preview, artwork, year, record, player)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                    """, song_id, song['artist'], song['title'], song['preview'],
                        song['artwork'], year, song['record'] or 0, song['player'] or 'NaN')
                    songs_migrated += 1

                # Add to Room_Songs (ignore if duplicate)
                try:
                    db.execute("""
                        INSERT INTO Room_Songs (room_name, song_id)
                        VALUES (?, ?)
                    """, room, song_id)
                except:
                    pass  # Already exists

        except Exception as e:
            print(f"   Error processing {room}: {e}")

    print(f"   Migrated {songs_migrated} unique songs, updated {songs_updated} records")

    # Step 3: Migrate personal_records (remove room dependency, keep best record per song)
    print("\n3. Migrating personal_records...")

    # Create new personal_records table
    db.execute("""
        CREATE TABLE IF NOT EXISTS personal_records_new (
            player TEXT,
            song_id INTEGER,
            record FLOAT,
            PRIMARY KEY (player, song_id),
            FOREIGN KEY (song_id) REFERENCES Song_Info(song_id)
        )
    """)

    # Get all existing personal records
    old_records = db.execute("SELECT * FROM personal_records")
    records_migrated = 0
    records_updated = 0

    for pr in old_records:
        player = pr['player']
        song_id = pr['song_ids']  # Note: old column name is song_ids
        record = pr['record']

        # Check if exists
        existing = db.execute("""
            SELECT * FROM personal_records_new
            WHERE player = ? AND song_id = ?
        """, player, song_id)

        if existing:
            # Keep better record
            if record < existing[0]['record']:
                db.execute("""
                    UPDATE personal_records_new
                    SET record = ?
                    WHERE player = ? AND song_id = ?
                """, record, player, song_id)
                records_updated += 1
        else:
            db.execute("""
                INSERT INTO personal_records_new (player, song_id, record)
                VALUES (?, ?, ?)
            """, player, song_id, record)
            records_migrated += 1

    print(f"   Migrated {records_migrated} records, updated {records_updated} duplicates")

    # Step 4: Rename tables
    print("\n4. Replacing old personal_records table...")
    db.execute("DROP TABLE IF EXISTS personal_records_old")
    db.execute("ALTER TABLE personal_records RENAME TO personal_records_old")
    db.execute("ALTER TABLE personal_records_new RENAME TO personal_records")

    print("\n=== Migration Complete ===")
    print(f"Song_Info: {db.execute('SELECT COUNT(*) as c FROM Song_Info')[0]['c']} songs")
    print(f"Room_Songs: {db.execute('SELECT COUNT(*) as c FROM Room_Songs')[0]['c']} room-song links")
    print(f"personal_records: {db.execute('SELECT COUNT(*) as c FROM personal_records')[0]['c']} records")

    # Show room counts
    print("\nSongs per room:")
    for room in ROOMS:
        count = db.execute("SELECT COUNT(*) as c FROM Room_Songs WHERE room_name = ?", room)[0]['c']
        print(f"  {room}: {count}")

if __name__ == "__main__":
    migrate()
