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
import math
import time
import threading

from pyngrok import ngrok

from flask_socketio import SocketIO, send, emit, join_room, leave_room

# Import multiplayer game management
from game_session import GameRoomManager, PlayerState
from guess_validator import validate_guess
from config import ROUNDS_PER_GAME, SONG_DURATION, DELAY_BETWEEN_ROUNDS

# public_url = ngrok.connect(5000)
# print(" * ngrok tunnel:", public_url)

app = Flask(__name__, template_folder='template')
socketio = SocketIO(app)

# Configure session to use filesystem (instead of signed cookies)
app.secret_key = 'TODO: CHANGE ONE DAY'
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

db = SQL("sqlite:///playing_songs.db")

db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, room TEXT)")

global all_rooms
all_rooms = ['Billion', 'DutchSongs', 'Short', 'Taylor']

# Initialize multiplayer game manager
game_manager = GameRoomManager()

# Listen for messages sent from the client
@socketio.on('message')
def handle_message(message):
    print(message)
    message, room = message.rsplit('_', 1)
    print(f"Received message: {message}")
    db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)", message.split(': ')[0], message.split(': ')[1], room)

    send(message, room=f"game_{room}")  # Broadcast the message only to users in this room


# ============================================================================
# MULTIPLAYER GAME SOCKETIO EVENTS
# ============================================================================

@socketio.on('join_game')
def handle_join_game(data):
    """Player joins a game room"""
    room_name = data.get('room_name')
    username = session.get('username', 'guest')

    if not room_name or room_name not in all_rooms:
        emit('error', {'message': 'Invalid room'})
        return

    print(f"Player {username} joining room {room_name}")

    # Check if player is in a different room and remove them from it
    previous_room = session.get('current_game_room')
    if previous_room and previous_room != room_name:
        prev_game_room = game_manager.get_room(previous_room)
        if prev_game_room and username in prev_game_room.players:
            del prev_game_room.players[username]
            print(f"Removed {username} from previous room {previous_room}")

            # Leave previous SocketIO room
            leave_room(f"game_{previous_room}")

            # Send leave message to previous room
            leave_message = f"System: {username} left the room"
            send(leave_message, room=f"game_{previous_room}")
            db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)",
                      "System", f"{username} left the room", previous_room)

            # Broadcast updated leaderboard to previous room
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(prev_game_room)
            }, room=f"game_{previous_room}")

    # Get or create game room
    game_room = game_manager.get_or_create_room(room_name)

    # Add player to room
    game_room.add_player(username)

    # Join SocketIO room
    join_room(f"game_{room_name}")

    # Track current room in session
    session['current_game_room'] = room_name

    # Send join message to chat
    join_message = f"System: {username} joined the room"
    send(join_message, room=f"game_{room_name}")

    # Also save to database
    db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)", "System", f"{username} joined the room", room_name)

    # Send current game state to joining player
    emit('game_state', {
        'round': game_room.get_current_round_in_cycle(),
        'game_state': game_room.game_state,
        'leaderboard': get_leaderboard(game_room),
        'time_remaining': get_time_remaining(game_room),
        'played_songs': game_room.played_songs
    })

    # Broadcast updated leaderboard to all other players in the room
    emit('leaderboard_update', {
        'leaderboard': get_leaderboard(game_room)
    }, room=f"game_{room_name}", include_self=False)

    # Start game if room is waiting (only start if truly waiting, not if round is active)
    if game_room.game_state == 'waiting' and game_room.has_connected_players():
        # Use threading to avoid blocking
        print(f"Starting first round in {room_name} after player {username} joined")
        threading.Timer(1.0, start_new_round, args=[room_name]).start()


@socketio.on('disconnect')
def handle_disconnect():
    """Handle socket disconnection - remove player from all rooms"""
    username = session.get('username', 'guest')

    # Check all rooms to see if this player is in any of them
    for room_name, game_room in list(game_manager.rooms.items()):
        if username in game_room.players:
            # Remove player from the game
            del game_room.players[username]
            print(f"Removed disconnected player {username} from {room_name}")

            # Send leave message to chat
            leave_message = f"System: {username} left the room"
            send(leave_message, room=f"game_{room_name}")

            # Save to database
            db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)",
                      "System", f"{username} left the room", room_name)

            # Broadcast updated leaderboard to remaining players
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(game_room)
            }, room=f"game_{room_name}")

            # Clean up if no players left
            if not game_room.has_connected_players():
                game_manager.cleanup_empty_rooms()
                print(f"Room {room_name} cleaned up - no players left")


@socketio.on('leave_game')
def handle_leave_game(data):
    """Player explicitly leaves game room"""
    room_name = data.get('room_name')
    username = session.get('username', 'guest')

    game_room = game_manager.get_room(room_name)
    if not game_room:
        return

    # Remove player completely from the game
    if username in game_room.players:
        del game_room.players[username]
        print(f"Removed player {username} from {room_name}")

    leave_room(f"game_{room_name}")

    # Send leave message to chat
    leave_message = f"System: {username} left the room"
    send(leave_message, room=f"game_{room_name}")

    # Save to database
    db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)",
               "System", f"{username} left the room", room_name)

    # Broadcast updated leaderboard to remaining players
    emit('leaderboard_update', {
        'leaderboard': get_leaderboard(game_room)
    }, room=f"game_{room_name}")

    # Clean up if no players left
    if not game_room.has_connected_players():
        game_manager.cleanup_empty_rooms()
        print(f"Room {room_name} cleaned up - no players left")


@socketio.on('submit_guess')
def handle_submit_guess(data):
    """Player submits a guess"""
    room_name = data.get('room_name')
    guess = data.get('guess', '').strip().lower()
    username = session.get('username', 'guest')

    if not guess:
        return

    game_room = game_manager.get_room(room_name)
    if not game_room or game_room.game_state != 'round_active':
        return

    # Calculate server-side time
    elapsed = time.time() - game_room.round_start_time
    if elapsed > SONG_DURATION:
        return  # Too late

    # Check if already guessed both
    if username in game_room.round_guesses:
        prev = game_room.round_guesses[username]
        if prev.get('artist') and prev.get('title'):
            return  # Already completed

    # Validate guess
    song = game_room.current_song
    result = validate_guess(guess, song['artist'], song['title'], room_name)

    # Initialize or update player's guess record
    if username not in game_room.round_guesses:
        game_room.round_guesses[username] = {
            'artist': False,
            'title': False,
            'time': None,
            'completion_order': None,
            'partial_scored': False
        }

    player_guess = game_room.round_guesses[username]

    # Update what they guessed
    if result['artist']:
        player_guess['artist'] = True
    if result['title']:
        player_guess['title'] = True

    # Check if both now complete
    if player_guess['artist'] and player_guess['title'] and player_guess['time'] is None:
        player_guess['time'] = round(elapsed, 2)

        # Determine completion order (1st, 2nd, 3rd, 4th+)
        completed = [g for g in game_room.round_guesses.values() if g['time'] is not None]
        player_guess['completion_order'] = len(completed)

        # Calculate score based on order: 1st=5, 2nd=4, 3rd=3, 4th+=3
        score = calculate_score(player_guess['completion_order'])
        game_room.players[username].score += score
        game_room.players[username].total_score += score
        game_room.players[username].guess_count += 1
        game_room.players[username].total_guess_time += player_guess['time']

        # Update records if applicable and check if new record was set
        is_new_record = update_records(room_name, song['ID'], username, player_guess['time'])

        # Broadcast score update with updated leaderboard
        emit('player_scored', {
            'username': username,
            'score': score,
            'total': game_room.players[username].score,
            'time': player_guess['time'],
            'order': player_guess['completion_order'],
            'new_record': is_new_record,
            'leaderboard': get_leaderboard(game_room)
        }, room=f"game_{room_name}")

    # Send individual feedback (partial points)
    elif result['artist'] or result['title']:
        # Give +1 for partial guess (only once)
        if not player_guess.get('partial_scored'):
            game_room.players[username].score += 1
            game_room.players[username].total_score += 1
            player_guess['partial_scored'] = True

            emit('player_scored', {
                'username': username,
                'score': 1,
                'total': game_room.players[username].score,
                'partial': True,
                'guessed_artist': result['artist'],
                'guessed_title': result['title'],
                'leaderboard': get_leaderboard(game_room)
            }, room=f"game_{room_name}")


# ============================================================================
# HELPER FUNCTIONS FOR MULTIPLAYER GAME
# ============================================================================

def calculate_score(order):
    """Calculate score based on completion order"""
    if order == 1:
        return 5
    elif order == 2:
        return 4
    else:  # 3rd and beyond all get 3
        return 3


def get_leaderboard(game_room):
    """Get sorted leaderboard with guess times for current round"""
    players = []
    for p in game_room.players.values():
        player_data = {
            'username': p.username,
            'score': p.score,
            'total_score': p.total_score,
            'guess_time': None
        }

        # Add guess time if player has guessed in current round
        if p.username in game_room.round_guesses:
            guess = game_room.round_guesses[p.username]
            if guess.get('time') is not None:
                player_data['guess_time'] = guess['time']

        players.append(player_data)

    return sorted(players, key=lambda x: x['score'], reverse=True)


def get_time_remaining(game_room):
    """Calculate time remaining in round"""
    if game_room.game_state != 'round_active' or not game_room.round_start_time:
        return 0
    elapsed = time.time() - game_room.round_start_time
    return max(0, round(SONG_DURATION - elapsed, 1))


def load_random_songs(room_name, count):
    """Load random songs from database"""
    songs = db.execute(f"SELECT * FROM {room_name} ORDER BY RANDOM() LIMIT ?", count)
    return songs


def update_records(room_name, song_id, username, guess_time):
    """Update global and personal records, returns True if new global record was set"""
    if username == 'guest':
        return False  # Don't save guest records

    is_new_record = False

    # Update global record
    current = db.execute(f"SELECT record, player FROM {room_name} WHERE ID = ?", song_id)
    if current:
        current = current[0]
        if current['record'] == 0 or guess_time < current['record']:
            db.execute(f"UPDATE {room_name} SET record = ?, player = ? WHERE ID = ?",
                      guess_time, username, song_id)
            is_new_record = True

    # Update personal record
    personal = db.execute(
        "SELECT record FROM personal_records WHERE song_ids = ? AND room = ? AND player = ?",
        song_id, room_name, username
    )

    if personal:
        if guess_time < personal[0]['record']:
            db.execute(
                "UPDATE personal_records SET record = ? WHERE song_ids = ? AND room = ? AND player = ?",
                guess_time, song_id, room_name, username
            )
    else:
        song = db.execute(f"SELECT artist, title FROM {room_name} WHERE ID = ?", song_id)
        if song:
            song = song[0]
            db.execute(
                "INSERT INTO personal_records (artist, title, record, player, room, song_ids) VALUES (?, ?, ?, ?, ?, ?)",
                song['artist'], song['title'], guess_time, username, room_name, song_id
            )

    return is_new_record


def start_new_round(room_name):
    """Start a new round in the room"""
    game_room = game_manager.get_room(room_name)
    if not game_room:
        return

    # Check if anyone is still connected
    if not game_room.has_connected_players():
        game_room.game_state = 'waiting'
        return

    # Prevent starting a new round if one is already active
    if game_room.game_state == 'round_active':
        print(f"WARNING: Attempted to start new round in {room_name} while round is already active")
        return

    # Increment round counter and round ID
    game_room.current_round += 1
    game_room.round_id += 1
    round_in_cycle = game_room.get_current_round_in_cycle()
    current_round_id = game_room.round_id

    # Check if starting new cycle (round 1 of 10)
    if round_in_cycle == 1:
        game_room.cycle_count += 1
        # Reset cycle scores but keep total_score
        for player in game_room.players.values():
            player.score = 0
            player.guess_count = 0
            player.total_guess_time = 0.0

        # Clear played songs list for new cycle
        game_room.played_songs = []

        # Pre-load songs for this cycle
        game_room.song_queue = load_random_songs(room_name, ROUNDS_PER_GAME)
        print(f"Starting new cycle {game_room.cycle_count} in room {room_name}")

    # Get current song from queue
    song_index = round_in_cycle - 1
    game_room.current_song = game_room.song_queue[song_index]

    # Reset round state
    game_room.round_guesses = {}
    game_room.round_start_time = time.time()
    game_room.game_state = 'round_active'

    print(f"Starting round {round_in_cycle}/{ROUNDS_PER_GAME} in {room_name}: {game_room.current_song['artist']} - {game_room.current_song['title']}")

    # Broadcast round start
    socketio.emit('round_start', {
        'round': round_in_cycle,
        'cycle': game_room.cycle_count,
        'preview_url': game_room.current_song['preview'],
        'artwork_url': game_room.current_song['artwork'],
        'leaderboard': get_leaderboard(game_room),
        'played_songs': game_room.played_songs
    }, room=f"game_{room_name}")

    # Schedule round end after SONG_DURATION seconds (pass round_id to prevent duplicate timers)
    threading.Timer(float(SONG_DURATION), end_round, args=[room_name, current_round_id]).start()


def end_round(room_name, round_id):
    """End the current round"""
    game_room = game_manager.get_room(room_name)
    if not game_room:
        print(f"WARNING: Attempted to end round in {room_name} but room doesn't exist")
        return

    # Check if this timer is for the current round (prevent duplicate/old timers)
    if game_room.round_id != round_id:
        print(f"WARNING: Ignoring end_round timer for old round {round_id} (current is {game_room.round_id})")
        return

    if game_room.game_state != 'round_active':
        print(f"WARNING: Attempted to end round in {room_name} but state is {game_room.game_state}")
        return

    game_room.game_state = 'round_ended'
    song = game_room.current_song

    print(f"Ending round {game_room.get_current_round_in_cycle()}/10 in {room_name}")

    # Get record holder info for this song
    record_info = db.execute(f"SELECT record, player FROM {room_name} WHERE ID = ?", song['ID'])
    record_holder = record_info[0] if record_info else {'record': 0, 'player': 'NaN'}

    # Add song to played songs history (keep last 10 for current cycle)
    played_song_info = {
        'artist': song['artist'],
        'title': song['title'],
        'artwork': song['artwork'],
        'record': record_holder['record'],
        'player': record_holder['player'],
        'ID': song['ID']
    }

    # Add to beginning of list and keep only last ROUNDS_PER_GAME
    game_room.played_songs.insert(0, played_song_info)
    if len(game_room.played_songs) > ROUNDS_PER_GAME:
        game_room.played_songs = game_room.played_songs[:ROUNDS_PER_GAME]

    # Prepare results
    results = {
        'artist': song['artist'],
        'title': song['title'],
        'artwork': song['artwork'],
        'round': game_room.get_current_round_in_cycle(),
        'leaderboard': get_leaderboard(game_room),
        'played_songs': game_room.played_songs,
        'record': record_holder['record'],
        'record_holder': record_holder['player'],
        'guesses': [
            {
                'username': username,
                'time': guess.get('time'),
                'order': guess.get('completion_order')
            }
            for username, guess in game_room.round_guesses.items()
            if guess.get('time') is not None
        ]
    }

    # Sort guesses by order
    results['guesses'].sort(key=lambda x: x['order'] if x['order'] else 999)

    # If this is the last round of the cycle, include top 3 stats
    round_in_cycle = game_room.get_current_round_in_cycle()
    if round_in_cycle == ROUNDS_PER_GAME:
        # Get top 3 players by score
        top_players = sorted(
            game_room.players.values(),
            key=lambda p: p.score,
            reverse=True
        )[:3]

        # Calculate stats for each
        top_3_stats = []
        for player in top_players:
            avg_time = (player.total_guess_time / player.guess_count) if player.guess_count > 0 else 0
            top_3_stats.append({
                'username': player.username,
                'total_score': player.score,
                'average_time': round(avg_time, 2)
            })

        results['cycle_complete'] = True
        results['top_3'] = top_3_stats

    # Broadcast round end
    socketio.emit('round_end', results, room=f"game_{room_name}")

    # Schedule next round after DELAY_BETWEEN_ROUNDS seconds (if players still connected)
    if game_room.has_connected_players():
        threading.Timer(float(DELAY_BETWEEN_ROUNDS), start_new_round, args=[room_name]).start()
    else:
        game_room.game_state = 'waiting'
        print(f"Room {room_name} going to waiting state - no players")


@app.route('/')
def main():

    try:
        room_name = session['active_room']
    except KeyError:
        # JUst to make room_name is named
        room_name = 'NONE'

    username = session.get("username", "guest")

    # Remove player from current game room when visiting homepage
    current_room = session.get('current_game_room')
    if current_room:
        game_room = game_manager.get_room(current_room)
        if game_room and username in game_room.players:
            del game_room.players[username]
            print(f"Removed {username} from {current_room} (navigated to homepage)")

            # Send leave message to room
            leave_message = f"System: {username} left the room"
            socketio.emit('message', leave_message, room=f"game_{current_room}")
            db.execute("INSERT INTO messages (username, message, room) VALUES (?, ?, ?)",
                      "System", f"{username} left the room", current_room)

            # Broadcast updated leaderboard
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(game_room)
            }, room=f"game_{current_room}")

        # Clear current game room from session
        session.pop('current_game_room', None)

    db.execute(f"DROP TABLE IF EXISTS active_{room_name}")
    db.execute(f"CREATE TABLE IF NOT EXISTS active_{room_name} (artist TEXT, title TEXT, imageUrl text)")

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


    if session.get("userID") is not None:  # Ensure userID exists in session
        userID = session["userID"]

        # Fetch username from the database
        user = db.execute("SELECT username FROM users WHERE userID = ?", (userID,))

        if user:  # Check if user exists
            username = user[0]['username']  # Extract username from result
            session["username"] = username  # Store it in session
        else:
            username = "guest"  # Default if user not found
    else:
        username = "guest"  # Default if not logged in

    session['active_room'] = 'NONE'

    return render_template("home.html", username = username, rooms = all_rooms, images = images, length_images = length_images)

@app.route("/register")
def register():
    return render_template("register.html", username = session.get("username", "guest"), rooms = all_rooms)

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
    return render_template("login.html", username = session.get("username", "guest"), rooms = all_rooms)

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

    username = 'guest'
    session.clear()

    # Redirect user to main page
    return redirect("/")

@app.route("/room/<room_name>")
def room(room_name):
    """Game room page (now multiplayer)"""
    if room_name not in all_rooms:
        return redirect("/")

    username = session.get("username", "guest")

    # Load last 20 chat messages for this room
    messages = db.execute(
        "SELECT username, message FROM messages WHERE room = ? ORDER BY id DESC LIMIT 20",
        room_name
    )
    messages = list(reversed(messages))

    # Get song count for room
    song_count_result = db.execute(f"SELECT COUNT(*) as count FROM {room_name}")
    song_count = song_count_result[0]['count'] if song_count_result else 0

    # Clean up old session variables (no longer needed)
    session.pop('active_room', None)

    return render_template("room.html",
        room=room_name,
        rooms=all_rooms,
        username=username,
        messages=messages,
        song_count=song_count,
        rounds_per_game=ROUNDS_PER_GAME,
        song_duration=SONG_DURATION
    )

@app.route('/data', methods = ['POST'])
def data_handler():
    output = request.get_json()
    result = json.loads(output)

    guessTime = float(result['guessTime'])
    username = result['username']
    ID = result['id']
    title = result['title']
    artist = result['artist']

    room_name = session['active_room']

    row = db.execute("SELECT * FROM " + room_name + " WHERE ID = ?", ID)
    record = row[0]['record']
    new_record = ''

    if record == 0:
        new_record = guessTime

    if guessTime < record:
        new_record = guessTime

    if new_record != '':
        if username != "guest":
            db.execute("UPDATE " + room_name + " SET record = " + str(new_record) + ", player = '" + username + "' WHERE ID = " + ID)
            db.execute(f"UPDATE active_{room_name} SET record = " + str(new_record) + ", player = '" + username + "' WHERE ID = " + ID)
    
    # Check if the record exists
    personal_record = db.execute("""
        SELECT id, record FROM personal_records 
        WHERE song_ids = ? AND room = ? AND player = ? 
        LIMIT 1
    """, ID, room_name, username)


    if personal_record:
        if guessTime < personal_record[0]['record']:
            db.execute("""
                UPDATE personal_records
                SET record = ?
                WHERE id = ?
            """, guessTime, personal_record[0]['id'])
            print(f"Updated record for {artist} - {title} in room {room_name} to {guessTime}")
    else:
        # If no record exists, insert a new record
        db.execute("""
            INSERT INTO personal_records (artist, title, record, player, room, song_ids)
            VALUES (?, ?, ?, ?, ?, ?)
        """, artist, title, guessTime, username, room_name, ID)


    return ''

@app.route('/account', methods = ['POST'])
def account():
    output = request.get_json()
    result = json.loads(output)
    score = int(result['score'])
    guessTime = float(result['guessTime'])


    username = session.get("username", "guest")

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
    Database = db.execute("SELECT * FROM users WHERE username = ?", (user,))  # Pass a tuple (user,)
    
    if Database:  # Checking if Database is not empty
        return render_template("profile.html", Database=Database[0], rooms=all_rooms, username=session.get("username", "guest"))
    else:
        return redirect("/")
    
# Route for when both user and room_name are provided
@app.route('/records/<user>/<room_name>')
def personal_records(user, room_name):

    global all_rooms

    # Fetch the main database for the room
    Database = db.execute("SELECT * FROM " + room_name + " ORDER BY record = 0, record")

    # Fetch personal records for the user
    personal_records = db.execute("SELECT * FROM personal_records WHERE player = ? ORDER BY record = 0, record", user)

    # Create a lookup dictionary for personal records (Key: (artist, title, room))
    personal_dict = {(pr["song_ids"], pr["room"]): pr["record"] for pr in personal_records}

    # Update record values in the main Database list
    for count, song in enumerate(Database):
        key = (str(song["ID"]), song["room"])

        if key in personal_dict:
            Database[count]["record"] = personal_dict[key]  # Update to personal record
        else:
            Database[count]["record"] = 0.0

        Database[count]['player'] = user

    Database = sorted(Database, key=lambda x: (x['record'] == 0.0, x['record']))

    return render_template("records.html", Database=Database, rooms=all_rooms, username=session.get("username", "guest"))

# Route for when only room_name is provided (without user)
@app.route('/records/<room_name>')
def records(room_name):
    global all_rooms

    # Fetch the main database for the room
    Database = db.execute("SELECT * FROM " + room_name + " ORDER BY record = 0, record")
    
    return render_template("records.html", Database=Database, rooms=all_rooms, username=session.get("username", "guest"))



@app.route('/leaderboards/<stat>')
def leaderboards(stat):

    if stat == "MGT":
        Database = db.execute("SELECT * FROM users ORDER BY mgt ASC")

    else:
        Database = db.execute("SELECT * FROM users ORDER BY Score DESC")
    return render_template("leaderboards.html", Database = Database, username = session.get("username", "guest"), stat = stat, rooms = all_rooms)

@app.route('/edit/<room_name>', methods = ['GET','POST'])
def edit(room_name):

    username = session.get("username", "guest")

    if request.method == "POST":
        change = False

        song_id = request.form.get('song_id')

        if int(song_id) == 0:
            if username not in ["Romandu"]:
                return redirect("/")

            else:
                Database = db.execute("SELECT * FROM " + room_name)
                return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)

        else:
            if username not in ["Romandu"]:
                return redirect("/")

            else:
                edit_song = db.execute("SELECT * FROM " + room_name + " WHERE ID = ?", song_id)
                print(edit_song)

                for i in ['artist', 'title', 'preview', 'artwork']:
                    if request.form.get(i) != edit_song[0][i]:
                        change=True
                        placeholder = request.form.get(i)
                        if "'" in placeholder:
                            placeholder = placeholder.replace("'", "''")
                        db.execute("UPDATE " + room_name + " SET " + i + " = '" + placeholder + "' WHERE ID = " + song_id)

                Database = db.execute("SELECT * FROM " + room_name)

                if change == True:
                    return redirect('/edit/' + room_name)

                Database = db.execute("SELECT * FROM " + room_name)
                return render_template("edit.html", Database = Database, song_id = song_id, room_name = room_name, edit_song = edit_song[0], username = username)
    else:

        Database = db.execute("SELECT * FROM " + room_name)
        return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)

if __name__ == '__main__':
    # Use socketio.run for multiplayer support
    socketio.run(app, debug=True, allow_unsafe_werkzeug=True)
    # For production: socketio.run(app, host="0.0.0.0", port=5000)