import sys
import os
import grpc
import threading
import logging
import argparse
import socket # Only for validating IP address inputted.
from datetime import datetime
# Import our proto materials
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
# Import UI Helpers
from UI.signup import LoginUI
from UI.chat import ChatUI
import tkinter as tk
from tkinter import ttk, messagebox
from client_config import SERVERS
import time


# MARK: Logger Initialization
# Configure logging set-up. We want to log times & types of logs, as well as
# function names & the subsequent message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
)
logger = logging.getLogger(__name__)

# MARK: Client Class
class Client:
    """
    The Client class creates our UI and the callbacks that make requests to the server.
    """

    def __init__(self, host, port):
        self.host = host
        self.port = port
        self.root = tk.Tk()
        self.show_login_ui()

        # Create a background task for monitoring for new messages from the server.
        self.messageObservation = threading.Thread(target=self._monitor_messages, daemon=True)

        # Handle communication with the servers
        self.current_stub = None
        self.check_servers()

    # MARK: Check Servers
    def check_servers(self):
        """Find a server that can be communicated with and handle changes in servers."""
        try:
            # If we already have a server that we are using to communicate, verify that it is still alive.
            if self.current_stub != None:
                # If there is no response after 2 seconds, assume the server has died.
                # Otherwise, no changes are needed.
                response = self.current_stub.Heartbeat(service_pb2.HeartbeatRequest(requestor_id="Client", server_id=""), timeout=2)
                return
            # Otherwise, look for a new server using the servers in the client_config.py file.
            else:
                self.current_stub = None
                for server in SERVERS:
                    try:
                        channel = grpc.insecure_channel(f'{server["ip"]}:{server["port"]}')
                        stub = service_pb2_grpc.MessageServerStub(channel)
                        # Check if it exists, if there is no response after 2 seconds, move on
                        stub.Heartbeat(service_pb2.HeartbeatRequest(requestor_id="Client", server_id=""), timeout=2)
                        # If we got a valid response, use this server.
                        self.current_stub = stub
                        logger.info(f"Found server to use with info: {server["ip"]}:{server["port"]}")
                        break
                    except Exception as e:
                        # This means that the given server is unavailable.
                        self.current_stub = None
                        continue 
        except Exception as e:
            # If something has gone wrong, start over until a suitable server is discovered.
            self.current_stub = None
            time.sleep(1) # To give time for replicas to come back online and/or to waste unnecessary calls.
            self.check_servers()

    def run(self):
        """Initialize the client."""
        try: 
            self.root.mainloop()
        finally:
            pass

    def show_login_ui(self):
        """Show the login UI."""
        for widget in self.root.winfo_children():
            widget.destroy() 
        self.ui = LoginUI(
            root=self.root,
            login_callback=self._handle_login,
            register_callback=self._handle_register
        )

    def show_chat_ui(self, username, settings, all_users, pending_messages, message_history):
        """
        Create the initial chat UI.
        """
        for widget in self.root.winfo_children():
            widget.destroy()
        
        self.current_user = username

        callbacks = {
            'send_message': self._handle_send_message,
            'get_inbox': self._handle_get_inbox,
            'save_settings': self._handle_save_settings,
            'delete_account': self._handle_delete_account
        }

        self.chat_ui = ChatUI(
            root=self.root,
            callbacks=callbacks,
            username=username,
            all_users=all_users, 
            pending_messages=pending_messages,
            message_history=message_history,
            settings=settings,
        )

        # After setting up the UI, start observing for new messages. 
        # This allows us to be ready to add the messages to the UI instantly.
        self.messageObservation.start()

    # MARK: Authentication
    def _handle_login(self, username : str, password : str):
        """
        Sends a login request to the server and handles the server's response.
        If the user successfully logs in, this also calls upon our set-up functionalities.

        Parameters:
            username (str): the user's username
            password (str): the user's password

        Returns:
            If successful, shows the chat, otherwise presents a failure message.
        """
        self.check_servers()
        response = self.current_stub.Login(service_pb2.LoginRequest(username=username, password=password, source="Client"))

        logger.info(f"Client {username} sent login request to server.")
        if response.status == service_pb2.LoginResponse.LoginStatus.SUCCESS:
            settings, all_users, message_history = self._handle_setup(username)
            self.show_chat_ui(username, settings, all_users, {}, message_history)
        else:
            logger.warning(f"Login failed for user {username} with message {response.message}")
            messagebox.showerror("Login Failed", response.message)
    
    def _handle_register(self, username, password, email):
        """
        Sends a register request to the server and handles the server's response.
        If the user successfully registers, this also calls upon our set-up functionalities.

        Parameters:
            username (str): the user's username
            password (str): the user's password
            email (str): the user's email
        Returns:
            If successful, shows the chat, otherwise presents a failure message.
        """
        self.check_servers()
        response = self.current_stub.Register(service_pb2.RegisterRequest(username=username, password=password, email=email, source="Client"))
        
        logger.info(f"Client {username} sent register request to server.")
        if response.status == service_pb2.RegisterResponse.RegisterStatus.SUCCESS:
            logger.info(f"Client {username} registered successfully.")
            settings, all_users, message_history = self._handle_setup(username)
            self.show_chat_ui(username, settings, all_users, {}, message_history)
        else:
            logger.warning(f"Register failed for {username} with message {response.message}.")
            messagebox.showerror("Register Failed", response.message)

    # MARK: Setup
    def _handle_setup(self, username):
        '''
        After successful registration or login, handle:
        (1) Fetch and return list of online users
        (2) Fetch and return user's settings
        '''
        try:
            logger.info(f"Setting up users and settings for {username}")
            self.check_servers()
            
            # Get list of users
            try:
                user_responses = self.current_stub.GetUsers(service_pb2.GetUsersRequest(username=username))
                all_users = [user.username for user in user_responses]
                logger.info(f"Retrieved {len(all_users)} users")
            except Exception as e:
                logger.error(f"Failed to get users: {e}")
                all_users = []  # Default to empty list if we can't get users
            
            # Get user settings
            try:
                settings_response = self.current_stub.GetSettings(service_pb2.GetSettingsRequest(username=username))
                settings = settings_response.setting
                logger.info(f"Retrieved settings: {settings}")
            except Exception as e:
                logger.error(f"Failed to get settings: {e}")
                settings = 10  # Default to a reasonable value if we can't get settings
            
            # Get message history
            try:
                message_history_iterator = self.current_stub.GetMessageHistory(service_pb2.MessageHistoryRequest(username=username))
                message_history = [item for item in message_history_iterator]
                logger.info(f"Retrieved {len(message_history)} message history items")
            except Exception as e:
                logger.error(f"Failed to get message history: {e}")
                message_history = []  # Default to empty list if we can't get message history
            
            return settings, all_users, message_history
            
        except Exception as e:
            logger.error(f"Failed in setup with error: {e}")
            # Instead of exiting, return default values
            return 10, [], []  # Default values for settings, all_users, message_history

    # MARK: Messaging
    def _handle_send_message(self, recipient, message):
        """Sends the server a message request and handles potential failures to deliver the message."""
        try: 
            logger.info(f"Sending message request to {recipient} with message: {message}")
            self.check_servers()
            message_request = service_pb2.Message(
                sender=self.current_user,
                recipient=recipient,
                message=message,
                timestamp=str(datetime.now()),
                source="Client"
            )
            response = self.current_stub.SendMessage(message_request)
            if response.status == service_pb2.MessageResponse.MessageStatus.SUCCESS:
                logger.info(f"Message sent to {recipient} successfully")
            else:
                logger.error(f"Message failed to send to {recipient}")

        except Exception as e:
            logger.error(f"Message failed with error to send to {recipient} with error: {e}")
            sys.exit(1)
    
    def _monitor_messages(self):
        """
        Creates a request to the server to open a stream. This stream will yield messages that other clients
        are sending. When the user is supposed to receive a message, it will hear that message by iterating over
        the stream iterator provided as a response to the RPC call.
        """
        try:
            logger.info(f"Starting message monitoring...")
            self.check_servers()
            message_iterator = self.current_stub.MonitorMessages(service_pb2.MonitorMessagesRequest(username=self.current_user, source="Client"))
            original_server = self.current_stub
            while True:
                try:
                    # If we experience a change in leader, we should end this stream and open a new one
                    # with the new leader.
                    if original_server != self.current_stub:
                        break
                    for message in message_iterator:
                        self.chat_ui.display_message(from_user=message.sender, message=message.message)
                except Exception as e:
                    # If we experience a disconnect or issue, restart the monitoring.
                    logger.warning(f"Restarting _monitor_messages after experiencing an exception: {e}")
                    self._monitor_messages()
            
            # If we break out of the loop, it signals that we have a new leader, so restart.
            logger.warning(f"Restarting _monitor_messages after experiencing a change in server.")
            time.sleep(3) # Give the new server time to get setup.
            self._monitor_messages()
        except Exception as e:
            logger.error(f"Failed with error in monitor messages: {e}")
            sys.exit(1)

    def _handle_get_inbox(self):
        """
        Sends a request to the server to update the user's pending messages inbox.
        If the user has pending messages, this will find out and display them by calling upon the server
        to update the user's inbox. It handles these responses in the form of a stream of Messages.
        """
        try:
            logger.info("Send request to get pending messages and update inbox.")
            self.check_servers()
            settings_response = self.current_stub.GetSettings(service_pb2.GetSettingsRequest(username=self.current_user))
            settings = settings_response.setting
            
            responses = self.current_stub.GetPendingMessage(service_pb2.PendingMessageRequest(username=self.current_user, inbox_limit=settings))
            pending_messages = {}
            for response in responses:
                # If there are no messages yet from this sender, create an empty list to add to.
                if response.message.sender not in pending_messages:
                    pending_messages[response.message.sender] = []
                pending_messages[response.message.sender].append(
                    {
                        'sender': response.message.sender,
                        'message': response.message.message,
                        'timestamp': response.message.timestamp
                    }
                )
            logger.info(f"Retrieved pending messages: {pending_messages}")
            return pending_messages
        
        except Exception as e:
            logger.error(f"Failed in handle get inbox with error: {e}")
            sys.exit(1)
    
    def _handle_save_settings(self, settings):
        """Send a request to the server to update the user's settings."""
        logger.info(f"Sent request to update settings to have a limit of {settings}")
        self.check_servers()
        response = self.current_stub.SaveSettings(service_pb2.SaveSettingsRequest(username=self.current_user, setting=settings, source="Client"))

    def _handle_delete_account(self):
        """Send a request to the server to delete the user's account."""
        logger.info("Sending a request to delete account.")
        self.check_servers()
        response = self.current_stub.DeleteAccount(service_pb2.DeleteAccountRequest(username=self.current_user, source="Client"))
        if response.status == service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS:
            self.root.destroy()
        else:
            messagebox.showerror("Delete Account Failed", response.message)

# MARK: Command-line arguments.

# Validate an IP address
def validate_ip(value):
    try:
        # Try to convert the value to a valid IP address using socket
        socket.inet_aton(value)  # This will raise an error if not a valid IPv4 address
        return value
    except socket.error:
        raise argparse.ArgumentTypeError(f"Invalid IP address: {value}")
    
def parse_arguments():
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description='Chat Client')

    # Add arguments
    parser.add_argument(
        '--ip',
        type=validate_ip,
        required=True,
        help='Server IP'    
    )

    parser.add_argument(
        '--port',
        type=int,
        default=5001,
        help='Server port (default: 5001)'    
    )

    return parser.parse_args()

# MARK: MAIN
if __name__ == "__main__":
    # Set up arguments.
    args = parse_arguments()
    port = args.port
    ip = args.ip
    client = Client(host=ip, port=port)
    client.run()