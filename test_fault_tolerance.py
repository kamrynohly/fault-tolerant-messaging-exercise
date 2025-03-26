import unittest
import time
import sys
import os
import random

# Import the test framework components
from test_framework import ServerInstance, TestClient, logger

class FaultToleranceTest(unittest.TestCase):
    
    def setUp(self):
        """Set up the test environment with multiple servers"""
        # Start leader server
        self.leader = ServerInstance("127.0.0.1", 5001)
        self.leader.start()
        # self.assertTrue(self.leader.start())
        
        # Start follower servers
        self.follower1 = ServerInstance("127.0.0.1", 5002, "127.0.0.1", 5001)
        self.follower1.start()
        # self.assertTrue(self.follower1.start())
        
        self.follower2 = ServerInstance("127.0.0.1", 5003, "127.0.0.1", 5001)
        self.follower2.start()
        # self.assertTrue(self.follower2.start())
        
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
    
    def test_leader_failure(self):
        """Test system continues when leader fails"""
        # Create and register test users
        alice = TestClient("alice_ft")
        bob = TestClient("bob_ft")
        
        # Connect to the leader
        alice.connect_to_server(self.leader)
        bob.connect_to_server(self.leader)
        
        # Register users
        # self.assertTrue(alice.register())
        self.assertTrue(bob.register())
        
        # Send an initial message
        message1 = f"Message before failure"
        success, _ = alice.send_message(bob.username, message1)
        
        self.assertTrue(success)
        
        # Kill the leader
        logger.info("Killing leader server to simulate failure")
        self.leader.stop()
        time.sleep(10)  # Allow time for leader election
        
        # Connect to one of the remaining servers (new leader should be elected)
        alice.disconnect()
        bob.disconnect()
        
        alice.connect_to_server(self.follower1)
        bob.connect_to_server(self.follower1)
        
        # Try to login
        self.assertTrue(alice.login())
        self.assertTrue(bob.login())
        
        # Send a new message after failure
        message2 = f"Message after failure"
        success, _ = alice.send_message(bob.username, message2)
        self.assertTrue(success)
        
        # Verify bob can retrieve the message
        time.sleep(2)  # Wait for processing
        messages = bob.get_pending_messages()
        
        # Check both messages were delivered
        found_before = False
        found_after = False
        for msg in messages:
            if msg['sender'] == alice.username:
                if msg['message'] == message1:
                    found_before = True
                if msg['message'] == message2:
                    found_after = True
        
        self.assertTrue(found_before, "Message sent before failure was lost")
        self.assertTrue(found_after, "Message sent after failure didn't arrive")

if __name__ == '__main__':
    unittest.main()