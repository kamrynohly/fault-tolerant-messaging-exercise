import sqlite3
import logging

# MARK: Initialize Logger
# Configure logging set-up. We want to log times & types of logs, as well as
# function names & the subsequent message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
)

# Create a logger
logger = logging.getLogger(__name__)

class DatabaseManager:
    """
    The DatabaseManager class contains helpful functionalities to manage the database of users
    and creation and updating of messages.
    """
    def __init__(self, ip, port):
        self.db_name = f"{ip}_{port}.db"
        
    def setup_databases(self, ip, port):
        """Initialize the SQLite database."""
        with sqlite3.connect(self.db_name) as conn:
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
            # Create a table to store messages between users
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS messages (
                    id INTEGER PRIMARY KEY,
                    sender TEXT NOT NULL,
                    recipient TEXT NOT NULL,
                    message TEXT NOT NULL,
                    timestamp INTEGER NOT NULL,
                    isPending BOOL NOT NULL
                )
            ''')

    # MARK: User Functionalities
    def get_contacts(self):
        """Register a new user."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT username FROM users')
                results = cursor.fetchall()
                usernames = []
                for row in results:
                    usernames.append(row[0])
                return usernames
        except Exception as e:
            return f"Fetching contacts failed: {str(e)}"

    def delete_account(self, username):
        """Remove the given username from the table to delete an account."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                
                # Start a transaction
                cursor.execute('BEGIN TRANSACTION')
                try:                    
                    # Delete user from users table
                    cursor.execute('''
                        DELETE FROM users 
                        WHERE username = ?
                    ''', (username,))
                    
                    # Commit the transaction
                    conn.commit()
                    logger.info(f"Successfully deleted account for user: {username}")
                    return True
                    
                except Exception as e:
                    # If any error occurs, rollback the transaction
                    cursor.execute('ROLLBACK')
                    logger.error(f"Error deleting account: {str(e)}")
                    return False
        except sqlite3.Error as e:
            logger.error(f"Database error: {str(e)}")
            return False
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False

    def get_settings(self, username):
        """Retrieve a user's setting for the limit of notifications from the table."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT settings FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()[0]
                return result
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False

    def save_settings(self, username, settings):
        """Save the user's settings in the database or update the existing value."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET settings = ? WHERE username = ?', (settings, username))
                conn.commit()
                return True
        except Exception as e:
            logger.error(f"Unexpected error: {str(e)}")
            return False

    # MARK: Persistent Messages 
    def save_message(self, sender, recipient, message, timestamp, isPending):
        """Store a message in the table with appropriate values. Denote if the message is currently pending delivery."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO messages (sender, recipient, message, timestamp, isPending) VALUES (?, ?, ?, ?, ?)',
                    (sender, recipient, message, timestamp, isPending)
                )
                conn.commit()
        except Exception as e:
            logger.error(f"Unexpected error while saving message: {str(e)}")

    def pending_message_sent(self, id):
        """Updates a pending message when it has been delivered."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE messages SET isPending = ? WHERE id = ?', (False, id))
                conn.commit()
        except Exception as e:
            logger.error(f"Unexpected error while updating message status: {str(e)}")

    def get_pending_messages(self, username):
        """Retrieve all messages that are pending for a given user."""
        try:
            with sqlite3.connect(self.db_name) as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM messages WHERE recipient = ? AND isPending = True ORDER BY timestamp ASC', (username,))
                pending_messages = cursor.fetchall()
                return pending_messages
        except Exception as e:
            logger.error(f"Unexpected error fetching pending messages for user: {str(e)}")
            return []

    def get_messages(self, username):
        try:
            with sqlite3.connect(self.db_name) as conn:
                conn.row_factory = sqlite3.Row # We want the rows as dictionaries, not tuples.
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM messages WHERE isPending = False AND (sender = ? OR recipient = ?) ORDER BY timestamp ASC', (username, username))
                all_messages = cursor.fetchall()
                return all_messages
        except Exception as e:
            logger.error(f"Unexpected error fetching messages for user: {str(e)}")
            return []