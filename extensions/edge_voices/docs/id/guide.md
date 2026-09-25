# Suara Edge

Suara Edge menambahkan suara neural online Microsoft Edge ke Suara Hariku, dengan suara
untuk banyak bahasa, termasuk suara bahasa Indonesia Ardi dan Gadis. Suara ini butuh
internet: teks yang dibacakan dikirim ke Microsoft.

## Mulai

Suara Edge tidak punya halaman sendiri. Suaranya kamu pilih di Pengaturan, Suara Hariku:

1. Buka Pengaturan, Suara Hariku.
2. Centang apa saja yang dibacakan Suara Hariku, misalnya "Bacakan pengingat dengan
   Suara Hariku saat waktunya tiba" atau "Bacakan jawaban Aruna dengan Suara Hariku".
3. Di "Sumber", pilih "Suara neural Microsoft Edge (online)".
4. Pilih "Bahasa", lalu "Jenis kelamin" kalau mau, lalu "Suara", misalnya Gadis atau
   Ardi untuk bahasa Indonesia.
5. Atur "Kecepatan (-10 sampai 10)" dan "Volume (0 sampai 100)", lalu tekan Coba untuk
   mendengar suaranya.
6. Tekan Oke.

Daftar suaranya diambil dari Microsoft, jadi pertama kali butuh sebentar untuk muncul.

## Kalau layanannya tidak menjawab

Layanan suara Edge dibuat untuk browser Edge, dan bisa berhenti berfungsi kapan saja.
Karena itu, pilih cadangan di "Jika suara ini tidak tersedia, gunakan": suara Windows,
atau "Screen reader". Hariku memakainya setiap kali suara Edge tidak bisa berbicara,
misalnya saat tidak ada internet. Setelah tiga kali gagal berturut-turut, Hariku tidak
memakai suara Edge selama sepuluh menit, supaya pengumumanmu tidak menunggu.

Apa yang sudah diucapkan suara Edge disimpan di komputermu, sampai 30 MB (yang paling
lama tidak dipakai dihapus duluan). Kalimat yang diucapkan lagi, seperti sapaan saat
Hariku menyala, langsung terdengar, bahkan tanpa internet.

## Privasi

Suara Edge hanya mengirim teks saat suara Edge berbicara: saat Edge menjadi sumber Suara
Hariku, saat kamu menekan Coba, atau saat ekstensi seperti Keliling Dunia atau Orbit
berbicara dengan suara Edge. Yang dikirim adalah teks yang dibacakan, beserta suara dan
kecepatannya, ke layanan suara Microsoft (`speech.platform.bing.com`) lewat koneksi
terenkripsi. Teks itu bisa berisi namamu dan judul pengingatmu. Permintaannya tidak
membawa akun atau data lain tentang kamu. Daftar suaranya diambil dari layanan yang
sama, paling sering seminggu sekali, dan tidak berisi apa pun tentang kamu.

"Tentang sumber ini" di halaman Suara Hariku juga menjelaskan hal ini. Suara yang
tersimpan dan daftar suaranya ada di `%APPDATA%\Hariku2\voice_cache\edge`; hapus folder
itu untuk membuangnya.
