# Project System

Pecah sebuah proyek menjadi tugas-tugas dengan tenggat waktu, centang yang sudah selesai,
dan dengar sudah sejauh mana proyeknya. Hariku juga memberi tahu kalau tanggal yang kamu
pilih di kalender punya tugas proyek yang jatuh tempo.

## Mulai

Tekan Ctrl+Shift+P di jendela utama Hariku. Jendela "Manajer Proyek" terbuka dengan daftar
"Proyek Anda:". Tiap proyek menampilkan progresnya dalam kurung, misalnya "[50%] Website",
atau "[DONE]" kalau semua tugasnya sudah selesai, lalu deskripsinya kalau ada.

Manajer Proyek dan jendela tugas tidak punya tombol tutup: tekan Alt+F4 untuk menutupnya.

## Menambah proyek

1. Tekan "Proyek Baru".
2. Ketik namanya di "Masukkan nama proyek:" lalu tekan Enter.
3. Ketik deskripsi singkat di "Masukkan deskripsi singkat (opsional):", atau biarkan
   kosong, lalu tekan Enter.

Nama dan deskripsi proyek tidak bisa diubah setelahnya.

## Menambah tugas

Pilih sebuah proyek lalu tekan "Kelola Tugas". Jendela berjudul "Tugas untuk:" dan nama
proyeknya terbuka, dengan tugas-tugasnya di bawah "Tugas:". Sebuah tugas tertulis seperti
"[ ] Beli cat (Due: 2026-10-01)", dan "[X]" menggantikan "[ ]" kalau sudah selesai.

1. Tekan "Tambah Tugas".
2. Ketik tugasnya di "Masukkan nama tugas:" lalu tekan Enter.
3. Ketik tenggatnya di "Masukkan tenggat waktu (YYYY-MM-DD):", misalnya 2026-10-01, lalu
   tekan Enter. Isinya mulai dari tanggal yang sedang dipilih di kalender.

Tenggat yang ditulis dengan cara lain ditolak dengan pesan "Format tanggal tidak valid.
Gunakan YYYY-MM-DD."

## Menyelesaikan tugas

Pilih sebuah tugas lalu tekan "Tandai Selesai / Belum". Hariku menyebutkan sejauh mana
proyeknya, misalnya "Tugas selesai. Proyek 'Website' sekarang 50% selesai." Saat tugas
terakhir selesai, Hariku memberi selamat dan proyeknya menampilkan "[DONE]". Menekan
"Tandai Selesai / Belum" pada tugas yang sudah selesai membuatnya belum selesai lagi.

## Menghapus tugas dan proyek

- "Hapus" di jendela tugas langsung menghapus tugas yang dipilih, tanpa bertanya.
- "Hapus" di Manajer Proyek bertanya dulu, "Apakah Anda yakin ingin menghapus proyek
  ...?", lalu menghapus proyek itu beserta semua tugasnya.

## Tenggat di kalender

Saat kamu pindah ke sebuah tanggal di kalender Hariku, Hariku menghitung tugas yang belum
selesai dengan tenggat di tanggal itu, lalu menyebutkan paling banyak tiga, misalnya
"Tugas: Beli cat untuk proyek Website." Jumlahnya selalu disebut "jatuh tempo hari ini",
tanggal berapa pun yang sedang kamu pilih.

## Tombol dan perintah

- Ctrl+Shift+P, di jendela utama Hariku: Open Project Manager.

Window Teleporter juga memakai Ctrl+Shift+P, untuk memaku jendela ke slot 10. Kalau kamu
memakai keduanya, beri salah satunya tombol lain di Pengaturan, Pintasan Keyboard; yang
ini ada di bawah "Project System". Aruna menjalankannya lewat nama bahasa Inggrisnya:
ketik "open project manager".
