import sqlite3

class DatabaseManager:
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

