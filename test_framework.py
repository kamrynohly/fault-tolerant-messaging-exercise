import unittest
import subprocess
import time
import sys
import os
import grpc
import signal
import threading
from datetime import datetime, timedelta
import logging
import random
import string

# Import the necessary modules
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(message)s'
)
logger = logging.getLogger("TestFramework")

class ServerInstance:
    """Helper class to manage server processes for testing"""
    
    def __init__(self, ip, port, connect_ip=None, connect_port=None):
        self.ip = ip
        self.port = port
        self.connect_ip = connect_ip
        self.connect_port = connect_port
        self.process = None
        self.stub = None
        self.channel = None
        
    def start(self):
        """Start a server instance as a subprocess"""
        cmd = ["python", "server.py", "--ip", self.ip, "--port", str(self.port)]
        if self.connect_ip and self.connect_port:
            cmd.extend(["--ip_connect", self.connect_ip, "--port_connect", str(self.connect_port)])
        
        logger.info(f"Starting server: {' '.join(cmd)}")
        self.process = subprocess.Popen(cmd)
        time.sleep(2)  # Give the server time to start
        
        # Create channel and stub
        self.channel = grpc.insecure_channel(f"{self.ip}:{self.port}")
        self.stub = service_pb2_grpc.MessageServerStub(self.channel)
        
        # Verify server is running with a heartbeat
        try:
            response = self.stub.Heartbeat(
                service_pb2.HeartbeatRequest(requestor_id="TestClient", server_id=""),
                timeout=2
            )
            logger.info(f"Server started successfully on {self.ip}:{self.port}")
            return True
        except Exception as e:
            logger.error(f"Failed to start server on {self.ip}:{self.port}: {e}")
            self.stop()
            return False
    
    def stop(self):
        """Stop the server instance"""
        if self.process:
            logger.info(f"Stopping server on {self.ip}:{self.port}")
            self.process.terminate()
            self.process.wait(timeout=5)
            self.process = None
        
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None

class TestClient:
    """Helper class to simulate a client for testing"""
    
    def __init__(self, username, password="password", email="test@example.com"):
        self.username = username
        self.password = password
        self.email = email
        self.stub = None
        self.channel = None
        self.connected_server = None
        self.message_monitor = None
        self.received_messages = []
    
    def connect_to_server(self, server_instance):
        """Connect to a specific server"""
        self.channel = grpc.insecure_channel(f"{server_instance.ip}:{server_instance.port}")
        self.stub = service_pb2_grpc.MessageServerStub(self.channel)
        self.connected_server = server_instance
        logger.info(f"Client {self.username} connected to {server_instance.ip}:{server_instance.port}")
    
    def register(self):
        """Register a new user"""
        try:
            response = self.stub.Register(
                service_pb2.RegisterRequest(
                    username=self.username,
                    password=self.password,
                    email=self.email,
                    source="Client"
                )
            )
            success = response.status == service_pb2.RegisterResponse.RegisterStatus.SUCCESS
            logger.info(f"Register for {self.username}: {'Success' if success else 'Failure'}")
            return success
        except Exception as e:
            logger.error(f"Register error for {self.username}: {e}")
            return False
    
    def login(self):
        """Login as this user"""
        try:
            response = self.stub.Login(
                service_pb2.LoginRequest(
                    username=self.username,
                    password=self.password,
                    source="Client"
                )
            )
            success = response.status == service_pb2.LoginResponse.LoginStatus.SUCCESS
            logger.info(f"Login for {self.username}: {'Success' if success else 'Failure'}")
            return success
        except Exception as e:
            logger.error(f"Login error for {self.username}: {e}")
            return False
    
    def send_message(self, recipient, message_text):
        """Send a message to another user"""
        try:
            timestamp = str(datetime.now())
            response = self.stub.SendMessage(
                service_pb2.Message(
                    sender=self.username,
                    recipient=recipient,
                    message=message_text,
                    timestamp=timestamp,
                    source="Client"
                )
            )
            success = response.status == service_pb2.MessageResponse.MessageStatus.SUCCESS
            logger.info(f"Message from {self.username} to {recipient}: {'Sent' if success else 'Failed'}")
            return success, timestamp
        except Exception as e:
            logger.error(f"Send message error from {self.username} to {recipient}: {e}")
            return False, None
    
    def start_message_monitor(self):
        """Start monitoring for incoming messages in a background thread"""
        def monitor_messages():
            try:
                request = service_pb2.MonitorMessagesRequest(username=self.username, source="Client")
                for message in self.stub.MonitorMessages(request):
                    logger.info(f"Received message for {self.username}: {message.message}")
                    self.received_messages.append({
                        'sender': message.sender,
                        'message': message.message,
                        'timestamp': message.timestamp
                    })
            except Exception as e:
                logger.error(f"Message monitor error for {self.username}: {e}")
        
        self.message_monitor = threading.Thread(target=monitor_messages, daemon=True)
        self.message_monitor.start()
        logger.info(f"Started message monitor for {self.username}")
    
    def get_pending_messages(self, limit=10):
        """Get pending messages"""
        try:
            pending_messages = []
            request = service_pb2.PendingMessageRequest(
                username=self.username,
                inbox_limit=limit,
                source="Client"
            )
            for response in self.stub.GetPendingMessage(request):
                if response.status == service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS:
                    pending_messages.append({
                        'sender': response.message.sender,
                        'message': response.message.message,
                        'timestamp': response.message.timestamp
                    })
            
            logger.info(f"Retrieved {len(pending_messages)} pending messages for {self.username}")
            return pending_messages
        except Exception as e:
            logger.error(f"Get pending messages error for {self.username}: {e}")
            return []
    
    def disconnect(self):
        """Disconnect from server"""
        if self.channel:
            self.channel.close()
            self.channel = None
            self.stub = None
            self.connected_server = None
            logger.info(f"Client {self.username} disconnected")

def random_string(length=10):
    """Generate a random string for test data"""
    letters = string.ascii_lowercase
    return ''.join(random.choice(letters) for _ in range(length))