import socket

client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
HEADER = 16
FORMAT = 'utf-8'
DC_MSG = 'DISCONNECTED'
SERVER = "127.0.0.1"
PORT = 5555
ADDRESS = (SERVER, PORT)


def send(msg):
    client.connect(ADDRESS)
    message = msg.encode(FORMAT)
    client.send(message)
    print("sent!")
    waiting = True
    while waiting:
        data = client.recv(HEADER)
        if data:
            print(f'Received response: {data}')    
            waiting = False
    
    client.send(DC_MSG.encode(FORMAT))
    # time.sleep(0.1)     #if you dont' hold off, the writes can be disrupted

send("SYN")
