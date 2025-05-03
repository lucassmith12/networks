import socket, select, json

CONFIG_FILE = "topology.txt"
PORT = 5555
EPOLLIN = select.EPOLLIN

def load_topology():
    topology = {}
    with open(CONFIG_FILE) as f:
        for line in f:
            parts = line.strip().split()
            router = parts[0]
            neighbors = {}
            for entry in parts[1:]:
                node, cost = entry.strip("<>").split(",")
                neighbors[node] = int(cost)
            topology[router] = neighbors
    return topology

def main():
    topology = load_topology()
    router_addrs = {}
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', PORT))
    sock.setblocking(False)
    epoll = select.epoll()
    epoll.register(sock.fileno(), EPOLLIN)

    try:
        while True:
            for fd, event in epoll.poll(1):
                if fd == sock.fileno():
                    msg, addr = sock.recvfrom(4096)
                    data = json.loads(msg.decode())
                    cmd = data["type"]
                    rid = data["router_id"]

                    if cmd == "JOIN":
                        router_addrs[rid] = addr
                        neighbors = topology[rid]
                        sock.sendto(json.dumps({
                            "type": "RESPONSE",
                            "router_id": rid,
                            "neighbors": neighbors
                        }).encode(), addr)

                    elif cmd == "UPDATE":
                        for neighbor in topology[rid]:
                            if neighbor in router_addrs:
                                sock.sendto(json.dumps(data).encode(), router_addrs[neighbor])
    finally:
        epoll.unregister(sock.fileno())
        epoll.close()
        sock.close()

if __name__ == "__main__":
    main()
