import sqlite3
from datetime import datetime
import random

class Database:
    def __init__(self, db_name="ratings.db"):
        self.conn = sqlite3.connect(db_name)
        self.cursor = self.conn.cursor()
        self.setup_database()
    
    def setup_database(self):
        # Create users table with player_index column
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                user_id INTEGER PRIMARY KEY,
                name TEXT,
                surname TEXT,
                position TEXT,
                elo INTEGER DEFAULT 1500,
                games_played INTEGER DEFAULT 0,
                player_index TEXT
            )
        ''')
        
        # Create games table
        self.cursor.execute('''
            CREATE TABLE IF NOT EXISTS games (
                game_id INTEGER PRIMARY KEY AUTOINCREMENT,
                player1_id INTEGER,
                player2_id INTEGER,
                player1_score INTEGER,
                player2_score INTEGER,
                timestamp DATETIME,
                confirmed BOOLEAN DEFAULT FALSE,
                FOREIGN KEY (player1_id) REFERENCES users (user_id),
                FOREIGN KEY (player2_id) REFERENCES users (user_id)
            )
        ''')
        self.conn.commit()
    
    def generate_unique_index(self):
        """Generate a unique 6-digit index that doesn't exist in the database yet"""
        while True:
            # Generate a random 6-digit number
            index = str(random.randint(100000, 999999))
            
            # Check if this index already exists
            self.cursor.execute("SELECT COUNT(*) FROM users WHERE player_index = ?", (index,))
            count = self.cursor.fetchone()[0]
            
            # If index doesn't exist, return it
            if count == 0:
                return index
    
    def register_user(self, user_id: int, name: str, surname: str, position: str) -> bool:
        try:
            # Generate a unique 6-digit index for the player
            player_index = self.generate_unique_index()
            
            self.cursor.execute(
                "INSERT INTO users (user_id, name, surname, position, player_index) VALUES (?, ?, ?, ?, ?)",
                (user_id, name, surname, position, player_index)
            )
            self.conn.commit()
            return True
        except sqlite3.IntegrityError:
            return False
    
    def get_user(self, user_id: int):
        self.cursor.execute("SELECT * FROM users WHERE user_id = ?", (user_id,))
        return self.cursor.fetchone()
    
    def get_user_by_name(self, name: str, surname: str):
        self.cursor.execute("SELECT * FROM users WHERE name = ? AND surname = ?", (name, surname))
        return self.cursor.fetchone()
    
    def get_all_users(self):
        # Add an index column to the results for better display in all_stats
        self.cursor.execute("""
            SELECT name, surname, elo, player_index 
            FROM users 
            ORDER BY elo DESC
        """)
        return self.cursor.fetchall()
    
    def create_game(self, player1_id: int, player2_id: int, player1_score: int, player2_score: int):
        self.cursor.execute(
            "INSERT INTO games (player1_id, player2_id, player1_score, player2_score, timestamp) VALUES (?, ?, ?, ?, ?)",
            (player1_id, player2_id, player1_score, player2_score, datetime.now())
        )
        self.conn.commit()
        return self.cursor.lastrowid
    
    def confirm_game(self, game_id: int):
        self.cursor.execute("UPDATE games SET confirmed = TRUE WHERE game_id = ?", (game_id,))
        self.conn.commit()
    
    def update_elo(self, user_id: int, new_elo: int):
        self.cursor.execute(
            "UPDATE users SET elo = ?, games_played = games_played + 1 WHERE user_id = ?",
            (new_elo, user_id)
        )
        self.conn.commit()
    
    def delete_game(self, game_id: int):
        self.cursor.execute("DELETE FROM games WHERE game_id = ?", (game_id,))
        self.conn.commit()
    
    def get_user_by_index(self, player_index: str):
        self.cursor.execute("SELECT * FROM users WHERE player_index = ?", (player_index,))
        return self.cursor.fetchone()
    
    # Add a method to get user's match history
    def get_user_games(self, user_id: int, limit: int = 10):
        self.cursor.execute("""
            SELECT g.game_id, g.player1_id, g.player2_id, 
                   g.player1_score, g.player2_score, g.timestamp,
                   u1.name || ' ' || u1.surname as player1_name,
                   u2.name || ' ' || u2.surname as player2_name
            FROM games g
            JOIN users u1 ON g.player1_id = u1.user_id
            JOIN users u2 ON g.player2_id = u2.user_id
            WHERE (g.player1_id = ? OR g.player2_id = ?) AND g.confirmed = TRUE
            ORDER BY g.timestamp DESC
            LIMIT ?
        """, (user_id, user_id, limit))
        return self.cursor.fetchall()
    
    # Add a method to get user rankings with position
    def get_user_rankings(self):
        self.cursor.execute("""
            SELECT name, surname, elo, player_index,
                   (SELECT COUNT(*) + 1 FROM users u2 WHERE u2.elo > u1.elo) as rank
            FROM users u1
            ORDER BY elo DESC
        """)
        return self.cursor.fetchall() 