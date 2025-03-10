import sqlite3
import hashlib
from datetime import datetime

class AuthHandler:
    """
    The AuthHandler class contains helpful functionalities to manage the authentication
    of new and existing users. It also manages the `users.db` permanent storage.
    """

    @staticmethod
    def hash_password(password):
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    @staticmethod
    def setup_database():
        """Initialize the SQLite database."""
        with sqlite3.connect('users.db') as conn:
            cursor = conn.cursor()
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    username TEXT PRIMARY KEY,
                    password_hash TEXT NOT NULL,
                    email TEXT,
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    last_login TIMESTAMP,
                    settings INTEGER DEFAULT 50
                )
            ''')
            conn.commit()

    @staticmethod
    def register_user(username, password, email):
        """Register a new user."""
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                password_hash = AuthHandler.hash_password(password)
                cursor.execute(
                    'INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)',
                    (username, password_hash, email)
                )
                conn.commit()
                return True, "Success"
        except sqlite3.IntegrityError:
            return False, "Username already exists."
        except Exception as e:
            return False, f"Registration failed with error {str(e)}"

    @staticmethod
    def authenticate_user(username, password):
        """Authenticate user login."""
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()
                
                if result and result[0] == AuthHandler.hash_password(password):
                    cursor.execute(
                        'UPDATE users SET last_login = ? WHERE username = ?',
                        (datetime.now(), username)
                    )
                    conn.commit()
                    return True, "Success"
                return False, "Invalid username or password"
        except Exception as e:
            return False, f"Authentication failed with error: {str(e)}"