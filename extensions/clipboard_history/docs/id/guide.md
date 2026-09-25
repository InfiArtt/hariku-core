# Riwayat Clipboard

Riwayat Clipboard menyimpan daftar teks yang kamu salin, jadi kamu bisa mencarinya,
menyematkannya, dan menyalinnya lagi nanti. Butuh Hariku 2.4 atau yang lebih baru.

## Mulai

Salin teks di mana saja di Windows seperti biasa, dengan Ctrl+C. Selama Hariku berjalan,
setiap salinan masuk ke riwayat. Di jendela utama Hariku, tekan V untuk membuka riwayat,
atau Shift+V untuk mendengar teks yang terakhir kamu salin.

## Menyalin lagi

1. Tekan V. Jendela "Riwayat clipboard" terbuka di daftar item, dari yang terbaru.
2. Telusuri daftarnya dengan panah. Tiap baris menyebut awal teksnya dan kapan kamu
  menyalinnya, misalnya "Rapat jam 10 / Ruang 4, 2 menit yang lalu". Kotak "Teks lengkap"
  di bawah daftar menampilkan seluruh isi item yang dipilih.
3. Tekan Enter, atau "Salin". Jendelanya tertutup dan Hariku bilang "Disalin. Tekan
  Control+V untuk menempel."
4. Tempel di tempat yang kamu mau dengan Ctrl+V.

Hariku tidak pernah menempel sendiri ke program lain.

## Mencari di riwayat

Kotak "Cari" ada tepat sebelum daftar: tekan Shift+Tab dari daftar untuk ke sana. Ketik
satu kata atau lebih, dan hanya item yang berisi semua kata itu yang tersisa di daftar.
Begitu kamu berhenti mengetik, Hariku menyebut berapa item yang cocok. Huruf besar kecil
tidak berpengaruh. Tekan Enter untuk kembali ke daftar.

## Menyematkan item

Sematkan teks yang sering kamu pakai, misalnya alamatmu. Pilih itemnya lalu tekan
"Sematkan". Item yang disematkan pindah ke atas daftar, diawali "Disematkan:", tidak
pernah tergeser salinan baru, dan tetap ada setelah Hariku dimulai ulang. Tekan tombol
yang sama, yang sekarang bernama "Lepas sematan", untuk melepasnya.

## Menghapus item

- Pilih item lalu tekan Delete, atau tombol "Hapus". Item yang disematkan ditanyakan
  dulu.
- "Hapus semua" menghapus semua item yang tidak disematkan, setelah bertanya dulu. Item
  yang disematkan tetap ada.

## Mendengar teks yang terakhir disalin

Tekan Shift+V. Hariku membacakan teks yang terakhir kamu salin. Teks yang sangat panjang
berhenti setelah sekitar 4.000 karakter; buka riwayat untuk membaca semuanya.

## Apa yang direkam

Riwayat Clipboard merekam teks yang kamu salin. Yang tidak direkam:

- teks yang disalin dari pengelola kata sandi seperti KeePass, 1Password dan Bitwarden,
  yang menandai salinannya sebagai rahasia
- salinan yang sama persis dengan salinan terakhir; menyalin lagi teks yang lebih lama
  memindahkannya kembali ke atas
- teks kosong, dan teks lebih dari 100 KB
- apa pun yang disalin saat perekaman dijeda, atau saat Hariku tidak berjalan
- teks yang kamu salin kembali dari riwayat itu sendiri

Riwayat hanya ada di memori dan hilang saat Hariku ditutup, kecuali kamu menyalakan "Ingat
riwayat setelah Hariku dimulai ulang". Item yang disematkan selalu disimpan di komputermu.
Tidak ada yang dikirim lewat internet.

## Pengaturan

Buka Pengaturan (Ctrl+P), lalu halaman Riwayat Clipboard.

- "Jumlah riwayat": 25, 50 atau 100 item; awalnya 50. Kalau daftarnya penuh, item tertua
  yang tidak disematkan dibuang. Item yang disematkan tidak ikut dihitung.
- "Ingat riwayat setelah Hariku dimulai ulang": awalnya mati. Kalau dinyalakan, riwayat
  disimpan di komputermu. Mematikannya langsung menghapus riwayat yang tersimpan, kecuali
  item yang disematkan.
- "Jeda perekaman": tidak ada salinan baru yang direkam sampai centangnya kamu hapus.
  Judul jendela riwayat lalu diakhiri "(perekaman dijeda)".
- "Privasi": catatan singkat tentang apa yang disimpan dan di mana.

Tekan Oke untuk menyimpan.

## Tombol dan perintah

- V: buka riwayat clipboard.
- Shift+V: ucapkan teks yang terakhir disalin.
- Di jendela riwayat: Enter menyalin item yang dipilih, Delete menghapusnya, dan Escape
  menutup jendela.

V dan Shift+V bekerja di jendela utama Hariku. Kamu bisa menggantinya di Pengaturan,
Pintasan Keyboard, di kelompok Clipboard History, dan menjadikannya global di sana supaya
bisa dipakai di luar Hariku juga.

Di Aruna (Ctrl+Alt+Backspace), "riwayat clipboard", "clipboard" atau "clipboard history"
membuka riwayat. "Teks terakhir disalin" atau "last copied text" membacakan salinan
terakhir, dan teksnya juga muncul di "Hasil terakhir" Aruna.
