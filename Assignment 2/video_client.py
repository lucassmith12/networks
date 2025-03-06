import socket
import time
import xml.etree.ElementTree as ET

BUFFER = 4096
FORMAT = 'utf-8'
SERVER = "149.165.170.233"
PORT = 80
ADDRESS = (SERVER, PORT)
PATH = "/vod/manifest.mpd"
REQUEST = f"GET {PATH} HTTP/1.1\r\nHost: {SERVER}\r\nConnection:close\r\n\r\n"


def get_manifest(msg):
    ''' Return manifest document'''
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect(ADDRESS)
    message = msg.encode(FORMAT)
    client.send(message)
    print("sent!")
    manifest = b''
    while True:
        chunk = client.recv(BUFFER)  
        if not chunk:
            break  
        manifest += chunk  

    client.close()
    return manifest.decode(FORMAT)
    
def parse_response(response: str):
    ''' Parse an HTTP Response into headers and body '''
    ressplit = response.split('\r\n\r\n', 1)
    headers = ressplit[0]
    body = ressplit[1] if len(ressplit) > 1 else ""
    return headers, body

def parse_mpd(mpd_body: str):
    ''' Returns a dictionary of each bitrate's {id(Kbps):bandwidth(bps)}'''

    try:
        root = ET.fromstring(mpd_body)
        namespace = {"mpd": "urn:mpeg:dash:schema:mpd:2011"}
        representations = root.findall(".//mpd:Representation", namespaces=namespace)
        res = {}

        for r in representations:
            res[int(r.attrib.get("id", "unknown"))] = int(r.attrib.get("bandwidth", "unknown"))
        return res
            
    except ET.ParseError as e:
        print(f"XML Parse Error: {e}")
        return {}

def get_segment(path, segment):
    client = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    client.connect((SERVER, PORT))
    
    request = f"GET /vod/{path}{segment} HTTP/1.1\r\nHost: {SERVER}\r\nConnection: close\r\n\r\n"
    client.send(request.encode(FORMAT))

    response = b""  # Using bytes to handle binary data
    while True:
        chunk = client.recv(BUFFER)
        if not chunk:
            break
        response += chunk  # Append chunk to response data
    
    client.close()    
    response = response.decode(FORMAT, errors='ignore')
    return response
    
def get_bitrates():    
    ''' Returns bitrates in terms of Kbps sorted in descending order '''
    manifest = get_manifest(REQUEST)
    headers, mpd_body = parse_response(manifest)
    representations = parse_mpd(mpd_body)
    return sorted(representations.keys(), reverse=True)

def select_bitrate(avg_tput):
    ''' Returns the highest bitrate such that average throughput (Kbps) is 50% larger.
        If no bitrate is small enough, return the smallest. '''
    bitrates = get_bitrates()
    print(bitrates)
    for rate in bitrates:
        if avg_tput >= rate * 1.5 :
            return rate
    return bitrates[-1] 


print(f'Bitrate chosen:{select_bitrate(150)}')

