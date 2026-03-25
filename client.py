"""
client.py - Terminal chat client with file transfer support
Commands:
  /list               - list files on the server
  /upload <filename>  - upload a local file to the server
  /download <filename>- download a file from the server
  Anything else is sent as a broadcast message
"""

import socket
import threading
import os
import sys

HOST = '127.0.0.1'
PORT = 5003          # Change to match the server you want to connect to
BUFFER_SIZE = 4096
DOWNLOAD_DIR = 'downloads'

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

# Shared state
stop_event = threading.Event()
download_state = {
    'active': False,
    'filename': None,
    'filesize': 0,
    'received': 0,
    'file': None,
}
ds_lock = threading.Lock()


# ── Receive thread ────────────────────────────────────────────────────────────

def receive_loop(sock):
    """Background thread: read from socket and print to terminal."""
    text_buffer = ''

    def flush_text():
        nonlocal text_buffer
        if text_buffer:
            # Re-print prompt after server message
            sys.stdout.write('\r' + ' ' * 60 + '\r')
            print(text_buffer, end='', flush=True)
            sys.stdout.write('> ')
            sys.stdout.flush()
            text_buffer = ''

    try:
        while not stop_event.is_set():
            data = sock.recv(BUFFER_SIZE)
            if not data:
                print('\n[Disconnected from server]')
                stop_event.set()
                break

            with ds_lock:
                if download_state['active']:
                    # Route bytes into the open file
                    ds = download_state
                    remaining = ds['filesize'] - ds['received']
                    chunk = data[:remaining]
                    ds['file'].write(chunk)
                    ds['received'] += len(chunk)

                    if ds['received'] >= ds['filesize']:
                        ds['file'].close()
                        print(f'\n[Downloaded "{ds["filename"]}" → {DOWNLOAD_DIR}/]')
                        sys.stdout.write('> ')
                        sys.stdout.flush()
                        # Reset state
                        ds['active'] = False
                        ds['filename'] = None
                        ds['filesize'] = 0
                        ds['received'] = 0
                        ds['file'] = None
                        # Any leftover goes to text
                        leftover = data[remaining:]
                        if leftover:
                            text_buffer += leftover.decode(errors='replace')
                            flush_text()
                    continue  # stay in receive loop

            # Normal text mode
            text_buffer += data.decode(errors='replace')

            # Check for FILE header: "FILE <name> <size>\n"
            while '\n' in text_buffer:
                line, text_buffer = text_buffer.split('\n', 1)
                line_stripped = line.strip()
                if line_stripped.startswith('FILE '):
                    parts = line_stripped.split(' ', 2)
                    if len(parts) == 3:
                        _, fname, fsize_str = parts
                        try:
                            fsize = int(fsize_str)
                            filepath = os.path.join(DOWNLOAD_DIR, fname)
                            with ds_lock:
                                download_state['active'] = True
                                download_state['filename'] = fname
                                download_state['filesize'] = fsize
                                download_state['received'] = 0
                                download_state['file'] = open(filepath, 'wb')
                            print(f'\n[Receiving "{fname}" ({fsize} bytes)...]')
                            sys.stdout.write('> ')
                            sys.stdout.flush()
                            # Any bytes already in text_buffer belong to the file
                            with ds_lock:
                                if text_buffer:
                                    tail = text_buffer.encode(errors='replace')
                                    text_buffer = ''
                                    remaining = fsize
                                    chunk = tail[:remaining]
                                    download_state['file'].write(chunk)
                                    download_state['received'] += len(chunk)
                                    if download_state['received'] >= fsize:
                                        download_state['file'].close()
                                        print(f'\n[Downloaded "{fname}" → {DOWNLOAD_DIR}/]')
                                        download_state['active'] = False
                            break
                        except ValueError:
                            pass
                    # Treat as regular text if parse fails
                    flush_text()
                else:
                    sys.stdout.write('\r' + ' ' * 60 + '\r')
                    print(line_stripped, flush=True)
                    sys.stdout.write('> ')
                    sys.stdout.flush()

    except OSError:
        if not stop_event.is_set():
            print('\n[Connection error]')
        stop_event.set()


# ── Send helpers ──────────────────────────────────────────────────────────────

def do_list(sock):
    sock.sendall(b'/list\n')


def do_upload(sock, filename):
    if not os.path.isfile(filename):
        print(f'[ERROR] Local file not found: {filename}')
        return
    filesize = os.path.getsize(filename)
    # Send command, wait for READY
    sock.sendall(f'/upload {os.path.basename(filename)} {filesize}\n'.encode())
    # Wait for server READY acknowledgement
    ack = b''
    while b'\n' not in ack:
        ack += sock.recv(BUFFER_SIZE)
    if b'READY' not in ack:
        print(f'[ERROR] Server not ready: {ack.decode()}')
        return
    sent = 0
    with open(filename, 'rb') as f:
        while True:
            chunk = f.read(BUFFER_SIZE)
            if not chunk:
                break
            sock.sendall(chunk)
            sent += len(chunk)
    print(f'[Uploaded "{filename}" ({sent} bytes)]')


def do_download(sock, filename):
    sock.sendall(f'/download {filename}\n'.encode())


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    global HOST, PORT
    args = sys.argv[1:]
    if len(args) >= 1:
        HOST = args[0]
    if len(args) >= 2:
        PORT = int(args[1])

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.connect((HOST, PORT))
    except ConnectionRefusedError:
        print(f'[ERROR] Cannot connect to {HOST}:{PORT}')
        sys.exit(1)

    print(f'Connected to {HOST}:{PORT}')
    print('Commands: /list  /upload <file>  /download <file>  Ctrl+C to quit\n')

    recv_thread = threading.Thread(target=receive_loop, args=(sock,), daemon=True)
    recv_thread.start()

    try:
        while not stop_event.is_set():
            sys.stdout.write('> ')
            sys.stdout.flush()
            try:
                line = input()
            except EOFError:
                break

            if not line.strip():
                continue

            if line.strip() == '/list':
                do_list(sock)

            elif line.strip().startswith('/upload '):
                parts = line.strip().split(' ', 1)
                do_upload(sock, parts[1])

            elif line.strip().startswith('/download '):
                parts = line.strip().split(' ', 1)
                do_download(sock, parts[1])

            else:
                sock.sendall((line + '\n').encode())

    except KeyboardInterrupt:
        print('\nDisconnecting...')
    finally:
        stop_event.set()
        sock.close()


if __name__ == '__main__':
    main()
