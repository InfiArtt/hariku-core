# Suara Piper

Suara Piper menambahkan suara neural Piper ke Suara Hariku. Suaranya berbicara di
komputermu, tanpa internet, dan ada suara bahasa Indonesia juga. Kamu cukup mengunduh
suara yang kamu mau; program Piper ikut terunduh bersama suara pertamamu.

## Mulai

1. Buka Pengaturan, Suara Piper, lalu unduh sebuah suara (lihat bagian berikutnya).
2. Buka Pengaturan, Suara Hariku, lalu di "Sumber" pilih "Suara neural Piper
   (offline)".
3. Pilih "Bahasa" dan "Suara", lalu tekan Coba untuk mendengarnya.
4. Centang apa saja yang dibacakan Suara Hariku, misalnya "Bacakan pengingat dengan
   Suara Hariku saat waktunya tiba", lalu tekan Oke.

## Mengunduh suara

1. Di Pengaturan, Suara Piper, pilih bahasa di "Bahasa". Bahasamu sendiri ada paling
   atas; "Semua bahasa" menampilkan semua suara.
2. Di daftar "Suara", tiap baris berisi nama suara, bahasa, kualitas (Sangat rendah,
   Rendah, Sedang, atau Tinggi), ukuran, dan apakah sudah terpasang. "Detail"
   menjelaskan lebih banyak tentang suara yang terpilih.
3. Tekan Unduh... (atau Enter di suaranya). Hariku mengambil model card suara itu
   dulu, lalu jendela "Unduh suara Piper" memberi tahu nama suara, kualitasnya, ukuran
   unduhan, dan lisensi datasetnya. Kotak "Model card" berisi keterangan dari model
   card tersebut.
4. Tekan Unduh untuk lanjut, atau Batal.

Pertama kali, program Piper (21,4 MB, dari GitHub) ikut diunduh bersama suaranya, dan
ukurannya sudah dihitung di jendela tadi. Hariku menyebutkan kemajuannya di 25, 50, 75,
dan 100 persen, lalu memberi tahu kalau suaranya siap. "Batalkan unduhan" menghentikan
unduhan; hanya satu unduhan yang berjalan dalam satu waktu. Status dan "Kemajuan
unduhan" di halaman itu menunjukkan sudah sampai mana.

Kalau model card tidak menyebutkan lisensi yang jelas untuk dataset suaranya, Hariku
memberi tahu. Cek dulu halaman dataset itu sebelum kamu mengandalkan suaranya.

## Menghapus suara

Pilih suara yang sudah terpasang lalu tekan Hapus (atau Delete). Hariku bertanya dulu.
Kamu bisa mengunduhnya lagi nanti.

## Daftar suara

Daftar suara diambil dari Hugging Face saat kamu pertama kali membuka halamannya, lalu
disimpan Hariku selama seminggu. Tekan "Perbarui katalog" untuk mengambil daftar
terbaru sekarang juga. Tanpa internet, Hariku menampilkan daftar yang tersimpan
terakhir kali, dan suara yang sudah kamu pasang selalu ditampilkan.

## Cara Piper berbicara

Teks panjang, seperti Briefing, diucapkan kalimat demi kalimat: kalimat pertama diputar
sementara Piper membuat kalimat berikutnya. Selama kamu memakainya, Piper tetap memuat
suaranya (sekitar 100 MB memori) dan melepasnya setelah sepuluh menit tidak dipakai. Apa
yang sudah diucapkan sebuah suara disimpan, sampai 30 MB, jadi kalimat yang diucapkan
lagi langsung terdengar.

## Privasi

Suara Piper berbicara di komputermu: teks yang dibacakannya tidak pernah keluar dari
komputermu. Suara Piper hanya terhubung ke internet untuk halaman pengaturannya:

- Saat kamu membuka halamannya, ia mengambil daftar suara dari Hugging Face, paling
  sering seminggu sekali, atau saat kamu menekan "Perbarui katalog". Melihat-lihat
  daftarnya tidak mengirim apa pun.
- Saat kamu menekan Unduh, ia mengambil model card suara itu dari Hugging Face, dan
  kalau kamu lanjut, berkas suaranya dari Hugging Face. Bersama suara pertamamu, ia
  juga mengambil program Piper dari GitHub.

Permintaan ini tidak membawa akun atau data apa pun tentang kamu. Hariku hanya mengunduh
dari GitHub dan Hugging Face, dan menghapus berkas yang checksum-nya tidak cocok.

Program dan suaranya ada di `%APPDATA%\Hariku2\piper`, suara yang tersimpan ada di
`%APPDATA%\Hariku2\voice_cache\piper`. Hapus suara di halaman Suara Piper, atau hapus
folder-folder itu untuk membuang semuanya.
