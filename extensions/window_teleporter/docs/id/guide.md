# Window Teleporter

Paku sampai sepuluh jendela ke slot, lalu kembali ke salah satunya dengan satu tombol,
lebih cepat daripada mencarinya dengan Alt+Tab. Ekstensi ini juga bisa pindah
antar-virtual desktop Windows. Semua tombolnya berfungsi di mana saja di Windows.

## Slot dan hurufnya

Tiap slot punya satu huruf dari baris atas keyboard: Q untuk slot 1, W slot 2, E slot 3, R
slot 4, T slot 5, Y slot 6, U slot 7, I slot 8, O slot 9, dan P slot 10. Huruf yang sama
juga dipakai untuk virtual desktop 1 sampai 10.

Slot hanya diingat selama Hariku menyala; setelah Hariku dinyalakan ulang, semuanya kosong
lagi.

## Memaku jendela

Buka jendela yang kamu mau, lalu tekan Ctrl+Shift dengan huruf slotnya, misalnya
Ctrl+Shift+Q untuk slot 1. Hariku menyebutkan judul jendelanya dan slotnya, misalnya
"Notepad dipaku ke slot 1." Memaku jendela lain ke slot yang sama menggantikan yang lama.

## Melompat ke jendela yang dipaku

Tekan Ctrl+Alt dengan huruf slotnya, misalnya Ctrl+Alt+Q untuk slot 1. Jendelanya muncul
di depan, dan dikembalikan kalau tadi di-minimize, lalu Hariku bilang "Melompat ke" dan
judulnya.

Kalau jendelanya sudah ditutup, Hariku bilang "Slot 1 kosong atau jendela sudah ditutup."
dan slot itu dikosongkan.

## Mengecek slot

Tekan Ctrl+Alt+Shift dengan huruf slotnya untuk mendengar isinya, misalnya "Slot 1
berisi:" lalu judulnya. Judul yang disebut adalah judul jendela saat kamu memakunya.

## Virtual desktop

Tekan Alt+Shift dengan sebuah huruf untuk pindah ke virtual desktop itu: Alt+Shift+Q untuk
desktop 1, Alt+Shift+W untuk desktop 2, dan seterusnya. Hariku bilang "Berada di Desktop
2."

Untuk pindah ke desktop mana saja lewat nomornya, tekan Alt+Shift+D, ketik nomornya di
"Masukkan nomor Virtual Desktop tujuan:" lalu tekan Enter. Kalau desktop itu tidak ada,
Hariku bilang gagal melompat ke sana.

## Tombol dan perintah

- Ctrl+Shift+Q sampai Ctrl+Shift+P: Paku Jendela ke Slot 1 sampai 10.
- Ctrl+Alt+Q sampai Ctrl+Alt+P: Teleportasi ke Slot 1 sampai 10.
- Ctrl+Alt+Shift+Q sampai Ctrl+Alt+Shift+P: Cek Jendela di Slot 1 sampai 10.
- Alt+Shift+Q sampai Alt+Shift+P: Lompat ke Virtual Desktop 1 sampai 10.
- Alt+Shift+D: Lompat ke Desktop Manapun.

Aksi-aksinya ada di bawah "window_teleporter" di Pengaturan, Pintasan Keyboard, dan tiap
tombolnya bisa kamu ganti di situ. Kalau program lain sudah memakai salah satu tombol ini,
Hariku tidak bisa memakainya; beri aksi itu tombol lain. Project System juga memakai
Ctrl+Shift+P, untuk membuka Manajer Proyek-nya; kalau kamu memakai keduanya, pindahkan
salah satunya.

Aruna menjalankan aksi-aksi ini lewat namanya, misalnya "teleportasi ke slot 1" atau
"lompat ke virtual desktop 2".
