import unittest
from unittest.mock import MagicMock, patch
import sys
import os
from collections import defaultdict
from datetime import datetime

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)

# Import proto files
from proto import service_pb2
from proto import service_pb2_grpc

# Import the MessageServer class
from Server.main import MessageServer

class TestMessageServer(unittest.TestCase):
    def setUp(self):
        # Create a server instance for testing
        self.server = MessageServer()
        
        # Mock the context
        self.context = MagicMock()
        
        # Initialize server state for testing
        self.server.active_clients = {}
        self.server.message_queue = defaultdict(list)
        self.server.pending_messages = defaultdict(list)
    
    def test_register_success(self):
        # Create a request
        request = service_pb2.RegisterRequest(
            username="testuser",
            password="testpassword",
            email="test@example.com"
        )
        
        # Mock the AuthHandler.register_user method
        with patch('Server.auth_handler.AuthHandler.register_user', return_value=(True, "Success")):
            response = self.server.Register(request, self.context)
            
            # Assert the response is correct
            self.assertEqual(response.status, service_pb2.RegisterResponse.RegisterStatus.SUCCESS)
            self.assertIn("Success", response.message)
    
    def test_register_failure(self):
        # Create a request with existing username
        request = service_pb2.RegisterRequest(
            username="existinguser",
            password="testpassword",
            email="test@example.com"
        )
        
        # Mock the AuthHandler.register_user method to return failure
        with patch('Server.auth_handler.AuthHandler.register_user', return_value=(False, "Username already exists")):
            response = self.server.Register(request, self.context)
            
            # Assert the response is correct - note that the status is a boolean False, not an enum FAILED
            self.assertEqual(response.status, False)
            self.assertIn("already exists", response.message)
    
    
    def test_login_failure(self):
        # Create a request with wrong credentials
        request = service_pb2.LoginRequest(
            username="testuser",
            password="wrongpassword"
        )
        
        # Mock the authentication to return failure
        with patch('Server.auth_handler.AuthHandler.authenticate_user', return_value=(False, "Invalid credentials")):
            response = self.server.Login(request, self.context)
            
            # Assert the response is correct
            self.assertEqual(response.status, service_pb2.LoginResponse.LoginStatus.FAILURE)
            self.assertIn("Invalid", response.message)
    
    def test_send_message_to_active_client(self):
        # Create a message
        request = service_pb2.Message(
            sender="user1",
            recipient="user2",
            message="Hello!",
            timestamp="2023-01-01 12:00:00"
        )
        
        # Set up an active client with a mock context that is active
        mock_context = MagicMock()
        mock_context.is_active.return_value = True
        self.server.active_clients = {"user2": mock_context}
        
        # Send the message
        response = self.server.SendMessage(request, self.context)
        
        # Assert the response is correct
        self.assertEqual(response.status, service_pb2.MessageResponse.MessageStatus.SUCCESS)
        
        # Assert the message was added to the queue
        self.assertEqual(len(self.server.message_queue["user2"]), 1)
        self.assertEqual(self.server.message_queue["user2"][0].sender, "user1")
        self.assertEqual(self.server.message_queue["user2"][0].message, "Hello!")
    
    def test_send_message_to_inactive_client(self):
        # Create a message
        request = service_pb2.Message(
            sender="user1",
            recipient="user3",
            message="Hello!",
            timestamp="2023-01-01 12:00:00"
        )
        
        # No active clients
        self.server.active_clients = {}
        
        # Send the message
        response = self.server.SendMessage(request, self.context)
        
        # Assert the response is correct
        self.assertEqual(response.status, service_pb2.MessageResponse.MessageStatus.SUCCESS)
        
        # Assert the message was added to pending messages
        self.assertEqual(len(self.server.pending_messages["user3"]), 1)
        self.assertEqual(self.server.pending_messages["user3"][0].sender, "user1")
        self.assertEqual(self.server.pending_messages["user3"][0].message, "Hello!")
    
    
    def test_get_pending_messages(self):
        # Create a request
        request = service_pb2.PendingMessageRequest(username="testuser", inbox_limit=10)
        
        # Add some pending messages
        message1 = service_pb2.Message(
            sender="user1",
            recipient="testuser",
            message="Hello!",
            timestamp="2023-01-01 12:00:00"
        )
        
        message2 = service_pb2.Message(
            sender="user2",
            recipient="testuser",
            message="Hi there!",
            timestamp="2023-01-01 12:01:00"
        )
        
        self.server.pending_messages["testuser"] = [message1, message2]
        
        # Get the generator
        response_generator = self.server.GetPendingMessage(request, self.context)
        
        # Convert generator to list
        responses = list(response_generator)
        
        # Assert the responses are correct
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0].message.sender, "user1")
        self.assertEqual(responses[0].message.message, "Hello!")
        self.assertEqual(responses[1].message.sender, "user2")
        self.assertEqual(responses[1].message.message, "Hi there!")
        
        # Assert the pending messages were cleared
        self.assertEqual(len(self.server.pending_messages["testuser"]), 0)
    
    def test_delete_account_success(self):
        # Create a request
        request = service_pb2.DeleteAccountRequest(username="testuser")
        
        # Mock the DatabaseManager.delete_account method
        with patch('Server.database.DatabaseManager.delete_account', return_value=True):
            response = self.server.DeleteAccount(request, self.context)
            
            # Assert the response is correct
            self.assertEqual(response.status, service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS)
    
    
    
    def test_save_settings_success(self):
        # Create a request
        request = service_pb2.SaveSettingsRequest(username="testuser", setting=75)
        
        # Mock the DatabaseManager.save_settings method
        with patch('Server.database.DatabaseManager.save_settings', return_value=True):
            response = self.server.SaveSettings(request, self.context)
            
            # Assert the response is correct
            self.assertEqual(response.status, service_pb2.SaveSettingsResponse.SaveSettingsStatus.SUCCESS)

    
    

if __name__ == "__main__":
    unittest.main()