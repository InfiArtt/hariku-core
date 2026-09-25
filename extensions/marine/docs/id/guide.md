# Kondisi Laut

Kondisi Laut memberi tahu gelombang, alun, suhu laut, dan pasang surut (air sedang naik
atau turun, serta pasang dan surut berikutnya) untuk pantai, pelabuhan, atau kota pesisir,
dan menampilkan hari-hari berikutnya serta pasang surutnya di sebuah jendela. Datanya dari
Open-Meteo.com, tanpa akun atau kunci. Butuh Hariku 2.8 atau yang lebih baru.

## Mulai

Di jendela utama Hariku, tekan O untuk mendengar kondisi laut sekarang dan Shift+O untuk
prakiraan laut. Dari mana saja, buka Aruna (Ctrl+Alt+Backspace) lalu ketik atau ucapkan
"kondisi laut" atau "sea conditions".

Kondisi Laut memakai tempat utamamu dari Pengaturan, Tempat (Ctrl+P membuka Pengaturan).
Tempat di daratan tidak punya data laut, jadi kalau rumahmu jauh dari laut, pilih pantai
atau pelabuhan di Pengaturan, Kondisi Laut (lihat Memilih tempat).

## Mendengar kondisi laut sekarang

Tekan O. Kamu mendengar nama tempatnya, gelombang (tinggi, keadaan laut, arah datangnya,
dan periodenya), alun, suhu laut, dan pasang surut. Contohnya: "Kuta: Gelombang 0,8
meter, rendah, dari barat daya, periode 9 detik. Alun 0,6 meter. Suhu laut 29 derajat. Air
laut sedang naik: pasang sekitar pukul 21:40, surut besok sekitar pukul 03:10."

Kata setelah tinggi gelombang adalah keadaan laut, menurut skala WMO yang juga dipakai
BMKG: tenang, rendah, sedang, tinggi, sangat tinggi, ekstrem, atau sangat ekstrem. Waktu
pasang surut dibulatkan ke 10 menit, makanya Hariku bilang "sekitar".

Kalau Hariku sudah mengambil datanya dalam 10 menit terakhir, kamu langsung mendengarnya.
Kalau belum, Hariku bilang "Mengambil kondisi laut..." lalu mengucapkannya begitu datanya
datang. Tanpa internet, kamu mendengar data terakhir selama umurnya belum 12 jam, lengkap
dengan jam datanya. Untuk tempat di daratan, kamu mendengar misalnya "Tidak ada data laut
untuk Rumah. Pilih pantai atau pelabuhan di Pengaturan, Kondisi Laut."

## Prakiraan laut

Tekan Shift+O. Jendela Prakiraan Laut punya dua daftar:

- "Hari-hari berikutnya di", dengan nama tempatnya: satu baris per hari, mulai hari ini,
  selama 7 hari. Tiap baris berisi gelombang tertinggi dan keadaan lautnya, arah
  datangnya, periode terpanjang, alun tertinggi, serta pasang dan surut hari itu.
- "Pasang surut berikutnya:": setiap pasang dan surut yang akan datang, dengan hari, jam,
  dan tinggi air di atas atau di bawah permukaan laut rata-rata. Contohnya: "Pasang hari
  ini sekitar pukul 21:40, 0,9 meter di atas permukaan laut rata-rata."

Tab berpindah antardaftar, dan tombol panah menelusuri isi tiap daftar. Baris di bawahnya
menyebutkan kapan datanya diperbarui. Tombol Perbarui mengambil data baru, dan Tutup atau
Escape menutup jendelanya. Data yang lebih tua dari 10 menit langsung diperbarui sendiri
saat jendelanya dibuka.

## Peringatan gelombang tinggi

Kondisi Laut bisa memberitahumu sekali sehari kalau gelombang di tempatmu tinggi. Di
Pengaturan, Kondisi Laut:

- "Umumkan gelombang tinggi sekali sehari": mati secara bawaan.
- "Umumkan bila gelombang mencapai:": dari "1 meter, rendah" sampai "6 meter, ekstrem";
  bawaannya "2,5 meter, tinggi".

Kalau gelombang tertinggi yang diperkirakan hari ini (sekarang, atau di prakiraan hari
ini) mencapai tinggi itu, terdengar suara lalu misalnya "Peringatan laut untuk Kuta:
gelombang hingga 2,6 meter hari ini, tinggi." Hariku memeriksanya setiap kali datanya
diperbarui: saat Hariku dimulai dan kira-kira setiap 30 menit. Selama jam tenang
(Pengaturan, Jam Tenang) peringatannya diam, dan pemeriksaan pertama setelah jam tenang
melihat gelombangnya lagi.

## Memilih tempat

Buka Pengaturan, Kondisi Laut. Daftar "Tempat:" berisi "Tempat utama" (bawaannya),
tempat-tempatmu yang lain, dan "Tempat sendiri…" untuk tempat khusus ekstensi ini,
misalnya pantai. Untuk memakai tempat sendiri:

1. Pilih "Tempat sendiri…" di "Tempat:".
2. Di "Pantai, pelabuhan, atau kota pesisir yang dicari, untuk tempat sendiri (tekan
   Enter untuk mencari):", ketik minimal 2 huruf namanya, lalu tekan Enter.
3. Fokus pindah ke "Hasil pencarian:". Pilih tempatnya, lalu tekan Oke.

"Tempat sendiri:" menampilkan tempat yang tersimpan.

Perlu diingat:

- Data laut berasal dari model laut global. Angkanya menggambarkan perairan di sekitar
  tempat itu, kira-kira 5 sampai 25 kilometer, bukan satu pantai saja.
- Waktu pasang surut adalah perkiraan dari tinggi muka laut model. Jangan
  mengandalkannya untuk navigasi atau keselamatan di laut.

## Di Briefing Pagi

Dengan ekstensi Briefing Pagi, briefing ikut menyebutkan kondisi laut: "Laut di Kuta:
gelombang 0,8 meter, rendah, pasang berikutnya sekitar pukul 21:40." Briefing hanya
memakai data dari 3 jam terakhir; Kondisi Laut memperbaruinya di latar belakang saat
Hariku dimulai dan kira-kira setiap 30 menit.

## Tombol dan perintah

- O: Ucapkan kondisi laut.
- Shift+O: Buka prakiraan laut.

Tombolnya berlaku di jendela utama Hariku. Ganti tombolnya di Pengaturan, Pintasan
Keyboard, di bawah "Sea Conditions". Di sana kamu juga bisa menjadikannya global, supaya
bisa dipakai di luar Hariku.

Di Aruna, diketik atau diucapkan:

- Kondisi laut sekarang: "kondisi laut", "ombak", "gelombang laut", "sea conditions" atau
  "waves". Perintah ini hanya berbicara, jadi jawabannya juga tampil di Hasil terakhir
  Aruna.
- Jendela prakiraan: sebut namanya, "Buka prakiraan laut" atau "Open the sea forecast".

## Privasi

Kondisi Laut tidak mengirim apa pun sebelum punya tempat. Setelah itu, ia meminta data ke
Marine API Open-Meteo (`marine-api.open-meteo.com`) saat Hariku dimulai, kira-kira setiap
30 menit, dan saat kamu memintanya. Permintaannya berisi tempat yang dibulatkan sekitar 1
kilometer dan zona waktunya, tidak pernah titik persisnya. Mencari tempat mengirim teks
yang kamu ketik dan bahasa Hariku-mu ke pencarian kota Open-Meteo
(`geocoding-api.open-meteo.com`). Data terakhir disimpan di komputermu.
