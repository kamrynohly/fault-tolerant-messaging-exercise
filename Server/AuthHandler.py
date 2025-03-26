import sqlite3
import hashlib
from datetime import datetime

class AuthHandler:
    """
    The AuthHandler class contains helpful functionalities to manage the authentication
    of new and existing users. It also manages the `users.db` permanent storage.
    """
    def __init__(self, ip, port):
        self.db_name = f"{ip}_{port}.db"

    @staticmethod
    def hash_password(password):
        """Hash password using SHA-256."""
        return hashlib.sha256(password.encode()).hexdigest()
    
    def register_user(self, username, password, email):
        """Register a new user."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                password_hash = self.hash_password(password)
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

    def authenticate_user(self, username, password):
        """Authenticate user login."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT password_hash FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()
                
                if result and result[0] == self.hash_password(password):
                    cursor.execute(
                        'UPDATE users SET last_login = ? WHERE username = ?',
                        (datetime.now(), username)
                    )
                    conn.commit()
                    return True, "Success"
                return False, "Invalid username or password"
        except Exception as e:
            return False, f"Authentication failed with error: {str(e)}"