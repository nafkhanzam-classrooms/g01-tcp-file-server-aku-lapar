[![Review Assignment Due Date](https://classroom.github.com/assets/deadline-readme-button-22041afd0340ce965d47ae6ef1cefeee28c7c493a6346c4f15d667ab976d596c.svg)](https://classroom.github.com/a/mRmkZGKe)
# Network Programming - Assignment G01

## Anggota Kelompok
| Nama           | NRP        | Kelas     |
| ---            | ---        | ----------|
| Qurrata Ayun Kamil    |  5025241031   |  D  |
|                |            |           |

## Link Youtube (Unlisted)
Link ditaruh di bawah ini
```

```

## Penjelasan Program

Program ini merupakan sistem **TCP Chat Server dengan File Transfer** yang dibuat dengan Python. Terdapat satu klien dan lima varian server yang menunjukkan berbagai teknik penanganan koneksi klien multipel.

### 1. **client.py** - Terminal Chat Client

Klien yang terhubung ke server untuk melakukan komunikasi chat dan transfer file.

**Fitur Utama:**
- Koneksi TCP ke server (default: `127.0.0.1:5003`)
- **Command Interaktif:**
  - `/list` - Menampilkan daftar file yang tersedia di server
  - `/upload <filename>` - Mengunggah file lokal ke server
  - `/download <filename>` - Mengunduh file dari server
  - Pesan biasa - Dikirim sebagai broadcast ke semua klien
- **Threading:** Menggunakan dua thread:
  - Thread utama: Menangani input dari user (`stdin`)
  - Thread background (`receive_loop`): Menerima pesan dan file dari server secara real-time
- **Transfer File:**
  - File diunduh ke folder `downloads/`
  - Menggunakan header `FILE <name> <size>` untuk menandai awal transfer file
  - Dukungan file besar dengan buffer chunk-based

**Mekanisme:**
- State management untuk upload/download dengan lock
- Parsing protokol kustom untuk membedakan pesan teks dan data biner
- Error handling untuk koneksi terputus

---

### 2. **server-sync.py** - Synchronous Server (Port 5000)

Server TCP paling sederhana yang menangani satu klien pada satu waktu secara **sinkron/blocking**.

**Karakteristik:**
- **Sinkron/Blocking:** Menerima satu koneksi, menyelesaikan sepenuhnya, kemudian menerima koneksi berikutnya
- **Keterbatasan:** Jika satu klien tidak memberikan input, klien lain harus menunggu
- **Cocok untuk:** Demonstrasi konsep dasar, aplikasi dengan volume klien rendah

**Operasi Utama:**
- `handle_client()`: Loop blocking untuk satu klien
- `broadcast()`: Mengirim pesan ke semua klien (dilakukan secara sekuensial)
- `send_file()` dan `receive_file()`: Transfer file point-to-point

**Protocol:**
- Chat: plaintext + newline
- Upload: `/upload <nama> <ukuran>` → klien mengirim raw bytes
- Download: `/download <nama>` → server mengirim header `FILE` + raw bytes
- Broadcast: Pesan dari klien dikirim ke semua klien lain dengan timestamp

---

### 3. **server-select.py** - Select-based Multiplexing Server (Port 5001)

Server yang menggunakan **`select.select()`** untuk I/O multiplexing cross-platform.

**Karakteristik:**
- **Non-blocking I/O:** Dapat menangani banyak klien secara bersamaan tanpa thread
- **select():** Memantau readable/exceptional sockets, menunggu event dengan timeout 1 detik
- **Cocok untuk:** Aplikasi dengan ratusan koneksi, cross-platform (Windows, Linux, macOS)

**Mekanisme:**
- `read_sockets`: List socket yang dimonitor
- State per socket: `{'addr': ..., 'buffer': str, 'upload': dict}`
- Pipeline data: Text commands → upload binary → continue
- Graceful disconnect handling

**Keunggulan:**
- Platform-independent
- Efisiensi CPU lebih baik daripada sync
- Cocok untuk aplikasi produksi dengan IO-bound workload

---

### 4. **server-poll.py** - Poll-based Multiplexing Server (Port 5002)

Server yang menggunakan **`select.poll()`** untuk I/O multiplexing **Linux-specific**.

**Karakteristik:**
- **Poll API:** Lebih efisien daripada `select()` untuk banyak file descriptor
- **Linux Only:** Menggunakan syscall Linux, tidak tersedia di Windows
- **Event-driven:** Hanya memproses socket yang memiliki aktivitas

**Mekanisme:**
- `fd_to_sock`: Map file descriptor → socket object
- `client_state`: Map fd → state dict
- `poller.poll()`: Mengembalikan list (fd, event) yang aktif
- Error handling: Deteksi POLLERR, POLLHUP, POLLNVAL

**Keunggulan:**
- Scalability lebih baik (O(n) vs O(n²) untuk select)
- Lebih cepat untuk ratusan/ribuan koneksi
- Lebih detail dalam event handling

---

### 5. **server-thread.py** - Threading-based Server (Port 5003)

Server yang menggunakan **threading** - satu thread per klien.

**Karakteristik:**
- **Multi-threaded:** Setiap klien mendapat thread dedicated sendiri
- **Simplicity:** Kode sederhana dan mudah dipahami (blocking logic per thread)
- **Thread-safe:** Menggunakan `threading.Lock()` untuk akses shared state (`clients` dict)

**Mekanisme:**
- `clients_lock`: Proteksi akses ke dict klien yang terhubung
- `handle_client()`: Function yang dijalankan dalam thread terpisah
- Thread daemon: Tidak perlu explicit cleanup
- `threading.active_count()`: Monitor jumlah thread aktif

**Trade-offs:**
- ✅ Mudah dipahami dan diimplementasikan
- ✅ Baik untuk aplikasi single-machine dengan klien moderat (< 1000)
- ❌ Context switching overhead meningkat dengan banyak thread
- ❌ Memory per thread (~1-8MB), kurang scalable

---

## Perbandingan Pendekatan

| Pendekatan | Port | Klien Simultan | CPU Usage | Memory | Kesulitan | Best Used For |
|---|---|---|---|---|---|---|
| **Sync** | 5000 | 1 | Rendah | Rendah | Sangat Mudah | Learning, Demo |
| **Select** | 5001 | 100-500 | Sedang | Rendah | Sedang | Cross-platform produksi |
| **Poll** | 5002 | 1000+ | Rendah | Rendah | Sedang | Linux high-concurrency |
| **Thread** | 5003 | 100-500 | Tinggi | Sedang | Mudah | Aplikasi I/O-bound |

---

## Cara Menjalankan

**Terminal 1 - Jalankan salah satu server:**
```bash
python server-sync.py    # atau server-select.py / server-poll.py / server-thread.py
```

**Terminal 2+ - Jalankan klien:**
```bash
python client.py [host] [port]
# Contoh: python client.py 127.0.0.1 5000
```

**Default:**
- Host: `127.0.0.1`
- Port: client terhubung ke 5003, tapi bisa diatur

## Screenshot Hasil

1. Broadcast seluruh client:

![alt text](images/image.png)

2. Upload 

![alt text](images/image-6.png)
![alt text](images/image-3.png)

3. List

![alt text](images/image-2.png)

4. Download

![alt text](images/image-4.png)
![alt text](images/image-5.png)
