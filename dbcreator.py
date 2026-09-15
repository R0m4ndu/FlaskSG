import csv
import requests
import time
from cs50 import SQL
import time
import math
from flask_socketio import SocketIO, send
from guess_validator import extract_artists, extract_titles, ABBREVIATIONS

db = SQL("sqlite:///playing_songs.db")

def lookups(listofid, room):
    listoflist = []
    count = 0
    for Id in listofid:
        time.sleep(0.5)
        print('hallo')
        count+=1

        print(count)

        ID = Id[0]

        url = f"https://itunes.apple.com/nl/lookup?id={ID}"
        response = requests.get(url)
        response.raise_for_status()
        res = response.json()['results']
        if res == []:
            url = f"https://itunes.apple.com/us/lookup?id={ID}"
            response = requests.get(url)
            response.raise_for_status()
            res = response.json()['results']

        Data = res[0]
        TrackData = []
        artist = Data['artistName']
        title = Data['trackName']
        TrackData.append(artist)
        TrackData.append(title)

        if len(Id) == 0:
            TrackData.append(Id[1])
        else:
            TrackData.append(Data['previewUrl'])

        TrackData.append(Data['artworkUrl60'])


        TrackData.append(ID)

        release_date = Data.get('releaseDate', '')
        year = release_date[:4] if release_date else 'Unknown'

        TrackData.append(year)

        artist_variations = extract_artists(title, artist)
        title_variations = extract_titles(title, 'ShortRock')

        
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

        TrackData.append(required_time)

        listoflist.append(TrackData)

    return listoflist

def lookups2(list_of_id):

    listoflist = []
    for Id in list_of_id:
        print(Id)
        song = db.execute("SELECT * FROM Rock WHERE id = ?", Id)
        song = song[0]
        TrackData = []
        TrackData.append(song['artist'])
        TrackData.append(song['title'])
        TrackData.append(song['preview'])
        TrackData.append(song['artwork'])
        TrackData.append(Id)
        TrackData.append(song['year'])
        TrackData.append(song['required_time'])

        listoflist.append(TrackData)
    return listoflist

# Start
#db.execute("DROP TABLE IF EXISTS users")
#db.execute('CREATE TABLE users (userID integer PRIMARY KEY, username text, password text, Score integer DEFAULT 0, Time float DEFAULT 0, Guess_Count integer DEFAULT 0, MGT float DEFAULT 0)')


rooms = ['Billion']
for room in rooms:
    #room not in ['DutchSongs', 'Billion', 'Short', 'Rock'] and db.execute(f'DROP TABLE IF EXISTS {room}')
    #db.execute('CREATE TABLE ' + room + ' (artist text, title text, preview text, artwork text, room text, record float DEFAULT 0.00, ID integer, player text DEFAULT NaN, year integer)')
    with open('TEMP' + '.csv','r') as csvFile:
        reader = csv.reader(csvFile)
        songlist = list(reader)
        IDs = [i for i in songlist]
        # IDs = IDs[XX:]

        DATA = lookups(IDs, room)
        #DATA = lookups2(IDs)


    for i in DATA:
        db.execute('INSERT into '+ room + '(artist, title, preview, artwork, room, ID, year, min_time) VALUES (:artist, :title, :preview, :artwork,  :room, :ID, :year, :min_time)',
        artist = i[0], title = i[1], preview = i[2], artwork = i[3], room = room, ID = i[4], year = i[5], min_time = i[6])

