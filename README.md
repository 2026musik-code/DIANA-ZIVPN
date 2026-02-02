# DIANA ZIVPN - Web Panel Manajemen VPN

Web Panel Manajemen VPN otomatis untuk protokol **UDP Zivpn**, dibangun dengan Python (Flask) dan SQLite. Panel ini memungkinkan penjualan akun VPN secara otomatis dengan integrasi pembayaran QRIS melalui **Paymenku.com**.

## Fitur

### Halaman Publik (Client Area)
- **Daftar Harga**: Menampilkan paket VPN yang tersedia.
- **Order Otomatis**: Form pembelian akun (Username & Password custom).
- **Pembayaran QRIS**: Integrasi langsung dengan Paymenku.
- **Cek Status**: Cek masa aktif akun dan status.

### Admin Dashboard (Backend)
- **Dashboard Statistik**: Penjualan, user aktif, riwayat transaksi.
- **Manajemen Paket**: CRUD paket harga VPN.
- **Manajemen User**:
  - List user aktif.
  - **Create User**: Membuat akun VPN manual (tanpa pembayaran).
  - **Kill Session**: Memutus koneksi user secara paksa (Restart Service).
- **Pengaturan API**: Konfigurasi Merchant ID dan API Key Paymenku.

### Sistem Backend (Zivpn Integration)
- **Config-Based Auth**: Menggunakan `config.json` Zivpn untuk autentikasi (bukan user Linux).
- **Auto Restart**: Service Zivpn otomatis restart saat user dibuat/dihapus.
- **Auto Delete**: Cron job otomatis menghapus akun expired.

---

## Persyaratan Sistem
- **OS**: Ubuntu 20.04+ / Debian 10+
- **Akses Root**: Wajib.

---

## Cara Install (Auto Install)

Cukup jalankan satu perintah berikut di terminal VPS Anda:

```bash
bash <(curl -fsSL https://raw.githubusercontent.com/2026musik-code/DIANA-ZIVPN/main/install.sh)
```

Script ini akan otomatis:
1. Menginstall Python & Dependencies.
2. Menginstall Binary UDP Zivpn (jika belum ada).
3. Menginstall Web Panel & Database.
4. Mengaktifkan Service Web di Port 80.
5. Mengaktifkan Auto-Delete Expired Account.

Setelah instalasi selesai, akses panel di browser:
`http://IP-VPS-ANDA/`

**Login Admin Default:**
- **Username:** `admin`
- **Password:** `admin123`

> **PENTING:** Segera ganti password admin setelah login!

---

## Konfigurasi Pasca Install

1. **Setting Payment**:
   - Login ke Admin Dashboard -> **Settings**.
   - Masukkan **Merchant ID** dan **API Key** dari [Paymenku.com](https://paymenku.com).
   - Copy **Callback URL** dan masukkan di dashboard Paymenku.

2. **Buat Paket**:
   - Masuk menu **Packages**.
   - Tambahkan paket (misal: 30 Hari, Rp 15.000).

---

## Catatan
- Panel berjalan menggunakan **Gunicorn** di port 80 secara default.
- Log sistem dapat dicek dengan: `journalctl -u diana-zivpn -f`.
- Log cron job (auto delete) ada di `/opt/diana-zivpn/cron.log`.
