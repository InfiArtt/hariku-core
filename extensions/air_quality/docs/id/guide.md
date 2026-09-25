# Kualitas Udara

Kualitas Udara memberi tahu seberapa bersih udara di tempatmu: indeks kualitas udara dan
kategorinya, partikel halus dan kasar (PM2,5 dan PM10), indeks UV, dan satu saran singkat.
Ekstensi ini juga menampilkan prakiraan beberapa jam dan hari ke depan, dan bisa
memperingatkanmu sekali sehari kalau udaranya jadi tidak sehat. Butuh Hariku 2.8 atau
lebih baru.

## Mulai

Kualitas Udara memakai tempat utamamu dari Pengaturan, Tempat (Pengaturan dibuka dengan
Ctrl+P). Kalau belum punya tempat, tambahkan di sana, atau pilih kota khusus untuk
Kualitas Udara di Pengaturan, Kualitas Udara.

Setelah itu, tekan U di jendela utama Hariku untuk mendengar kualitas udara, dan Shift+U
untuk membuka prakiraannya. Bisa juga lewat Aruna, bilah perintah Hariku: tekan
Ctrl+Alt+Backspace lalu ketik "kualitas udara".

## Mendengar kualitas udara

Tekan U. Hariku menyebutkan, berurutan:

- tempatnya, indeks kualitas udara (0 sampai 500) dan kategorinya: baik, sedang, tidak
  sehat bagi kelompok sensitif, tidak sehat, sangat tidak sehat, atau berbahaya
- kalau udaranya tidak baik, polutan yang paling menentukan indeksnya, misalnya ozon atau
  partikel halus
- PM2,5 dan PM10, dalam mikrogram per meter kubik
- indeks UV dan kategorinya: rendah, sedang, tinggi, sangat tinggi, atau ekstrem
- saran singkat sesuai kategori, misalnya siapa yang sebaiknya mengurangi aktivitas di
  luar ruangan

Kalau data terakhir umurnya kurang dari 10 menit, kamu langsung mendengarnya. Kalau lebih,
Hariku bilang "Mengambil data kualitas udara..." lalu mengambil data baru. Kalau
layanannya tidak bisa dihubungi, Hariku menyebutkan masalahnya, lalu membacakan data
terakhir yang ada beserta jam pengambilannya, selama umurnya kurang dari 12 jam.

Hariku juga memperbarui kualitas udara sendiri saat mulai dan kira-kira tiap 30 menit,
jadi jawabannya biasanya sudah siap.

## Jendela prakiraan

Tekan Shift+U untuk membuka jendela Prakiraan Kualitas Udara. Isinya dua daftar:

- Jam-jam berikutnya di tempatmu: satu baris tiap 3 jam untuk kira-kira sehari, berisi
  indeks, PM2,5, dan indeks UV kalau nilainya di atas nol.
- "Hari-hari berikutnya (nilai tertinggi)": satu baris per hari mulai hari ini, sampai 5
  hari, berisi indeks, PM2,5, dan indeks UV tertinggi hari itu.

Tiap baris satu kalimat, jadi tombol panah membacakan satu jam atau satu hari utuh. Di
bawah daftar ada keterangan kapan data diperbarui. Tekan Perbarui untuk mengambil data
lagi, dan Tutup atau Escape untuk menutup jendelanya.

## Peringatan udara tidak sehat

Supaya diberi tahu saat udara memburuk, buka Pengaturan, Kualitas Udara, centang "Umumkan
sekali sehari bila udara menjadi tidak sehat (indeks 151 atau lebih)", lalu tekan Oke.

Saat indeksnya mencapai 151 atau lebih, Hariku membunyikan suara lalu menyebutkan tempat,
indeks, kategori, dan sarannya. Paling banyak sekali sehari, dan hanya dari data yang
umurnya kurang dari satu jam. Selama jam tenang (Pengaturan, Jam Tenang) Hariku diam saja;
pemeriksaan pertama setelah jam tenang akan melihat udaranya lagi.

## Di Briefing Pagi

Kalau data terakhir umurnya kurang dari 3 jam, Briefing Pagi menyebutkan satu kalimat
berisi tempat, indeks, dan kategorinya. Tidak ada yang perlu dinyalakan.

## Pengaturan

Buka Pengaturan, Kualitas Udara:

- "Tempat": tempat yang dipakai. Bawaannya "Tempat utama"; kamu juga bisa memilih tempatmu
  yang lain, atau "Tempat sendiri…" untuk kota khusus Kualitas Udara.
- Kalau "Tempat sendiri…" dipilih, ketik nama kota di "Kota yang dicari, untuk tempat
  sendiri (tekan Enter untuk mencari)" lalu tekan Enter atau Cari. Pilih kotamu di "Hasil
  pencarian" lalu tekan Oke. Kolom "Tempat sendiri" menampilkan kota yang tersimpan.
- "Umumkan sekali sehari bila udara menjadi tidak sehat (indeks 151 atau lebih)":
  peringatan di atas. Awalnya mati.

## Tentang angkanya

- Indeksnya adalah US AQI (Indeks Kualitas Udara Amerika Serikat) dari U.S. EPA.
  Kategorinya mirip ISPU Indonesia, tapi cara menghitung angkanya berbeda, jadi bisa tidak
  sama dengan angka ISPU.
- Datanya dari model global (CAMS) dengan sel sekitar 40 kilometer (sekitar 10 kilometer
  di Eropa). Angkanya menggambarkan wilayah yang lebih luas, bukan jalan rumahmu.
- Sarannya mengikuti panduan umum U.S. EPA untuk tiap kategori. Ini bukan nasihat medis.

## Tombol dan perintah

Tombol ini berlaku di jendela utama Hariku:

- U: Ucapkan kualitas udara
- Shift+U: Buka prakiraan kualitas udara

Kamu bisa menggantinya di Pengaturan, Pintasan Keyboard.

Di Aruna (Ctrl+Alt+Backspace), "kualitas udara", "polusi udara", "air quality", atau
"pollution" membacakan kualitas udara. Untuk prakiraan, ketik namanya: "buka prakiraan
kualitas udara".

## Privasi

Data kualitas udara berasal dari Open-Meteo (`air-quality-api.open-meteo.com`), tanpa akun
atau kunci. Tidak ada yang dikirim sebelum kamu punya tempat. Setelah itu, Hariku meminta
data saat mulai, kira-kira tiap 30 menit, dan saat kamu bertanya. Tiap permintaan berisi
tempatmu yang dibulatkan sekitar 1 kilometer, beserta zona waktunya, tidak pernah titik
persisnya.

Mencari kota mengirim teks yang kamu ketik, dan bahasa Hariku-mu, ke pencarian kota
Open-Meteo (`geocoding-api.open-meteo.com`).
