# Developer Toolkit

Alat untuk kamu yang membuat ekstensi Hariku: konsol Python yang berjalan di dalam Hariku,
catatan event yang dikirim Hariku, log Hariku, daftar ekstensi yang sedang dimuat dan bisa
dimuat ulang, serta pengemas yang mengubah folder ekstensi menjadi file `.hrk`. Jendelanya
berbahasa Inggris, jadi label di panduan ini ditulis seperti yang muncul di layar.

## Mulai

Tekan Ctrl+Alt+D di mana saja di Windows, atau pilih "Developer Toolkit" di menu ikon
Hariku di tray. Jendelanya punya lima tab: "REPL Console", "Event Sniffer", "Log Viewer",
"Extension Inspector", dan "HRK Packer". Pindah antartab dengan Ctrl+Tab. Tombol "Close"
menutup jendelanya.

## Menjalankan kode Python

Tab "REPL Console" menjalankan kode Python di dalam Hariku.

1. Ketik kodemu di "Python Code (multi-line supported):". Di kotak ini, Tab mengetik
   karakter tab; untuk keluar, tekan Ctrl+M untuk pindah ke output, lalu Tab.
2. Tekan F5, atau tombol "Execute (F5)".
3. Hasilnya muncul di "Output:" dan 200 karakter pertamanya dibacakan. Teks yang di-print,
   pesan error, dan nilai sebuah ekspresi (setelah ">>>") semuanya masuk ke situ.

Ctrl+M berpindah antara kotak kode dan output. "Clear Output" dan "Clear Input"
mengosongkannya. Nama-nama ini langsung bisa dipakai: `wx`, `core`, `api` (yaitu
`core.api` Hariku), `bus` (event bus), `speak`, dan `help`. Apa yang kamu buat tetap ada
sampai Toolkit ditutup.

Kodemu punya akses penuh ke Hariku, jadi satu kesalahan bisa mengubah datamu atau
menghentikan Hariku.

## Melihat event

Tab "Event Sniffer" mencatat semua event yang dikirim bagian-bagian Hariku satu sama lain,
lengkap dengan jam dan awal tiap argumennya. Pencatatan mulai saat Hariku memuat ekstensi
ini, dan yang disimpan hanya 500 event terakhir.

- "Refresh (F5)" menampilkan daftarnya dan menyebutkan jumlah event serta yang terbaru.
- "Clear Events" mengosongkan daftar.
- "Stop Sniffer" menghentikan pencatatan; tombol yang sama lalu berganti menjadi "Start
  Sniffer".

## Membaca log

Tab "Log Viewer" menampilkan log debug Hariku, `hariku_debug.log` di folder `hariku2`
dalam folder temp Windows-mu. Lokasinya tertulis setelah "Log File:".

- "Refresh (F5)" memuat ulang log dan menyebutkan berapa baris yang terbaca.
- "Show last 200 lines only" awalnya dicentang; hapus centangnya untuk melihat seluruh
  log.
- "Auto-refresh (3s)" memuat ulang log tiap 3 detik, tanpa dibacakan.
- "Copy All" menyalin yang tampil ke clipboard.
- "Open Log Folder" membuka foldernya di File Explorer.

## Memuat ulang ekstensi

Tab "Extension Inspector" berisi daftar ekstensi yang sudah dimuat Hariku, di bawah
"Loaded Extensions in Memory:", dengan ID, nama, versi, mode (Unpacked atau Zipped), dan
modulnya. Pilih satu, lalu:

- "Inspect Module" menampilkan detailnya (pembuat, file, resmi atau tidak) dan nama-nama
  publik yang dimilikinya, di kotak di bawah tombol.
- "Force Reload Selected" memanggil `teardown()` ekstensi itu lalu memuatnya lagi dari
  foldernya, jadi perubahan yang kamu buat langsung berlaku tanpa menyalakan ulang Hariku.
- "Refresh List" membaca ulang daftarnya.

Memuat ulang tidak membatalkan apa yang sudah didaftarkan salinan lamanya. Handler event
yang dipasangnya tetap terpasang kecuali `teardown()`-nya melepasnya, jadi nyalakan ulang
Hariku sebelum kamu percaya hasil sebuah tes.

## Mengemas ekstensi

Tab "HRK Packer" mengemas folder ekstensi menjadi file `.hrk`, bentuk terkemas yang dimuat
Hariku.

1. Tekan "Browse..." dan pilih folder ekstensinya. Pemilih folder mulai dari folder
   ekstensi Hariku.
2. Tekan "Validate & Pack into .hrk".

Pengemas memeriksa bahwa `manifest.json` ada dan berisi name, version, author,
description, main, language, dan minimum_core_version, dan bahwa file main-nya ada. Lalu
folder `__pycache__` di dalam foldermu dihapus, dan sisanya dikemas menjadi
`<nama folder>.hrk` di sebelah folder itu. File dan folder yang namanya diawali titik
tidak ikut, dan `.hrk` lama dengan nama yang sama diganti. "Packer Output:" menampilkan
tiap langkah dan lokasi filenya.

## Tombol dan perintah

- Ctrl+Alt+D, di mana saja di Windows: buka Developer Toolkit.
- Ctrl+Tab: tab berikutnya.
- F5, di kotak kode atau output REPL Console: jalankan kode.
- F5, di teks Event Sniffer atau Log Viewer: muat ulang.
- Ctrl+M, di REPL Console: pindah antara kotak kode dan output.

Tombol untuk membuka Toolkit ada di bawah "Developer Toolkit" di Pengaturan, Pintasan
Keyboard, dan bisa kamu ganti di situ. Aruna menjalankannya lewat nama bahasa Inggrisnya:
ketik "open developer toolkit".
