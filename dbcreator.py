import csv
import requests
import time
from cs50 import SQL
import time

db = SQL("sqlite:///playing_songs.db")

def lookups(listofid, room):
    listoflist = []
    count = 0
    for Id in listofid:
        time.sleep(1)
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

# Start
#db.execute("DROP TABLE IF EXISTS users")
#db.execute('CREATE TABLE users (userID integer PRIMARY KEY, username text, password text, Score integer DEFAULT 0, Time float DEFAULT 0, Guess_Count integer DEFAULT 0, MGT float DEFAULT 0)')


rooms = ['DutchSongs']
for room in rooms:
    # db.execute('DROP TABLE IF EXISTS ' + room)
    # db.execute('CREATE TABLE ' + room + ' (artist text, title text, preview text, artwork text, room text, record float DEFAULT 0.00, ID integer, player text DEFAULT NaN)')
    with open(room + '.csv','r') as csvFile:
        reader = csv.reader(csvFile)
        songlist = list(reader)
        IDs = [i for i in songlist]
        IDs = IDs[805:]

        DATA = lookups(IDs,room)


    for i in DATA:
        db.execute('INSERT into '+ room + '(artist, title, preview, artwork, room, ID) VALUES (:artist, :title, :preview, :artwork,  :room, :ID)',
        artist = i[0], title = i[1], preview = i[2], artwork = i[3], room = room, ID = i[4])



