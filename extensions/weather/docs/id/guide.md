# Cuaca

Cuaca memberi tahu cuaca sekarang dan menampilkan prakiraan 7 hari untuk satu tempat.
Datanya dari Open-Meteo.com, tanpa akun atau kunci. Butuh Hariku 2.8 atau yang lebih baru.

## Mulai

Cuaca memakai tempat utamamu dari Pengaturan, Tempat (Ctrl+P membuka Pengaturan). Kalau
belum punya tempat, tambahkan dulu di sana, atau pilih kota khusus untuk Cuaca di
Pengaturan, Cuaca.

Lalu, di jendela utama Hariku:

- Shift+W mengucapkan cuaca sekarang.
- "Buka prakiraan cuaca" membuka jendela prakiraan. Awalnya aksi ini belum punya tombol:
  jalankan lewat Aruna (Ctrl+Alt+Backspace), atau beri tombol di Pintasan Keyboard.

## Mendengar cuaca sekarang

Tekan Shift+W, atau bilang ke Aruna "cuaca" atau "weather". Kamu mendengar nama tempatnya,
kondisi langit, suhu dan rasanya, kelembapan dan angin, lalu suhu tertinggi, terendah, dan
peluang hujan hari ini. Contohnya: "Rumah: Hujan ringan, 27 derajat, terasa seperti 30.
Kelembapan 80 persen, angin 12 kilometer per jam. Hari ini: tertinggi 31, terendah 24,
peluang hujan 70 persen."

Kalau Hariku sudah mengambil data cuaca dalam 10 menit terakhir, kamu langsung
mendengarnya. Kalau belum, Hariku bilang "Mengambil data cuaca..." lalu mengucapkannya
begitu datanya datang. Tanpa internet, kamu mendengar data cuaca terakhir selama umurnya
belum 12 jam, lengkap dengan jam datanya.

## Prakiraan 7 hari

Jalankan "Buka prakiraan cuaca", atau bilang ke Aruna "prakiraan cuaca" atau "weather
forecast". Jendela Prakiraan Cuaca berisi satu hari per baris, mulai hari ini: tanggal,
kondisi langit, suhu tertinggi dan terendah, serta peluang hujan. Pindah antarhari dengan
tombol panah. Label daftarnya menyebutkan satuan suhu yang dipakai.

Di bawah daftar ada baris yang menyebutkan kapan prakiraannya diperbarui. Tombol Perbarui
mengambil prakiraan baru, dan Tutup atau Escape menutup jendelanya. Prakiraan yang lebih
tua dari 10 menit langsung diperbarui sendiri saat jendelanya dibuka.

## Memilih tempat

Buka Pengaturan, Cuaca. Daftar "Tempat:" berisi:

- "Tempat utama", dengan namanya: tempat utamamu dari Pengaturan, Tempat. Ini pilihan
  bawaannya.
- Tempat-tempatmu yang lain, sesuai namanya.
- "Tempat sendiri…": kota khusus untuk Cuaca.

Untuk memakai kota sendiri:

1. Pilih "Tempat sendiri…" di "Tempat:".
2. Di "Kota yang dicari, untuk tempat sendiri (tekan Enter untuk mencari):", ketik minimal
   2 huruf nama kotanya, lalu tekan Enter.
3. Fokus pindah ke "Hasil pencarian:". Pilih kotamu, lalu tekan Oke.

"Tempat sendiri:" menampilkan kota yang tersimpan. Pencarian hanya bisa dipakai selama
"Tempat sendiri…" yang dipilih. Kalau kamu menghapus tempat yang dipakai Cuaca, Cuaca
kembali memakai tempat utama.

## Pengaturan

Di Pengaturan, Cuaca:

- "Tempat:": tempat yang dipakai (lihat di atas).
- "Satuan:": "Celsius, kilometer per jam" (bawaan) atau "Fahrenheit, mil per jam".

## Cuaca di briefing dan teksmu

Cuaca memperbarui prakiraannya di latar belakang saat Hariku dimulai dan kira-kira setiap
30 menit, jadi yang berikut ini siap tanpa menunggu:

- Briefing Pagi (B) menyebutkan cuaca sekarang serta suhu tertinggi, terendah, dan
  peluang hujan hari ini: "Cuaca di Rumah: Hujan ringan, 27 derajat, tertinggi 31,
  terendah 24, peluang hujan 70 persen."
- Ringkasan malam (Shift+B) menyebutkan cuaca besok: "Besok: hujan ringan, 31 derajat."
- %weather% di pengingat, rutinitas, atau sapaan saat Hariku dimulai diganti dengan cuaca
  sekarang, misalnya "hujan ringan, 25 derajat".

Semuanya hanya memakai prakiraan dari 3 jam terakhir. Kalau tidak ada, briefing melewatkan
cuaca dan %weather% dibiarkan kosong.

## Tombol dan perintah

- Shift+W: Ucapkan cuaca saat ini.
- Tanpa tombol: Buka prakiraan cuaca.

Tombolnya berlaku di jendela utama Hariku. Ganti tombolnya, atau beri tombol untuk
prakiraan, di Pengaturan, Pintasan Keyboard, di bawah "Weather". Di sana kamu juga bisa
menjadikannya global, supaya bisa dipakai di luar Hariku.

Di Aruna, diketik atau diucapkan:

- Cuaca sekarang: "cuaca", "cuaca hari ini", "cuaca sekarang", "cuaca saat ini", "suhu",
  "berapa suhu", "weather", "current weather" atau "temperature". Perintah ini hanya
  berbicara, jadi jawabannya juga tampil di Hasil terakhir Aruna.
- Jendela prakiraan: "prakiraan cuaca", "ramalan cuaca", "cuaca besok", "weather
  forecast", "forecast" atau "weather tomorrow".

## Privasi

Cuaca tidak mengirim apa pun sebelum punya tempat. Setelah itu, Cuaca meminta prakiraan ke
Open-Meteo (`api.open-meteo.com`) saat Hariku dimulai, kira-kira setiap 30 menit, dan saat
kamu memintanya. Permintaannya berisi tempat yang dibulatkan sekitar 1 kilometer dan zona
waktunya, tidak pernah titik persisnya. Mencari kota mengirim teks yang kamu ketik dan
bahasa Hariku-mu ke pencarian kota Open-Meteo (`geocoding-api.open-meteo.com`). Prakiraan
terakhir disimpan di komputermu.
