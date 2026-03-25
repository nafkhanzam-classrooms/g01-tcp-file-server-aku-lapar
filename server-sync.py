"""
server-sync.py - Synchronous multi-client chat server with file transfer
Handles one client at a time (sequential/blocking)
"""

import socket
import os
import struct

HOST = '0.0.0.0'
PORT = 5000
FILES_DIR = 'server_files'
BUFFER_SIZE = 4096

os.makedirs(FILES_DIR, exist_ok=True)

clients = []  # (conn, addr) list for broadcast (handled sequentially)


def broadcast(message: str, sender_conn=None):
    """Send a message to all connected clients except the sender."""
    dead = []
    for conn, addr in clients:
        if conn is sender_conn:
            continue
        try:
            conn.sendall(message.encode())
        except Exception:
            dead.append((conn, addr))
    for item in dead:
        clients.remove(item)


def send_file(conn, filename: str):
    """Send a file to a client."""
    filepath = os.path.join(FILES_DIR, filename)
    if not os.path.isfile(filepath):
        conn.sendall(b'ERROR: File not found\n')
        return
    filesize = os.path.getsize(filepath)
    # Send header: "FILE <name> <size>\n"
    header = f'FILE {filename} {filesize}\n'.encode()
    conn.sendall(header)
    with open(filepath, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            conn.sendall(chunk)
    print(f'[SEND] Sent "{filename}" ({filesize} bytes)')


def receive_file(conn, filename: str, filesize: int):
    """Receive a file from a client and save it."""
    filepath = os.path.join(FILES_DIR, filename)
    received = 0
    with open(filepath, 'wb') as f:
        while received < filesize:
            chunk = conn.recv(min(BUFFER_SIZE, filesize - received))
            if not chunk:
                break
            f.write(chunk)
            received += len(chunk)
    print(f'[RECV] Received "{filename}" ({received} bytes)')
    conn.sendall(f'OK: Upload of "{filename}" complete\n'.encode())


def handle_client(conn, addr):
    """Handle a single client connection (blocking)."""
    print(f'[CONNECT] {addr}')
    clients.append((conn, addr))
    conn.sendall(b'Welcome! Commands: /list  /upload <file>  /download <file>\n')
    try:
        buffer = ''
        while True:
            data = conn.recv(BUFFER_SIZE)
            if not data:
                break
            buffer += data.decode(errors='replace')
            while '\n' in buffer:
                line, buffer = buffer.split('\n', 1)
                line = line.strip()
                if not line:
                    continue

                if line == '/list':
                    files = os.listdir(FILES_DIR)
                    if files:
                        conn.sendall(('Files: ' + ', '.join(files) + '\n').encode())
                    else:
                        conn.sendall(b'No files on server\n')

                elif line.startswith('/upload '):
                    # Protocol: client sends "/upload <name> <size>\n" then raw bytes
                    parts = line.split(' ', 2)
                    if len(parts) == 3:
                        _, fname, fsize_str = parts
                        try:
                            fsize = int(fsize_str)
                            conn.sendall(b'READY\n')
                            receive_file(conn, fname, fsize)
                            broadcast(f'[SERVER] {addr} uploaded "{fname}"\n', sender_conn=conn)
                        except ValueError:
                            conn.sendall(b'ERROR: Invalid upload command\n')
                    else:
                        conn.sendall(b'Usage: /upload <filename> <filesize>\n')

                elif line.startswith('/download '):
                    parts = line.split(' ', 1)
                    if len(parts) == 2:
                        fname = parts[1].strip()
                        send_file(conn, fname)
                    else:
                        conn.sendall(b'Usage: /download <filename>\n')

                else:
                    # Regular chat message — broadcast to all
                    msg = f'[{addr[0]}:{addr[1]}] {line}\n'
                    print(f'[MSG] {msg.strip()}')
                    broadcast(msg, sender_conn=conn)

    except ConnectionResetError:
        pass
    finally:
        print(f'[DISCONNECT] {addr}')
        clients.remove((conn, addr))
        conn.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(5)
    print(f'[SYNC SERVER] Listening on {HOST}:{PORT} (one client at a time)')

    while True:
        conn, addr = server.accept()
        handle_client(conn, addr)  # Blocks until client disconnects


if __name__ == '__main__':
    main()
