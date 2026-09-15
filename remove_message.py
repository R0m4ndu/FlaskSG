from cs50 import SQL

import math, re, time, random, string, json, os
from unidecode import unidecode

from collections import Counter

db = SQL("sqlite:///playing_songs.db")


db.execute("""
    DELETE FROM messages
    WHERE id = (SELECT MAX(id) FROM messages)
""")