# PERSIJA AUTO UPDATE FAN PORTAL

## Cara pakai paling gampang

1. Buat repository GitHub baru.
2. Upload **semua isi folder ini** ke repository:
   - `index.html`
   - `data.json`
   - `update.py`
   - `.github/workflows/auto-update.yml`
3. Aktifkan GitHub Pages dari branch `main` / root.
4. GitHub Actions akan menjalankan updater otomatis setiap 15 menit.
5. Buka URL GitHub Pages kamu. Portal akan mengambil `data.json` terbaru tanpa edit HTML manual.

## Yang otomatis
- Berita Persija dari halaman berita resmi.
- Jadwal/hasil pertandingan Persija dari feed pertandingan.
- Timestamp sinkronisasi.
- Match berikutnya dan hasil terakhir di UI.
- Browser melakukan refresh data setiap 5 menit saat halaman sedang terbuka.

## Catatan
- Interval 15 menit adalah polling; tidak berarti sumber resmi mengirim webhook setiap ada berita.
- Kalau halaman sumber/API berubah struktur, parser mungkin perlu disesuaikan.
- Untuk skor live per detik, gunakan provider live-score khusus; versi ini fokus pada update otomatis yang ringan dan stabil.


## V2 Live Center
Versi ini menambahkan:
- Live match detector.
- Skor & status pertandingan.
- Klasemen Indonesia Super League 26/27.
- Form 5 pertandingan.
- Recent scorer board.
- Match statistics saat pertandingan live tersedia.
- Data lanjutan di `advanced.json`.
