# Pembaca Markdown

Buka file Markdown (`.md`) dan baca dengan screen reader-mu: daftar judul untuk melompat,
teks tanpa tanda-tanda Markdown, dan web view untuk browse mode NVDA.

## Mulai

Untuk membuka file, pakai aksi "Buka file Markdown di pembaca", atau pilih "Buka File
Markdown" di menu ikon Hariku di tray. Pilih filenya di dialog "Buka File Markdown";
dialog ini menampilkan file `.md`, `.markdown`, dan `.txt`, atau semua file.

Tombol bawaan aksi ini Ctrl+M di jendela utama Hariku, tapi "Sembunyikan ke System Tray"
milik Hariku sendiri juga memakai Ctrl+M dan biasanya menang. Beri aksi ini tombolnya
sendiri di Pengaturan, Pintasan Keyboard, di bawah "Pembaca Markdown", atau pakai menu
tray atau Aruna.

Begitu filenya terbuka, Hariku menyebutkan namanya dan berapa baris serta judul di
dalamnya, misalnya "Dimuat: catatan.md — 120 baris, 8 judul".

## Jendela pembaca

Judul jendelanya "Pembaca Markdown —" lalu nama filenya. Isinya:

- "Daftar Judul" dengan jumlahnya: daftar judul, dengan level yang lebih dalam menjorok ke
  dalam.
- "Konten": teks filenya, hanya bisa dibaca, untuk dibaca baris per baris.
- Baris status berisi nama file serta jumlah baris dan judulnya.
- Tombol "Buka File...", "Baca di Web View", "Salin Semua", dan "Tutup".

Di "Konten", tanda-tanda Markdown sudah hilang. Tautan tampil sebagai teksnya diikuti
alamatnya dalam kurung, gambar tampil sebagai deskripsinya, item daftar diawali bullet,
tabel tampil satu baris per baris tabel dengan "|" di antara selnya, dan kode diapit
"[Code]" dan "[/Code]". Setiap judul diikuti satu baris garis.

## Pindah antarjudul

Tekan Alt+Panah Bawah untuk judul berikutnya dan Alt+Panah Atas untuk judul sebelumnya,
dari mana saja di jendela ini. Kursor di "Konten" pindah ke judul itu dan Hariku
menyebutkannya, jadi kamu bisa lanjut membaca dari situ. Kalau filenya tidak punya judul,
Hariku bilang "Tidak ada judul ditemukan".

Bergerak di daftar judul dengan tombol panah juga sama hasilnya. Klik dua kali sebuah
judul di daftar untuk membacakan seluruh bagiannya.

## Membaca di web view

Tekan Ctrl+B, atau tombol "Baca di Web View", untuk membuka file sebagai halaman web di
jendela terpisah, dengan judul, daftar, tabel, dan tautan sungguhan. Hariku bilang "Dibuka
di Web View. Gunakan NVDA Browse Mode." Di sana, H pindah antarjudul, 1 sampai 6 ke level
judul tertentu, T ke tabel, dan K ke tautan. Escape menutup web view.

## Menyalin teks

Tekan Ctrl+Shift+C, atau tombol "Salin Semua", untuk menyalin seluruh teks, tanpa tanda
Markdown, ke clipboard.

## Membuka file lain

Tekan Ctrl+O, atau tombol "Buka File...", untuk membuka file lain di jendela yang sama.

## File terakhir

Aksi "Buka file Markdown yang baru dibaca", Ctrl+Shift+M di jendela utama Hariku,
menampilkan "File Terakhir": 10 file terakhir yang kamu buka, masing-masing dengan nama
dan foldernya. File yang sudah tidak ada tidak ditampilkan. Pilih satu lalu tekan Enter
untuk membukanya. Item terakhir, "Hapus Daftar File Terakhir", mengosongkan daftarnya.

File yang kamu buka dengan Ctrl+O di dalam pembaca tidak masuk ke daftar ini.

## Tombol dan perintah

Di jendela utama Hariku:

- Ctrl+M: Buka file Markdown di pembaca (lihat bagian Mulai).
- Ctrl+Shift+M: Buka file Markdown yang baru dibaca.

Di jendela pembaca:

- Alt+Panah Bawah dan Alt+Panah Atas: judul berikutnya dan sebelumnya.
- Ctrl+B: baca di web view.
- Ctrl+Shift+C: salin semua teks.
- Ctrl+O: buka file lain.
- Escape: tutup pembaca.

Dua tombol utamanya bisa kamu ganti di Pengaturan, Pintasan Keyboard, di bawah "Pembaca
Markdown". Aruna menjalankan kedua aksi itu lewat namanya, misalnya "buka file markdown di
pembaca".
