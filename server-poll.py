"""
server-poll.py - Multi-client chat server with file transfer using poll()
Uses select.poll() syscall for I/O multiplexing (Linux only)
"""

import socket
import select
import os

HOST = '0.0.0.0'
PORT = 5002
FILES_DIR = 'server_files'
BUFFER_SIZE = 4096

os.makedirs(FILES_DIR, exist_ok=True)

# Map fd -> socket
fd_to_sock = {}
# Map fd -> {'addr': ..., 'buffer': str, 'upload': None or dict}
client_state = {}


def broadcast(message: str, sender_fd=None):
    for fd, sock in fd_to_sock.items():
        if fd == server_fd or fd == sender_fd:
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


def process_command(fd, line):
    sock = fd_to_sock[fd]
    state = client_state[fd]
    addr = state['addr']

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
        broadcast(msg, sender_fd=fd)


def handle_data(fd, data):
    state = client_state[fd]
    upload = state.get('upload')

    if upload:
        remaining = upload['filesize'] - upload['received']
        chunk = data[:remaining]
        upload['file'].write(chunk)
        upload['received'] += len(chunk)

        if upload['received'] >= upload['filesize']:
            upload['file'].close()
            fname = upload['filename']
            sock = fd_to_sock[fd]
            print(f'[RECV] Received "{fname}" ({upload["received"]} bytes)')
            sock.sendall(f'OK: Upload of "{fname}" complete\n'.encode())
            broadcast(f'[SERVER] {state["addr"]} uploaded "{fname}"\n', sender_fd=fd)
            state['upload'] = None
            leftover = data[remaining:]
            if leftover:
                state['buffer'] += leftover.decode(errors='replace')
    else:
        state['buffer'] += data.decode(errors='replace')

    while '\n' in state['buffer'] and not state.get('upload'):
        line, state['buffer'] = state['buffer'].split('\n', 1)
        line = line.strip()
        if line:
            process_command(fd, line)


def disconnect_client(fd, poller):
    state = client_state.get(fd, {})
    addr = state.get('addr', '?')
    upload = state.get('upload')
    if upload and upload.get('file'):
        upload['file'].close()
    print(f'[DISCONNECT] {addr}')
    poller.unregister(fd)
    if fd in fd_to_sock:
        fd_to_sock[fd].close()
        del fd_to_sock[fd]
    if fd in client_state:
        del client_state[fd]


# ---- Main ----
if not hasattr(select, 'poll'):
    raise RuntimeError('poll() is not available on this platform (requires Linux)')

server_sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
server_sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
server_sock.bind((HOST, PORT))
server_sock.listen(10)
server_fd = server_sock.fileno()
fd_to_sock[server_fd] = server_sock

poller = select.poll()
POLL_IN = select.POLLIN | select.POLLPRI
poller.register(server_fd, POLL_IN)

print(f'[POLL SERVER] Listening on {HOST}:{PORT}')

while True:
    events = poller.poll(1000)  # 1 second timeout

    for fd, event in events:
        if event & (select.POLLERR | select.POLLHUP | select.POLLNVAL):
            disconnect_client(fd, poller)
            continue

        if fd == server_fd:
            conn, addr = server_sock.accept()
            cfd = conn.fileno()
            fd_to_sock[cfd] = conn
            client_state[cfd] = {'addr': addr, 'buffer': '', 'upload': None}
            poller.register(cfd, POLL_IN)
            conn.sendall(b'Welcome! Commands: /list  /upload <file> <size>  /download <file>\n')
            print(f'[CONNECT] {addr}')
        else:
            try:
                data = fd_to_sock[fd].recv(BUFFER_SIZE)
                if data:
                    handle_data(fd, data)
                else:
                    disconnect_client(fd, poller)
            except OSError:
                disconnect_client(fd, poller)
