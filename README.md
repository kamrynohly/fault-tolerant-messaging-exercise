# DIY Wire Protocol Chat Application
## Assignment 2 Updates:
### Updated Directory Structure
```
DIY-WIRE-PROTOCOL/
├── Client/
│   ├── UI/
│   │   ├── chat.py
│   │   └── signup.py
│   ├── main.py
│   └── test_client.py
├── Server/
│   ├── auth_handler.py
│   ├── database.py
│   ├── main.py
│   ├── test_server.py
│   └── service_actions.py
├── proto/
│   ├── service.proto
│   ├── service_pb2.py
│   └── service_pb2_grpc.py

```
## Updated Setup
1. Install the required packages:
    ```bash 
    pip install -r requirements.txt
    ```

2. Generate Protocol Buffer code (only needed if you modify the proto files):
   ```bash
   python -m grpc_tools.protoc -I./proto --python_out=. --grpc_python_out=. ./proto/service.proto
   ```

3. Start the leader server:
   ```bash
   python Server/main.py --ip your_ip --port 5001
   ```

4. Start any number of follower servers:
   ```bash
   python Server/main.py --ip your_ip --port 5002 --port_connect [any port number in the system] --ip_connect [any ip address in the system]
   ```

5. In a separate terminal, start the client:
   ```bash
   python Client/main.py --ip server_ip --port 5001
   ```
   You can use any server_ip and port number here, as the client will cycle through known servers from `client_config.py` to find a connection.


6. Run the tests:
   ```bash
   pytest Client/test_client.py
   pytest Server/test_server.py
   python test_fault_tolerance.py
   python test_replication.py
   ```


## gRPC  Specification

- **Service Definition**: Defined in `proto/service.proto` using the Protocol Buffers IDL
- **Generated Code**: The protocol compiler generates client and server code in `service_pb2.py` and `service_pb2_grpc.py`
- **RPC Methods**: Supports both unary calls (request-response) and streaming for real-time messaging
- **Message Types**: Strongly typed message definitions for all operations (login, registration, messaging, etc.)

Key gRPC services include:
- `Register`: User registration with email validation
- `Login`: User authentication
- `SendMessage`: Message delivery to recipients
- `GetUsers`: Retrieves available contacts
- `GetPendingMessage`: Streams pending messages to clients
- `MonitorMessages`: Real-time message monitoring via server streaming
- `DeleteAccount`: Account management
- `SaveSettings` and `GetSettings`: User preference management

---

# Assignment 1 Submission

## Overview
This project is a client-server chat application that implements a flexible wire protocol for messaging. It supports both a custom delimiter-based protocol and a JSON-based protocol, selectable via a command-line flag. The application features user authentication, real-time messaging, and a graphical user interface (GUI) built with Tkinter.

## Architecture

### Directory Structure
```
DIY-WIRE-PROTOCOL/
├── Client/
│   ├── Model/
│   │   └── ServerRequest.py
│   ├── UI/
│   │   ├── chat.py
│   │   └── signup.py
│   ├── main.py
│   └── test_client.py
├── Server/
│   ├── Model/
│   │   └── SerializationManager.py
│   ├── auth_handler.py
│   ├── database.py
│   ├── main.py
│   ├── test_server.py
│   └── service_actions.py
```

### Components
#### Client Side
- **UI Components** (`Client/UI/`)
  - **chat.py**: Main chat interface featuring message display, user search, inbox management, and settings.
  - **signup.py**: User registration (and login) interface.
  - *(Note: The dedicated `login.py` file has been merged into or replaced by the signup interface.)*
- **Core Modules** (`Client/`)
  - **main.py**: Application entry point, handles socket management and command-line argument parsing.
  - **communication_manager.py**: Manages all communications with the server.
  - **middleware.py**: Processes messages, implements the protocol, and routes commands.
- **Model** (`Client/Model/`)
  - **ServerRequest.py**: Provides functions to serialize and deserialize requests/responses using either the custom or JSON protocol.
- **Tests**
  - **test_client.py**: Contains test cases for client-side functionality including protocol parsing and UI interactions.
  - **test_server.py**: Contains test cases for server-side functionality including protocol parsing and networking connections.

#### Server Side
- **Core Modules** (`Server/`)
  - **main.py**: Server entry point that manages client connections and the socket server.
  - **auth_handler.py**: Handles user authentication and registration.
  - **database.py**: Manages all database operations via SQLite (automatically set up on first run).
  - **service_actions.py**: Implements business logic to handle different types of client requests.
  - **test_server.py**: Contains server-side tests (e.g., for serialization and protocol parsing).
- **Model** (`Server/Model/`)
  - **SerializationManager.py**: Provides functions for serializing responses and parsing requests using either protocol.


## Protocol Specification

The application supports **two protocols**:

1. **Custom Protocol**  
   Messages follow the format:  
   ```
   VERSION§LENGTH§OPCODE§ARGUMENTS∞
   ```  
   - **VERSION**: Numeric version of the protocol.
   - **LENGTH**: The character length of the operation-specific part (which is built by concatenating the opcode and its arguments, each separated by "§").
   - **OPCODE**: A string defining the operation (e.g., `LOGIN`, `SEND_MESSAGE`).
   - **ARGUMENTS**: Command-specific arguments. For list-type arguments, each element is appended with its own delimiter.
   - The message ends with a trailing "∞" marker.

2. **JSON Protocol**  
   The JSON protocol creates a message object that includes:
   - `version`: Protocol version.
   - `length`: Computed as `len(op_code) + len(arguments)` (number of arguments).
   - `opcode`: Operation code.
   - `arguments`: List of command-specific arguments.

## Running the Application

### Command-Line Options

Both client and server can run in either JSON mode or custom-protocol mode. To use the JSON protocol, simply include the `--isJSON true` flag when starting an application.

### Starting the Server
From the project root, start the server with:
```bash
python3 Server/main.py --port 5001 --version 1
```
- `5001` is the port number.
- `1` is the protocol version.
- Include `--isJSON true` to use the JSON protocol. Omit this flag to use the custom delimiter-based protocol.

### Starting the Client
From the project root, start the client with:
```bash
python3 Client/main.py --host your_ip --port 5001 --version 1
```
- `--host` specifies the server's IP address.
- `--port` specifies the server's port.
- `--version` specifies the server's port.
- Include `--isJSON true` if you want the client to communicate with the server using the JSON protocol.

## Setup and Installation

### Prerequisites
- Python 3.7+
- SQLite3 (for the database)
- Required Python packages (install via pip):
  ```bash
  pip install pytest pytest-mock
  ```
  *Note: Tkinter should be available with standard Python installations; if missing, install the appropriate package for your OS.*

### Database Setup
The SQLite database is automatically initialized with the required tables on the first run of the server application.

## Testing

Run the test suite using pytest from the project root:
```bash
python -m pytest -v
```
This runs tests for authentication, messaging, database operations, UI components, and protocol parsing/serialization on both client and server sides.

### Test Coverage
- **Client Side**:  
  - Authentication and registration interface.
  - Chat interface functionality.
  - ServerRequest serialization/deserialization.
  - UI component actions and error handling.
- **Server Side**:  
  - Request parsing and validation.
  - Serialization and deserialization using both the custom and JSON protocols.
  - Database operations.
  - Business logic and service actions.

## Features

### User Authentication
- Secure password hashing (e.g., SHA-256).
- Email validation and duplicate username prevention.
- Session management with active connection tracking.

### Messaging
- Real-time message delivery.
- Offline message queuing.
- Message history and user search functionality.

### User Interface
- Clean, intuitive design built with Tkinter.
- Message notifications and contact management.
- Configuration options for notifications and other settings.

## Error Handling

### Client-Side
- Connection loss detection and reconnection strategies.
- Input validation and user feedback for invalid actions.
- UI state management to handle errors gracefully.

### Server-Side
- Robust error handling for database connectivity.
- Validating and filtering malformed or invalid client requests.
- Managing protocol version mismatches and unexpected errors.

## Security Features

1. **Password Security**
   - SHA-256 hashing without storing plaintext passwords.
2. **Input Validation**
   - Strict email and username format verification.
   - Password strength and uniqueness checks.
3. **Session Management**
   - Active session tracking and proper session cleanup upon disconnection.

## Troubleshooting

### Common Issues

1. **Connection Errors**
   - Ensure the server is running and reachable.
   - Confirm that the host IP and port match between client and server.
2. **Database Errors**
   - Check file permissions for the SQLite database file.
   - Ensure the database schema is intact.
   - Delete users.db if needed.
  3. **Parsing Errors**
   - Ensure that both the server and client are either using JSON parsing, or the custom parsing.
   - Check by ensuring that both were run using the isJSON flag or without it. A mismatch will lead to errors. 

## Future Improvements

1. **Feature Enhancements**
   - Group chat support.
   - File sharing capabilities.
   - End-to-end message encryption.
   - Detailed user profiles.
2. **Technical Enhancements**
   - Connection pooling for improved performance.
   - Message compression and caching.
   - Load balancing for scaling the server.
   - Advanced logging and monitoring.
   - Adding a checksum to the protocol.
