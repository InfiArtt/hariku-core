# Briefing Pagi

Briefing Pagi membacakan ringkasan singkat harimu: sapaan, tanggal, pengingat hari ini,
dan kabar dari ekstensimu yang lain. Malam harinya, ada ringkasan kedua yang menyebutkan
apa yang sudah kamu selesaikan hari ini dan apa yang menunggu besok. Butuh Hariku 2.7 atau
yang lebih baru.

## Mulai

Di jendela utama Hariku, tekan B untuk briefing pagi dan Shift+B untuk ringkasan malam.
Dari mana saja, buka Aruna (Ctrl+Alt+Backspace) lalu ketik atau ucapkan "briefing" atau
"ringkasan malam". Keduanya juga bisa diputar sendiri: lihat Memutar otomatis di bawah.

## Isi briefing pagi

Urutannya:

1. Sapaan sesuai waktu, misalnya "Selamat pagi, Budi." Sapaannya memakai sebutan dan
   panggilanmu dari Pengaturan, Profil. Saat kamu ulang tahun, ada tambahan "Selamat
   ulang tahun!".
2. Tanggal hari ini, dengan format tanggal yang kamu pilih di Pengaturan.
3. Pengingat hari ini yang belum selesai, urut sesuai jam, masing-masing dengan jamnya:
   "Ada 2 pengingat hari ini. 09:00, Rapat pagi. 14:00, Telepon Budi." Paling banyak 10
   yang dibacakan, lalu disebutkan berapa sisanya. Pengingat berulang ikut dihitung, dan
   placeholder di judulnya sudah diisi.
4. Satu kalimat dari tiap ekstensimu yang lain yang punya kabar untuk hari ini.

Kalau tidak ada pengingat, kamu mendengar "Tidak ada pengingat hari ini.", dan kalau
semuanya sudah selesai, "Semua pengingat hari ini sudah selesai."

## Tambahan dari ekstensi lain

Briefing Pagi tidak punya daftar yang perlu dicentang. Tiap ekstensi terpasang yang ikut
serta menambahkan kalimatnya sendiri setelah pengingatmu, dan hanya kalau datanya masih
baru:

- Cuaca: cuaca sekarang, serta suhu tertinggi, terendah, dan peluang hujan hari ini.
- Gempa & Tsunami: gempa di dekatmu dalam 24 jam terakhir, menurut BMKG.
- Kondisi Laut: gelombang dan pasang berikutnya.
- Kualitas Udara: indeks kualitas udara.
- Antariksa: matahari terbenam dan fase bulan, serta peluncuran roket hari ini.
- Pola Tidur: berapa lama kamu tidur semalam.
- Timer & Alarm: alarm hari ini yang belum berbunyi.
- Kokpit: cuaca bandaramu, dalam Mode Kapten atau kalau "Tambahkan cuaca bandara ke
  Briefing Pagi (tanpa Mode Kapten)" dicentang.

Untuk melewatkan salah satunya, matikan pilihannya sendiri kalau ada (seperti di Kokpit),
atau nonaktifkan ekstensinya di Pengelola Ekstensi (Ctrl+X). Briefing hanya membaca data
yang sudah dimiliki ekstensinya, jadi tidak pernah menunggu internet.

## Ringkasan malam

Tekan Shift+B, atau bilang ke Aruna "ringkasan malam" atau "evening summary". Urutannya:

1. Sapaan, dan "Selamat ulang tahun!" saat kamu ulang tahun.
2. Hasil hari ini: "3 dari 5 pengingat hari ini sudah selesai. Belum selesai:", lalu yang
   tersisa, urut sesuai jam. Atau "Semua pengingat hari ini sudah selesai.", atau "Hari
   ini tidak ada pengingat."
3. Besok: berapa pengingatmu, dan yang pertama dengan jamnya. Misalnya "Besok ada 1
   pengingat: 08:00, Dokter gigi." Atau "Besok tidak ada pengingat."
4. Tambahan ekstensi untuk besok: Cuaca menyebutkan cuaca besok ("Besok: hujan ringan, 31
   derajat."), dan Kokpit dalam Mode Kapten menyebutkan prakiraan bandaramu.

## Memutar otomatis

Di Pengaturan, Briefing Pagi:

- "Putar briefing saat Hariku pertama kali dijalankan setiap hari": mati secara bawaan.
  Kalau dinyalakan, briefing diputar beberapa detik setelah Hariku dimulai, sekali sehari.
  Kalau Hariku menyapamu saat dimulai ("Sapa saya saat Hariku dimulai" di Pengaturan,
  Profil), briefing menunggu sapaan itu selesai dan tidak menyapa lagi.
- "Putar ringkasan malam secara otomatis setiap malam": mati secara bawaan.
- "Waktu ringkasan malam:": dari 18:00 sampai 23:00, tiap setengah jam; bawaannya 20:00.

Briefing pagi diputar saat Hariku dimulai, bukan pada jam tertentu. Kalau Hariku menyala
semalaman, tekan B di pagi hari. Ringkasan malam diputar sekali tiap malam: kalau Hariku
belum jalan pada jam yang kamu pilih, ringkasannya diputar begitu Hariku jalan, sampai
tengah malam.

## Mendengarnya dengan Suara Hariku

Screen reader-mu yang membacakan briefing dan ringkasan malam. Supaya dibacakan suara
lain, centang "Bacakan Briefing dan ringkasan malam dengan Suara Hariku" di Pengaturan,
Suara Hariku. Tekan S di jendela utama Hariku untuk menghentikan Suara Hariku.

## Tombol dan perintah

- B: Putar briefing pagi.
- Shift+B: Putar ringkasan malam.

Tombolnya berlaku di jendela utama Hariku. Ganti tombolnya di Pengaturan, Pintasan
Keyboard, di bawah "Morning Briefing". Di sana kamu juga bisa menjadikannya global, supaya
bisa dipakai di luar Hariku.

Di Aruna, diketik atau diucapkan:

- Briefing pagi: "briefing", "briefing pagi", "ringkasan pagi" atau "morning briefing".
- Ringkasan malam: "ringkasan malam", "rangkuman malam" atau "evening summary".

Keduanya hanya berbicara, jadi teksnya juga tampil di Hasil terakhir Aruna.

## Privasi

Briefing Pagi tidak membuat sambungan internet sendiri. Ia membaca pengingatmu dan data
yang sudah dimiliki ekstensimu di komputermu. Kalau Suara Hariku membacakannya dengan
suara online, seperti Edge Voices, teksnya dikirim ke layanan suara itu.
