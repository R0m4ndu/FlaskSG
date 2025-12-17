from cs50 import SQL

from collections import Counter

db = SQL("sqlite:///playing_songs.db")

db.execute("UPDATE Billion SET record = 0")

db.execute("DELETE FROM personal_records WHERE room = 'Billion'")



# with open("songs.txt", "w", encoding="utf-8") as f:
#     for i in all_songs:
#         f.write(f"{i['artist']} - {i['title']}, {i['ID']}\n")

# db.execute("DELETE FROM messages WHERE id IN (SELECT id FROM messages ORDER BY id DESC LIMIT 2);")
        
# db.execute("DELETE FROM DutchSongs WHERE artist = 'Mr Belt & Wezol'")



# db.execute("DROP TABLE IF EXISTS personal_records")
# db.execute("""
#     CREATE TABLE personal_records (
#         id INTEGER PRIMARY KEY AUTOINCREMENT,
#         artist TEXT,
#         title TEXT,
#         record REAL,
#         player TEXT,
#         room TEXT
#     )
# """)

# for i in ['Billion', 'DutchSongs', 'Short']:

#     data = db.execute(f'SELECT * FROM {i}')

#     for song in data:
#         db.execute("""
#             INSERT INTO personal_records (artist, title, record, player, room)
#             VALUES (?, ?, ?, ?, ?)
#         """, song['artist'], song['title'], song['record'], song['player'], song['room'])