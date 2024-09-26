# SongGuesser
#
# Ramon Duursma
#
# high speed version of a song guessing game in which you can guess the songs.

import csv
import json
import random
from flask_session import Session
import os
import requests
import urllib.parse
from werkzeug.security import check_password_hash, generate_password_hash
from flask import Flask, redirect, render_template, request, session
from cs50 import SQL

app = Flask(__name__, template_folder='template')

# Configure session to use filesystem (instead of signed cookies)
app.secret_key = 'TODO: CHANGE ONE DAY'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

db = SQL("sqlite:///playing_songs.db")


@app.route('/')
def main():

    global all_rooms
    all_rooms = ['Short', 'DutchSongs', 'challenge']

    global active_room
    active_room = 'NONE'

    global username

    db.execute("DROP TABLE IF EXISTS active_game")
    db.execute("CREATE TABLE IF NOT EXISTS active_game (artist TEXT, title TEXT, imageUrl text)")

    images = []
    images2 = []
    for room in all_rooms:
        img = db.execute("SELECT artwork FROM " + room + " ORDER BY RANDOM () LIMIT 1")
        images2.append(img)

    for i in images2:
        for ele in i:
            I = ele['artwork']
            I = I.replace('60x60', '1000x1000')
            images.append(I)

    length_images = len(images)


    if not session.get("userID") is None:
        # global makes it so the var can be used anywhere

        global userID
        userID = session["userID"]
        # db.execute uses the db with a SQL command
        user = db.execute("SELECT username FROM users WHERE userID = ?", userID)
        for x in user:
            username = x['username']


    else:
        username = "guest"

    return render_template("home.html", username = username, rooms = all_rooms, images = images, length_images = length_images)

@app.route("/register")
def register():
    return render_template("register.html", username = username, rooms = all_rooms)

@app.route("/reg", methods=["GET", "POST"])
def reg():

    if request.method == "POST":

        apology = ""

        username = request.form.get("username")
        if len(username) == 0:
            apology = "Please fill in your username!"

        userExists = db.execute("SELECT username FROM users WHERE username = ?", username)

        if len(userExists) > 0:
            apology = "Username already exists!"

        password = request.form.get("password")
        confirmation = request.form.get("confirmation")

        # long enough
        if len(password) < 3 or len(confirmation) < 3:
            apology = "Password needs to be at 3 least characters long!"

        if len(password) > 20 or len(confirmation) > 20:
            apology = "Password needs to be under 20 characters"

        if password != confirmation:
            apology = "Passwords do not match!"

        if apology == "":
            password_hash = generate_password_hash(password)
            db.execute("INSERT INTO users (username, password) VALUES(?, ?)", username, password_hash)
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
            session["userID"] = rows[0]["userID"]
            return redirect("/")

        else:
            # needs to return guest since session was lost
            return render_template("register.html", apology = apology, username = 'guest', rooms = all_rooms)

    else:
        return redirect('/')

@app.route("/login")
def login():
    return render_template("login.html", username = username, rooms = all_rooms)

@app.route("/log", methods=["GET", "POST"])
def log():

    session.clear()

    if request.method == "POST":

        apology = ""

        username = request.form.get("username")
        if len(username) == 0:
            apology = "Please fill in your username!"

        # long enough
        if len(request.form.get("password")) < 3:
            apology = "Password needs to be at 3 least characters long!"

        if len(request.form.get("password")) > 20:
            apology = "Password needs to be under 20 characters"

        rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))

        if apology == "":
            if not check_password_hash(rows[0]["password"], request.form.get("password")):
                if apology == "":
                    apology = "Please fill in your correct password!"


        if apology == "":
            rows = db.execute("SELECT * FROM users WHERE username = ?", request.form.get("username"))
            session["userID"] = rows[0]["userID"]
            return redirect("/")

        else:
            # needs to return guest since session was lost
            return render_template("login.html", apology = apology, username = 'guest', rooms = all_rooms)

    else:
        return redirect('/')

@app.route("/logout")
def logout():
    """Log user out"""

    global username
    username = 'guest'
    session.clear()

    # Redirect user to main page
    return redirect("/")

@app.route("/room/<room_name>")
def room(room_name):

    global active_room

    rounds = 10

    if room_name != active_room:
        active_room = room_name
        db.execute("DROP TABLE IF EXISTS active_game")

    TrackData = db.execute('SELECT * from ' + active_room + ' ORDER BY RANDOM() LIMIT 1')
    TrackData = TrackData[0]

    rec = db.execute("SELECT record, player FROM " + room_name + " WHERE ID = ?", TrackData['ID'])
    record = rec[0]


    db.execute("CREATE TABLE IF NOT EXISTS active_game (artist TEXT, title TEXT, imageUrl text, record float, player text, ID integer)")
    db.execute("INSERT INTO active_game (artist, title, imageUrl, record, player, ID) VALUES (:artist, :title, :imageUrl, :record, :player, :ID)",
    artist = TrackData['artist'], title = TrackData['title'], imageUrl = TrackData['artwork'], record = record['record'], player = record['player'], ID = TrackData['ID'])

    x = db.execute("SELECT COUNT (*) FROM active_game")
    count = list(x[0].values())[0]

    if count == rounds+1:
        db.execute("DROP TABLE IF EXISTS active_game")
        return redirect('/room/'+active_room)

    database = db.execute("select * from active_game")

    last_played = list(reversed(database))[0]

    return render_template("room.html", artist = str(TrackData['artist']), title = str(TrackData['title']), preview = TrackData['preview'], image = TrackData['artwork'],
    rounds = rounds, database = list(reversed(database))[1:], count = count, last_played = last_played, username = username, ID = TrackData['ID'], room = active_room, rooms = all_rooms)

@app.route('/data', methods = ['POST'])
def data_handler():
    output = request.get_json()
    result = json.loads(output)
    guessTime = float(result['guessTime'])
    username = result['username']
    ID = result['id']

    global active_room
    room = active_room

    row = db.execute("SELECT * FROM " + room + " WHERE ID = ?", ID)
    record = row[0]['record']
    new_record = ''

    if record == 0:
        new_record = guessTime

    if guessTime < record:
        new_record = guessTime

    if new_record != '':
        if username != "guest":
            db.execute("UPDATE " + room + " SET record = " + str(new_record) + ", player = '" + username + "' WHERE ID = " + ID)
            db.execute("UPDATE active_game SET record = " + str(new_record) + ", player = '" + username + "' WHERE ID = " + ID)

    return ''

@app.route('/account', methods = ['POST'])
def account():
    output = request.get_json()
    result = json.loads(output)
    score = int(result['score'])
    guessTime = float(result['guessTime'])

    rows = db.execute("SELECT * FROM users WHERE username = ?", username)
    user_score = rows[0]['Score']
    GC = rows[0]['Guess_Count']
    Time = rows[0]['Time']

    if GC != 0:
        MGT = round(Time/GC, 2)
    else:
        MGT = 0

    if score == 6:
        GC += 1
        Time+=guessTime

    user_score += score

    db.execute("UPDATE users SET Score = " + str(user_score) + ", Guess_Count = " + str(GC) + ",Time = " + str(Time) + ",MGT = " + str(MGT) + " WHERE username = '" + username+"'")

    return ''

@app.route('/profile/<user>')
def profile(user):

    Database = db.execute("SELECT * FROM users WHERE username = ?", user)
    if Database != []:
        return render_template("profile.html", Database = Database[0], rooms = all_rooms, username = username)
    else:
        return redirect("/")


@app.route('/records/<room_name>')
def records(room_name):
    global all_rooms

    Database = db.execute("SELECT * FROM " + room_name + " ORDER BY record=0, record")
    return render_template("records.html", Database = Database, rooms = all_rooms, username = username)


@app.route('/leaderboards/<stat>')
def leaderboards(stat):

    if stat == "MGT":
        Database = db.execute("SELECT * FROM users ORDER BY mgt ASC")

    else:
        Database = db.execute("SELECT * FROM users ORDER BY Score DESC")
    return render_template("leaderboards.html", Database = Database, username = username, stat = stat, rooms = all_rooms)

@app.route('/edit/<room_name>', methods = ['GET','POST'])
def edit(room_name):

    if request.method == "POST":
        change = False

        song_id = request.form.get('song_id')

        if int(song_id) == 0:
            if username != "Romandu":
                return render_template("/")

            else:
                Database = db.execute("SELECT * FROM " + room_name)
                return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)

        else:
            if username != "Romandu":
                return render_template("/")

            else:

                edit_song = db.execute("SELECT * FROM " + room_name + " WHERE ID = ?", song_id)

                for i in ['artist', 'title', 'preview', 'artwork']:
                    if request.form.get(i) != edit_song[0][i]:
                        change=True
                        db.execute("UPDATE " + room_name + " SET " + i + " = '" + request.form.get(i) + "' WHERE ID = " + song_id)

                Database = db.execute("SELECT * FROM " + room_name)

                if change == True:
                    return redirect('/edit/' + room_name)

                Database = db.execute("SELECT * FROM " + room_name)
                return render_template("edit.html", Database = Database, song_id = song_id, room_name = room_name, edit_song = edit_song[0], username = username)
    else:

        Database = db.execute("SELECT * FROM " + room_name)
        return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)
