# 🛡️ Bot Antispam + Nexus AI

Bot Telegram antispam untuk grup, dilengkapi sistem AI (Nexus) yang belajar secara pasif dari pola spam yang ditemukan.

---

## ✨ Fitur Utama

- **Filter Regex** — pola spam global (owner) dan lokal (per grup)
- **Anti Mention** — deteksi mention massal ke user eksternal
- **Anti Link** — blokir link tidak diizinkan
- **Anti Duplikat** — cegah pesan berulang per user dan lintas grup (anti-gcast)
- **Filter Bio** — deteksi spam dari bio profil user
- **CAS Integration** — cek otomatis via Combot Anti-Spam
- **Nexus AI** — sistem skor berbasis Naive Bayes + konteks, belajar pasif dari penghapusan
- **Sistem Hukuman Eskalasi** — 10 pelanggaran → mute 5 menit, tiap pelanggaran berikutnya 2× lipat
- **Panel DM Interaktif** — kelola semua pengaturan lewat chat privat bot
- **Log Channel** — setiap penghapusan dicatat lengkap beserta alasannya

---

## ⚙️ Konfigurasi

Salin `.env.example` menjadi `.env` lalu isi sesuai kebutuhan:

```bash
cp .env.example .env
```

| Variabel | Wajib | Keterangan |
|---|---|---|
| `API_ID` | ✅ | Dari my.telegram.org |
| `API_HASH` | ✅ | Dari my.telegram.org |
| `BOT_TOKEN` | ✅ | Dari @BotFather |
| `OWNER_ID` | ✅ | User ID Telegram pemilik bot |
| `LOG_CHANNEL` | ✅ | ID channel log (format `-100...`) |
| `CODE_BOT` | ✅ | Nama unik bot untuk namespace database |
| `MONGO_URL` | ❌ | Opsional, jika pakai MongoDB |
| `SQLITE_PATH` | ❌ | Default: `nexus_bot.db` |
| `CHANNEL_OWNER` | ❌ | ID channel update, tampil di /start |
| `PORT` | ❌ | Port health check, default `8000` |

---

## 🚀 Cara Menjalankan

### Termux (Android)

```bash
pkg install python git -y
pip install -r requirements.txt
cp .env.example .env
# edit .env sesuai kebutuhan
python antigcast.py
```

### VPS / Server

```bash
pip install -r requirements.txt
cp .env.example .env
# edit .env sesuai kebutuhan
python antigcast.py
```

### MongoDB (Opsional)

Jika ingin pakai MongoDB, uncomment baris `motor` dan `pymongo` di `requirements.txt`, lalu isi `MONGO_URL` di `.env`. Jika tidak diisi, bot otomatis pakai SQLite.

---

## 📁 Struktur Project

```
├── antigcast.py              # Entry point
├── database.py               # Abstraksi MongoDB / SQLite
├── core/
│   ├── punishment.py         # Sistem hukuman eskalasi
│   └── regex_utils.py        # Utilitas regex
├── nexus/
│   └── ai_core/              # Engine Nexus AI (Bayes, scorer, learner)
└── plugins/
    ├── filters/              # antispam, bio, cas
    ├── commands/             # settings, regex, log, antigcast_group
    ├── nexus/                # Handler grup Nexus AI
    └── ui/                   # Panel DM interaktif
```

---

## 💬 Perintah Bot

### Owner (via DM)
| Perintah | Fungsi |
|---|---|
| `/start` | Buka panel utama |
| `/list` | Lihat daftar grup aktif |
| `/delregex` | Hapus regex global |
| `/infobot` | Info status bot |

### Admin Grup
| Perintah | Fungsi |
|---|---|
| `/antigcast` | Aktifkan/nonaktifkan anti-gcast |
| `/spam` | Tandai pesan sebagai spam (latih Nexus) |
| `/vip` | Beri status VIP ke user |
| `/unvip` | Cabut status VIP |
| `/addgroupregex` | Tambah regex lokal grup |
| `/delgroupregex` | Hapus regex lokal grup |
| `/listgroupregex` | Lihat daftar regex lokal |
| `/setlocal` `/setglobal` `/setbio` `/setwaktu` `/status` | Pengaturan grup |
