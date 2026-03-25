"""
server-thread.py - Multi-client chat server with file transfer using threading
One thread per connected client
"""

import socket
import threading
import os

HOST = '0.0.0.0'
PORT = 5003
FILES_DIR = 'server_files'
BUFFER_SIZE = 4096

os.makedirs(FILES_DIR, exist_ok=True)

clients_lock = threading.Lock()
clients = {}  # socket -> addr


def broadcast(message: str, sender_sock=None):
    with clients_lock:
        targets = list(clients.keys())
    for sock in targets:
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


def receive_file(conn, filename: str, filesize: int):
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
    return received


def handle_client(conn, addr):
    print(f'[CONNECT] {addr}  (thread: {threading.current_thread().name})')
    with clients_lock:
        clients[conn] = addr
    conn.sendall(b'Welcome! Commands: /list  /upload <file> <size>  /download <file>\n')

    buffer = ''
    try:
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
                    reply = ('Files: ' + ', '.join(files) + '\n') if files else 'No files on server\n'
                    conn.sendall(reply.encode())

                elif line.startswith('/upload '):
                    parts = line.split(' ', 2)
                    if len(parts) == 3:
                        _, fname, fsize_str = parts
                        try:
                            fsize = int(fsize_str)
                            conn.sendall(b'READY\n')
                            received = receive_file(conn, fname, fsize)
                            broadcast(f'[SERVER] {addr} uploaded "{fname}"\n', sender_sock=conn)
                        except ValueError:
                            conn.sendall(b'ERROR: Invalid upload command\n')
                    else:
                        conn.sendall(b'Usage: /upload <filename> <filesize>\n')

                elif line.startswith('/download '):
                    parts = line.split(' ', 1)
                    fname = parts[1].strip() if len(parts) == 2 else ''
                    send_file(conn, fname)

                else:
                    msg = f'[{addr[0]}:{addr[1]}] {line}\n'
                    print(f'[MSG] {msg.strip()}')
                    broadcast(msg, sender_sock=conn)

    except (ConnectionResetError, OSError):
        pass
    finally:
        print(f'[DISCONNECT] {addr}')
        with clients_lock:
            clients.pop(conn, None)
        conn.close()


def main():
    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((HOST, PORT))
    server.listen(20)
    print(f'[THREAD SERVER] Listening on {HOST}:{PORT}')

    while True:
        conn, addr = server.accept()
        t = threading.Thread(target=handle_client, args=(conn, addr), daemon=True)
        t.start()
        print(f'[THREADS] Active: {threading.active_count() - 1}')


if __name__ == '__main__':
    main()
