import unittest
import time
import sys
import os
from datetime import datetime

# Import the test framework components
from test_framework import ServerInstance, TestClient, logger

class ReplicationTest(unittest.TestCase):
    
    def setUp(self):
        """Set up the test environment with multiple servers"""
        # Start leader server
        self.leader = ServerInstance("127.0.0.1", 5001)
        self.assertTrue(self.leader.start())
        
        # Start follower servers
        self.follower1 = ServerInstance("127.0.0.1", 5002, "127.0.0.1", 5001)
        self.assertTrue(self.follower1.start())
        
        self.follower2 = ServerInstance("127.0.0.1", 5003, "127.0.0.1", 5001)
        self.assertTrue(self.follower2.start())
        
        # Wait for system to stabilize
        time.sleep(5)
    
    def tearDown(self):
        """Clean up after the test"""
        if hasattr(self, 'leader'):
            self.leader.stop()
        if hasattr(self, 'follower1'):
            self.follower1.stop()
        if hasattr(self, 'follower2'):
            self.follower2.stop()
    
    def test_basic_replication(self):
        """Test that messages replicate across servers"""
        # Create and register test users
        alice = TestClient("alice")
        bob = TestClient("bob")
        
        # Connect to the leader
        alice.connect_to_server(self.leader)
        bob.connect_to_server(self.leader)
        
        # Register users
        self.assertTrue(alice.register())
        self.assertTrue(bob.register())
        
        # Login
        self.assertTrue(alice.login())
        self.assertTrue(bob.login())
        
        # Send a test message
        message = f"Test message at {datetime.now()}"
        success, timestamp = alice.send_message(bob.username, message)
        self.assertTrue(success)
        
        # Wait for replication
        time.sleep(2)
        
        # Check the message is available through all servers
        # Disconnect from leader, connect to follower
        bob.disconnect()
        bob.connect_to_server(self.follower1)
        self.assertTrue(bob.login())
        
        # Get pending messages from follower1
        messages = bob.get_pending_messages()
        
        # Verify message was replicated
        self.assertGreaterEqual(len(messages), 1)
        found = False
        for msg in messages:
            if msg['sender'] == alice.username and msg['message'] == message:
                found = True
                break
        self.assertTrue(found, "Message was not properly replicated to follower1")
        
        # Test another follower
        bob.disconnect()
        bob.connect_to_server(self.follower2)
        self.assertTrue(bob.login())
        
        # Get pending messages from follower2
        messages = bob.get_pending_messages()
        
        # Verify message was replicated
        self.assertGreaterEqual(len(messages), 1)
        found = False
        for msg in messages:
            if msg['sender'] == alice.username and msg['message'] == message:
                found = True
                break
        self.assertTrue(found, "Message was not properly replicated to follower2")

if __name__ == '__main__':
    unittest.main()