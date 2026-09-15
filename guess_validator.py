# SongGuesser Server-Side Guess Validation
#
# Ramon Duursma
#
# Validates player guesses on the server to prevent client-side cheating
# Ported from client-side JavaScript validation logic

import math
from unidecode import unidecode
import time


# Artist abbreviations dictionary
ABBREVIATIONS = {
    'bfmv': 'bullet for my valentine',
    'brmc': 'black rebel motorcycle club',
    'ccr': 'creedence clearwater revival',
    'elo': 'electric light orchestra',
    'fgth': 'frankie goes to hollywood',
    'jsbx': 'the jon spencer blues explosion',
    'mcr': 'my chemical romance',
    'nkotb': 'new kids on the block',
    'omd': 'orchestral manoeuvres in the dark',
    'pusa': 'the presidents of the united states of america',
    'qotsa': 'queens of the stone age',
    'ratm': 'rage against the machine',
    'rhcp': 'red hot chili peppers',
    'soad': 'system of a down',
    'stp': 'stone temple pilots',
    'atcq': 'a tribe called quest',
    'tdcc': 'two door cinema club',
    '5sos': '5 seconds of summer',
    'nbhd': 'the neighbourhood',
    'bto': 'bachman-turner overdrive',
    '30stm': 'thirty seconds to mars',
    'ffdp': 'five finger death punch',
    '5fdp': 'five finger death punch',
    'a7x': 'avenged sevenfold',
    'cas': 'cigarettes after sex',
    'patd': 'panic! at the disco',
    'p!atd': 'panic! at the disco',
    'top': 'twenty one pilots',
}


def extract_artists(title, artist):

    """
    Extract all valid artist variations from artist and title fields
    Returns a set of possible artist strings to match against
    """

    title = title.lower()
    artist = artist.lower()

    # Replace square brackets with round ones for consistency
    title = title.replace('[', '(').replace(']', ')')

    artists = set()

    # Extract featured artists from title (in brackets)
    if '(' in title and ')' in title:
        import re
        between_brackets_list = re.findall(r'\(([^)]+)\)', title)

        for between_brackets in between_brackets_list:
            # Check if it's a featuring
            if between_brackets.startswith('feat. '):
                between_brackets = between_brackets[6:]  # Remove 'feat. '

                # Replace & and + with commas
                between_brackets = between_brackets.replace(' & ', ', ').replace(' + ', ', ')

                # Split by commas and add each artist
                for feat_artist in between_brackets.split(', '):
                    artists.add(feat_artist.strip())

    # Extract main artists (handle & and + separators)
    artist = artist.replace(' & ', ', ').replace(' + ', ', ')

    for a in artist.split(', '):
        artists.add(a.strip())

    # Process each artist to add variations
    artists_copy = list(artists)
    for element in artists_copy:
        # Add abbreviation if artist is in abbreviations
        for abbr, full_name in ABBREVIATIONS.items():
            if element == full_name:
                artists.add(abbr)

        # Remove "the " prefix
        if element.startswith('the '):
            without_the = element[4:]
            artists.add(without_the)
            artists.add(unidecode(without_the))
            
            # Also remove special characters from the version without "the"
            cleaned_without_the = without_the
            for char in ['.', '-', "'", '!', '?']:
                cleaned_without_the = cleaned_without_the.replace(char, '')
            if cleaned_without_the != without_the:
                artists.add(cleaned_without_the)
                artists.add(unidecode(cleaned_without_the))

        # Remove special characters
        cleaned = element
        for char in ['.', '-', "'", '!', '?']:
            cleaned = cleaned.replace(char, '')
        if cleaned != element:
            artists.add(cleaned)

    artists.update(unidecode(s) for s in artists.copy())

    if 'the jimi hendrix experience' in artists:
        artists.add('jimi hendrix')

    print(artists)

    return artists


def extract_titles(title, room):
    """
    Extract all valid title variations
    Returns a set of possible title strings to match against
    """
    title = title.lower()
    titles = set()
    titles.add(title)

    # Title without any brackets
    title_no_brackets = title
    for char in ['[', ']', '(', ')']:
        title_no_brackets = title_no_brackets.replace(char, '')
    titles.add(title_no_brackets.strip())

    # Title without content inside brackets
    import re
    shortest_title = re.sub(r'\s*(?:\[[^\]]*\]|\([^)]*\))\s*', '', title)
    titles.add(shortest_title.strip())

    # Process each title to add variations
    titles_copy = list(titles)
    for element in titles_copy:
        cleaned = element
        # Remove special characters
        for char in ['.', '-', ',', "'", '!', '?']:
            cleaned = cleaned.replace(char, '')
        if cleaned != element:
            titles.add(cleaned.strip())

        # Replace & and + with "and"
        if ' & ' in element:
            titles.add(element.replace(' & ', ' and '))
        if ' + ' in element:
            titles.add(element.replace(' + ', ' and '))

        # For Dutch songs, also replace & with "en"
        if room == 'DutchSongs' and ' & ' in element:
            titles.add(element.replace(' & ', ' en '))

    # Remove empty strings
    titles = {t for t in titles if t.strip()}

    titles.update(unidecode(s) for s in titles.copy())

    return titles


def levenshtein_distance(str1, str2):
    """
    Calculate the Levenshtein distance between two strings
    Returns the minimum number of single-character edits needed
    """
    track = [[0] * (len(str1) + 1) for _ in range(len(str2) + 1)]

    for i in range(len(str1) + 1):
        track[0][i] = i

    for j in range(len(str2) + 1):
        track[j][0] = j

    for j in range(1, len(str2) + 1):
        for i in range(1, len(str1) + 1):
            indicator = 0 if str1[i - 1] == str2[j - 1] else 1
            track[j][i] = min(
                track[j][i - 1] + 1,  # deletion
                track[j - 1][i] + 1,  # insertion
                track[j - 1][i - 1] + indicator  # substitution
            )

    return track[len(str2)][len(str1)]


def validate_guess(guess, artist, title, room):
    """
    Validate a player's guess against the song's artist and title

    Args:
        guess (str): The player's guess (lowercase)
        artist (str): The correct artist name
        title (str): The correct title
        room (str): The room name (for Dutch-specific rules)

    Returns:
        dict: {'artist': bool, 'title': bool} indicating what was guessed correctly
    """
    ABBR = False

    guess = guess.lower().strip()

    artists = extract_artists(title, artist)
    titles = extract_titles(title, room)


    artist_match = False
    title_match = False

    # Check artist match
    for a in artists:
        if not a:
            continue
        threshold = round(math.log(len(a))) if len(a) > 1 else 0
        distance = levenshtein_distance(guess, a)

        # Abbreviations require exact match
        if a in ABBREVIATIONS:
            if distance == 0:
                ABBR = True
                artist_match = True
                break
        else:
            if distance <= threshold:
                artist_match = True
                break

    shortest_artist = min(artists, key=len) if artists else ""
    if shortest_artist in ABBREVIATIONS:
        threshold_artist = 0
    else:
        threshold_artist = round(math.log(len(shortest_artist))) if len(shortest_artist) > 1 else 0

    shortest_title = min(titles, key=len) if titles else ""
    threshold_title = round(math.log(len(shortest_title))) if len(shortest_title) > 1 else 0

    total = len(shortest_title)-threshold_title + len(shortest_artist)-threshold_artist + 1

    required_time = round(1+total*0.1, 1)

    for t in titles:
        if not t:
            continue
        threshold = round(math.log(len(t))) if len(t) > 1 else 0
        distance = levenshtein_distance(guess, t)

        if distance <= threshold:
            title_match = True
            break

    return {'artist': artist_match, 'title': title_match}
