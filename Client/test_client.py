import unittest
from unittest.mock import MagicMock, patch
import sys
import os
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.append(project_root)
from proto import service_pb2
from proto import service_pb2_grpc
from datetime import datetime

class TestClient(unittest.TestCase):
    def setUp(self):
        class SimpleClient:
            def __init__(self):
                self.stub = None
                self.current_user = None
                self.active = True
            
            def _handle_login(self, username, password):
                response = self.stub.Login(service_pb2.LoginRequest(username=username, password=password))
                if response.status == service_pb2.LoginResponse.LoginStatus.SUCCESS:
                    self.current_user = username
                    return True
                return False
            
            def _handle_register(self, username, password, email):
                response = self.stub.Register(service_pb2.RegisterRequest(
                    username=username, 
                    password=password, 
                    email=email
                ))
                return response.status == service_pb2.RegisterResponse.RegisterStatus.SUCCESS
            
            def _handle_send_message(self, recipient, message):
                response = self.stub.SendMessage(service_pb2.Message(
                    sender=self.current_user,
                    recipient=recipient,
                    message=message,
                    timestamp=str(datetime.now())
                ))
                return response
            
            def _handle_get_users(self):
                users = []
                responses = self.stub.GetUsers(service_pb2.GetUsersRequest(username=self.current_user))
                for response in responses:
                    if response.status == service_pb2.GetUsersResponse.GetUsersStatus.SUCCESS:
                        users.append(response.username)
                return users
            
            def _handle_get_pending_messages(self):
                pending_messages = {}
                responses = self.stub.GetPendingMessage(service_pb2.PendingMessageRequest(username=self.current_user))
                for response in responses:
                    if response.status == service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS:
                        sender = response.message.sender
                        if sender not in pending_messages:
                            pending_messages[sender] = []
                        pending_messages[sender].append({
                            'sender': sender,
                            'message': response.message.message,
                            'timestamp': response.message.timestamp
                        })
                return pending_messages
            
            def _handle_delete_account(self):
                response = self.stub.DeleteAccount(service_pb2.DeleteAccountRequest(username=self.current_user))
                if response.status == service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS:
                    self.current_user = None
                    self.active = False
                    return True
                return False
            
            def _handle_save_settings(self, setting_value):
                response = self.stub.SaveSettings(service_pb2.SaveSettingsRequest(
                    username=self.current_user,
                    setting=setting_value
                ))
                return response.status == service_pb2.SaveSettingsResponse.SaveSettingsStatus.SUCCESS
            
            def _handle_get_settings(self):
                response = self.stub.GetSettings(service_pb2.GetSettingsRequest(username=self.current_user))
                if response.status == service_pb2.GetSettingsResponse.GetSettingsStatus.SUCCESS:
                    return response.setting
                return 50  # Default value
        
        # Mock the gRPC stub
        self.stub = MagicMock()
        
        # Create a client instance with the mock stub
        self.client = SimpleClient()
        self.client.stub = self.stub
        self.client.current_user = "testuser"
    
    def test_login_success(self):
        # Mock the login response
        mock_response = MagicMock()
        mock_response.status = service_pb2.LoginResponse.LoginStatus.SUCCESS
        self.stub.Login.return_value = mock_response
        
        # Call the login method
        result = self.client._handle_login("testuser", "testpassword")
        
        # Assert the stub was called correctly
        self.stub.Login.assert_called_with(
            service_pb2.LoginRequest(username="testuser", password="testpassword")
        )
        
        # Assert the result is correct
        self.assertTrue(result)
        self.assertEqual(self.client.current_user, "testuser")
    
    def test_login_failure(self):
        # Mock the login response for failure
        mock_response = MagicMock()
        mock_response.status = service_pb2.LoginResponse.LoginStatus.FAILURE
        self.stub.Login.return_value = mock_response
        
        # Call the login method
        result = self.client._handle_login("wronguser", "wrongpassword")
        
        # Assert the stub was called correctly
        self.stub.Login.assert_called_with(
            service_pb2.LoginRequest(username="wronguser", password="wrongpassword")
        )
        
        # Assert the result is correct
        self.assertFalse(result)
    
    def test_register_success(self):
        # Mock the register response
        mock_response = MagicMock()
        mock_response.status = service_pb2.RegisterResponse.RegisterStatus.SUCCESS
        self.stub.Register.return_value = mock_response
        
        # Call the register method
        result = self.client._handle_register("newuser", "newpassword", "new@example.com")
        
        # Assert the stub was called correctly
        self.stub.Register.assert_called_with(
            service_pb2.RegisterRequest(
                username="newuser", 
                password="newpassword", 
                email="new@example.com"
            )
        )
        
        # Assert the result is correct
        self.assertTrue(result)
    
    def test_send_message(self):
        # Mock the send message response
        mock_response = MagicMock()
        mock_response.status = service_pb2.MessageResponse.MessageStatus.SUCCESS
        self.stub.SendMessage.return_value = mock_response
        
        # Call the send message method
        result = self.client._handle_send_message("recipient", "Hello!")
        
        # Assert the stub was called with the right parameters
        self.stub.SendMessage.assert_called_once()
        call_args = self.stub.SendMessage.call_args[0][0]
        self.assertEqual(call_args.sender, "testuser")
        self.assertEqual(call_args.recipient, "recipient")
        self.assertEqual(call_args.message, "Hello!")
    
    def test_get_users(self):
        # Mock the GetUsers response
        mock_response1 = MagicMock()
        mock_response1.status = service_pb2.GetUsersResponse.GetUsersStatus.SUCCESS
        mock_response1.username = "user1"
        
        mock_response2 = MagicMock()
        mock_response2.status = service_pb2.GetUsersResponse.GetUsersStatus.SUCCESS
        mock_response2.username = "user2"
        
        self.stub.GetUsers.return_value = [mock_response1, mock_response2]
        
        # Call the get users method
        users = self.client._handle_get_users()
        
        # Assert the stub was called correctly
        self.stub.GetUsers.assert_called_with(
            service_pb2.GetUsersRequest(username="testuser")
        )
        
        # Assert the result is correct
        self.assertEqual(users, ["user1", "user2"])
    
    def test_get_pending_messages(self):
        # Create mock messages
        message1 = MagicMock()
        message1.sender = "user1"
        message1.message = "Hello!"
        message1.timestamp = "2023-01-0 1 12:00:00"
        
        message2 = MagicMock()
        message2.sender = "user1"
        message2.message = "How are you?"
        message2.timestamp = "2023-01-01 12:01:00"
        
        message3 = MagicMock()
        message3.sender = "user2"
        message3.message = "Hi there!"
        message3.timestamp = "2023-01-01 12:02:00"
        
        # Mock the GetPendingMessage responses
        mock_response1 = MagicMock()
        mock_response1.status = service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS
        mock_response1.message = message1
        
        mock_response2 = MagicMock()
        mock_response2.status = service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS
        mock_response2.message = message2
        
        mock_response3 = MagicMock()
        mock_response3.status = service_pb2.PendingMessageResponse.PendingMessageStatus.SUCCESS
        mock_response3.message = message3
        
        self.stub.GetPendingMessage.return_value = [mock_response1, mock_response2, mock_response3]
        
        # Call the get pending messages method
        pending_messages = self.client._handle_get_pending_messages()
        
        # Assert the stub was called correctly
        self.stub.GetPendingMessage.assert_called_with(
            service_pb2.PendingMessageRequest(username="testuser")
        )
        
        # Assert the result is correct
        self.assertEqual(len(pending_messages), 2)  # Two senders
        self.assertEqual(len(pending_messages["user1"]), 2)  # Two messages from user1
        self.assertEqual(len(pending_messages["user2"]), 1)  # One message from user2
        self.assertEqual(pending_messages["user1"][0]["message"], "Hello!")
        self.assertEqual(pending_messages["user2"][0]["message"], "Hi there!")
    
    def test_delete_account_success(self):
        # Mock the DeleteAccount response
        mock_response = MagicMock()
        mock_response.status = service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS
        self.stub.DeleteAccount.return_value = mock_response
        
        # Call the delete account method
        result = self.client._handle_delete_account()
        
        # Assert the stub was called correctly
        self.stub.DeleteAccount.assert_called_with(
            service_pb2.DeleteAccountRequest(username="testuser")
        )
        
        # Assert the result is correct
        self.assertTrue(result)
        self.assertIsNone(self.client.current_user)
        self.assertFalse(self.client.active)
    
    def test_delete_account_failure(self):
        # Mock the DeleteAccount response for failure
        mock_response = MagicMock()
        mock_response.status = service_pb2.DeleteAccountResponse.DeleteAccountStatus.FAILURE
        self.stub.DeleteAccount.return_value = mock_response
        
        # Call the delete account method
        result = self.client._handle_delete_account()
        
        # Assert the result is correct
        self.assertFalse(result)
        self.assertEqual(self.client.current_user, "testuser")  # User should remain logged in
    
    def test_save_settings(self):
        # Mock the SaveSettings response
        mock_response = MagicMock()
        mock_response.status = service_pb2.SaveSettingsResponse.SaveSettingsStatus.SUCCESS
        self.stub.SaveSettings.return_value = mock_response
        
        # Call the save settings method
        result = self.client._handle_save_settings(75)
        
        # Assert the stub was called correctly
        self.stub.SaveSettings.assert_called_with(
            service_pb2.SaveSettingsRequest(username="testuser", setting=75)
        )
        
        # Assert the result is correct
        self.assertTrue(result)
    
    def test_get_settings(self):
        # Mock the GetSettings response
        mock_response = MagicMock()
        mock_response.status = service_pb2.GetSettingsResponse.GetSettingsStatus.SUCCESS
        mock_response.setting = 75
        self.stub.GetSettings.return_value = mock_response
        
        # Call the get settings method
        setting = self.client._handle_get_settings()
        
        # Assert the stub was called correctly
        self.stub.GetSettings.assert_called_with(
            service_pb2.GetSettingsRequest(username="testuser")
        )
        
        # Assert the result is correct
        self.assertEqual(setting, 75)
    
    def test_get_settings_failure(self):
        # Mock the GetSettings response for failure
        mock_response = MagicMock()
        mock_response.status = service_pb2.GetSettingsResponse.GetSettingsStatus.FAILURE
        self.stub.GetSettings.return_value = mock_response
        
        # Call the get settings method
        setting = self.client._handle_get_settings()
        
        # Assert the result is the default value
        self.assertEqual(setting, 50)

if __name__ == "__main__":
    unittest.main()