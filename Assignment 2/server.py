import socket

PROXY = "127.0.0.1"
PROXY_PORT = 5555
PROXY_ADDR = (PROXY, PROXY_PORT)

def start():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.bind(PROXY_ADDR)
    print(f'Server on {PROXY}:{PROXY_PORT}')
    return server

def handle_client(conn, addr):
    print(f'[NEW CONNECTION] {addr}')

    connected = True
    while connected:
        msg = conn.recv(HEADER).decode(FORMAT)
        if msg:
            if msg == DC_MSG:
                print(f'[DISCONNECTING] {addr}')
                connected = False
                return
            print(f'[{addr}] {msg}')
            ack = f'ACK {msg}'
            conn.send(ack.encode())
            
server = start()
while True:
    server.listen(5)
    (connection, address) = server.accept()
    print('Blocking Start')
    handle_client(connection, address)
    print('Blocking End')

    