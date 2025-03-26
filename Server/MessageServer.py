import sys
import os
import grpc
import uuid
import threading
from datetime import datetime, timedelta
import logging
from collections import defaultdict
# Handle our file paths properly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
from AuthHandler import AuthHandler
from DatabaseManager import DatabaseManager


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
    client conversations and allow clients to request services. The server also
    communicates with other servers to build replicas. 
    
    At any give time, only one server will be a "Leader" and the rest will be "Replicas."

    When a leader disappears, a new leader is elected based on which replica has the lowest UUID value.
    """
        
    def __init__(self, ip, port, ip_connect=None, port_connect=None):
        # Set up the independant database of the server.
        self.db_manager = DatabaseManager(ip, port)
        self.auth_manager = AuthHandler(ip, port)
        self.db_manager.setup_databases(ip, port)

        # Define server information, including its unique identifier.
        self.ip = str(ip)
        self.port = str(port)
        self.server_id = str(uuid.uuid4())
        self.active_clients = {}
        self.message_queue = defaultdict(list)
        logger.info(f"Server created with UUID: {self.server_id}")

        # Store information about the other servers in the chat application.
        self.servers = {}  
        self.leader = defaultdict(dict)
        # Keep a thread that will constantly send and monitor heartbeats from the other servers.
        self.heartbeatThread = threading.Thread(target=self._heartbeat, daemon=True)

        # If we are the leader, define the appropriate information for the leader.
        if not ip_connect and not port_connect:
            logger.info("This process is currently the leader.")
            channel = grpc.insecure_channel(f'{ip}:{port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.leader["stub"] = stub
            self.leader["id"] = self.server_id
            self.leader["ip"] = ip
            self.leader["port"] = port
            self.heartbeatThread.start()
        else:
            # If we are not the leader, then other servers are currently operating.
            logger.info("This process is currently a replica.")
            self.setup(ip_connect, port_connect)

    # MARK: User Authentication
    def Register(self, request : service_pb2.RegisterRequest, context):
        """
        Registers a new user via an RPC request.
        If a replica receives this request by a client, it forwards it to the leader.
        The leader then propagates the request to all replicas.

        Parameters:
            request (RegisterRequest): Contains the user's registration details.
                - username (str): The desired username.
                - password (str): The chosen password.
                - email (str): The user's email address.
                - source (str): The originator of the request (Client or Leader)
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
            
            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                logger.info("Forwarding register request from replica to leader.")
                return self.leader["stub"].Register(request)
        
            # Register the new user with the authentication manager.
            status, message = self.auth_manager.register_user(request.username, request.password, request.email)
            
            # If we are the leader, propagate the request to all replicas to maintain consistency.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating register request from leader to replicas.")
                new_request = service_pb2.RegisterRequest(username=request.username, password=request.password, email=request.email, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].Register(new_request)

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
        If a replica receives this request by a client, it forwards it to the leader.
        The leader then propagates the request to all replicas.

        Parameters:
            request (LoginRequest): Contains the user's login information.
                - username (str): The username of the user attempting to log in.
                - password (str): The password provided by the user.
                - source (str): The originator of the request (Client or Leader)
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
            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                logger.info("Forwarding login request from replica to leader.")
                return self.leader["stub"].Login(request)

            response, message = self.auth_manager.authenticate_user(request.username, request.password)
            
            # If the leader is handling this request, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating login request from leader to replicas.")
                new_request = service_pb2.LoginRequest(username=request.username, password=request.password, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].Login(new_request)

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
            users = self.db_manager.get_contacts()
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
        If a replica receives this request by a client, it forwards it to the leader.
        The leader then propagates the request to all replicas.

        Parameters:
            request (PendingMessageRequest): Contains the request info for retrieving pending messages.
                - username (str): The user who is requesting messages.
                - inbox_limit (int): The maximum number of messages to retrieve in one request.
                - source (str): The originator of the request (Client or Leader)
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
            
            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                logger.info("Forwarding GetPendingMessage request from replica to leader.")
                return self.leader["stub"].GetPendingMessage(request)
            
            # Only send the number of messages that the user desires.
            counter = 0
            pending_messages = self.db_manager.get_pending_messages(request.username)
            logger.info(f"Messages pending for {request.username}: {pending_messages}")

            while len(pending_messages) > 0 and counter < request.inbox_limit:
                counter += 1
                pending_message = pending_messages.pop(0)
                # Update persistent storage status of message.
                self.db_manager.pending_message_sent(pending_message["id"])
                serialized_message = service_pb2.Message(sender=pending_message["sender"], 
                                                recipient=pending_message["recipient"], 
                                                message=pending_message["message"], 
                                                timestamp=pending_message["timestamp"])
                yield service_pb2.PendingMessageResponse(
                    status=service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS,
                    message=serialized_message
                )
            
            # If we are the leader, propagate the request to all replicas to maintain consistency.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating GetPendingMessage request from leader to replicas.")
                new_request = service_pb2.GetPendingMessage(username=request.username, inbox_limit=request.inbox_limit, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].GetPendingMessage(new_request)

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

    def GetMessageHistory(self, request : service_pb2.MessageHistoryRequest, context):
        """
        Streams all stored messages relevant for the given user

        Parameters:
            request (MessageHistoryRequest): Contains the request info for retrieving all stored messages.
                - username (str): The user who is requesting messages.
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (streams):
            Message: A stream of responses containing the messages for the user.

        Behavior with Exceptions:
            If an error occurs while retrieving or streaming messages, a failure response is sent to the client with an error message.
        """
        try:
            logger.info(f"Retrieving message history for user: {request.username}")
            # Messages are already ordered by timestamp for conversations. 
            # Serialize the messages and yield them individually to the stream.
            messages = self.db_manager.get_messages(request.username)
            for message in messages:
                serialized_message = service_pb2.Message(sender=message["sender"], 
                                                recipient=message["recipient"], 
                                                message=message["message"], 
                                                timestamp=message["timestamp"])
                yield serialized_message
        except Exception as e:
            logger.error(f"Failed to retrieve message history for user {request.username} with error: {e}")
            error_message = service_pb2.Message(sender="error", 
                                                recipient="error", 
                                                message=str(e), 
                                                timestamp=str(datetime.now()))
            yield error_message

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
                - source (str): The originator of the request (Client or Leader)
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
            
            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                logger.info("Forwarding SendMessage request from replica to leader.")
                return self.leader["stub"].SendMessage(request)

            message_request = service_pb2.Message(
                    sender=request.sender,
                    recipient=request.recipient,
                    message=request.message,
                    timestamp=request.timestamp
                )
            
            #  If the leader is handling this request, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating SendMessage request from leader to replicas.")
                new_request = service_pb2.Message(sender=request.sender, recipient=request.recipient, message=request.message, timestamp=request.timestamp, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].SendMessage(new_request)

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
                    # Save to persistent storage
                    self.db_manager.save_message(request.sender, request.recipient, request.message, request.timestamp, False)
                    return service_pb2.MessageResponse(
                        status=service_pb2.MessageResponse.MessageStatus.SUCCESS
                    )
            # If the client is not active and reachable, add the message to the pending message in our database.
            self.db_manager.save_message(request.sender, request.recipient, request.message, request.timestamp, True)
            return service_pb2.MessageResponse(status=service_pb2.MessageResponse.MessageStatus.SUCCESS)

        except Exception as e:
            logger.error(f"Failed to send message from {request.sender} to {request.recipient} with error: {e}")
            return service_pb2.MessageResponse(status=service_pb2.MessageResponse.MessageStatus.FAILURE)

    def MonitorMessages(self, request : service_pb2.MonitorMessagesRequest, context):
        """
        Handles a client's RPC request to subscribe to updates about new messages.
        This service also handles adding and removing a client from the clients who are active and reachable.
        Clients will create a stream with the server through this monitor service, which will be stored in 
        self.active_clients.

        Parameters:
            request (MonitorMessagesRequest): Contains the client's details.
                - username (str): The username of the sender.
                - source (str): The originator of the request (Client or Leader)
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (stream):
            Message: The message that is to be delivered from a different client to the client who called this service.
        """
        try:
            logger.info(f"Handling client {request.username}'s request to monitor for messages.")

            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Before we forward, let's make sure the leader hasn't died!
                try:
                    self.leader["stub"].Heartbeat(service_pb2.HeartbeatRequest(requestor_id=self.server_id, server_id=self.leader["id"]), timeout=1)
                    logger.info("Forwarding MonitorMessages request from replica to leader.")
                    return self.leader["stub"].MonitorMessages(request)
                except Exception as e:
                    # In the event that the leader has died, the replica will run
                    # a leader election and continue.
                    logger.warning("In MonitorMessages where the leader has died.")

            # Check to ensure that this isn't creating a double connection.
            # This could happen if the client was lost and is restarting.
            if request.username in self.active_clients:
                # Remove it and start again
                self.active_clients.pop(request.username)
            
            # Add our client to our active clients and begin listening for messages
            # via a stream.
            client_stream = context
            self.active_clients[request.username] = client_stream
            
            # If the leader is handling this request, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating MonitorMessages request from leader to replicas.")
                new_request = service_pb2.MonitorMessagesRequest(username=request.username, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].MonitorMessages(new_request)

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
            # if request.username in self.active_clients:
            #     self.active_clients.pop(request.username)


    # MARK: Account Settings
    def DeleteAccount(self, request : service_pb2.DeleteAccountRequest, context) -> service_pb2.DeleteAccountResponse:
        """
        Handles the deletion of an account via an RPC request from the client.

        Parameters:
            request (DeleteAccountRequest): Contains the request details for deleting the account.
                - username (str): The username of the account to be deleted.
                - source (str): The originator of the request (Client or Leader)
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            DeleteAccountResponse: Returns the status (DeleteAccountStatus) of SUCCESS or FAILURE.
        """
        try:
            logger.info(f"Handling request to delete account with username {request.username}.")

            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                logger.info("Forwarding delete account request from replica to leader.")
                return self.leader["stub"].DeleteAccount(request)
    
            status = self.db_manager.delete_account(request.username)

            # If the leader is handling this request, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating delete account request from leader to replicas.")
                new_request = service_pb2.DeleteAccountRequest(username=request.username, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].DeleteAccount(new_request)

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
                - source (str): The originator of the request (Client or Leader)
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            SaveSettingsResponse: Returns the status (SaveSettingsStatus) of SUCCESS or FAILURE of saving the new limit.
        """
        try:
            logger.info(f"Handling save setting request from {request.username} to update setting to {request.setting}.")

            # If we are not the leader and the request is from a client, forward the request to the leader.
            if request.source == "Client" and self.leader["id"] != self.server_id:
                logger.info("Forwarding SaveSettings request from replica to leader.")
                return self.leader["stub"].SaveSettings(request)

            status = self.db_manager.save_settings(request.username, request.setting)

            # If the leader is handling this request, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                logger.info("Propagating SaveSettings request from leader to replicas.")
                new_request = service_pb2.SaveSettingsRequest(username=request.username, setting=request.setting, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].SaveSettings(new_request)

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
            settings = self.db_manager.get_settings(request.username)
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
    
    # MARK: Fault Tolerance
    def setup(self, ip_connect, port_connect):
        """
        Handles the setup of a replica. Announces the creation of the replica to other replicas and the leader,
        retrieves the current leader, and starts the heartbeat with other servers.

        Parameters:
            ip_connect (String): The IP address of either another replica or the leader of the Chat application.
            port_connect (String): The port of either another replica or the leader of the Chat application.
        """
        try:
            logger.info(f"Setting up replica by connecting it to {ip_connect}:{port_connect}")
            # Connect to the provided other server
            initial_channel = grpc.insecure_channel(f'{ip_connect}:{port_connect}')
            initial_stub = service_pb2_grpc.MessageServerStub(initial_channel)
            leader_info_response = initial_stub.NewReplica(service_pb2.NewReplicaRequest(new_replica_id=self.server_id, ip=self.ip, port=self.port))

            # Connect to the leader that was passed back by the first server.
            leader_channel = grpc.insecure_channel(f'{leader_info_response.ip}:{leader_info_response.port}')
            leader_stub = service_pb2_grpc.MessageServerStub(leader_channel)
            self.leader["stub"] = leader_stub
            self.leader["id"] = leader_info_response.id
            self.leader["ip"] = leader_info_response.ip
            self.leader["port"] = leader_info_response.port

            # Retrieve information about the other active, online servers.
            servers = self.leader["stub"].GetServers(service_pb2.GetServersRequest(requestor_id=self.server_id))
            for server in servers:
                server_channel = grpc.insecure_channel(f'{server.ip}:{server.port}')
                server_stub = service_pb2_grpc.MessageServerStub(server_channel)
                self.servers[server.id] = {"ip": server.ip, "port": server.port, "heartbeat": datetime.now(), "stub": server_stub}
            # Add the leader to our list of servers as well for ease of use.
            self.servers[leader_info_response.id] = {"ip": leader_info_response.ip, "port": leader_info_response.port, "stub": leader_stub, "heartbeat": datetime.now()}
            # Start the heartbeats from the replicas to the leader.
            self.heartbeatThread.start()
        except Exception as e:
            logger.error(f"Failed to setup replica with error: {e}")

    def GetServers(self, request: service_pb2.GetServersRequest, context):
        """
        Retrieves a stream of all online, active users via an RPC request.

        Parameters:
            request (GetServersRequest): Contains the request details.
                - requestor_id (str): The uuid of the server making the request
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (streams):
            ServerInfoResponse: A stream of responses containing the data about the servers.
                - id (str): The uuid of the server
                - ip (str): The ip of the server
                - port (str): The port of the server
        """
        try:
            logger.info(f"Handling request to GetServers by {request.requestor_id}")
            for server_id, info in self.servers.items():
                if not request.requestor_id == server_id:
                    serialized_server = service_pb2.ServerInfoResponse(id=server_id, ip=info["ip"], port=info["port"])
                    yield serialized_server
        except Exception as e:
            logger.error(f"Failed to retrieve servers with error: {e}")

    def NewReplica(self, request: service_pb2.NewReplicaRequest, context):
        """
        Announces the newly active status of a replica via an RPC request.

        Parameters:
            request (NewReplicaRequest): Contains the request details.
                - new_replica_id (str): The uuid of the new replica
                - ip (str): The ip address of the replica
                - port (str): The port of the replica
            context (RPCContext): The RPC call context, containing information about the client.

        Returns LeaderResponse: The information for the Chat application's current leader
                - id (str): The uuid of the leader
                - ip (str): The ip of the leader
                - port (str): The port of the leader
        """
        try:
            logger.info(f"Handling request to add NewReplica with id: {request.new_replica_id} at {request.ip}:{request.port}")
            # A new server will call this function first to inform the leader that they now exist.
            channel = grpc.insecure_channel(f'{request.ip}:{request.port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.servers[request.new_replica_id] = {"ip": request.ip, "port": request.port, "stub": stub, "heartbeat": datetime.now()}

            logger.info("Forward announcement of new replica to all other servers.")
            if self.leader["id"] == self.server_id:
                for id in self.servers:
                    if not request.new_replica_id == id:
                        try:
                            self.servers[id]["stub"].NewReplica(request) # Send same request to all servers
                        except Exception as e:
                            logger.error(f"Encountered problem forwarding new replica request to all servers: {e}")
            return service_pb2.LeaderResponse(id=self.leader["id"], ip=self.leader["ip"], port=self.leader["port"])
        except Exception as e:
            logger.error(f"Creating NewReplica failed with error: {e}")

    def Heartbeat(self, request: service_pb2.HeartbeatRequest, context):
        """
        Handles sending heartbeats via an RPC request.

        Parameters:
            request (HeartbeatRequest): Contains the request details.
                - requestor_id (str): The id of the server sending the heartbeat
                - server_id (str): The id of the intended recipient of the heartbeat
            context (RPCContext): The RPC call context, containing information about the client.

        Returns HeartbeatResponse: The response of the server to the heartbeat request.
                - responder_id (str): The id of the server responding to the heartbeat
                - status (str): A description of the state
        """
        try:
            logger.info(f"Heartbeat requested from server: {request.requestor_id} reaching out to server: {request.server_id}")
            if request.requestor_id == "Client":
                # This is just the client checking in to ensure this server is still alive.
                return service_pb2.HeartbeatResponse(status="Heartbeat received")
            
            # Since we received a request from the requestor, we know they are still active.
            # Update the timestamp of the requestor and send a response.
            requestor_id = request.requestor_id
            server_id = request.server_id
            self.update_heartbeat(requestor_id)
            return service_pb2.HeartbeatResponse(responder_id=self.server_id, status="Heartbeat received")
        except Exception as e:
            logger.error(f"Error occurred in Heartbeat request: {e}")

    def update_heartbeat(self, id):
        """Update heartbeat timestamp for the server"""
        logger.info(f"Heartbeat from {id} updated at {self.servers[id]}")
        self.servers[id]["heartbeat"] = datetime.now()

    def _heartbeat(self):
        """Handle the background daemon of sending heartbeats and removing failed servers."""
        if self.leader["id"] == self.server_id:
            # If I am the leader, I don't need to send heartbeats, but if I stop receiving
            # them from the replicas, then I know something has gone wrong with the replica.
            self.check_and_remove_failed_replicas()
            threading.Timer(1, self._heartbeat).start()  # Schedule the next heartbeat in 2 seconds
        else:
            for id in self.servers:
                try:
                    heartbeat_request = self.servers[id]["stub"].Heartbeat(service_pb2.HeartbeatRequest(requestor_id=self.server_id, server_id=id))
                    self.update_heartbeat(id)
                except Exception as e:
                    # We handle the exceptions from failed servers in the check_and_remove_failed_replicas()
                    pass
            self.check_and_remove_failed_replicas()
            threading.Timer(1, self._heartbeat).start() # Schedule the next heartbeat in 2 seconds

    def check_and_remove_failed_replicas(self):
        """Handle failed servers."""
        logger.info(f"Checking heartbeats and removing failed servers. Current heartbeats: {self.servers}")

        current_time = datetime.now()
        failed_replicas = []
        for server_id, info in self.servers.items():
            last_heartbeat = info["heartbeat"]
            
            # Ensure last_heartbeat is a datetime object, if not convert it.
            if isinstance(last_heartbeat, str):  # If it's a string
                last_heartbeat = datetime.fromisoformat(last_heartbeat)  # Convert string to datetime
            
            # Check the difference between current time and last heartbeat
            if current_time - last_heartbeat > timedelta(seconds=3):
                logger.warning(f"Server {server_id} has failed due to lack of heartbeat response! Removing now.")
                failed_replicas.append(server_id)
        
        for id in failed_replicas:
            del self.servers[id]
            if id == self.leader["id"]:
                # If we have lost the leader, then we must facilitate a new leader election!
                self.run_election()

    def run_election(self):
        """Handle electing a new leader. Utilises the lowest UUID of the existing servers."""
        # If we are the only server remaining, we become the leader.
        if len(self.servers) == 0:
            self.leader["id"] = self.server_id
            self.leader["ip"] = self.ip
            self.leader["port"] = self.port
            channel = grpc.insecure_channel(f'{self.ip}:{self.port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.leader["stub"] = stub
            return

        # Otherwise, elect a new leader by finding the lowest UUID between this server's uuid and the
        # other servers.
        all_servers = list(self.servers.keys()) + [self.server_id]
        next_leader_id = min(all_servers)
        self.leader["id"] = next_leader_id

        if next_leader_id == self.server_id:
            logger.info("Server has become the new leader.")
            self.leader["ip"] = self.ip
            self.leader["port"] = self.port
            channel = grpc.insecure_channel(f'{self.ip}:{self.port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.leader["stub"] = stub
        else:
            logger.info("This process is still a replica. A new leader has been selected.")
            self.leader["ip"] = self.servers[next_leader_id]["ip"]
            self.leader["port"] = self.servers[next_leader_id]["port"]
            self.leader["stub"] = self.servers[next_leader_id]["stub"]
