# SongGuesser Multiplayer Game Session Manager
#
# Ramon Duursma
#
# Manages game state for real-time multiplayer song guessing

import time
from config import ROUNDS_PER_GAME


class PlayerState:
    """Represents a player's state within a game room"""

    def __init__(self, username, socket_id=None):
        self.username = username
        self.socket_id = socket_id
        self.score = 0  # Resets each 10-round cycle
        self.total_score = 0  # Cumulative across all cycles
        self.connected = True
        self.guess_count = 0
        self.total_guess_time = 0.0


class GameRoom:
    """Represents a persistent game room (endless loop)"""

    def __init__(self, room_name):
        self.room_name = room_name  # 'Billion', 'DutchSongs', 'Short', 'Latin'
        self.players = {}  # {username: PlayerState}
        self.current_round = 0  # Increments forever
        self.current_song = None
        self.song_queue = []  # Pre-loaded songs for current cycle
        self.round_start_time = None
        self.round_guesses = {}  # {username: {artist: bool, title: bool, time: float, etc.}}
        self.game_state = 'waiting'  # waiting, round_active, round_ended
        self.cycle_count = 0  # Number of cycles completed
        self.played_songs = []  # List of recently played songs
        self.round_id = 0  # Unique ID for each round to prevent duplicate timers
        self.round_timer = None  # Timer object for cancelling early round end

    def get_current_round_in_cycle(self):
        """Returns current position in cycle (1 to ROUNDS_PER_GAME)"""
        return ((self.current_round - 1) % ROUNDS_PER_GAME) + 1

    def add_player(self, username, socket_id=None):
        """Add a new player to the room"""
        if username not in self.players:
            self.players[username] = PlayerState(username, socket_id)
        else:
            # Player rejoining
            self.players[username].connected = True
            self.players[username].socket_id = socket_id

    def remove_player(self, username):
        """Mark a player as disconnected"""
        if username in self.players:
            self.players[username].connected = False

    def get_connected_players(self):
        """Return list of all players in the room"""
        return list(self.players.values())

    def has_connected_players(self):
        """Check if any players are still in the room"""
        return len(self.players) > 0


class GameRoomManager:
    """Singleton managing all game rooms"""

    def __init__(self):
        self.rooms = {}  # {room_name: GameRoom}

    def get_or_create_room(self, room_name):
        """Get existing room or create if doesn't exist"""
        if room_name not in self.rooms:
            self.rooms[room_name] = GameRoom(room_name)
        return self.rooms[room_name]

    def get_room(self, room_name):
        """Get existing room or None"""
        return self.rooms.get(room_name)

    def cleanup_empty_rooms(self):
        """Remove rooms with no players"""
        empty_rooms = [
            name for name, room in self.rooms.items()
            if len(room.players) == 0
        ]
        for name in empty_rooms:
            del self.rooms[name]
        return len(empty_rooms)
