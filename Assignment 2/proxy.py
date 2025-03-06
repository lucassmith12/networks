import socket, select, re
import time
import xml.etree.ElementTree as ET

class Proxy:
    def __init__(self, ip, port, buffer):
        self.ip = ip
        self.port = port
        self.address = (ip, port)
        self.buffer_size = buffer
        self.format = 'utf-8'
        
        self.client_read = b''
        self.client_write = b''
        self.server_read = b''
        self.server_write = b''
        self.connections = {}

        self.dash_ip = "149.165.170.233"
        self.dash_port = 80
        self.dash_addr = (self.dash_ip, self.dash_port)
        self.sock = None
        self.server_sock = None
        self.avg_tput = 0
        self.epoll = select.epoll()
        self.setup()

    def setup(self):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.sock.bind((self.ip, self.port))
        self.sock.listen(5)
        self.sock.setblocking(False)
        self.epoll.register(self.sock.fileno(), select.EPOLLIN | select.EPOLLET)
        print(f'Proxy listening on {self.ip}:{self.port}')
        self.connect_server()
    def connect_server(self):  
        try:
            self.server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.server_sock.connect(self.dash_addr)
            print(f"Connected to DASH Server: {self.server_sock.getpeername()}")
            self.connections[self.server_sock.fileno()] = {"type": "server", "conn": self.server_sock, "start_time": None}
            self.epoll.register(self.server_sock.fileno(), select.EPOLLIN | select.EPOLLOUT)
        except Exception as e:
            print(f"Failed to connect to DASH server: {e}")

    def accept_request(self, fd):
        try:
            connection = self.connections[fd]["conn"]
            chunk = connection.recv(self.buffer_size)
            print("Request received from client")
            
            if not chunk:
                return
            
            request = chunk.decode(self.format, errors='ignore')
            print(f"Forwarding request: {request}")         
            self.server_write += request.encode(self.format)
            
            self.epoll.modify(fd, select.EPOLLIN | select.EPOLLOUT)
        except BlockingIOError:
            pass
        except Exception as e:
            print(f"Error in accept_request: {e}")

    def forward_request(self, fd):
        try:
            if self.server_write:
                sent = self.server_sock.send(self.server_write)
                self.server_write = self.server_write[sent:]
                print('Request forwarded to server')
            else:
                self.epoll.modify(fd, select.EPOLLIN)  # No data left to send
        except Exception as e:
            print(f"Error in forward_request: {e}")
            self.connect_server()
        
    def accept_response(self, fd):
        connection = self.connections[fd]["conn"]
        try:
            chunk = connection.recv(self.buffer_size)
        except Exception:
            chunk = b''  # Handle connection reset

        if chunk:
            self.server_read += chunk
        else:
            if self.server_read:
                self.client_write += self.server_read
                self.server_read = b''
                self.epoll.modify(fd, select.EPOLLOUT)  # Now ready to send to client
            else:
                connection.close() # No data at all, close connection
                
            self.server_read += chunk
            
            if not chunk:
                if self.server_read:
                    print("Response received from server")
                    self.client_write += self.server_read
                    self.server_read = b''
                    self.epoll.modify(fd, select.EPOLLOUT)
        
    def forward_response(self, fd):
        connection = self.connections[fd]["conn"]
        while self.client_write:
            try:
                sent = connection.send(self.client_write)
                print(f"Forwarded {sent} bytes to client \n{self.client_write}")
                self.client_write = self.client_write[sent:]
            except Exception as e:
                print(f"Error forwarding response: {e}")
                self.client_write = b''
                connection.close()
                
        
        if not self.client_write:
            self.epoll.modify(fd, select.EPOLLIN)
    
    def main_loop(self):
        try:
            while True:
                events = self.epoll.poll(1)
                for fd, event in events:
                    if fd == self.sock.fileno():
                        try:
                            client, addr = self.sock.accept()
                            print(f"[NEW CONNECTION] {addr} connected")
                            client.setblocking(False)
                            self.connections[client.fileno()] = {"type": 'client', "conn": client, "start_time": None}
                            self.epoll.register(client.fileno(), select.EPOLLIN)
                        except Exception as e:
                            print(f'Exception caught: {e}')
                            continue
                    elif self.connections[fd]["type"] == 'client':
                        if event & select.EPOLLIN:
                            self.accept_request(fd)
                        elif event & select.EPOLLOUT:
                            self.forward_request(fd)
                    elif self.connections[fd]["type"] == 'server':
                        if event & select.EPOLLIN:
                            self.accept_response(fd)
                        elif event & select.EPOLLOUT:
                            self.forward_response(fd)
                    elif event & (select.EPOLLHUP | select.EPOLLERR):
                        self.close_connection(fd)
        except KeyboardInterrupt:
            print('Force quitting the program')
        except Exception as e:
            print(e)
        finally:
            self.epoll.close()
            self.sock.close()
            self.server_sock.close
    
if __name__ == '__main__':
    dash_proxy = Proxy('127.0.0.1', 9999, 4096)
    dash_proxy.main_loop()
