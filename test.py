import csv
import json
import random
import requests

def song(csvFile):
    with open(csvFile,'r') as csvFile:
        reader = csv.reader(csvFile)
        songlist = list(reader)
        song = random.choice(songlist)

    ID = song[0]

    url = f"https://itunes.apple.com/us/lookup?id={ID}"
    response = requests.get(url)
    response.raise_for_status()
    res = response.json()['results']
    if res == []:
        url = f"https://itunes.apple.com/nl/lookup?id={ID}"
        response = requests.get(url)
        response.raise_for_status()
        res = response.json()['results']

    Data = res[0]
    TrackData = []
    TrackData.append(Data['artistName'])
    TrackData.append(Data['trackName'])

    if len(song) == 2:
        TrackData.append(song[1])
    else:
        TrackData.append(Data['previewUrl'])

    TrackData.append(Data['artworkUrl60'])
    TrackData.append(ID)

    return TrackData

for i in range(2):
    print(i)