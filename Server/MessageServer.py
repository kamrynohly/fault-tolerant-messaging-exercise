import sys
import os
import grpc
import uuid
from datetime import datetime, timedelta
# import argparse
import logging
# import socket # For retrieving local IP address only
from collections import defaultdict
# from concurrent import futures
# Handle our file paths properly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
from AuthHandler import AuthHandler
from DatabaseManager import DatabaseManager
import threading

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
        
    def __init__(self, ip, port, ip_connect=None, port_connect=None):
        # Set up the users table, messages table, and servers tables.
        self.db_manager = DatabaseManager(ip, port)
        self.auth_manager = AuthHandler(ip, port)
        self.db_manager.setup_databases(ip, port)

        self.ip = str(ip)
        self.port = str(port)
        self.server_id = str(uuid.uuid4())
        self.active_clients = {}
        self.message_queue = defaultdict(list)
        logger.info(f"Server created with UUID: {self.server_id}")

        self.servers = {}  
        self.heartbeatThread = threading.Thread(target=self._heartbeat, daemon=True)
        self.leader = defaultdict(dict)

        print("IP CONNECT", ip_connect)
        print("PORT CONNECT", port_connect)
        # If we are the leader:
        if not ip_connect and not port_connect:
            print("WE ARE THE LEADER")
            channel = grpc.insecure_channel(f'{ip}:{port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.leader["stub"] = stub
            self.leader["id"] = self.server_id
            self.leader["ip"] = ip
            self.leader["port"] = port
            self.heartbeatThread.start()

        # If we are not the leader:
        else:
            print("WE ARE NOT THE LEADER")
            self.setup(ip_connect, port_connect)


    # MARK: User Authentication
    def Register(self, request : service_pb2.RegisterRequest, context):
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
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                # TODO CHECK CHECK CHECK
                print("FORWARD REGISTER TO LEADER!!!")
                response = self.leader["stub"].Register(request)
                return response
        
            logger.info(f"Handling register request from {request.username}")
            # Set up databases if not completed already
            status, message = self.auth_manager.register_user(request.username, request.password, request.email)
            
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND REGISTER BACK TO SERVERS")
                # Send to other databases
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
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD LOGIN TO LEADER!!!")
                response = self.leader["stub"].Login(request)
                return response

            logger.info(f"Handling login request from {request.username}")
            response, message = self.auth_manager.authenticate_user(request.username, request.password)
            
            # If the leader is handling this, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND LOGIN BACK TO SERVERS")
                # Send to other databases
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
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD GET PENDING MESSAGES TO LEADER!!!")
                response = self.leader["stub"].GetPendingMessage(request)
                return response
            
            logger.info(f"Handling request from {request.username} to retrieve pending messages.")

            # Only send the number of messages that the user desires.
            counter = 0
            pending_messages = self.db_manager.get_pending_messages(request.username)
            logger.info(f"Messages pending for {request.username}: {pending_messages}")

            while len(pending_messages) > 0 and counter < request.inbox_limit:
                counter += 1
                pending_message = pending_messages.pop(0)
                # Update persistent storage status of message
                self.db_manager.pending_message_sent(pending_message["id"])
                serialized_message = service_pb2.Message(sender=pending_message["sender"], 
                                                recipient=pending_message["recipient"], 
                                                message=pending_message["message"], 
                                                timestamp=pending_message["timestamp"])
                yield service_pb2.PendingMessageResponse(
                    status=service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS,
                    message=serialized_message
                )
            
            # If the leader is handling this, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND GET PENDING MESSAGES BACK TO SERVERS")
                # Send to other databases
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
        try:
            # Should already be ordered by timestamp
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
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            MessageResponse: A response indicating the status of the message delivery.
                - status (MessageStatus): SUCCESS or FAILURE.

        Note on behavior:
            - If the recipient is active and has a valid streaming connection, the message is added to their message queue for immediate delivery.
            - If the recipient is inactive or unreachable, the message is added to the pending messages queue for later delivery when the recipient becomes active.
            - If an error occurs during the message sending process, a FAILURE message is sent to the client.
        """
        print("IN SEND MESSAGE")
        try:
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD Message TO LEADER!!!")
                response = self.leader["stub"].SendMessage(request)
                return response

            logger.info(f"Handling request to send a message from {request.sender} to {request.recipient} for message: {request.message}")
            message_request = service_pb2.Message(
                    sender=request.sender,
                    recipient=request.recipient,
                    message=request.message,
                    timestamp=request.timestamp
                )
            
            print("ACTIVE USERS NUM", len(self.active_clients.keys()))

            #  If the leader is handling this, forward it to all of the replicas.
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND MESSAGES BACK TO SERVERS")
                # Send to other databases
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
                    
                    #  If the leader is handling this, forward it to all of the replicas.
                    # We do this twice so it doesn't get missed!
                    # if request.source == "Client" and self.leader["id"] == self.server_id:
                    #     print("SEND MESSAGES BACK TO SERVERS")
                    #     # Send to other databases
                    #     new_request = service_pb2.Message(sender=request.sender, recipient=request.recipient, message=request.message, timestamp=request.timestamp, source="Leader")
                    #     for id in self.servers:
                    #         self.servers[id]["stub"].SendMessage(new_request)

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
            context (RPCContext): The RPC call context, containing information about the client.

        Yields (stream):
            Message: The message that is to be delivered from a different client to the client who called this service.
        """
        try:
            print("MONITOR MESSAGES GOT CALLED!!!")
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD monitor messages TO LEADER!!!")
                response = self.leader["stub"].MonitorMessages(request)
                return response

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
            
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND Monitor Messages BACK TO SERVERS")
                # Send to other databases
                new_request = service_pb2.MonitorMessagesRequest(username=request.username, source="Leader")
                for id in self.servers:
                    self.servers[id]["stub"].MonitorMessages(new_request)

            original_leader = self.leader["id"]
            while True:
                # We should check if there have been updates to the leader.
                # In that event, we want to shut down the stream, as it will be restarted.
                if self.leader["id"] != original_leader:
                    break

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
            if request.username in self.active_clients:
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
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD delete account TO LEADER!!!")
                response = self.leader["stub"].DeleteAccount(request)
                return response
    
            logger.info(f"Handling request to delete account with username {request.username}.")
            status = self.db_manager.delete_account(request.username)

            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND delete account BACK TO SERVERS")
                # Send to other databases
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
            context (RPCContext): The RPC call context, containing information about the client.

        Returns:
            SaveSettingsResponse: Returns the status (SaveSettingsStatus) of SUCCESS or FAILURE of saving the new limit.
        """
        try:
            if request.source == "Client" and self.leader["id"] != self.server_id:
                # Forward request
                print("FORWARD save settings TO LEADER!!!")
                response = self.leader["stub"].SaveSettings(request)
                return response

            logger.info(f"Handling save setting request from {request.username} to update setting to {request.setting}.")
            status = self.db_manager.save_settings(request.username, request.setting)
            
            if request.source == "Client" and self.leader["id"] == self.server_id:
                print("SEND save settings BACK TO SERVERS")
                # Send to other databases
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
        # Connect to another server
        initial_channel = grpc.insecure_channel(f'{ip_connect}:{port_connect}')  # Replace with actual second server address
        initial_stub = service_pb2_grpc.MessageServerStub(initial_channel)
        leader_info_response = initial_stub.NewReplica(service_pb2.NewReplicaRequest(new_replica_id=self.server_id, ip_addr=self.ip, port=self.port))

        # Connecting to the leader
        leader_channel = grpc.insecure_channel(f'{leader_info_response.ip}:{leader_info_response.port}')
        leader_stub = service_pb2_grpc.MessageServerStub(leader_channel)
        self.leader["stub"] = leader_stub
        self.leader["id"] = leader_info_response.id
        self.leader["ip"] = leader_info_response.ip
        self.leader["port"] = leader_info_response.port
        
        print("Leader is currently", self.leader)

        # Now, get info for the rest of the servers from the leader!
        servers = self.leader["stub"].GetServers(service_pb2.GetServersRequest(requestor_id=self.server_id))
        
        for server in servers:
            if not server.id == self.server_id:

                server_channel = grpc.insecure_channel(f'{server.ip}:{server.port}')
                server_stub = service_pb2_grpc.MessageServerStub(server_channel)
                self.servers[server.id] = {"ip": server.ip, "port": server.port, "heartbeat": datetime.now(), "stub": server_stub}
        
        # Add the leader to our list of servers as well for ease of use.
        self.servers[leader_info_response.id] = {"ip": leader_info_response.ip, "port": leader_info_response.port, "stub": leader_stub, "heartbeat": datetime.now()}
        self.heartbeatThread.start()

    def GetServers(self, request, context):
        # servers = DatabaseManager.get_servers()
        # print("servers:", servers)
        # for server in servers:
        #     if not request.requestor_id == server["server_id"]:
        #         serialized_server = service_pb2.ServerInfoResponse(id=server["server_id"], ip=server["ip"], port=server["port"])
        #         yield serialized_server
        for server_id, info in self.servers.items():
            if not request.requestor_id == server_id:
                serialized_server = service_pb2.ServerInfoResponse(id=server_id, ip=info["ip"], port=info["port"])
                yield serialized_server

    def NewReplica(self, request, context):
        # A new server will call this function first to inform the leader that they now exist.
        # Do a couple of things
        #       1: Update this server in SQL db
        #       2: Add this server to list of current servers
        # DatabaseManager.add_server(request.new_replica_id, request.ip_addr, request.port)
        
        channel = grpc.insecure_channel(f'{request.ip_addr}:{request.port}')
        stub = service_pb2_grpc.MessageServerStub(channel)
        self.servers[request.new_replica_id] = {"stub": stub, "heartbeat": datetime.now(), "ip": request.ip_addr, "port": request.port}

        # FORWARD REQUEST TO ALL SERVERS
        if self.leader["id"] == self.server_id:
            for id in self.servers:
                if not request.new_replica_id == id:
                    try:
                        self.servers[id]["stub"].NewReplica(request) # Send same request to all servers
                    except Exception as e:
                        print("Encountered problem forwarding new replica request to all servers", e)


        return service_pb2.LeaderResponse(id=self.leader["id"], ip=self.leader["ip"], port=self.leader["port"])

    def Heartbeat(self, request, context):
        if request.requestor_id == "Client":
            # This is just the client checking in.
            # Treat differently than other heartbeats
            return service_pb2.HeartbeatResponse(status="Heartbeat received")
        
        # Manage heartbeats
        requestor_id = request.requestor_id
        server_id = request.server_id
        # logger.info(f"Heartbeat requested from server: {requestor_id} reaching out to server: {server_id}")
        self.update_heartbeat(requestor_id)
        return service_pb2.HeartbeatResponse(status="Heartbeat received")

    def update_heartbeat(self, id):
        # print(id)
        # Update heartbeat timestamp for the server
        self.servers[id]["heartbeat"] = datetime.now()
        # logger.info(f"Heartbeat from {id} updated at {self.servers[id]}")

    def _heartbeat(self):
        if self.leader["id"] == self.server_id:
            # If I am the leader, I don't need to send heartbeats, but if I stop receiving
            # them from the replicas, then I know something has gone wrong with the replica.
            self.check_and_remove_failed_replicas()
            threading.Timer(5, self._heartbeat).start()  # Schedule the next heartbeat in 2 seconds
        else:
            for id in self.servers:
                # Create the stub for each server
                try:
                    heartbeat_request = self.servers[id]["stub"].Heartbeat(service_pb2.HeartbeatRequest(requestor_id=self.server_id, server_id=id))
                    self.update_heartbeat(id)
                except Exception as e:
                    # TODO
                    # This means the connection has disappeared?
                    # logger.error(f"Unable to reach server in _heartbeat with error {e}")
                    pass
            self.check_and_remove_failed_replicas()
            threading.Timer(2, self._heartbeat).start()

    def check_and_remove_failed_replicas(self):
        # If we are the leader and we lose a replica, no big deal!
        # If we are a replica and we lose the leader, we must run a new leader election!

        print("checking heartbeats!", self.servers)
        # Remove replicas that haven't sent a heartbeat in the last 10 seconds
        current_time = datetime.now()
        failed_replicas = []
        for server_id, info in self.servers.items():
            last_heartbeat = info["heartbeat"]
            
            # Ensure last_heartbeat is a datetime object, if not convert it.
            if isinstance(last_heartbeat, str):  # If it's a string, for example
                last_heartbeat = datetime.fromisoformat(last_heartbeat)  # Convert string to datetime
            
            # Check the difference between current time and last heartbeat
            if current_time - last_heartbeat > timedelta(seconds=10):
                print(f"Server {server_id} has failed!!!! Removing now!")
                failed_replicas.append(server_id)
        
        for id in failed_replicas:
            del self.servers[id]
            # DatabaseManager.remove_server(server_id)
            if id == self.leader["id"]:
                # If we have lost the leader, then we must facilitate a new leader election!
                self.run_election()

    def run_election(self):
        # Since we have lost the leader, let's elect the leader with the lowest UUID out of those that remain in our
        # servers.

        # We assume that we will be correct, but then call others to verify that our leader is correct.
        if len(self.servers) == 0:
            # We are the only one alive!! We are the leader!
            self.leader["id"] = self.server_id
            self.leader["ip"] = self.ip
            self.leader["port"] = self.port
            channel = grpc.insecure_channel(f'{self.ip}:{self.port}')
            stub = service_pb2_grpc.MessageServerStub(channel)
            self.leader["stub"] = stub
        else:
            all_servers = list(self.servers.keys()) + [self.server_id]
            print("all servers: ", all_servers)
            next_leader_id = min(all_servers)
            print("we need to elect a new leader: ", next_leader_id)

            print("NEW LEADER BEING SET", )
            self.leader["id"] = next_leader_id

            if next_leader_id == self.server_id:
                print("I AM THE NEW LEADER")
                self.leader["ip"] = self.ip
                self.leader["port"] = self.port
                channel = grpc.insecure_channel(f'{self.ip}:{self.port}')
                stub = service_pb2_grpc.MessageServerStub(channel)
                self.leader["stub"] = stub
            else:
                print("I AM NOT THE NEW LEADER")
                self.leader["ip"] = self.servers[next_leader_id]["ip"]
                self.leader["port"] = self.servers[next_leader_id]["port"]
                self.leader["stub"] = self.servers[next_leader_id]["stub"]

            print("todo: ALERT CLIENT")


    def ElectLeader(self, request, context):
        # The leader must have died!
        # Verify?? #TODO 
        # logger.info("Electing leader")
        # next_leader_id = min(self.servers.keys())
        # print("NEW LEADER IS ", next_leader_id)
        # # Set this to be new leader
        # self.leader["id"] = next_leader_id
        # self.leader["ip"] = self.servers[next_leader_id]["ip"]
        # self.leader["port"] = self.servers[next_leader_id]["port"]
        # self.leader["stub"] = self.servers[next_leader_id]["stub"]

        # return service_pb2.LeaderResponse(id=self.leader["id"], ip=self.leader["ip"], port=self.leader["port"])
        pass
