
import sys, os
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

import os
import sqlite3
import unittest
from datetime import datetime, timedelta
from types import SimpleNamespace

# Import the server and its dependencies.
from MessageServer import MessageServer
from DatabaseManager import DatabaseManager
from proto import service_pb2


# --- Dummy Classes for Testing --- #

class DummyContext:
    """A dummy gRPC context with an is_active() method."""
    def is_active(self):
        return True

class OneTimeActiveContext:
    """A dummy context that is active only once (for MonitorMessages test)."""
    def __init__(self):
        self.calls = 0
    def is_active(self):
        if self.calls < 1:
            self.calls += 1
            return True
        return False

class DummyAuthHandler:
    """A dummy authentication handler that always returns success."""
    def register_user(self, username, password, email):
        return (True, "Registration successful")
    def authenticate_user(self, username, password):
        return (True, "Login successful")


# --- Test Suite --- #

class TestMessageServer(unittest.TestCase):
    def setUp(self):
        # Use a test-specific IP and port.
        self.ip = "127.0.0.1"
        self.port = "5001"
        # Instantiate the server as leader (no ip_connect/port_connect)
        self.server = MessageServer(self.ip, self.port)
        # Override the auth_manager with our dummy version.
        self.server.auth_manager = DummyAuthHandler()
        # Make sure the database is set up cleanly.
        self.db_file = f"{self.ip}_{self.port}.db"

    def tearDown(self):
        # Remove the database file after each test.
        if os.path.exists(self.db_file):
            os.remove(self.db_file)

    def test_register(self):
        request = SimpleNamespace(
            username="user1",
            password="pass1",
            email="user1@example.com",
            source="Client"
        )
        context = DummyContext()
        response = self.server.Register(request, context)
        # Check that the response indicates success.
        self.assertEqual(response.status, service_pb2.RegisterResponse.RegisterStatus.SUCCESS)
        self.assertEqual(response.message, "Registration successful")

    def test_login(self):
        request = SimpleNamespace(
            username="user1",
            password="pass1",
            source="Client"
        )
        context = DummyContext()
        response = self.server.Login(request, context)
        self.assertEqual(response.status, service_pb2.LoginResponse.LoginStatus.SUCCESS)
        self.assertEqual(response.message, "Login successful")

    def test_get_users(self):
        # Insert a dummy user into the users table.
        with sqlite3.connect(self.server.db_manager.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                ("user1", "hash", "user1@example.com")
            )
            conn.commit()
        request = SimpleNamespace(username="user1")
        context = DummyContext()
        responses = list(self.server.GetUsers(request, context))
        usernames = [resp.username for resp in responses if resp.username]
        self.assertIn("user1", usernames)

    

    def test_send_message_active(self):
        # Simulate an active client for recipient "user2".
        class ActiveClientStream:
            def is_active(self):
                return True
        self.server.active_clients["user2"] = ActiveClientStream()
        timestamp = str(datetime.now())
        request = SimpleNamespace(
            sender="user1",
            recipient="user2",
            message="Test message",
            timestamp=timestamp,
            source="Client"
        )
        context = DummyContext()
        response = self.server.SendMessage(request, context)
        self.assertEqual(response.status, service_pb2.MessageResponse.MessageStatus.SUCCESS)
        # Verify that the message was queued for streaming.
        self.assertGreater(len(self.server.message_queue["user2"]), 0)

    def test_send_message_inactive(self):
        # Ensure that "user3" is not active.
        if "user3" in self.server.active_clients:
            del self.server.active_clients["user3"]
        timestamp = str(datetime.now())
        request = SimpleNamespace(
            sender="user1",
            recipient="user3",
            message="Test message inactive",
            timestamp=timestamp,
            source="Client"
        )
        context = DummyContext()
        response = self.server.SendMessage(request, context)
        self.assertEqual(response.status, service_pb2.MessageResponse.MessageStatus.SUCCESS)
        # Check that the message was saved as pending (isPending == True).
        with sqlite3.connect(self.server.db_manager.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "SELECT isPending FROM messages WHERE sender=? AND recipient=? AND message=?",
                ("user1", "user3", "Test message inactive")
            )
            result = cursor.fetchone()
            self.assertIsNotNone(result)
            # SQLite stores Boolean True as 1.
            self.assertEqual(result[0], 1)

    def test_delete_account(self):
        # Insert a dummy user to be deleted.
        with sqlite3.connect(self.server.db_manager.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email) VALUES (?, ?, ?)",
                ("user_del", "hash", "user_del@example.com")
            )
            conn.commit()
        request = SimpleNamespace(username="user_del", source="Client")
        context = DummyContext()
        response = self.server.DeleteAccount(request, context)
        self.assertEqual(response.status, service_pb2.DeleteAccountResponse.DeleteAccountStatus.SUCCESS)
        # Verify that the user was removed from the database.
        with sqlite3.connect(self.server.db_manager.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute("SELECT * FROM users WHERE username=?", ("user_del",))
            result = cursor.fetchone()
            self.assertIsNone(result)

    def test_save_get_settings(self):
        # Insert a dummy user with default settings.
        with sqlite3.connect(self.server.db_manager.db_name) as conn:
            cursor = conn.cursor()
            cursor.execute(
                "INSERT INTO users (username, password_hash, email, settings) VALUES (?, ?, ?, ?)",
                ("user_set", "hash", "user_set@example.com", 50)
            )
            conn.commit()
        # First, test GetSettings.
        request_get = SimpleNamespace(username="user_set")
        context = DummyContext()
        response_get = self.server.GetSettings(request_get, context)
        self.assertEqual(response_get.setting, 50)
        # Then, update the settings via SaveSettings.
        request_save = SimpleNamespace(username="user_set", setting=100, source="Client")
        response_save = self.server.SaveSettings(request_save, context)
        self.assertEqual(response_save.status, service_pb2.SaveSettingsResponse.SaveSettingsStatus.SUCCESS)
        # Verify the updated settings.
        response_get2 = self.server.GetSettings(request_get, context)
        self.assertEqual(response_get2.setting, 100)


    def test_new_replica(self):
        request = SimpleNamespace(
            new_replica_id="replica1",
            ip="127.0.0.2",
            port="5002"
        )
        context = DummyContext()
        leader_response = self.server.NewReplica(request, context)
        self.assertIn("replica1", self.server.servers)
        self.assertEqual(leader_response.id, self.server.leader["id"])

    def test_get_servers(self):
        # Populate server.servers with dummy entries.
        self.server.servers = {
            "server1": {"ip": "127.0.0.2", "port": "5002", "stub": None, "heartbeat": datetime.now()},
            "server2": {"ip": "127.0.0.3", "port": "5003", "stub": None, "heartbeat": datetime.now()}
        }
        request = SimpleNamespace(requestor_id="server1")
        context = DummyContext()
        responses = list(self.server.GetServers(request, context))
        for resp in responses:
            self.assertNotEqual(resp.id, "server1")

    def test_monitor_messages(self):
        # Set up a message in the queue for a given user.
        self.server.message_queue["user_monitor"] = []
        # Use a proto Message to simulate a pending message.
        message = service_pb2.Message(
            sender="user1",
            recipient="user_monitor",
            message="Hello Monitor",
            timestamp=str(datetime.now())
        )
        self.server.message_queue["user_monitor"].append(message)
        request = SimpleNamespace(username="user_monitor", source="Client")
        context = OneTimeActiveContext()
        gen = self.server.MonitorMessages(request, context)
        try:
            msg = next(gen)
            self.assertEqual(msg.message, "Hello Monitor")
        except StopIteration:
            self.fail("MonitorMessages generator did not yield a message")

    def test_run_election(self):
        # Add dummy servers with fixed UUIDs.
        self.server.servers = {
            "a-replica": {"ip": "127.0.0.2", "port": "5002", "stub": None, "heartbeat": datetime.now()},
            "z-replica": {"ip": "127.0.0.3", "port": "5003", "stub": None, "heartbeat": datetime.now()}
        }
        # Force the leader to be a replica that is not the lowest.
        self.server.leader["id"] = "z-replica"
        self.server.run_election()
        expected_leader = min(["a-replica", "z-replica", self.server.server_id])
        self.assertEqual(self.server.leader["id"], expected_leader)

if __name__ == "__main__":
    unittest.main()
