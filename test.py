from cs50 import SQL

import math, re, time, random, string, json, os
from unidecode import unidecode

from collections import Counter

db = SQL("sqlite:///playing_songs.db")


from guess_validator import extract_artists, extract_titles, ABBREVIATIONS


with open('years.txt', 'w') as year_file:
    all_songs = db.execute("SELECT * FROM Short")

    for song in all_songs:
        artist = song['artist']
        title = song['title']

        artist_variations = extract_artists(title, artist)
        title_variations = extract_titles(title, 'Short')

        
        shortest_artist = min(artist_variations, key=len) if artist_variations else ""
        if shortest_artist in ABBREVIATIONS:
            threshold_artist = 0
        else:
            threshold_artist = round(math.log(len(shortest_artist))) if len(shortest_artist) > 1 else 0

        shortest_title = min(title_variations, key=len) if title_variations else ""
        threshold_title = round(math.log(len(shortest_title))) if len(shortest_title) > 1 else 0

        if shortest_artist == "":
            shortest_artist = "?"

        total = len(shortest_title)-threshold_title + len(shortest_artist)-threshold_artist + 1

        required_time = round(1+total*0.1, 1)

        year_file.write(f"{required_time}\n")




# db.execute("UPDATE Short SET record = 0")

# db.execute("DELETE FROM personal_records WHERE room = 'Short'")



# with open("songs.txt", "w", encoding="utf-8") as f:
#     for i in all_songs:
#         f.write(f"{i['artist']} - {i['title']}, {i['ID']}\n")

# db.execute("DELETE FROM messages WHERE id IN (SELECT id FROM messages ORDER BY id DESC LIMIT 2);")
        
# db.execute("DELETE FROM Short WHERE title = 'xxx'")



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

# with open("songs.txt", "w", encoding="utf-8") as f:
#     data = db.execute("SELECT * from Short")
#     for i in data:
    
#         f.write(f"{i['artist']} - {i['title']}: {i['ID']}\n")

# for i in ['Short', 'Short', 'Short']:

#     data = db.execute(f'SELECT * FROM {i}')

#     for song in data:
#         db.execute("""
#             INSERT INTO personal_records (artist, title, record, player, room)
#             VALUES (?, ?, ?, ?, ?)
#         """, song['artist'], song['title'], song['record'], song['player'], song['room'])