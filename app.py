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
import pandas as pd
from datetime import datetime

from pyngrok import ngrok

from flask_socketio import SocketIO, send, emit, join_room, leave_room

# Import multiplayer game management
from game_session import GameRoomManager, PlayerState, GameRoom
from guess_validator import validate_guess
from config import ROUNDS_PER_GAME, SONG_DURATION, DELAY_BETWEEN_ROUNDS, LEADERBOARD_TIME, ALL_ROOMS

# public_url = ngrok.connect(5000)
# print(" * ngrok tunnel:", public_url)

app = Flask(__name__, template_folder='template')
socketio = SocketIO(app, async_mode='eventlet', cors_allowed_origins='*')

# Configure session to use filesystem (instead of signed cookies)
app.secret_key = os.environ.get('SECRET_KEY', 'TODO: CHANGE ONE DAY')
app.config['SESSION_TYPE'] = 'filesystem'
Session(app)

db = SQL("sqlite:///playing_songs.db")

db.execute("CREATE TABLE IF NOT EXISTS messages (id INTEGER PRIMARY KEY AUTOINCREMENT, username TEXT, message TEXT, room TEXT)")

# Add wins column to users table if it doesn't exist
try:
    db.execute("ALTER TABLE users ADD COLUMN wins INTEGER DEFAULT 0")
except:
    pass  # Column already exists

all_rooms = ALL_ROOMS

# Initialize multiplayer game manager
game_manager = GameRoomManager()


def get_players_per_room():
    """Return the current player count for every configured room."""
    return {
        room_name: len(game_manager.get_room(room_name).players)
        if game_manager.get_room(room_name) else 0
        for room_name in all_rooms
    }


def broadcast_player_counts():
    socketio.emit('player_counts_update', {
        'players_per_room': get_players_per_room()
    })

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

    # A username may only be connected to one game tab at a time.
    for existing_room in game_manager.rooms.values():
        if username in existing_room.players:
            emit('join_rejected', {
                'message': 'This account is already playing in another tab or room.'
            })
            return

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

            # Broadcast updated leaderboard to previous room
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(prev_game_room)
            }, room=f"game_{previous_room}")

    # Get or create game room
    game_room = game_manager.get_or_create_room(room_name)

    # Add player to room
    game_room.add_player(username, request.sid)
    broadcast_player_counts()

    # Join SocketIO room
    join_room(f"game_{room_name}")

    # Track current room in session
    session['current_game_room'] = room_name

    # Send join message to chat
    join_message = f"System: {username} joined the room"
    send(join_message, room=f"game_{room_name}")

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
        if username in game_room.players and game_room.players[username].socket_id == request.sid:
            # Remove player from the game
            del game_room.players[username]
            print(f"Removed disconnected player {username} from {room_name}")

            # Send leave message to chat
            leave_message = f"System: {username} left the room"
            send(leave_message, room=f"game_{room_name}")

            # Broadcast updated leaderboard to remaining players
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(game_room)
            }, room=f"game_{room_name}")
            broadcast_player_counts()

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
    if username in game_room.players and game_room.players[username].socket_id == request.sid:
        del game_room.players[username]
        print(f"Removed player {username} from {room_name}")

    leave_room(f"game_{room_name}")

    # Send leave message to chat
    leave_message = f"System: {username} left the room"
    send(leave_message, room=f"game_{room_name}")

    # Broadcast updated leaderboard to remaining players
    emit('leaderboard_update', {
        'leaderboard': get_leaderboard(game_room)
    }, room=f"game_{room_name}")
    broadcast_player_counts()

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
        player_guess['time'] = round(elapsed, 3)

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

        account(score, player_guess['time'])

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

        # Check if all players have completed their guesses
        total_players = len(game_room.players)
        completed_players = sum(
            1 for guess in game_room.round_guesses.values()
            if guess.get('artist') and guess.get('title')
        )

        # If everyone has guessed correctly, end round early
        if completed_players == total_players and total_players > 0:
            print(f"All players completed in {room_name} - ending round early!")
            # Cancel the scheduled timer
            if game_room.round_timer:
                game_room.round_timer.cancel()
            # End round immediately (use threading to avoid blocking)
            threading.Timer(1, end_round, args=[room_name, game_room.round_id]).start()

    # Send individual feedback (partial points)
    elif result['artist'] or result['title']:
        # Give +1 for partial guess (only once)
        if not player_guess.get('partial_scored'):
            game_room.players[username].score += 1
            game_room.players[username].total_score += 1
            player_guess['partial_scored'] = True

            account(1, player_guess['time'])

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

def account(score, guessTime):

    username = session.get("username", "guest")

    rows = db.execute("SELECT * FROM users WHERE username = ?", username)
    user_score = rows[0]['Score']
    GC = rows[0]['Guess_Count']
    Time = rows[0]['Time']

    if GC != 0:
        MGT = round(Time/GC, 3)
    else:
        MGT = 0

    if score > 1:
        GC += 1
        Time+=guessTime

    user_score += score

    db.execute("UPDATE users SET Score = ?, Guess_Count = ?, Time = ?, MGT = ? WHERE username = ?",
               user_score, GC, Time, MGT, username)

    return ''


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

    # Update the global record atomically so a slower concurrent request cannot
    # overwrite a faster record after both requests have read the old value.
    db.execute(
        f"UPDATE {room_name} SET record = ?, player = ? "
        "WHERE ID = ? AND (record = 0 OR record > ?)",
        guess_time, username, song_id, guess_time
    )

    current = db.execute(f"SELECT record, player FROM {room_name} WHERE ID = ?", song_id)
    if current and current[0]['record'] == guess_time and current[0]['player'] == username:
        is_new_record = True

    # Update personal record
    personal = db.execute(
        "SELECT record FROM personal_records WHERE song_ids = ? AND room = ? AND player = ?",
        song_id, room_name, username
    )

    if personal:
        db.execute(
            "UPDATE personal_records SET record = ? "
            "WHERE song_ids = ? AND room = ? AND player = ? AND record > ?",
            guess_time, song_id, room_name, username, guess_time
        )
    else:
        db.execute(
            "INSERT INTO personal_records (player, room, song_ids, record) VALUES (?, ?, ?, ?)",
            username, room_name, song_id, guess_time
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
    game_room.round_timer = threading.Timer(float(SONG_DURATION), end_round, args=[room_name, current_round_id])
    game_room.round_timer.start()

def show_final_leaderboard(room_name):
    """Show final leaderboard after the last round"""
    game_room = game_manager.get_room(room_name)
    if not game_room:
        print(f"WARNING: Attempted to show final leaderboard in {room_name} but room doesn't exist")
        return

    # Get top 3 players by score
    top_players = sorted(
        game_room.players.values(),
        key=lambda p: p.score,
        reverse=True
    )[:3]

    # Award win to the first place player (if not guest and has score > 0)
    if top_players and top_players[0].username != 'guest' and top_players[0].score > 0:
        winner = top_players[0].username
        db.execute("UPDATE users SET wins = wins + 1 WHERE username = ?", winner)
        print(f"Awarded win to {winner} in room {room_name}")

    # Calculate stats for each
    top_3_stats = []
    for player in top_players:
        avg_time = (player.total_guess_time / player.guess_count) if player.guess_count > 0 else 0
        top_3_stats.append({
            'username': player.username,
            'total_score': player.score,
            'average_time': round(avg_time, 3)
        })

    # Broadcast final leaderboard
    socketio.emit('final_leaderboard', {
        'leaderboard': get_leaderboard(game_room),
        'top_3': top_3_stats,
        'cycle_complete': True
    }, room=f"game_{room_name}")

    # Schedule next round after LEADERBOARD_TIME seconds
    if game_room.has_connected_players():
        threading.Timer(float(LEADERBOARD_TIME), start_new_round, args=[room_name]).start()
    else:
        game_room.game_state = 'waiting'
        print(f"Room {room_name} going to waiting state - no players")


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
    game_room.round_timer = None  # Clear timer reference
    song = game_room.current_song

    print(f"Ending round {game_room.get_current_round_in_cycle()}/10 in {room_name}")

    # Get record holder info for this song
    record_info = db.execute(f"SELECT record, player, year, min_time FROM {room_name} WHERE ID = ?", song['ID'])
    record_holder = record_info[0] if record_info else {'record': 0, 'player': 'NaN', 'year': None, 'min_time': None}

    # Add song to played songs history (keep last 10 for current cycle)
    played_song_info = {
        'artist': song['artist'],
        'title': song['title'],
        'artwork': song['artwork'],
        'record': record_holder['record'],
        'player': record_holder['player'],
        'ID': song['ID'],
        'year': record_holder.get('year'),
        'min_time': record_holder.get('min_time')
    }



    # Add to beginning of list and keep only last ROUNDS_PER_GAME
    game_room.played_songs.insert(0, played_song_info)
    if len(game_room.played_songs) > ROUNDS_PER_GAME:
        game_room.played_songs = game_room.played_songs[:ROUNDS_PER_GAME]

    # Check if this is the last round
    round_in_cycle = game_room.get_current_round_in_cycle()
    is_last_round = (round_in_cycle == ROUNDS_PER_GAME)

    # Prepare results
    results = {
        'artist': song['artist'],
        'title': song['title'],
        'artwork': song['artwork'],
        'round': round_in_cycle,
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

    # Only include leaderboard if NOT the last round
    if not is_last_round:
        results['leaderboard'] = get_leaderboard(game_room)

    # Sort guesses by order
    results['guesses'].sort(key=lambda x: x['order'] if x['order'] else 999)

    # Broadcast round end
    socketio.emit('round_end', results, room=f"game_{room_name}")

    # Schedule next actions
    if game_room.has_connected_players():
        if is_last_round:
            # For last round, show final leaderboard after DELAY_BETWEEN_ROUNDS
            threading.Timer(float(DELAY_BETWEEN_ROUNDS), show_final_leaderboard, args=[room_name]).start()
        else:
            # For normal rounds, start next round after DELAY_BETWEEN_ROUNDS
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

            # Broadcast updated leaderboard
            socketio.emit('leaderboard_update', {
                'leaderboard': get_leaderboard(game_room)
            }, room=f"game_{current_room}")
            broadcast_player_counts()

        # Clear current game room from session
        session.pop('current_game_room', None)

    # Only execute table operations if room_name is valid (prevent SQL injection)
    if room_name in all_rooms or room_name == 'NONE':
        db.execute(f"DROP TABLE IF EXISTS active_{room_name}")
        db.execute(f"CREATE TABLE IF NOT EXISTS active_{room_name} (artist TEXT, title TEXT, imageUrl text)")

    images = []
    images2 = []
    for room in all_rooms:
        # room comes from all_rooms whitelist, so this is safe
        img = db.execute(f"SELECT artwork FROM {room} ORDER BY RANDOM() LIMIT 1")
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

    players_per_room = get_players_per_room()

    return render_template("home.html", username = username, rooms = all_rooms, images = images, length_images = length_images, players_per_room = players_per_room)

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

        rows = db.execute("SELECT * FROM users WHERE username = ?", username)

        if apology == "":
            if not rows or not check_password_hash(rows[0]["password"], request.form.get("password")):
                apology = "Please fill in your correct username or password!"


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
        song_duration=SONG_DURATION,
        delay_between_rounds=DELAY_BETWEEN_ROUNDS,
        leaderboard_time=LEADERBOARD_TIME
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

    # Validate room_name against whitelist to prevent SQL injection
    if room_name not in all_rooms:
        return '', 400

    row = db.execute(f"SELECT * FROM {room_name} WHERE ID = ?", ID)
    record = row[0]['record']
    new_record = ''

    if record == 0:
        new_record = guessTime

    if guessTime < record:
        new_record = guessTime

    if new_record != '':
        if username != "guest":
            db.execute(f"UPDATE {room_name} SET record = ?, player = ? WHERE ID = ?", new_record, username, ID)
            db.execute(f"UPDATE active_{room_name} SET record = ?, player = ? WHERE ID = ?", new_record, username, ID)
    
    # Check if the record exists
    personal_record = db.execute("""
        SELECT record FROM personal_records
        WHERE song_ids = ? AND room = ? AND player = ?
        LIMIT 1
    """, ID, room_name, username)


    if personal_record:
        if guessTime < personal_record[0]['record']:
            db.execute("""
                UPDATE personal_records
                SET record = ?
                WHERE song_ids = ? AND room = ? AND player = ?
            """, guessTime, ID, room_name, username)
            print(f"Updated record for {artist} - {title} in room {room_name} to {guessTime}")
    else:
        # If no record exists, insert a new record
        db.execute("""
            INSERT INTO personal_records (player, room, song_ids, record)
            VALUES (?, ?, ?, ?)
        """, username, room_name, ID, guessTime)


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

    # Validate room_name against whitelist to prevent SQL injection
    if room_name not in all_rooms:
        return redirect("/")

    # Fetch the main database for the room
    Database = db.execute(f"SELECT * FROM {room_name} ORDER BY record = 0, record")

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

    # Validate room_name against whitelist to prevent SQL injection
    if room_name not in all_rooms:
        return redirect("/")

    # Fetch the main database for the room
    Database = db.execute(f"SELECT * FROM {room_name} ORDER BY record = 0, record")
    
    return render_template("records.html", Database=Database, rooms=all_rooms, username=session.get("username", "guest"))



@app.route('/leaderboards/<stat>')
def leaderboards(stat):

    if stat == "MGT":
        Database = db.execute("SELECT * FROM users ORDER BY mgt ASC")
    elif stat == "wins":
        Database = db.execute("SELECT * FROM users ORDER BY wins DESC")
    else:
        Database = db.execute("SELECT * FROM users ORDER BY Score DESC")
    return render_template("leaderboards.html", Database = Database, username = session.get("username", "guest"), stat = stat, rooms = all_rooms)

@app.route('/edit/<room_name>', methods = ['GET','POST'])
def edit(room_name):
    # Validate room_name against whitelist to prevent SQL injection
    if room_name not in all_rooms:
        return redirect("/")

    username = session.get("username", "guest")

    # Only allow admin users
    if username not in ["Romandu"]:
        return redirect("/")

    if request.method == "POST":
        change = False

        song_id = request.form.get('song_id')

        if int(song_id) == 0:
            Database = db.execute(f"SELECT * FROM {room_name}")
            return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)

        else:
            edit_song = db.execute(f"SELECT * FROM {room_name} WHERE ID = ?", song_id)
            print(edit_song)

            # Allowed columns whitelist
            allowed_columns = ['artist', 'title', 'preview', 'artwork']
            for col in allowed_columns:
                new_value = request.form.get(col)
                if new_value != edit_song[0][col]:
                    change = True
                    db.execute(f"UPDATE {room_name} SET {col} = ? WHERE ID = ?", new_value, song_id)

            if change:
                return redirect('/edit/' + room_name)

            Database = db.execute(f"SELECT * FROM {room_name}")
            return render_template("edit.html", Database = Database, song_id = song_id, room_name = room_name, edit_song = edit_song[0], username = username)
    else:
        Database = db.execute(f"SELECT * FROM {room_name}")
        return render_template("edit.html", Database = Database, room_name = room_name, edit_song = 0, username = username, rooms = all_rooms)


# Cache for kworb data (refreshes every 30 minutes)
# Cache structure: {period: {'data': df, 'timestamp': time}}
_kworb_cache = {}
_CACHE_DURATION = 30 * 60  # 30 minutes in seconds

# Period options with display names and kworb URLs
KWORB_PERIODS = {
    'all': {'name': 'All Time (Top 2500)', 'url': 'https://kworb.net/spotify/songs.html'},
    '2026': {'name': '2026', 'url': 'https://kworb.net/spotify/songs_2026.html'},
    '2025': {'name': '2025', 'url': 'https://kworb.net/spotify/songs_2025.html'},
    '2024': {'name': '2024', 'url': 'https://kworb.net/spotify/songs_2024.html'},
    '2023': {'name': '2023', 'url': 'https://kworb.net/spotify/songs_2023.html'},
    '2022': {'name': '2022', 'url': 'https://kworb.net/spotify/songs_2022.html'},
    '2021': {'name': '2021', 'url': 'https://kworb.net/spotify/songs_2021.html'},
    '2020': {'name': '2020', 'url': 'https://kworb.net/spotify/songs_2020.html'},
    '2019': {'name': '2019', 'url': 'https://kworb.net/spotify/songs_2019.html'},
    '2018': {'name': '2018', 'url': 'https://kworb.net/spotify/songs_2018.html'},
    '2017': {'name': '2017', 'url': 'https://kworb.net/spotify/songs_2017.html'},
    '2016': {'name': '2016', 'url': 'https://kworb.net/spotify/songs_2016.html'},
    '2015': {'name': '2015', 'url': 'https://kworb.net/spotify/songs_2015.html'},
    '2014': {'name': '2014', 'url': 'https://kworb.net/spotify/songs_2014.html'},
    '2013': {'name': '2013', 'url': 'https://kworb.net/spotify/songs_2013.html'},
    '2012': {'name': '2012', 'url': 'https://kworb.net/spotify/songs_2012.html'},
    '2011': {'name': '2011', 'url': 'https://kworb.net/spotify/songs_2011.html'},
    '2010': {'name': '2010', 'url': 'https://kworb.net/spotify/songs_2010.html'},
    '2005-2009': {'name': '2005-2009', 'url': 'https://kworb.net/spotify/songs_2005.html'},
    '2000-2004': {'name': '2000-2004', 'url': 'https://kworb.net/spotify/songs_2000.html'},
    '90s': {'name': '90s', 'url': 'https://kworb.net/spotify/songs_1990.html'},
    '80s': {'name': '80s', 'url': 'https://kworb.net/spotify/songs_1980.html'},
    '70s': {'name': '70s', 'url': 'https://kworb.net/spotify/songs_1970.html'},
    '60s': {'name': '60s', 'url': 'https://kworb.net/spotify/songs_1960.html'},
    'pre60s': {'name': 'pre60s', 'url': 'https://kworb.net/spotify/songs_1950.html'},
    'combined': {'name': 'All Combined', 'url': None},  # Special case - fetches all periods
}

# Manual entries: [Artist and Title, Streams, Daily]
MANUAL_BILLION_ENTRIES = [
    # ['Artist - Song Title', 900000000, 2000000],
    # ["Bruno Mars - I Just Might", 124339472, 3407316],
    #  ["Harry Styles - Aperture", 66347082,2711572]
]

@app.route("/billion_info", defaults={'stat': '', 'period': 'all'})
@app.route("/billion_info/<stat>", defaults={'period': 'all'})
@app.route("/billion_info/<stat>/<period>")
def billion_info(stat, period):
    start_time = datetime.now()

    # Validate period, default to 'all' if invalid
    if period not in KWORB_PERIODS:
        period = 'all'

    current_time = time.time()

    # Special handling for 'combined' - fetch all periods and merge
    if period == 'combined':
        if (period not in _kworb_cache or
            _kworb_cache[period]['data'] is None or
            _kworb_cache[period]['timestamp'] is None or
            current_time - _kworb_cache[period]['timestamp'] > _CACHE_DURATION):
            # Cache is stale or empty, fetch all periods
            print(f"Fetching fresh data from all kworb.net periods...")
            year_dfs = []  # Year-specific periods
            all_time_df = None  # The 'all' (top 2500) period

            for p_key, p_val in KWORB_PERIODS.items():
                if p_key == 'combined':  # Skip combined to avoid recursion
                    continue
                try:
                    print(f"  Fetching {p_key}...")
                    period_df = pd.read_html(p_val['url'])[0]
                    period_df['Period'] = p_val['name']  # Add period column

                    if p_key == 'all':
                        all_time_df = period_df
                    else:
                        year_dfs.append(period_df)
                except Exception as e:
                    print(f"  Error fetching {p_key}: {e}")

            # Start with top 2500 ('all') as base since it updates sooner
            if all_time_df is not None:
                df = all_time_df.copy()
                df['_title_lower'] = df['Artist and Title'].str.lower()
            else:
                df = pd.DataFrame()
                df['_title_lower'] = pd.Series(dtype=str)

            # Merge all year-specific data and add songs not already in top 2500
            if year_dfs:
                year_df = pd.concat(year_dfs, ignore_index=True)
                year_df['_title_lower'] = year_df['Artist and Title'].str.lower()
                # Remove duplicates among year-specific, keeping highest streams
                year_df = year_df.sort_values('Streams', ascending=False).drop_duplicates(subset=['_title_lower'], keep='first')
                # Update Period for top 2500 songs that have a year-specific period
                period_map = year_df.set_index('_title_lower')['Period']
                mask = df['_title_lower'].isin(period_map.index)
                df.loc[mask, 'Period'] = df.loc[mask, '_title_lower'].map(period_map)
                # Only add songs from year-specific that aren't in the top 2500
                existing_songs = set(df['_title_lower'])
                year_unique = year_df[~year_df['_title_lower'].isin(existing_songs)]
                df = pd.concat([df, year_unique], ignore_index=True)

            # Remove the helper column
            df = df.drop(columns=['_title_lower'])

            # Filter out songs with >30M daily streams (likely data bugs)
            df = df[df['Daily'] <= 30000000]

            # Filter out songs with both <200k daily AND <400M streams (to reduce data size)
            df = df[~((df['Daily'] < 100000) & (df['Streams'] < 200000000))]
            _kworb_cache[period] = {'data': df, 'timestamp': current_time}
        else:
            print(f"Using cached combined data (age: {int(current_time - _kworb_cache[period]['timestamp'])}s)")
            df = _kworb_cache[period]['data']
    else:
        kworb_url = KWORB_PERIODS[period]['url']
        # Check if cache is valid for this period
        if (period not in _kworb_cache or
            _kworb_cache[period]['data'] is None or
            _kworb_cache[period]['timestamp'] is None or
            current_time - _kworb_cache[period]['timestamp'] > _CACHE_DURATION):
            # Cache is stale or empty, fetch new data
            print(f"Fetching fresh data from kworb.net for period '{period}'...")
            df = pd.read_html(kworb_url)[0]
            _kworb_cache[period] = {'data': df, 'timestamp': current_time}
        else:
            # Use cached data
            print(f"Using cached data for '{period}' (age: {int(current_time - _kworb_cache[period]['timestamp'])}s)")
            df = _kworb_cache[period]['data']

    # Merge manual entries into the dataframe
    if MANUAL_BILLION_ENTRIES:
        manual_df = pd.DataFrame(MANUAL_BILLION_ENTRIES, columns=['Artist and Title', 'Streams', 'Daily'])
        df = pd.concat([df, manual_df], ignore_index=True)

    # List of songs/artists to exclude (use | for multiple: 'Song1|Song2|Song3')
    exclude_items = [
        'Master Of Puppets', 'Let It Snow,', 'Let Is Snow', 'White Noise',
    ]
    exclude_pattern = '|'.join(exclude_items)

    # Get all songs that have already reached 1 billion
    songs_over_1b = set(df[df['Streams'] >= 1000000000]['Artist and Title'])

    # Filter data using pandas vectorized operations
    df_filtered = df[
        (df['Streams'] < 1000000000) &  # Not yet at 1 billion
        (df['Daily'].notna()) &  # Has daily data
        (df['Daily'] <= 30000000) &  # Filter out >30M daily (data bugs)
        (~df['Artist and Title'].str.contains(exclude_pattern, na=False, regex=True)) &  # Exclude manual list
        (~df['Artist and Title'].isin(songs_over_1b))  # Exclude songs that also have >1B entry
    ].copy()

    # Calculate days using vectorized numpy operations (no apply/lambda)
    df_filtered['days'] = ((1000000000 - df_filtered['Streams']) / df_filtered['Daily']).astype(int) + 1
    df_filtered['Streams'] = df_filtered['Streams'].astype(int)
    df_filtered['Daily'] = df_filtered['Daily'].astype(int)

    # Remove duplicates (keep first occurrence)
    df_filtered = df_filtered.drop_duplicates(subset=['Artist and Title'], keep='first')

    # Sort in pandas before converting to dict (much faster)
    if stat == 'streams':
        df_filtered = df_filtered.sort_values('Streams', ascending=False)
    elif stat == 'daily':
        df_filtered = df_filtered.sort_values('Daily', ascending=False)
    else:
        df_filtered = df_filtered.sort_values('days', ascending=True)

    # Convert to dictionary using itertuples (much faster than iterrows)
    sorted_dict = {}
    if period == 'combined' and 'Period' in df_filtered.columns:
        for row in df_filtered[['Artist and Title', 'days', 'Streams', 'Daily', 'Period']].itertuples(index=False):
            sorted_dict[row[0]] = {
                'days': row[1],
                'Streams': row[2],
                'Daily': row[3],
                'Period': row[4]
            }
    else:
        for row in df_filtered[['Artist and Title', 'days', 'Streams', 'Daily']].itertuples(index=False):
            sorted_dict[row[0]] = {
                'days': row[1],
                'Streams': row[2],
                'Daily': row[3]
            }

    end_time = datetime.now()

    time_taken = end_time - start_time
    print(time_taken)


    username = session.get("username", "guest")

    return render_template("billion_info.html",
                         username=username,
                         rooms=all_rooms,
                         Database=sorted_dict,
                         stat=stat,
                         period=period,
                         periods=KWORB_PERIODS)



if __name__ == '__main__':
    # Use socketio.run for multiplayer support and bind to Render's PORT when present.
    port = int(os.environ.get('PORT', 5000))
    socketio.run(app, host='0.0.0.0', port=port, debug=False, allow_unsafe_werkzeug=True)