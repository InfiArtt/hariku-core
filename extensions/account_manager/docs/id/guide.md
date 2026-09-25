# Hariku Account Manager

Masuk ke Hariku dengan akun InfiArtt-mu dari infiartt.com, supaya ekstensi dengan fitur
online bisa tahu siapa kamu. Saat ini belum ada ekstensi resmi Hariku yang memakainya,
jadi kamu baru perlu masuk kalau ada ekstensi yang memintanya. Halamannya berbahasa
Inggris, jadi labelnya ditulis seperti yang muncul di layar.

## Mulai

Buka Pengaturan lalu pilih halaman "Hariku Cloud". Di bawah "Account Status" tertulis
"Status: Not logged in", atau "Logged in as:" dengan nama penggunamu dan "Roles:" dengan
peranmu.

## Masuk

1. Tekan "Login with Passkey / 2FA". Statusnya berubah menjadi "Status: Waiting for
   browser login...".
2. Browser-mu membuka halaman masuk infiartt.com. Masuk di sana dengan cara yang diminta
   situsnya. Kata sandimu tidak pernah diketik di Hariku.
3. Saat browser menampilkan "Login Successful!", tutup halaman itu dan kembali ke Hariku.
   Notifikasi "Welcome back," dengan nama penggunamu muncul, dan halamannya menampilkan
   "Logged in as:".

Browser mengembalikan hasil masuknya ke Hariku lewat komputermu sendiri (localhost, port
16623). Kalau gagal atau kamu membatalkannya di situs, notifikasi "Login Failed" muncul.
Kalau kamu menutup browser sebelum selesai, Hariku terus menunggu; nyalakan ulang Hariku
sebelum mencoba lagi.

## Keluar

Tekan "Logout". Hariku menghapus token akses dan profilmu dari komputer ini, lalu
notifikasi "You have been securely logged out." muncul. Ini tidak mengeluarkanmu dari
infiartt.com di browser.

## Privasi

Account Manager hanya terhubung ke infiartt.com saat kamu masuk. Ia membuka halaman masuk
situs itu di browser-mu, lalu mengirim ke infiartt.com kode sekali pakai yang diberikan
situs itu, menerima token akses, dan mengambil profilmu: nama pengguna dan peranmu. Token
dan profil itu disimpan di komputermu sampai kamu keluar. Saat Hariku menyala, ekstensi
ini tidak menghubungi apa pun; ia hanya memberi tahu ekstensimu yang lain bahwa kamu sudah
masuk. Kebijakan privasi infiartt.com, di infiartt.com/privacy, mengatur data yang
disimpan situs itu.
