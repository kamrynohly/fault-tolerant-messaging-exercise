import sys
import os
import grpc
import uuid
from datetime import datetime
import argparse
import logging
import socket # For retrieving local IP address only
from collections import defaultdict
from concurrent import futures
# Handle our file paths properly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
from AuthHandler import AuthHandler
from DatabaseManager import DatabaseManager
from MessageServer import MessageServer
from ReplicaServer import ReplicaServer

# MARK: Initialize Logger
# Configure logging set-up. We want to log times & types of logs, as well as
# function names & the subsequent message.
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(funcName)s - %(message)s'
)

# Create a logger
logger = logging.getLogger(__name__)

# MARK: Server Initialization

def serve(ip, port):
    primary_server_channel = grpc.insecure_channel('127.0.0.1:5001')  # Replace with actual second server address
    primary_server_stub = service_pb2_grpc.MessageServerStub(primary_server_channel)

    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))

    service_pb2_grpc.add_MessageServerServicer_to_server(ReplicaServer(ip, port, primary_server_stub), server)
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