import sys
import os
import grpc
import argparse
import logging
import socket # For retrieving local IP address only
from concurrent import futures
# Handle our file paths properly.
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from proto import service_pb2
from proto import service_pb2_grpc
from MessageServer import MessageServer


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
def serve(ip, port, ip_connect=None, port_connect=None):
    # Create our connection and launch the MessageServer.
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    service_pb2_grpc.add_MessageServerServicer_to_server(MessageServer(ip, port, ip_connect, port_connect), server)
    server.add_insecure_port(f'{ip}:{port}')
    server.start()
    logger.info(f"Server started on port {port} for ip {ip}")
    server.wait_for_termination()


# MARK: Command-line arguments.
def validate_ip(value):
    """Validate an IP address"""
    try:
        # Try to convert the value to a valid IP address using socket library
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

    parser.add_argument(
        '--port_connect',
        type=int,
        default=None,
        help='Server port to connect to'
    )

    parser.add_argument(
        '--ip_connect',
        type=validate_ip,
        default=None,
        help='Server IP to connect to'
    )

    return parser.parse_args()

# MARK: MAIN
if __name__ == "__main__":
    # Set up arguments.
    args = parse_arguments()
    ip = args.ip
    port = args.port
    ip_connect = args.ip_connect
    port_connect = args.port_connect

    # Start our server
    serve(ip, str(port), ip_connect, port_connect)