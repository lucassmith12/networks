import socket, json, threading, time, sys

SERVER = ('localhost', 5555)

def send_join(sock, router_id):
    msg = {"type": "JOIN", "router_id": router_id}
    sock.sendto(json.dumps(msg).encode(), SERVER)

def update_distance_vector(my_id, neighbors, dv_table, neighbor_dvs):
    updated = False
    for dest in dv_table:
        if dest == my_id:
            continue
        min_cost = float('inf')
        for neighbor in neighbors:
            if dest in neighbor_dvs[neighbor]:
                min_cost = min(min_cost, neighbors[neighbor] + neighbor_dvs[neighbor][dest])
        if dv_table[dest] != min_cost:
            dv_table[dest] = min_cost
            updated = True
    return updated

def main(router_id):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(('', 0))
    send_join(sock, router_id)

    dv = {}
    neighbors = {}
    neighbor_dvs = {}

    while True:
        msg, _ = sock.recvfrom(4096)
        data = json.loads(msg.decode())
        if data["type"] == "RESPONSE":
            neighbors = data["neighbors"]
            dv = {n: neighbors[n] if neighbors[n] >= 0 else float('inf') for n in "uvwxyz"}
            dv[router_id] = 0
            neighbor_dvs = {n: {k: float('inf') for k in "uvwxyz"} for n in neighbors}
            break

    def listen():
        while True:
            msg, _ = sock.recvfrom(4096)
            data = json.loads(msg.decode())
            if data["type"] == "UPDATE":
                neighbor_id = data["router_id"]
                neighbor_dvs[neighbor_id] = data["dv"]
    
    threading.Thread(target=listen, daemon=True).start()

    while True:
        time.sleep(2)
        updated = update_distance_vector(router_id, neighbors, dv, neighbor_dvs)
        if updated:
            msg = {"type": "UPDATE", "router_id": router_id, "dv": dv}
            sock.sendto(json.dumps(msg).encode(), SERVER)
        else:
            print(f"Router {router_id} stabilized. Final DV: {dv}")
            break

if __name__ == "__main__":
    main(sys.argv[1])
