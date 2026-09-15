"""
Script to add a 'year' column to the Short table and populate it with years from years.txt
"""
from cs50 import SQL

# Connect to database
db = SQL("sqlite:///playing_songs.db")

# Read years from years.txt
with open('years.txt', 'r') as f:
    years = [line.strip() for line in f.readlines()]

print(f"Loaded {len(years)} years from years.txt")

# Add the year column to the Short table if it doesn't exist
try:
    db.execute("ALTER TABLE Short ADD COLUMN min_time TEXT")
    print("Added 'min_time' column to Short table")
except Exception as e:
    print(f"Column might already exist or error occurred: {e}")

# Get all songs from Short table ordered by rowid (to maintain order)
songs = db.execute("SELECT rowid, ID FROM Short ORDER BY rowid")
print(f"Found {len(songs)} songs in Short table")

# Update each song with the corresponding year
updated_count = 0
for i, song in enumerate(songs):
    if i < len(years):
        rowid = song['rowid']
        year = years[i]
        db.execute("UPDATE Short SET min_time = ? WHERE rowid = ?", year, rowid)
        updated_count += 1
    else:
        print(f"Warning: No year available for song at index {i}")

print(f"Updated {updated_count} songs with years")
print("Done!")
