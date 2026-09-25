# Gempa & Tsunami

Gempa & Tsunami memberi tahu gempa terkini dari BMKG, menampilkan daftar gempa terbaru di
Indonesia (dan, kalau kamu mau, gempa kuat di seluruh dunia dari USGS), serta mengumumkan
peringatan: untuk gempa yang menurut BMKG berpotensi tsunami, dan, kalau kamu
menyalakannya, untuk gempa di dekatmu atau yang dirasakan di wilayahmu. Butuh Hariku 2.8
atau yang lebih baru.

**Hariku bukan sistem peringatan resmi. Selalu ikuti BMKG dan pihak berwenang setempat.**

## Mulai

Di jendela utama Hariku, tekan G untuk mendengar gempa terkini dan Shift+G untuk daftar
gempa terbaru. Dari mana saja, buka Aruna (Ctrl+Alt+Backspace) lalu ketik atau ucapkan
"gempa terbaru" atau "latest earthquake".

Peringatan tsunami langsung menyala sejak awal. Jarak dan peringatan gempa di dekatmu
memakai tempat utamamu dari Pengaturan, Tempat (Ctrl+P membuka Pengaturan). Peringatan
lainnya dan pilihan tempat ada di Pengaturan, Gempa & Tsunami.

## Mendengar gempa terkini

Tekan G. Kamu mendengar gempa terkini dari BMKG:

- magnitudo, kedalaman, dan keterangan lokasi dari BMKG;
- jaraknya dari tempatmu dan arahnya, misalnya "120 kilometer di sebelah selatan Rumah";
- waktunya, dalam zona waktu BMKG (misalnya WIB), dan sudah berapa lama;
- daerah yang merasakannya, dalam skala MMI, kalau BMKG melaporkannya;
- pernyataan BMKG soal potensi tsunami.

Kata-kata BMKG sendiri (lokasi, daerah yang merasakan, pernyataan tsunami) dibacakan apa
adanya seperti yang ditulis BMKG. Kalau BMKG menyatakan ada potensi tsunami, laporannya
dimulai dengan "Berpotensi tsunami, menurut BMKG.", disertai suara kalau suara peringatan
menyala.

Kalau Hariku sudah memeriksa BMKG dalam 30 detik terakhir, kamu langsung mendengarnya.
Kalau belum, Hariku bilang "Memeriksa BMKG..." dulu. Tanpa internet, kamu mendengar data
terakhir selama umurnya belum 6 jam, lengkap dengan jam datanya. Gempa yang sudah kamu
dengar lewat G tidak diumumkan lagi sebagai peringatan, kecuali BMKG belakangan
menambahkan potensi tsunami.

## Gempa terbaru

Tekan Shift+G. Jendela Gempa Terbaru berisi satu gempa per baris, yang paling baru di
atas: magnitudo, lokasi, kedalaman, waktu, dan jarak dari tempatmu. Barisnya dimulai
dengan "Berpotensi tsunami, menurut BMKG." kalau BMKG menyatakannya, dan diakhiri daerah
yang merasakannya kalau BMKG melaporkannya. Daftarnya berisi gempa kuat terbaru dari BMKG
(magnitudo 5 ke atas), gempa dirasakan dari BMKG, dan gempa yang tertangkap pemeriksaan
peringatan Hariku dalam dua hari terakhir.

- Telusuri daftarnya dengan tombol panah. Kotak Detail di bawahnya menampilkan semua
  keterangan gempa yang dipilih: magnitudo, waktu, lokasi, koordinat, kedalaman, jarak,
  daerah yang merasakan, pernyataan BMKG, dan sumbernya.
- Enter di daftar, atau tombol Detail, membacakan detailnya.
- "Sertakan gempa kuat di seluruh dunia dari USGS (magnitudo 5 ke atas, 24 jam terakhir)"
  menambahkan gempa dari USGS yang tidak dilaporkan BMKG. Barisnya diakhiri "Sumber:
  USGS." Hariku mengingat pilihan ini.
- Segarkan mengambil daftarnya lagi. Tutup atau Escape menutup jendelanya.

Saat dibuka, jendelanya mengambil daftar baru, kecuali daftarnya belum berumur 2 menit.

## Peringatan

Selama Hariku berjalan, Hariku memeriksa gempa terkini BMKG kira-kira setiap menit (kalau
ada peringatan BMKG yang menyala) dan USGS kira-kira setiap 5 menit (kalau peringatan
seluruh dunia menyala). Setiap gempa diumumkan sekali. Gempa yang terjadi lebih dari satu
jam yang lalu tidak diumumkan (tiga jam untuk yang berpotensi tsunami), jadi kabar lama
tidak diulang saat Hariku baru dimulai.

Pilih peringatannya di Pengaturan, Gempa & Tsunami:

- "Umumkan gempa yang menurut BMKG berpotensi tsunami, di mana pun lokasinya
  (disarankan)": menyala secara bawaan. Peringatan ini memotong ucapan screen reader-mu,
  dan tetap datang kalau BMKG menambahkan potensi tsunami ke gempa yang sudah kamu dengar.
- "Umumkan gempa di dekat saya": mati secara bawaan. Memakai "Jarak peringatan:" (100,
  300, 500, atau 1.000 kilometer; bawaannya 300) dan "Magnitudo minimum untuk gempa di
  dekat saya:" (3,0 sampai 6,0; bawaannya 4,0).
- "Umumkan gempa yang menurut BMKG dirasakan di wilayah saya": mati secara bawaan. Lihat
  Peringatan gempa dirasakan di bawah.
- "Umumkan gempa kuat di mana pun di dunia (USGS, magnitudo 6,5 ke atas)": mati secara
  bawaan. Kalau USGS memasang tanda tsunami, Hariku menyebutkannya, dan bahwa tanda itu
  saja tidak berarti tsunami terjadi.
- "Putar suara saat peringatan": menyala secara bawaan. Potensi tsunami punya suaranya
  sendiri.

Setiap kali Hariku berjalan, peringatan pertama diakhiri dengan "Hariku bukan sistem
peringatan resmi. Selalu ikuti BMKG dan pihak berwenang setempat." (Kalau kamu lebih dulu
mendengar potensi tsunami lewat G, laporan itulah yang membawanya.) Gempa yang sudah
diumumkan dari BMKG tidak diumumkan lagi dari USGS, begitu juga sebaliknya.

### Peringatan gempa dirasakan

Laporan gempa dirasakan dari BMKG menyebutkan kota dan kabupaten tempat gempanya terasa.
Hariku mencari kota tempatmu di sana (bukan nama yang kamu berikan untuk tempat itu,
seperti Rumah). Untuk tempat sendiri, Hariku juga mencari kabupatennya kalau hasil
pencarian kotanya punya. Untuk menambah nama, misalnya kabupatenmu, ketik di "Nama wilayah
lain yang dicari dalam laporan gempa dirasakan, misalnya kabupaten Anda (pisahkan dengan
koma, opsional):". Baris di bawah kolom itu menyebutkan nama-nama yang dicari Hariku.

### Jam tenang

Selama jam tenang (Pengaturan, Jam Tenang), hanya peringatan tsunami yang diucapkan.
Peringatan gempa lainnya dilewati dan tidak diulang nanti.

## Memilih tempat

Buka Pengaturan, Gempa & Tsunami. Daftar "Tempat:" berisi "Tempat utama" (bawaannya),
tempat-tempatmu yang lain, dan "Tempat sendiri…" untuk kota khusus ekstensi ini. Untuk
memakai kota sendiri:

1. Pilih "Tempat sendiri…" di "Tempat:".
2. Di "Kota yang dicari, untuk tempat sendiri (tekan Enter untuk mencari):", ketik minimal
   2 huruf nama kotanya, lalu tekan Enter.
3. Fokus pindah ke "Hasil pencarian kota:". Pilih kotamu, lalu tekan Oke.

"Tempat sendiri, untuk jarak dan peringatan gempa di dekat Anda:" menampilkan kota yang
tersimpan.

## Di Briefing Pagi

Dengan ekstensi Briefing Pagi, briefing menyebutkan gempa yang dilaporkan BMKG dalam jarak
peringatanmu selama 24 jam terakhir: "Gempa di dekat Anda dalam 24 jam terakhir, menurut
BMKG: ...", dengan magnitudo, jarak, dan waktunya, serta apakah BMKG menyatakan potensi
tsunami. Briefing memakai pengaturan "Jarak peringatan:" walaupun peringatan gempa di
dekatmu mati, dan hanya data yang sudah dimiliki Hariku.

## Tombol dan perintah

- G: Ucapkan gempa terkini dari BMKG.
- Shift+G: Buka daftar gempa terbaru.

Tombolnya berlaku di jendela utama Hariku. Ganti tombolnya di Pengaturan, Pintasan
Keyboard, di bawah "Earthquakes". Di sana kamu juga bisa menjadikannya global, supaya bisa
dipakai di luar Hariku.

Di Aruna, diketik atau diucapkan:

- Gempa terkini: "gempa", "gempa terbaru", "gempa terkini", "info gempa", "gempa bumi
  terbaru", "latest earthquake", "earthquake" atau "last earthquake". Perintah ini hanya
  berbicara, jadi jawabannya juga tampil di Hasil terakhir Aruna.
- Daftarnya: "daftar gempa", "daftar gempa terbaru", "recent earthquakes" atau "list of
  earthquakes".

## Privasi

Gempa & Tsunami mengunduh berkas gempa publik BMKG dari `data.bmkg.go.id`: kira-kira
sekali semenit selama ada peringatan BMKG yang menyala (peringatan tsunami menyala secara
bawaan), dan saat kamu memintanya. Dengan peringatan seluruh dunia atau daftar seluruh
dunia, ia juga mengunduh data publik USGS dari `earthquake.usgs.gov`. Permintaan ini tidak
berisi data apa pun tentangmu: semua orang mendapat berkas yang sama, dan jarak dihitung
di komputermu, jadi tempatmu tidak pernah keluar dari komputer. Mencari kota mengirim teks
yang kamu ketik dan bahasa Hariku-mu ke pencarian kota Open-Meteo
(`geocoding-api.open-meteo.com`). Data gempa: BMKG (Badan Meteorologi, Klimatologi, dan
Geofisika) dan USGS.
