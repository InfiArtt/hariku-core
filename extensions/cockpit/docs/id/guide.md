# Kokpit

Kokpit memberi nuansa pilot untuk Hariku. Ekstensi ini membacakan cuaca penerbangan
bandara-bandaramu: laporan terbaru (METAR) yang diterjemahkan jadi kalimat biasa, dan
prakiraannya (TAF). Mode Kapten memasukkan cuaca bandara ke Briefing Pagi dan ringkasan
malam, dan bisa membuat Hariku memanggilmu Kapten. Ada juga tema suara Kokpit. Butuh
Hariku 2.8 atau lebih baru.

Datanya dari NOAA Aviation Weather Center. Hanya untuk informasi, bukan untuk perencanaan
penerbangan.

## Mulai

1. Buka Pengaturan, Kokpit (Pengaturan dibuka dengan Ctrl+P).
2. Di "Kode ICAO bandara yang mau ditambahkan (tekan Enter untuk menambah)", ketik kode
  ICAO bandara yang terdiri dari 4 huruf, misalnya WIDD untuk Batam atau WIII untuk
  Jakarta, lalu tekan Enter. Bandara pertama di daftarmu jadi bandara utama.
3. Tekan Q di jendela utama Hariku untuk mendengar cuacanya, atau Shift+Q untuk melihat
  semua bandaramu.

Kamu tidak wajib menambah bandara: kalau belum ada bandara favorit, Kokpit memakai bandara
yang punya laporan cuaca dan paling dekat dari tempat utamamu di Pengaturan, Tempat,
sampai sekitar 300 kilometer jauhnya.

## Mendengar cuaca bandaramu

Tekan Q. Hariku membacakan laporan terbaru dari bandara utamamu:

- nama bandara dan kodenya, "stasiun otomatis" kalau memang begitu, dan kapan laporannya
  dibuat, dalam waktu lokal dan Zulu (UTC); untuk laporan yang lebih dari 2 jam, berapa
  jam umurnya
- angin, jarak pandang, cuaca seperti hujan, kabut, atau badai petir, serta awan dan
  ketinggiannya
- suhu dan titik embun, serta QNH (tekanan udara yang dipasang pilot di altimeter)
- kalau ada di laporannya: jarak pandang landasan (RVR), wind shear, cuaca yang baru saja
  terjadi, dan perkiraan perubahan beberapa jam ke depan
- kategori penerbangan (VFR, VFR marginal, IFR, atau IFR rendah) beserta artinya

Laporan diambil paling sering 10 menit sekali, jadi menekan Q lagi sebelum itu mengulang
laporan yang sudah ada. Kalau layanannya tidak bisa dihubungi, Hariku menyebutkan
masalahnya, lalu membacakan laporan terakhir beserta jam pengambilannya, selama umurnya
kurang dari 12 jam.

Kalau belum ada bandara favorit, tekanan pertama membuat Hariku bilang "Mencari bandara
terdekat dari" tempatmu, lalu bandara mana yang dipilih, disusul cuacanya. Hariku
mengingat bandara itu untuk tempatmu.

Untuk ikut mendengar laporan dalam kode aslinya, centang "Bacakan juga laporan aslinya" di
Pengaturan, Kokpit.

## Jendela Cuaca Bandara

Tekan Shift+Q untuk membuka jendela Cuaca Bandara:

- "Bandaramu": satu baris per bandara, berisi nama, kode, "utama" untuk yang pertama, dan
  ringkasan singkat: langit, suhu, angin, dan kategori penerbangan.
- "Laporan dan prakiraan yang sudah diterjemahkan": laporan bandara yang dipilih dalam
  kalimat, lalu prakiraannya: kapan diterbitkan, berlaku sampai kapan, dan tiap
  periodenya, misalnya "untuk sementara" atau peluang sekian persen, beserta suhu
  tertinggi dan terendah.
- "Kode asli": laporan dan prakiraan persis seperti yang dikirim.
- Tombol: Perbarui, Tambah bandara..., Hapus, Jadikan utama, dan Tutup (atau Escape).

Saat jendelanya dibuka, Hariku mengambil yang sudah lewat waktunya: laporan yang lebih
dari 10 menit dan prakiraan yang lebih dari 30 menit. Kalau kamu menekan Perbarui saat
semuanya masih baru, Hariku bilang datanya sudah terbaru.

## Mengatur bandaramu

Kamu bisa menyimpan sampai 20 bandara favorit. Atur di Pengaturan, Kokpit, di "Bandara
favorit (yang pertama jadi bandara utama)", atau di jendela Cuaca Bandara:

- Untuk menambah, ketik kode ICAO-nya lalu tekan Enter atau Tambah (di jendela: Tambah
  bandara..., yang menanyakan kodenya). Hariku memeriksa kodenya dulu ke layanan cuaca,
  lalu menyebutkan nama bandaranya dan apakah ada laporan terbarunya.
- Hapus menghapus bandara yang dipilih.
- Jadikan utama memindahkan bandara yang dipilih ke paling atas.

Tombol-tombol ini langsung bekerja; tidak perlu menekan Oke.

Kalau belum ada bandara favorit, daftarnya menampilkan bandara terdekat yang ditemukan
Hariku. Bandara itu tidak bisa dihapus, tapi begitu kamu menambah bandaramu sendiri, yang
dipakai bandaramu. Untuk mencari bandara terdekat dari tempatmu yang lain, pilih tempat
itu di "Tempat, untuk bandara terdekat kalau belum ada bandara favorit".

## Mode Kapten

Di Pengaturan, Kokpit, centang "Mode Kapten" lalu tekan Oke. Mode Kapten:

- menambahkan satu baris ke Briefing Pagi: jam dalam Zulu serta angin, jarak pandang,
  cuaca, awan, suhu, dan QNH di bandara utamamu
- menambahkan prakiraan besok pagi di bandara utamamu ke ringkasan malam
- memperbarui laporan dan prakiraan bandara utamamu di latar belakang, kira-kira tiap 30
  menit
- mengeja kode bandara dengan alfabet penerbangan, misalnya "Whiskey India Delta Delta"

Saat Mode Kapten dinyalakan, Hariku mengajukan dua pertanyaan (Ya atau Tidak). Pertama,
mau dipanggil Kapten atau tidak; ini hanya ditanyakan kalau kolom Sapaan di Pengaturan,
Profil masih kosong. Kedua, mau dipasangkan sapaan kokpit saat Hariku dimulai atau tidak.
Sapaan kokpit menyambutmu dengan sebutan dan nama panggilanmu, lalu menyebutkan jam lokal
dan Zulu, cuaca bandaramu, dan agendamu. Saat Mode Kapten dimatikan, Hariku menawarkan
untuk menghapus sebutan Kapten dan sapaan kokpitnya lagi.

## Cuaca bandara di briefing tanpa Mode Kapten

Centang "Tambahkan cuaca bandara ke Briefing Pagi (tanpa Mode Kapten)" untuk mendengar
satu baris singkat di Briefing Pagi: langit, suhu, dan angin di bandara utamamu. Butuh
setidaknya satu bandara favorit.

Tanpa Mode Kapten, Hariku tidak mengambil apa pun di latar belakang. Briefing Pagi hanya
membaca yang sudah ada di komputermu, jadi baris ini muncul kalau laporan terakhir umurnya
kurang dari 3 jam, misalnya setelah kamu menekan Q.

## Placeholder %airportweather%

Tulis %airportweather% di kalimat yang diucapkan Hariku saat dimulai (Pengaturan, Profil),
di pengingat, atau di rutinitas, dan Hariku mengisinya dengan cuaca bandara utamamu dari
laporan terakhir: angin, jarak pandang, cuaca, awan, suhu, dan QNH. Kalau tidak ada
laporan dari 3 jam terakhir, isinya kosong.

## Tema suara Kokpit

Tekan "Pasang tema suara Kokpit" di Pengaturan, Kokpit. Tombol ini menambahkan tema
bernama Cockpit ke ekstensi Tema Suara: bunyi "ding dong" kabin untuk informasi dan
pengingat, satu denting untuk konfirmasi, bip ganda pendek bernada rendah untuk kesalahan,
dan denting naik saat Hariku dimulai. Suara-suaranya dibuat di komputermu.

Ekstensi Tema Suara harus sudah terpasang dan aktif. Untuk memakai temanya, buka
Pengaturan, Tema Suara, pilih Cockpit, lalu tekan "Gunakan tema ini".

## Pengaturan

Buka Pengaturan, Kokpit:

- "Mode Kapten": lihat di atas. Awalnya mati.
- "Pasang tema suara Kokpit": lihat di atas.
- "Bandara favorit (yang pertama jadi bandara utama)", dengan "Kode ICAO bandara yang mau
  ditambahkan (tekan Enter untuk menambah)", Tambah, Hapus, dan Jadikan utama.
- "Tempat, untuk bandara terdekat kalau belum ada bandara favorit": tempat utama (bawaan)
  atau tempatmu yang lain.
- "Bacakan juga laporan aslinya": Q ikut membacakan laporan dalam kode aslinya.
- "Tambahkan cuaca bandara ke Briefing Pagi (tanpa Mode Kapten)".

Mode Kapten dan kedua kotak centang disimpan saat kamu menekan Oke; tombol-tombol bandara
langsung bekerja.

## Tombol dan perintah

Tombol ini berlaku di jendela utama Hariku:

- Q: Cuaca pilot: ucapkan METAR bandara utamamu
- Shift+Q: Cuaca bandara: buka daftar bandaramu beserta METAR dan TAF-nya

Kamu bisa menggantinya di Pengaturan, Pintasan Keyboard.

Di Aruna (Ctrl+Alt+Backspace), "cuaca pilot", "metar", atau "pilot weather" membacakan
cuacanya, dan "cuaca bandara" atau "airport weather" membuka jendela Cuaca Bandara.

## Privasi

Kokpit mengunduh laporan dan prakiraan dari NOAA Aviation Weather Center
(`aviationweather.gov`), tanpa akun atau kunci: saat kamu memintanya (laporan paling
sering 10 menit sekali, prakiraan 30 menit sekali), saat kamu menambah bandara (untuk
memeriksa kodenya), dan hanya dengan Mode Kapten, di latar belakang kira-kira tiap 30
menit. Permintaan ini hanya berisi kode ICAO bandaramu.

Untuk mencari bandara terdekat, Kokpit mengirim sebuah kotak sekitar 110 kilometer di
sekitar tempatmu, atau sekitar 330 kilometer kalau belum ketemu, dengan sudut-sudutnya
dibulatkan ke 0,1 derajat. Kokpit tidak pernah mengirim lokasimu sendiri atau apa pun dari
profilmu.
