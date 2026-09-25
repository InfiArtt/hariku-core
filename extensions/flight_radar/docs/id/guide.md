# Radar Pesawat

Radar Pesawat memberi tahu pesawat apa saja yang terbang di dekatmu: beberapa yang
terdekat dengan satu tombol, daftar semua pesawat dalam jangkauan, dan kalau kamu mau,
pengumuman saat ada pesawat melintas di atas atau melaporkan keadaan darurat. Kamu juga
bisa melacak penerbangan di mana saja di dunia dari nomornya, dan membuka LiveATC di
peramban untuk mendengarkan pengatur lalu lintas udara. Butuh Hariku 2.8 atau lebih baru.

## Mulai

Radar Pesawat memakai tempat utamamu dari Pengaturan, Tempat (Pengaturan dibuka dengan
Ctrl+P). Kamu bisa memilih tempatmu yang lain, atau tempat khusus (kota, alamat jalan,
atau koordinat persis), di Pengaturan, Radar Pesawat.

Setelah itu, tekan P di jendela utama Hariku untuk mendengar pesawat di dekatmu, atau
Shift+P untuk membuka daftar radar. Bisa juga lewat Aruna, bilah perintah Hariku: tekan
Ctrl+Alt+Backspace lalu ketik "pesawat terdekat" atau "daftar pesawat".

## Pesawat apa di dekat sini

Tekan P. Hariku bilang "Memeriksa radar..." lalu membacakan 3 pesawat terdekat dalam
radius radarmu (25 kilometer kalau tidak kamu ubah), yang terdekat lebih dulu, lalu berapa
pesawat lainnya. Untuk tiap pesawat kamu mendengar:

- namanya: maskapai dan nomor penerbangan, misalnya Garuda Indonesia 155, atau registrasi
  dan negaranya, atau "Pesawat tanpa identitas"
- dari mana dan ke mana, kalau Hariku menemukan rute yang cocok dengan posisi pesawatnya
- tipe pesawatnya, misalnya Boeing 737-800
- jarak dan arahnya dari tempatmu
- ketinggiannya, dan apakah sedang naik, turun, atau terbang datar

Pesawat yang melaporkan keadaan darurat disebutkan paling dulu, diawali "Perhatian".

Kalau kamu bertanya lagi dalam 15 detik, kamu mendengar radar yang sama. Kalau layanannya
tidak bisa dihubungi, Hariku menyebutkan masalahnya, lalu membacakan radar dari 2 menit
terakhir beserta jamnya, kalau ada.

## Daftar radar

Tekan Shift+P untuk membuka jendela Radar Pesawat. Daftarnya berisi semua pesawat dalam
radius radarmu, yang terdekat lebih dulu, satu kalimat per baris. Baris pesawat yang
sedang darurat diawali "Darurat".

- Telusuri daftar dengan tombol panah. "Detail pesawat yang dipilih" menampilkan info
  tambahan: registrasi, tipe, kecepatan, arah terbang, seberapa cepat naik atau turun,
  kode squawk beserta artinya, status yang dilaporkannya, dan bandara mana yang akan
  dibuka Dengarkan ATC.
- Enter, atau tombol Detail, membacakan detailnya (Hariku mencari rutenya dulu).
- Perbarui mengambil radar baru. Setelah itu Hariku menyebutkan berapa pesawat dalam
  jangkauan, dengan keadaan darurat disebut paling dulu.
- Dengarkan ATC membuka LiveATC untuk pesawat yang dipilih (lihat "Mendengarkan pengatur
  lalu lintas udara" di bawah).
- Lacak... membuka Lacak Penerbangan dengan pesawat yang dipilih sudah terisi.
- Tutup, atau Escape, menutup jendelanya.

Di bawah detail ada keterangan kapan radar diperbarui dan dari layanan mana.

## Pesawat melintas di atas

Supaya diberi tahu saat pesawat lewat di atasmu, buka Pengaturan, Radar Pesawat, centang
"Umumkan pesawat yang melintas di atas", pilih "Jarak peringatan pesawat melintas" (1, 2,
3, 5, atau 10 kilometer; bawaannya 5), lalu tekan Oke.

Selama Hariku berjalan, Hariku memeriksa kira-kira tiap 30 detik. Saat ada pesawat di
udara yang masuk ke jarak itu, Hariku membunyikan suara lalu bilang "Melintas di atas",
disusul pesawatnya. Tiap pesawat diumumkan sekali, lalu tidak lagi selama 10 menit.
Peringatan ini diam selama jam tenang (Pengaturan, Jam Tenang).

## Pemantauan keadaan darurat

Centang "Pantau keadaan darurat di latar belakang" di Pengaturan, Radar Pesawat. Selama
Hariku berjalan, Hariku memeriksa kira-kira tiap 60 detik (tiap 30 detik kalau peringatan
pesawat melintas juga nyala). Saat ada pesawat dalam radius radarmu yang memancarkan kode
darurat (7500, 7600, atau 7700) atau melaporkan keadaan darurat, misalnya bahan bakar
menipis atau gangguan radio, Hariku membunyikan suara lalu bilang "Perhatian", nama
pesawatnya, apa yang dilaporkannya, dan posisinya.

Hariku menyampaikannya sebagai apa yang dipancarkan transponder pesawat, karena kodenya
kadang terpasang tidak sengaja. Tiap pesawat dan keadaan daruratnya diumumkan sekali, lalu
tidak lagi selama 30 menit. Pemantauan ini diam selama jam tenang, dan tidak ada yang
disimpan untuk diumumkan sesudahnya.

## Melacak penerbangan

Tekan Shift+T untuk membuka Lacak Penerbangan. Ketik nomor penerbangan atau registrasi,
misalnya GA 408, QZ 7510, atau PK-GPA, lalu tekan Enter. Kode ICAO 3 huruf maskapainya
juga bisa, misalnya GIA 408. Kalau Hariku tidak mengenal kode maskapai 2 huruf, Hariku
memintamu mengetik kode 3 hurufnya.

Hariku mencari penerbangan itu di mana saja di dunia dan menyebutkan posisinya: rutenya
kalau diketahui, jaraknya dari bandara terdekat yang dikenal Hariku, ketinggiannya, dan
apakah sedang naik atau turun. Kalau penerbangannya sedang tidak memancarkan sinyal
(mungkin masih di darat atau di luar jangkauan), Hariku bilang begitu. Apa pun hasilnya,
penerbangan itu mulai dilacak. Kalau pencariannya sendiri gagal, Hariku menyebutkan
masalahnya dan tidak melacak apa pun. Kamu bisa melacak sampai 3 penerbangan.

Selama Hariku berjalan, penerbangan yang kamu lacak diperiksa kira-kira tiap menit (tiap
30 detik kalau peringatan pesawat melintas nyala), dan Hariku memberi tahu, dengan suara,
saat sebuah penerbangan:

- lepas landas
- melintas di dekatmu (dalam jarak peringatan pesawat melintas)
- sudah 50 kilometer atau kurang dari tujuannya (kalau rutenya diketahui)
- mendarat

Pelacakan berhenti sendiri satu jam setelah mendarat, atau setelah 24 jam. Penerbangan
yang dilacak tetap dilacak walaupun Hariku dibuka ulang, dan tetap diumumkan selama jam
tenang, karena kamu sendiri yang memintanya.

Di jendela Lacak Penerbangan, "Penerbangan yang dilacak (maksimal 3)" menampilkan tiap
penerbangan dengan posisi terakhirnya dan jam pemeriksaannya. Berhenti melacak (atau
Delete) menghentikan penerbangan yang dipilih, dan Periksa sekarang mencari semuanya lalu
menyebutkan posisinya.

Untuk mendengar posisi semua penerbangan yang kamu lacak tanpa membuka jendela, tekan T di
jendela utama Hariku.

## Mendengarkan pengatur lalu lintas udara

Tekan Shift+L untuk membuka halaman web LiveATC di peramban, untuk bandara terdekat dari
tempatmu. Hariku mengenal semua bandara besar dan menengah di Indonesia, serta bandara
besar di sekitar Indonesia dan di kawasan ini, misalnya Singapura, Kuala Lumpur, Bangkok,
Manila, Perth, dan Darwin.

Untuk Jakarta Soekarno-Hatta (WIII) dan Surabaya (WARR), Hariku membuka halaman dengar
LiveATC untuk siaran bandara itu. Untuk bandara lain, Hariku membuka halaman pencarian
LiveATC untuk bandara itu, yang menunjukkan ada siaran langsungnya atau tidak.

Di daftar radar, Dengarkan ATC memilih bandara yang paling mungkin sedang dihubungi
pesawat yang dipilih: bandara tujuannya kalau pesawat sedang turun, bandara asalnya kalau
sedang naik, selain itu yang lebih dekat dari keduanya. Kamu mendengar seluruh
frekuensinya, bukan hanya pesawat itu.

Hariku tidak pernah memutar radionya sendiri. Aturan tentang mendengarkan radio
penerbangan berbeda di setiap negara.

## Pengaturan

Buka Pengaturan, Radar Pesawat:

- "Tempat": tempat yang dipakai. Bawaannya "Tempat utama"; kamu juga bisa memilih tempatmu
  yang lain, atau "Tempat sendiri…" untuk tempat khusus Radar Pesawat.
- "Radius radar": 10, 25 (bawaan), atau 50 kilometer.
- "Satuan": "Metrik: kilometer, meter, km/jam" atau "Penerbangan: mil laut, kaki, knot".
- "Sertakan pesawat yang berada di darat": awalnya mati.
- "Umumkan pesawat yang melintas di atas" dan "Jarak peringatan pesawat melintas": lihat
  di atas.
- "Pantau keadaan darurat di latar belakang": lihat di atas.

### Tempat sendiri

Kalau "Tempat sendiri…" dipilih, cari tempatnya dengan salah satu dari tiga cara, lalu
tekan Oke:

- Kota: ketik di "Kota yang dicari (tekan Enter untuk mencari)" lalu tekan Enter atau
  Cari, kemudian pilih di "Hasil pencarian kota".
- Alamat jalan: ketik di "Alamat jalan yang dicari (tekan Enter untuk mencari)" lalu tekan
  Enter atau Cari alamat, kemudian pilih di "Hasil pencarian alamat".
- Koordinat persis: tempelkan koordinat, misalnya -6,2088; 106,8456, atau tautan peta dari
  Google Maps, Apple Maps, atau OpenStreetMap, di "Koordinat atau tautan peta (tekan Enter
  untuk memakai)", lalu tekan Enter atau Gunakan. Hariku menyebutkan titik yang ditemukan
  dan jaraknya dari bandara terdekat.

Untuk alamat atau koordinat, "Nama tempat ini" memberi nama tempatnya (bawaannya Rumah).
Kolom "Tempat sendiri" menampilkan tempat yang tersimpan.

## Tombol dan perintah

Tombol ini berlaku di jendela utama Hariku:

- P: "Pesawat apa di dekat sini? Ucapkan pesawat terdekat"
- Shift+P: "Buka daftar radar pesawat"
- T: "Di mana penerbangan yang saya lacak? Ucapkan posisinya"
- Shift+T: "Lacak penerbangan"
- Shift+L: "Dengarkan pengatur lalu lintas udara (membuka LiveATC di peramban Anda)"

Kamu bisa menggantinya di Pengaturan, Pintasan Keyboard.

Di Aruna (Ctrl+Alt+Backspace):

- "pesawat", "pesawat di dekat sini", "pesawat terdekat", "radar pesawat", "planes
  nearby", atau "what's flying nearby": pesawat di dekat sini
- "daftar pesawat", "daftar radar pesawat", "flight list", atau "radar list": daftar radar
- "penerbangan yang dilacak", "tracked flights", atau "where are my flights": posisi
  penerbangan yang kamu lacak
- "lacak penerbangan" dan "dengarkan pengatur lalu lintas udara" juga bisa, sesuai nama
  aksinya.

## Privasi

Radar Pesawat hanya terhubung ke internet saat kamu memakainya: saat kamu bertanya pesawat
apa di dekat sini, membuka daftar radar, melacak penerbangan, atau menyalakan peringatan
pesawat melintas atau pemantauan keadaan darurat (yang lalu memeriksa tiap 30 sampai 60
detik, tapi tidak selama jam tenang).

- Titik persis tempatmu tetap di komputermu. Tiap pemeriksaan radar hanya mengirim titik
  itu yang dibulatkan sekitar 1 kilometer, dengan radius yang sedikit lebih lebar, ke
  adsb.fi (`opendata.adsb.fi`), atau ke adsb.lol (`api.adsb.lol`) kalau adsb.fi tidak
  menjawab. Jarak dan arah tiap pesawat dihitung Hariku sendiri dari titik persismu.
- Untuk menyebutkan tujuan penerbangan, Hariku hanya mengirim callsign-nya ke adsbdb
  (`api.adsbdb.com`). Rute hanya diingat selama Hariku berjalan, tidak pernah disimpan.
- Melacak penerbangan hanya mengirim nomor penerbangan atau registrasinya ke adsb.fi (atau
  adsb.lol), kira-kira sekali semenit (dua kali kalau peringatan pesawat melintas nyala)
  selama dilacak, tidak pernah lokasimu.
- Mencari kota mengirim teks yang kamu ketik, dan bahasa Hariku-mu, ke pencarian kota
  Open-Meteo (`geocoding-api.open-meteo.com`).
- Mencari alamat mengirim alamat yang kamu ketik, dan bahasa Hariku-mu, ke layanan
  Nominatim OpenStreetMap. Koordinat dan tautan peta lengkap yang kamu tempel dibaca di
  komputermu; tautan pendek Google Maps dikirim sekali ke Google untuk mencari koordinat
  yang ditunjuknya.
- Dengarkan ATC membuka halaman liveatc.net di peramban. Hariku sendiri tidak mengirim apa
  pun ke LiveATC.
