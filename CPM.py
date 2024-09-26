import csv
import requests
import time
from cs50 import SQL
import time
import re
import math

db = SQL("sqlite:///playing_songs.db")

room_name = 'Short'

Database = db.execute("SELECT * FROM " + room_name + " ORDER BY record=0, record")


abbreviations = {
    'bfmv': 'bullet for my valentine',
    'brmc': 'black rebel motorcycle club',
    'ccr': 'creedence clearwater revival',
    'elo': 'electric light orchestra',
    'fgth': 'frankie goes to hollywood',
    'jsbx': 'jon spencer blues explosion',
    'mcr': 'my chemical romance',
    'nkotb': 'new kids on the block',
    'omd': 'orchestral manoeuvres in the dark',
    'pusa': 'presidents of the united states of america',
    'qotsa': 'queens of the stone age',
    'ratm': 'rage against the machine',
    'rhcp': 'red hot chili peppers',
    'soad': 'system of a down',
    'stp': 'stone temple pilots'
}



def extract_artists(title, artist):
    # Important to first set the title and artist to lowercase
    title = title.lower()
    artist = artist.lower()

    # To not allow any inconvenience to happen replace all square brackets in the title with round ones
    title = title.replace("[", "(").replace("]", ")")

    # Make a set that will contain every possible artist to guess
    artists = set()

    # First extract the featurings from the artists this is the part between brackets
    # TODO: In case it is possible that an artist can have multiple brackets (which I think isn't possible) reflection is needed
    if "(" in title and ")" in title:
        between_brackets_ = re.findall(r'\(([^)]+)\)', title)

        for between_brackets in between_brackets_:
            # If there is feat. in the first six positions it means that featurings exist
            if between_brackets.startswith('feat. '):
                between_brackets = between_brackets[6:]

                # Replace the and (&, +) signs for commas so we can perform split only on commas
                between_brackets = between_brackets.replace(" & ", ", ").replace(" + ", ", ")

                # Perform the split so we now found all artists that feature
                for element in between_brackets.split(", "):
                    artists.add(element)

    # Now we will perform the same operation with the artist part
    artist = artist.replace(" & ", ", ").replace(" + ", ", ")

    # Perform the split on the artists
    for element in artist.split(", "):
        artists.add(element)

    # Perform operations on each individual artist
    processed_artists = set()
    for element in artists:
        if element in abbreviations.values():
            element = list(abbreviations.keys())[list(abbreviations.values()).index(element)]
        if element.startswith('the '):
            element = element[4:]
        element = element.replace(".", "").replace("-", "")
        processed_artists.add(element)

    return processed_artists


def extract_titles(title):
    # Important to convert the entire title to lowercase
    title = title.lower()

    # Make a set that will contain every possibility to guess the title
    titles = set()
    titles.add(title)

    # This section also makes the full title without typing any brackets guessable
    title_no_brackets = re.sub(r'[\[\]\(\)]', '', title)
    titles.add(title_no_brackets)

    # Extract all that is not between the brackets and add it to the set
    shortest_title = re.sub(r'\s*(?:\[[^\]]*\]|\([^)]*\))\s*', '', title)
    titles.add(shortest_title)

    processed_titles = set()
    for element in titles:
        element = element.replace(".", "").replace("-", "").replace(",", "")
        processed_titles.add(element)
        if " & " in element:
            element = element.replace(" & ", " and ")
        if " + " in element:
            element = element.replace(" + ", " and ")
        processed_titles.add(element)

    return processed_titles

def shortest_string(strings):
    return min(strings, key=len)


def calculate_threshold(title_length):
    return round(math.log(title_length))

def calculate_cpm(number_of_chars, time_in_seconds):
    if time_in_seconds == 0:
        return 0
    return (number_of_chars / (time_in_seconds - 0.6)) * 60

DICT = dict()

for i in Database:

    len_artist = len(shortest_string(extract_artists(i['title'], i['artist'])))
    len_title = len(shortest_string(extract_titles(i['title'])))

    title = len_title - calculate_threshold(len_title)
    artist = len_artist - calculate_threshold(len_artist)

    total_len = title+artist

    DICT[i['artist'], i['title']] = calculate_cpm(total_len,i['record'])

def sort_dict_by_keys(d):
    return {k: v for k, v in sorted(d.items(), key=lambda item: item[1], reverse = True)}

count = 0

sorted_dict = sort_dict_by_keys(DICT)
for k,v in sorted_dict.items():
    count+=1
    if count < 50:
        if v != 0:
            print(k, v)
