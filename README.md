# VPN Management Panel (UDP Zivpn)

Web Panel Manajemen VPN otomatis untuk protokol UDP Zivpn, dibangun dengan Python (Flask) dan SQLite. Panel ini memungkinkan penjualan akun VPN secara otomatis dengan integrasi pembayaran QRIS melalui **Paymenku.com**.

## Fitur

### Halaman Publik (Client Area)
- **Daftar Harga**: Menampilkan paket VPN yang tersedia (Harian/Bulanan).
- **Order Otomatis**: Form pembelian akun (Username & Password custom).
- **Pembayaran QRIS**: Integrasi langsung dengan Paymenku (QRIS otomatis muncul).
- **Cek Status**: Fitur untuk mengecek sisa masa aktif akun dan status (Active/Expired).

### Admin Dashboard (Backend)
- **Dashboard Statistik**: Total penjualan, jumlah user aktif, dan riwayat transaksi.
- **Manajemen Paket**: Tambah, Edit, dan Hapus paket harga VPN.
- **Manajemen User**:
  - Melihat daftar user yang aktif.
  - **Kill Session**: Memutus koneksi user secara paksa.
- **Pengaturan API**: Konfigurasi Merchant ID dan API Key Paymenku langsung dari web.

### Sistem Backend
- **Auto Account Creation**: Membuat user sistem Linux (`useradd`) otomatis setelah pembayaran sukses.
- **Auto Delete**: Script otomatis menghapus akun yang sudah expired.
- **Secure**: Password admin terenkripsi, proteksi command injection.

---

## Persyaratan Sistem
- **OS**: Ubuntu 20.04+ / Debian 10+
- **Python**: Python 3.8+
- **Root Access**: Diperlukan untuk menjalankan perintah `useradd`, `userdel`, dll.
- **Zivpn Binary**: Pastikan binary UDP Zivpn sudah terinstall dan berjalan (biasanya di port 53/5300).

---

## Tutorial Instalasi di VPS Ubuntu/Debian

Ikuti langkah-langkah berikut untuk menginstall panel di VPS Anda.

### 1. Update dan Install Dependencies
Update repository dan install Python serta pip.

```bash
apt update && apt upgrade -y
apt install python3 python3-pip python3-venv git -y
```

### 2. Clone Repository
Download source code panel ini (sesuaikan URL jika sudah di-upload ke GitHub Anda, atau upload manual).

```bash
cd /root
mkdir vpn-panel
cd vpn-panel
# Upload file-file panel ke folder ini
```

### 3. Buat Virtual Environment
Agar library python tidak tercampur dengan system.

```bash
python3 -m venv venv
source venv/bin/activate
```

### 4. Install Requirements
Install library Flask dan lainnya.

```bash
pip install -r requirements.txt
```

### 5. Inisialisasi Database
Jalankan script untuk membuat database dan user admin default.

```bash
python3 init_project.py
```
*Output: Admin user 'admin' created.*

> **Catatan:** Default login admin adalah **Username:** `admin`, **Password:** `admin123`. Segera ganti password atau buat admin baru di database untuk keamanan.

### 6. Konfigurasi Sistem (PENTING)
Agar panel bisa membuat user Linux, panel harus berjalan dengan akses root atau user yang memiliki hak akses.
Pastikan file `utils/system.py` dikonfigurasi untuk **Production**.

Buka file `utils/system.py`:
```bash
nano utils/system.py
```
Ubah baris `MOCK_MODE = True` menjadi:
```python
MOCK_MODE = False
```
Simpan (Ctrl+X, Y, Enter).

### 7. Jalankan Aplikasi
Untuk percobaan (Development):
```bash
python3 app.py
```
Akses di browser: `http://IP-VPS:5000`

Untuk Production (Menggunakan Gunicorn):
```bash
gunicorn -w 4 -b 0.0.0.0:80 app:app
```

---

## Konfigurasi Cron Job (Auto Delete Expired)

Agar sistem otomatis menghapus akun yang sudah habis masa aktifnya, tambahkan cron job yang berjalan setiap hari atau setiap jam.

1. Buka crontab:
```bash
crontab -e
```

2. Tambahkan baris berikut di paling bawah (jalan setiap jam 12 malam):
```bash
0 0 * * * cd /root/vpn-panel && venv/bin/python3 cron_cleanup.py >> cron.log 2>&1
```

---

## Cara Penggunaan

1. **Login Admin**: Buka `http://IP-VPS:5000/admin`.
2. **Setting Payment**: Masuk menu **Settings**, isi **Merchant ID** dan **API Key** dari Paymenku.
3. **Setting Callback**: Copy **Callback URL** yang muncul di menu Settings, lalu tempel di Dashboard Merchant Paymenku.
4. **Buat Paket**: Masuk menu **Packages**, buat paket (misal: 30 Hari, Rp 15.000).
5. **Siap Jualan**: Berikan link `http://IP-VPS:5000` ke pelanggan.

---

## Catatan Keamanan
- Jangan gunakan `MOCK_MODE = True` di production karena user tidak akan benar-benar terbuat di sistem Linux.
- Gunakan reverse proxy seperti **Nginx** dan pasang **SSL (HTTPS)** agar transaksi lebih aman.
- Pastikan port 5000 (atau port yang digunakan) sudah dibuka di firewall VPS.
