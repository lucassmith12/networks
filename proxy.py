'''
Lucas Smith (ljs174)
CSDS 325 Project 1
'''

import socket
import sys
import uuid
import json
import select


def get_servers(config):
    """
    Loads and returns the backend servers from the configuration file.
    
    Args:
        config (str): Path to the configuration file containing server information.
    
    Returns:
        list: A list of backend servers, each represented as a dictionary containing 'ip' and 'port'.
    """
    with open(config) as f:
        servers = json.load(f)
    return servers['backend_servers']


class Proxy:
    def __init__(self, host, port, config, buffer):
        """
        Initializes the Proxy class and sets up necessary properties.
        
        Args:
            host (str): Host address for the proxy server.
            port (int): Port number for the proxy server.
            config (str): Path to the configuration file containing backend servers.
            buffer (int): Size of the buffer for reading data.
        """
        self.config = config
        self.servers = [f"{dct['ip']}:{dct['port']}" for dct in get_servers(config)]
        self.host = host
        self.port = port
        self.buffer = buffer
        self.serverNo = 0
        self.server_socks = {}
        self.client_socks = {}
        self.requests = {}
        self.sock = None
        self.epoll = select.epoll()
        self.setup()

    def setup(self):
        """
        Sets up the proxy server, binds it to the specified host and port, and listens for incoming connections.
        Registers the proxy socket with the epoll instance.
        """
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.host, self.port))
        self.sock.listen(5)
        self.sock.setblocking(False)
        self.epoll.register(self.sock.fileno(), select.EPOLLIN | select.EPOLLET)
        print(f'Proxy listening on {self.host}:{self.port}')

    def handle_request(self, conn, addr):
        """
        Handles a new incoming client connection, adds it to the client sockets dictionary.
        
        Args:
            conn (socket.socket): The client connection socket.
            addr (tuple): The address of the client.
        """
        print(f'[NEW CONNECTION] {addr} connected')
        self.client_socks[conn.fileno()] = {
            'sock': conn,
            'read': b'',
            'write': b'',
            'active_reqs': {}
        }

    def handle_client(self, fileNo, event):
        """
        Handles events for the client side of the connection. This includes reading data from the client and sending
        data back if necessary. It also handles client disconnections and errors.
        
        Args:
            fileNo (int): The file descriptor of the client connection.
            event (int): The event that triggered this handler.
        """
        client = self.client_socks[fileNo]

        if event & (select.EPOLLHUP | select.EPOLLERR):
            self.cleanup(fileNo, self.client_socks)
            if not client:
                return

        elif event & select.EPOLLIN:
            try:
                recvData = client['sock'].recv(self.buffer)
                if not recvData:
                    self.cleanup(fileNo, self.client_socks)
                    return
                client['read'] += recvData
                self.read_req(fileNo)

            except ConnectionResetError:
                self.cleanup(fileNo, self.client_socks)

        elif event & select.EPOLLOUT:
            if client['write']:
                try:
                    msg = client['sock'].send(client['write'])
                    client['write'] = client['write'][msg:]
                except ConnectionResetError:
                    self.cleanup(fileNo, self.client_socks)
            else:
                self.epoll.modify(fileNo, select.EPOLLIN)

    def cleanup(self, fileNo, socks):
        """
        Cleans up a connection, unregisters the socket from epoll, and closes the socket.
        
        Args:
            fileNo (int): The file descriptor of the socket to clean up.
            socks (dict): The dictionary of client or server sockets.
        """
        self.epoll.unregister(fileNo)
        socks[fileNo]['sock'].close()
        print(f'Closed Connection to {socks[fileNo]["sock"]}')

        del socks[fileNo]
        

    def read_req(self, fileNo):
        """
        Reads the request data from the client socket and sends it to the backend server after processing the request.
        
        Args:
            fileNo (int): The file descriptor of the client connection.
        """
        client = self.client_socks[fileNo]
        while True:
            header = client['read'].find(b'\r\n\r\n')
            if header < 0:
                break

            headers = client['read'][:header + 4]
            body = client['read'][header + 4:]
            header_list = headers.split(b'\r\n')

            first = header_list[0].decode().split()
            if len(first) < 3:
                break

            method, path, version = first[:3]
            content_length = 0

            for h in header_list[1:]:
                if b':' in h:
                    k, v = h.split(b':', 1)
                    k, v = k.strip().decode().lower(), v.strip().decode()
                    if k == 'content-length':
                        content_length = int(v)

            total_length = header + 4 + content_length
            if len(client['read']) < total_length:
                break

            request_data = client['read'][:total_length]
            client['read'] = client['read'][total_length:]
            self.send_req(fileNo, request_data)

    def send_req(self, fileNo, request):
        """
        Sends the client request to a backend server after modifying the headers to include a unique request ID.
        
        Args:
            fileNo (int): The file descriptor of the client connection.
            request (bytes): The raw HTTP request data from the client.
        """
        server = None
        for _ in range(len(self.servers)):
            server = self.select_server()
            backend = self.backend_connect(get_servers(self.config)[server])
            if backend:
                break

        if not backend:
            self.err(fileNo)

        req_id = str(uuid.uuid4())
        head, body = request.split(b'\r\n\r\n', 1)
        headers = head.replace(b'\r\n', b'\n').decode().split('\n')
        new_headers = [h for h in headers if not h.startswith('X-Request-ID:')]
        new_headers.insert(1, f'X-Request-ID: {req_id}')
        modified_headers = (
            '\r\n\r\n'.join(new_headers).encode() + b'\r\n\r\n' + body
        )

        self.server_socks[backend]['write'] += modified_headers
        self.server_socks[backend]['request'] = req_id
        self.server_socks[backend]['client'] = fileNo
        self.requests[req_id] = fileNo

        client = self.client_socks[fileNo]
        client['active_reqs'][req_id] = fileNo

        self.epoll.modify(backend, select.EPOLLOUT)

    def err(self, fileNo):
        """
        Sends an error response (502 Bad Gateway) to the client if a backend server could not be connected to.
        
        Args:
            fileNo (int): The file descriptor of the client connection.
        """
        client = self.client_socks[fileNo]
        client['write'] += b'HTTP/1.1 502 Bad Gateway\r\n\r\n'
        self.epoll.modify(fileNo, select.EPOLLOUT)

    def backend_connect(self, server):
        """
        Connects to a backend server and registers the socket with the epoll instance.
        
        Args:
            server (dict): A dictionary containing the 'ip' and 'port' of the backend server.
        
        Returns:
            int: The file descriptor of the connected backend server, or None if the connection fails.
        """
        backend = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        backend.setblocking(False)

        try:
            backend.connect((server['ip'], server['port']))
        except BlockingIOError:
            pass
        except Exception as e:
            print(f'Could not connect to server: {e}')
            return None

        fileNo = backend.fileno()
        self.epoll.register(fileNo, select.EPOLLOUT)

        self.server_socks[fileNo] = {
            'sock': backend,
            'client': None,
            'request': None,
            'read': b'',
            'write': b'',
            'server': server
        }
        return fileNo

    def handle_server(self, fileNo, event):
        """
        Handles events for the server side of the connection, including sending and receiving data from the backend server.
        
        Args:
            fileNo (int): The file descriptor of the server connection.
            event (int): The event that triggered this handler.
        """
        server = self.server_socks[fileNo]
        if event & (select.EPOLLHUP or select.EPOLLERR):
            self.cleanup(fileNo, self.server_socks)
            return

        if event & select.EPOLLOUT:
            if server['write']:
                try:
                    sent = server['sock'].send(server['write'])
                    server['write'] = server['write'][sent:]
                    
                except:
                    print(f'Bad request to backend {server["sock"]}')
                    self.cleanup(fileNo, self.server_socks)
                    return
            if not server['write']:
                self.epoll.modify(fileNo, select.EPOLLIN)

        elif event & select.EPOLLIN:
            try:
                recvData = server['sock'].recv(self.buffer)
                if not recvData:
                    self.cleanup(fileNo, self.server_socks)
                    return
                server['read'] += recvData
                self.process_response(self, fileNo)
            except:
                self.cleanup(fileNo, self.server_socks)

    def process_response(self, fileNo):
        """
        Processes the response from the backend server and sends it back to the client.
        
        Args:
            fileNo (int): The file descriptor of the server connection.
        """
        server = self.server_socks[fileNo]

        if b'\r\n\r\n' not in server['read']:
            return
        head = server['read'].find(b'\r\n\r\n') + 4
        split = server['read'][:head]
        header_list = split.split(b'\r\n')

        req_id = None
        for header in header_list:
            if header.startswith(b'X-Request-ID:'):
                req_id = header.split(b':', 1)[1].strip().decode()
                break

        if not req_id:
            print('Could not find a request id')
            self.cleanup(fileNo, self.server_socks)

        client = self.requests[req_id].pop(req_id, None)
        if client is None:
            print(f'Bad Request ID: {req_id}')
            self.cleanup(fileNo, self.server_socks)
            return

        client['read'] += server['read']
        server['read'] = b''

        if req_id in client['active_reqs']:
            del client['active_reqs'][req_id]

        self.epoll.modify(fileNo, select.EPOLLOUT)
        self.cleanup(fileNo, self.server_socks)

    def select_server(self):
        """
        Selects the next server in the round-robin fashion.
        
        Returns:
            str: The address of the selected backend server.
        """
        s = self.serverNo 
        self.serverNo = (1+ self.serverNo) % len(self.servers)
        return s

    def start(self):
        """
        Starts the proxy server, accepts connections, and processes events for both client and server sides.
        """
        read_only = select.EPOLLIN | select.EPOLLPRI | select.EPOLLHUP | select.EPOLLERR
        for server in self.servers:
            print(server)

        try:
            while True:
                events = self.epoll.poll(1)

                for fileNo, event in events:
                    if fileNo == self.sock.fileno():
                        connection, addr = self.sock.accept()
                        connection.setblocking(False)
                        self.epoll.register(connection.fileno(), select.EPOLLIN | select.EPOLLET)
                        self.handle_request(connection, addr)
                    elif fileNo in self.client_socks:
                        self.handle_client(fileNo, event)
                    elif fileNo in self.server_socks:
                        self.handle_server(fileNo, event)

        except Exception as e:
            print(f'Error occurred: {e}')

        finally:
            self.epoll.unregister(self.sock.fileno())
            self.epoll.close()
            self.sock.close()


if __name__ == "__main__":
    
    BUFFER = 4096
    HOST = "127.0.0.1"
    PROXYPORT = 9999
    if len(sys.argv) < 2:
        print('Did you forget servers.conf argument?')
        raise AssertionError
    CONFIG = sys.argv[1]
    
    proxy = Proxy(HOST, PROXYPORT, CONFIG, BUFFER)
    proxy.start()
