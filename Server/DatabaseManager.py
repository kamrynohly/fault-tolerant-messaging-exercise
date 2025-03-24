import sqlite3

class DatabaseManager:
    @staticmethod
    def setup_databases():
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
            # Create a table to store information about leaders and replicas
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS servers (
                    server_id TEXT NOT NULL,
                    ip TEXT NOT NULL,
                    port TEXT NOT NULL,
                    isLeader BOOL DEFAULT FALSE
                )
            ''')
            conn.commit()

    # MARK: User-Related
    @staticmethod
    def get_contacts():
        """Register a new user."""
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT username FROM users')
                results = cursor.fetchall()
                usernames = []
                for row in results:
                    usernames.append(row[0])
                return usernames
        except Exception as e:
            return f"Fetching contacts failed: {str(e)}"

    def delete_account(username):
        """Remove the given username from the table to delete an account."""
        try:
            with sqlite3.connect('users.db') as conn:
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
                    print(f"Successfully deleted account for user: {username}")
                    return True
                    
                except Exception as e:
                    # If any error occurs, rollback the transaction
                    cursor.execute('ROLLBACK')
                    print(f"Error deleting account: {str(e)}")
                    return False
        except sqlite3.Error as e:
            print(f"Database error: {str(e)}")
            return False
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return False

    def get_settings(username):
        """Retrieve a user's setting for the limit of notifications from the table."""
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT settings FROM users WHERE username = ?', (username,))
                result = cursor.fetchone()[0]
                return result
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return False

    def save_settings(username, settings):
        """Save the user's settings in the database or update the existing value."""
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE users SET settings = ? WHERE username = ?', (settings, username))
                conn.commit()
                return True
        
        except Exception as e:
            print(f"Unexpected error: {str(e)}")
            return False

    # MARK: Messages Table

    # Persistent Messages
    def save_message(sender, recipient, message, timestamp, isPending):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute(
                    'INSERT INTO messages (sender, recipient, message, timestamp, isPending) VALUES (?, ?, ?, ?, ?)',
                    (sender, recipient, message, timestamp, isPending)
                )
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error while saving message: {str(e)}")
            return

    def pending_message_sent(id):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE messages SET isPending = ? WHERE id = ?', (False, id))
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error while updating message status: {str(e)}")
            return

    def get_pending_messages(username):
        try:
            with sqlite3.connect('users.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM messages WHERE recipient = ? AND isPending = True ORDER BY timestamp ASC', (username,))
                pending_messages = cursor.fetchall()
                return pending_messages
        except Exception as e:
            print(f"Unexpected error fetching pending messages for user: {str(e)}")
            return []

    def get_messages(username):
        try:
            with sqlite3.connect('users.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM messages WHERE isPending = False AND (sender = ? OR recipient = ?) ORDER BY timestamp ASC', (username, username))
                all_messages = cursor.fetchall()
                return all_messages
        except Exception as e:
            print(f"Unexpected error fetching messages for user: {str(e)}")
            return []

    # MARK: Server Table
    def get_servers():
        try:
            with sqlite3.connect('users.db') as conn:
                conn.row_factory = sqlite3.Row
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM servers')
                servers = cursor.fetchall()
                return servers
        except Exception as e:
            print(f"Unexpected error getting servers: {str(e)}")
            return []

    def check_leader():
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('SELECT * FROM servers WHERE isLeader = True')
                leader = cursor.fetchall()
                print("LEADER IS ", leader)
                if len(leader) == 0:
                    return None
                return leader[0]
        except Exception as e:
            print(f"Unexpected error getting leader: {str(e)}")
            return None

    def new_leader(server_id):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE servers SET isLeader = ? WHERE server_id = ?', (True, server_id))
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error updating leader: {str(e)}")
            return 

    def remove_leader(server_id):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('UPDATE servers SET isLeader = False WHERE isLeader = True')
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error removing leader: {str(e)}")
            return 

    def add_server(server_id, ip, port):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('INSERT INTO servers (server_id, ip, port) VALUES (?, ?, ?)', (server_id, ip, port))
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error while adding server to database: {str(e)}")
            return

    def remove_server(server_id):
        try:
            with sqlite3.connect('users.db') as conn:
                cursor = conn.cursor()
                cursor.execute('DELETE FROM servers WHERE server_id = ?', (server_id,))
                conn.commit()
                return
        except Exception as e:
            print(f"Unexpected error removing server: {str(e)}")
            return