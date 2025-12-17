import csv
import requests
import time
from cs50 import SQL
import time
from flask_socketio import SocketIO, send

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
        TrackData.append(Data['artistName'])
        TrackData.append(Data['trackName'])

        if len(Id) == 0:
            TrackData.append(Id[1])
        else:
            TrackData.append(Data['previewUrl'])

        TrackData.append(Data['artworkUrl60'])
        TrackData.append(ID)

        listoflist.append(TrackData)

    return listoflist

def lookups2(list_of_id):
    listoflist = []
    for Id in list_of_id:
        print(Id[0])
        song = db.execute("SELECT * FROM DutchSongs WHERE id = " + Id[0])
        song = song[0]
        TrackData = []
        TrackData.append(song['artist'])
        TrackData.append(song['title'])
        TrackData.append(song['preview'])
        TrackData.append(song['artwork'])
        TrackData.append(Id[0])

        listoflist.append(TrackData)
    return listoflist

# Start
#db.execute("DROP TABLE IF EXISTS users")
#db.execute('CREATE TABLE users (userID integer PRIMARY KEY, username text, password text, Score integer DEFAULT 0, Time float DEFAULT 0, Guess_Count integer DEFAULT 0, MGT float DEFAULT 0)')


rooms = ['Billion']
for room in rooms:
    #room not in ['DutchSongs', 'Billion', 'Short'] and db.execute(f'DROP TABLE IF EXISTS {room}')
    #db.execute('CREATE TABLE ' + room + ' (artist text, title text, preview text, artwork text, room text, record float DEFAULT 0.00, ID integer, player text DEFAULT NaN)')
    with open('TEMP' + '.csv','r') as csvFile:
        reader = csv.reader(csvFile)
        songlist = list(reader)
        IDs = [i for i in songlist]
        # IDs = IDs[XX:]

        DATA = lookups(IDs, room)
        #DATA = lookups2(IDs)


    for i in DATA:
        db.execute('INSERT into '+ room + '(artist, title, preview, artwork, room, ID) VALUES (:artist, :title, :preview, :artwork,  :room, :ID)',
        artist = i[0], title = i[1], preview = i[2], artwork = i[3], room = room, ID = i[4])

