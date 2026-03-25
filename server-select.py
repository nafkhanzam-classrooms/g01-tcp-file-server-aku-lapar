"""
server-select.py - Multi-client chat server with file transfer using select()
Uses the select module for non-blocking I/O multiplexing
"""

import socket
import select
import os

HOST = '0.0.0.0'
PORT = 5001
FILES_DIR = 'server_files'
BUFFER_SIZE = 4096

os.makedirs(FILES_DIR, exist_ok=True)

# Map socket -> {'addr': ..., 'buffer': str, 'upload': None or dict}
client_state = {}


def broadcast(message: str, sender_sock=None, sockets=None):
    """Broadcast a message to all clients except the sender."""
    for sock in (sockets or []):
        if sock is sender_sock:
            continue
        try:
            sock.sendall(message.encode())
        except Exception:
            pass


def send_file(conn, filename: str):
    filepath = os.path.join(FILES_DIR, filename)
    if not os.path.isfile(filepath):
        conn.sendall(b'ERROR: File not found\n')
        return
    filesize = os.path.getsize(filepath)
    conn.sendall(f'FILE {filename} {filesize}\n'.encode())
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            conn.sendall(chunk)
    print(f'[SEND] Sent "{filename}" ({filesize} bytes)')


def process_command(sock, line, read_sockets):
    """Process a single text command from a client."""
    addr = client_state[sock]['addr']
    state = client_state[sock]

    if line == '/list':
        files = os.listdir(FILES_DIR)
        reply = ('Files: ' + ', '.join(files) + '\n') if files else 'No files on server\n'
        sock.sendall(reply.encode())

    elif line.startswith('/upload '):
        parts = line.split(' ', 2)
        if len(parts) == 3:
            _, fname, fsize_str = parts
            try:
                fsize = int(fsize_str)
                state['upload'] = {
                    'filename': fname,
                    'filesize': fsize,
                    'received': 0,
                    'file': open(os.path.join(FILES_DIR, fname), 'wb')
                }
                sock.sendall(b'READY\n')
            except ValueError:
                sock.sendall(b'ERROR: Invalid upload command\n')
        else:
            sock.sendall(b'Usage: /upload <filename> <filesize>\n')

    elif line.startswith('/download '):
        parts = line.split(' ', 1)
        fname = parts[1].strip() if len(parts) == 2 else ''
        send_file(sock, fname)

    else:
        msg = f'[{addr[0]}:{addr[1]}] {line}\n'
        print(f'[MSG] {msg.strip()}')
        broadcast(msg, sender_sock=sock, sockets=[s for s in read_sockets if s is not server_sock])


def handle_data(sock, data, read_sockets):
    """Handle incoming raw data for a client, routing binary or text."""
    state = client_state[sock]
    upload = state.get('upload')

    if upload:
        # Binary upload in progress
        remaining = upload['filesize'] - upload['received']
        chunk = data[:remaining]
        upload['file'].write(chunk)
        upload['received'] += len(chunk)

        if upload['received'] >= upload['filesize']:
            upload['file'].close()
            fname = upload['filename']
            print(f'[RECV] Received "{fname}" ({upload["received"]} bytes)')
            sock.sendall(f'OK: Upload of "{fname}" complete\n'.encode())
            broadcast(f'[SERVER] {state["addr"]} uploaded "{fname}"\n',
                      sender_sock=sock,
                      sockets=[s for s in read_sockets if s is not server_sock])
            state['upload'] = None
            # Any leftover bytes go to text buffer
            leftover = data[remaining:]
            if leftover:
                state['buffer'] += leftover.decode(errors='replace')
    else:
        state['buffer'] += data.decode(errors='replace')

    # Process complete lines in text buffer
    while '\n' in state['buffer'] and not state.get('upload'):
        line, state['buffer'] = state['buffer'].split('\n', 1)
        line = line.strip()
        if line:
            process_command(sock, line, read_sockets)


server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_sock.bind((HOST, PORT))
server_sock.listen(10)
print(f'[SELECT SERVER] Listening on {HOST}:{PORT}')

read_sockets = [server_sock]

while True:
    readable, _, exceptional = select.select(read_sockets, [], read_sockets, 1.0)

    for sock in readable:
        if sock is server_sock:
            conn, addr = server_sock.accept()
            conn.setblocking(True)
            read_sockets.append(conn)
            client_state[conn] = {'addr': addr, 'buffer': '', 'upload': None}
            conn.sendall(b'Welcome! Commands: /list  /upload <file> <size>  /download <file>\n')
            print(f'[CONNECT] {addr}')
        else:
            try:
                data = sock.recv(BUFFER_SIZE)
                if data:
                    handle_data(sock, data, read_sockets)
                else:
                    raise ConnectionResetError
            except (ConnectionResetError, OSError):
                addr = client_state[sock]['addr']
                print(f'[DISCONNECT] {addr}')
                upload = client_state[sock].get('upload')
                if upload and upload.get('file'):
                    upload['file'].close()
                read_sockets.remove(sock)
                del client_state[sock]
                sock.close()

    for sock in exceptional:
        read_sockets.remove(sock)
        if sock in client_state:
            del client_state[sock]
        sock.close()
