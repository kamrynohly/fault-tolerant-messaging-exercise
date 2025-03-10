import sys
import os
import grpc
import datetime
import argparse
import logging
import socket # For retrieving local IP address only
from collections import defaultdict
from concurrent import futures
# Handle our file paths properly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
from auth_handler import AuthHandler
from database import DatabaseManager


# MARK: Initialize Logger
# Configure logging set-up. We want to log times & types of logs, as well as
# function names & the subsequent message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
)

# Create a logger
logger = logging.getLogger(__name__)

# MARK: MessageServer 
class MessageServer(service_pb2_grpc.MessageServerServicer):

    """
    The MessageServer class defines the service protocols defined in our
    proto/service.proto. This class provides vital functionalities that manage
    client conversations and allow clients to request services.
    """
        
    def __init__(self):
        self.active_clients = {}
        self.pending_messages = defaultdict(list)
        self.message_queue = defaultdict(list)
    
    # MARK: User Authentication
    def Register(self, request : service_pb2.RegisterRequest, context) -> service_pb2.RegisterResponse:
        """
        Registers a new user via an RPC request.

        Parameters:
            request (RegisterRequest): Contains the user's registration details.
                - username (str): The desired username.
                - password (str): The chosen password.
                - email (str): The user's email address.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            RegisterResponse: A response containing the registration status and message.
                - status (RegisterStatus): SUCCESS or FAILURE.
                - message (str): A message indicating the result of the registration.

        Behavior with Exceptions:
            If an error occurs during registration, a failure response is returned to the client, in the same
            style as the failure of a registration. It will contain the error message instead.
        """
        try:
            logger.info(f"Handling register request from {request.username}")
            status, message = AuthHandler.register_user(request.username, request.password, request.email)
            
            if status:
                logger.info(f"Successfully registered username {request.username}")
                status_message = service_pb2.RegisterResponse.RegisterStatus.SUCCESS
                return service_pb2.RegisterResponse(
                    status=status_message, 
                    message=message)
            else:
                logger.warning(f"Registration failed for username {request.username} with message: {message}")
                return service_pb2.RegisterResponse(
                    status=status, 
                    message=message)
        
        except Exception as e:
            logger.error(f"Failed to register user {request.username} with error: {e}")
            status = service_pb2.RegisterResponse.RegisterStatus.FAILURE
            return service_pb2.RegisterResponse(
                status=status, 
                message="User registration failed.")

    def Login(self, request: service_pb2.LoginRequest, context) -> service_pb2.LoginResponse:
        """
        Authenticates a user via an RPC login request.

        Parameters:
            request (LoginRequest): Contains the user's login information.
                - username (str): The username of the user attempting to log in.
                - password (str): The password provided by the user.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            LoginResponse: A response containing the login status and message.
                - status (LoginStatus): SUCCESS or FAILURE.
                - message (str): A message indicating the result of the login attempt.

        Behavior with Exceptions:
            If an error occurs during login, a failure response is returned to the client with the specific error message.
        """
        try:
            logger.info(f"Handling login request from {request.username}")
            response, message = AuthHandler.authenticate_user(request.username, request.password)
            
            if response:
                logger.info(f"Successfully logged in user with username {request.username}")
                status_message = service_pb2.LoginResponse.LoginStatus.SUCCESS
                return service_pb2.LoginResponse(
                    status=status_message, 
                    message=message)
            else:
                logger.warning(f"Login failed for username {request.username} with message: {message}")
                status = service_pb2.LoginResponse.LoginStatus.FAILURE
                return service_pb2.LoginResponse(
                    status=status, 
                    message=message)
        
        except Exception as e:
            logger.error(f"Failed to login user {request.username} with error: {e}")
            status_message = service_pb2.LoginResponse.LoginStatus.FAILURE
            return service_pb2.LoginResponse(
                status=status_message, 
                message="User login failed.")

    # MARK: Set-Up Services
    def GetUsers(self, request : service_pb2.GetUsersRequest, context) -> service_pb2.GetUsersResponse:
        """
        Retrieves a stream of users from the database who can be messaged via an RPC request.

        Parameters:
            request (GetUsersRequest): Contains the request details.
                - username (str): The username making the request (for logging purposes).
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (streams):
            GetUsersResponse: A stream of responses containing the usernames.
                - status (GetUsersStatus): SUCCESS or FAILURE.
                - username (str): The username retrieved from the database.

        Behavior with Exceptions:
            If an error occurs during the process of retrieving users, a failure response is sent with an empty username.
        """
        try:
            logger.info(f"Handling get_users request from {request.username}")
            users = DatabaseManager.get_contacts()
            logger.info(f"Retrieved users from database to send to client via a stream: {users}")
            for user in users:
                yield service_pb2.GetUsersResponse(
                    status=service_pb2.GetUsersResponse.GetUsersStatus.SUCCESS,
                    username=user
                )
        except Exception as e:
            logger.error(f"Failed to retrieve stream of users from database with error: {e}")
            yield service_pb2.GetUsersResponse(
                status=service_pb2.GetUsersResponse.GetUsersStatus.FAILURE,
                username=""
            )

    def GetPendingMessage(self, request : service_pb2.PendingMessageRequest, context) -> service_pb2.PendingMessageResponse:
        """
        Streams messages that a user has missed upon an RPC request.

        Parameters:
            request (PendingMessageRequest): Contains the request info for retrieving pending messages.
                - username (str): The user who is requesting messages.
                - inbox_limit (int): The maximum number of messages to retrieve in one request.
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (streams):
            PendingMessageResponse: A stream of responses containing the messages for the user.
                - status (PendingMessageStatus): SUCCESS if messages are successfully retrieved, FAILURE if not.
                - message (Message): The pending message in the form of a Message as outlined by our proto.

        Behavior with Exceptions:
            If an error occurs while retrieving or streaming pending messages, a failure response is sent to the client with an error message.
        """
        try:
            logger.info(f"Handling request from {request.username} to retrieve pending messages.")
            logger.info(f"Messages pending for {request.username}: {self.pending_messages[request.username]}")

            # Only send the number of messages that the user desires.
            counter = 0
            while self.pending_messages[request.username] and counter < request.inbox_limit:
                counter += 1
                pending_message = self.pending_messages[request.username].pop(0)
                yield service_pb2.PendingMessageResponse(
                    status=service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS,
                    message=pending_message
                )
        except Exception as e:
            logger.error(f"Failed to stream pending messages to {request.username} with error: {e}")
            error_message = service_pb2.Message(sender="error", 
                                                recipient="error", 
                                                message=str(e), 
                                                timestamp=str(datetime.now()))
            yield service_pb2.PendingMessageResponse(
                status=service_pb2.PendingMessageResponse.PendingMessageStatus.FAILURE,
                message=error_message
            )

    # MARK: Message Handling
    def SendMessage(self, request : service_pb2.Message, context) -> service_pb2.MessageResponse:
        """
        Handles a client's RPC request to send a message to another client.

        Parameters:
            request (Message): Contains the message details.
                - sender (str): The username of the sender.
                - recipient (str): The username of the recipient.
                - message (str): The message being sent.
                - timestamp (str): The time when the message was created.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            MessageResponse: A response indicating the status of the message delivery.
                - status (MessageStatus): SUCCESS or FAILURE.

        Note on behavior:
            - If the recipient is active and has a valid streaming connection, the message is added to their message queue for immediate delivery.
            - If the recipient is inactive or unreachable, the message is added to the pending messages queue for later delivery when the recipient becomes active.
            - If an error occurs during the message sending process, a FAILURE message is sent to the client.
        """
        try:
            logger.info(f"Handling request to send a message from {request.sender} to {request.recipient} for message: {request.message}")
            message_request = service_pb2.Message(
                    sender=request.sender,
                    recipient=request.recipient,
                    message=request.message,
                    timestamp=request.timestamp
                )
            
            # If the other client is currently online, send the message instantly.
            if request.recipient in self.active_clients.keys():
                logger.info(f"The recipient {request.recipient} is active, now confirming they have a valid streaming connection.")
                
                # Verify that the connection is still active, or treat this like our pending messages.
                if not self.active_clients[request.recipient].is_active():
                    logger.info(f"The recipient {request.recipient} has become inactive. Removing them from active clients list.")
                    # Remove the disconnected client from the active list.
                    self.active_clients.pop(request.recipient)
                else:
                    logger.info(f"Message from {request.sender} added to queue for streaming to {request.recipient}.")
                    self.message_queue[request.recipient].append(message_request)
                    return service_pb2.MessageResponse(
                        status=service_pb2.MessageResponse.MessageStatus.SUCCESS
                    )
            
            # If the client is not active and reachable, add the message to the pending messages.
            self.pending_messages[request.recipient].append(message_request)
            return service_pb2.MessageResponse(status=service_pb2.MessageResponse.MessageStatus.SUCCESS)
        
        except Exception as e:
            logger.error(f"Failed to send message from {request.sender} to {request.recipient} with error: {e}")
            return service_pb2.MessageResponse(status=service_pb2.MessageResponse.MessageStatus.FAILURE)

    def MonitorMessages(self, request : service_pb2.MonitorMessagesRequest, context) -> service_pb2.Message:
        """
        Handles a client's RPC request to subscribe to updates about new messages.
        This service also handles adding and removing a client from the clients who are active and reachable.
        Clients will create a stream with the server through this monitor service, which will be stored in 
        self.active_clients.

        Parameters:
            request (MonitorMessagesRequest): Contains the client's details.
                - username (str): The username of the sender.
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (stream):
            Message: The message that is to be delivered from a different client to the client who called this service.
        """
        try:
            logger.info(f"Handling client {request.username}'s request to monitor for messages.")
            
            # Check to ensure that this isn't creating a double connection.
            # This could happen if the client was lost and is restarting.
            if request.username in self.active_clients:
                # Remove it and start again
                self.active_clients.pop(request.username)
            
            # Add our client to our active clients and begin listening for messages
            # via a stream.
            client_stream = context
            self.active_clients[request.username] = client_stream
            
            while True:
                # If we have a message ready to send, verify our status and yield the message to the stream.
                if len(self.message_queue[request.username]) > 0:
                    if context.is_active():
                        message = self.message_queue[request.username].pop(0)
                        logger.info(f"Sending a message to {request.username}: {message.message}")
                        yield message
                    else:
                        logger.warning(f"Connection concerns with client {request.username}.")
        
        except Exception as e:
            logger.error(f"Failed to send a message or lost connection to client with error {e}")
        
        finally:
            # When the client's stream closes, remove them from the active clients.
            logger.info(f"Client disconnected with username: {request.username}")
            self.active_clients.pop(request.username)

    # MARK: Account Settings
    def DeleteAccount(self, request : service_pb2.DeleteAccountRequest, context) -> service_pb2.DeleteAccountResponse:
        """
        Handles the deletion of an account via an RPC request from the client.

        Parameters:
            request (DeleteAccountRequest): Contains the request details for deleting the account.
                - username (str): The username of the account to be deleted.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            DeleteAccountResponse: Returns the status (DeleteAccountStatus) of SUCCESS or FAILURE.
        """
        try:
            logger.info(f"Handling request to delete account with username {request.username}.")
            status = DatabaseManager.delete_account(request.username)
            if status:
                logger.info(f"Account successfully deleted for user {request.username}.")
                return service_pb2.DeleteAccountResponse(
                    status=service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS
                )
            else:
                logger.warning(f"Could not delete account for user {request.username}")
                return service_pb2.DeleteAccountResponse(
                    status=service_pb2.DeleteAccountResponse.DeleteAccountStatus.FAILURE
                )
        except Exception as e:
            logger.error(f"Failed to delete account for user {request.username} with error {e}")
            return service_pb2.DeleteAccountResponse(
                status=service_pb2.DeleteAccountResponse.DeleteAccountStatus.FAILURE
            )
    
    def SaveSettings(self, request : service_pb2.SaveSettingsRequest, context) -> service_pb2.SaveSettingsResponse:
        """
        Handles a RPC request from the client to update their limit on the number of messages to receive at a time.

        Parameters:
            request (SaveSettingsRequest): Contains the client info for setting updates.
                - username (str): The username of the account to be updated.
                - setting (int32): The number of pending messages the client wants to receive at a given time.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            SaveSettingsResponse: Returns the status (SaveSettingsStatus) of SUCCESS or FAILURE of saving the new limit.
        """
        try:
            logger.info(f"Handling save setting request from {request.username} to update setting to {request.setting}.")
            status = DatabaseManager.save_settings(request.username, request.setting)
            if status:
                logger.info(f"Successfully updated user settings for user {request.username}.")
                return service_pb2.SaveSettingsResponse(
                    status=service_pb2.SaveSettingsResponse.SaveSettingsStatus.SUCCESS
                )
            else:
                logger.warning(f"Unable to save setting for user {request.username}.")
                return service_pb2.SaveSettingsResponse(
                    status=service_pb2.SaveSettingsResponse.SaveSettingsStatus.FAILURE
                )
        except Exception as e:
            logger.error(f"Failed with error to save setting for user {request.username} with error: {e}")
            return service_pb2.SaveSettingsResponse(
                status=service_pb2.SaveSettingsResponse.SaveSettingsStatus.FAILURE
            )

    def GetSettings(self, request : service_pb2.GetSettingsRequest, context) -> service_pb2.GetSettingsResponse:
        """
        Handles a RPC request from the client to retrieve their limit on the number of messages to receive at a time.

        Parameters:
            request (GetSettingsRequest): Contains the client info for finding their settings.
                - username (str): The username of the client.
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            GetSettingsResponse: 
                - status (GetSettingsStatus): SUCCESS or FAILURE of retrieving the limit.
                - setting (int32): the limit of notifications to receive at one time.
        """
        try: 
            logger.info(f"Retrieving settings for user {request.username}.")
            settings = DatabaseManager.get_settings(request.username)
            return service_pb2.GetSettingsResponse(
                status=service_pb2.GetSettingsResponse.GetSettingsStatus.SUCCESS,
                setting=settings
            )
        except Exception as e:
            logger.error(f"Failed with error to retrieve settings for user {request.username} with error: {e}")
            return service_pb2.GetSettingsResponse(
                status=service_pb2.GetSettingsResponse.GetSettingsStatus.FAILURE,
                setting=0
            )
    

# MARK: Server Initialization

def serve(ip, port):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service_pb2_grpc.add_MessageServerServicer_to_server(MessageServer(), server)
    server.add_insecure_port(f'{ip}:{port}')
    server.start()
    logger.info(f"Server started on port {port} for ip {ip}")
    server.wait_for_termination()


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
    ip = args.ip
    port = args.port
    # Start our server
    serve(ip, port)