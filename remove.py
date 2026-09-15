from cs50 import SQL
db = SQL("sqlite:///playing_songs.db")

db.execute("DELETE FROM ShortRock WHERE title = 'I Want It All (Single Version)' AND artist = 'Queen'")