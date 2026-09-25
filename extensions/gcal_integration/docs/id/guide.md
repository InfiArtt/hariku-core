# Google Calendar Reader

Baca acara Google Calendar-mu dan hari libur di kalender Hariku. Ekstensi ini
hanya membaca dari Google: acara yang kamu tambah atau ubah di Hariku tetap di komputer
ini dan tidak pernah dikirim balik ke Google. Jendelanya berbahasa Inggris, jadi label di
panduan ini ditulis seperti yang muncul di layar.

Selama ekstensi ini aktif, Enter di sebuah tanggal, dan "Tambah pengingat..." di menu
Pengingat, membuka jendela "New Event" miliknya, bukan jendela pengingat Hariku; lihat
bagian Menambah acaramu sendiri.

## Mulai

1. Buka Pengaturan lalu pilih halaman "Google Calendar".
2. Di "Private iCal URL (.ics):", tempel alamat rahasia kalendermu. Cara mendapatkannya:
   buka Google Calendar di web, masuk ke Settings, pilih kalendermu, lalu Integrate
   Calendar, dan salin "Secret address in iCal format". Nama-nama ini sesuai petunjuk di
   halaman pengaturannya, yaitu nama di Google Calendar berbahasa Inggris.
3. Kalau mau hari libur juga, pilih negara atau agama di "Public Holidays Calendar:".
4. Tekan Oke. Hariku mengunduh acara-acaramu.

Jangan bagikan alamat rahasia itu: siapa pun yang memilikinya bisa membaca kalendermu.
Alamat `.ics` dari kalender lain juga bisa, asal diawali `https://` atau `http://`.

Hariku mengunduh acaranya lagi setiap kali menyala dan setiap 60 menit, selama alamat
kalender atau kalender hari libur sudah diisi. Kalau unduhan gagal, misalnya saat tidak
ada internet, acara dari alamat itu hilang dari Hariku sampai unduhan berikutnya berhasil.
Acara buatanmu sendiri selalu tetap ada.

## Mendengar acara hari itu

Pilih tanggal di kalender lalu tekan Shift+C. Hariku menyebutkan jumlah acara dan acara
pertamanya, misalnya "2 events. Next: 09:00 Rapat tim at Ruang 3". Tekan Shift+C dua kali
dengan cepat untuk mendengar semuanya. Acara seharian disebut lebih dulu, diawali "All
day:", dan acara yang kamu tambahkan di Hariku diakhiri "(local)". Kalau tidak ada acara,
Hariku bilang "No events for this date."

## Acara di agenda

Tekan Spasi di sebuah tanggal untuk membuka agendanya: acara-acaranya muncul setelah
pengingatmu, dengan tempatnya setelah "at", dan "[GCal]" untuk acara dari Google atau
"[Local]" untuk acaramu sendiri.

## Menambah acaramu sendiri

Tekan Enter di sebuah tanggal, atau Shift+A. Jendela "New Event" terbuka dengan:

- "Title:": judul acaranya.
- "All day event": centang untuk acara tanpa jam.
- "Start Date (YYYY-MM-DD):", yang awalnya berisi tanggal yang dipilih, dan "Start Time
  (HH:MM):".
- "End Date (YYYY-MM-DD):" dan "End Time (HH:MM):".
- "Location:" dan "Description:": tempat dan keterangannya.
- "Repeat:": Does not repeat, Daily, Weekly, Monthly, atau Yearly.
- "Status:": Confirmed, Tentative, atau Cancelled.

Tekan "Save". Hariku bilang "Event saved:" lalu judulnya.

Acaramu tetap di Hariku dan tidak pernah dikirim ke Google. Acara ini tidak berbunyi atau
mengingatkanmu; gunanya untuk dibaca. Untuk menambah pengingat Hariku selama ekstensi ini
aktif, tekan N untuk pengingat cepat, atau bilang ke Aruna, misalnya "ingatkan aku telepon
Ibu besok jam 8".

## Mengubah acaramu

Pilih tanggalnya lalu tekan Shift+E. Pilih salah satu acaramu di daftar "Select an event
to edit:", ubah di jendela "Edit Event", lalu tekan "Save". Acara dari Google tidak bisa
diubah, dan pengubahan hanya berlaku untuk acara yang tidak berulang.

## Menghapus atau menyembunyikan acara

Pakai aksi "Delete or hide an event" (tanpa tombol), atau "Hapus Terpilih" di agenda.
Pilih acaranya:

- Acaramu sendiri langsung dihapus.
- Acara dari Google hanya disembunyikan di Hariku: "Event hidden from view. Note: it still
  exists in your Google Calendar."

Untuk acara yang berulang, semua tanggalnya ikut terhapus atau tersembunyi. Acara yang
sudah disembunyikan tidak bisa dimunculkan lagi dari Hariku.

## Hari libur

"Public Holidays Calendar:" berisi "None", hari raya Kristen (Christian), Islam (Islamic),
Yahudi (Jewish), dan Ortodoks (Orthodox), serta lebih dari seratus negara dan wilayah.
Hari liburnya diambil dari kalender hari libur publik Google dan tampil seperti acaramu
yang lain. Hari libur Indonesia berbahasa Indonesia.

## Catatan sejarah

Di "Historical Data Country Code (e.g. ID, US):" kamu mengisi negara, awalnya ID
(Indonesia), yang catatan sejarah tanggal-tanggal tertentunya ikut diunduh Hariku bersama
acaramu. Kosongkan kalau tidak mau mengunduh apa pun.

Di tanggal yang punya setidaknya satu acara, tekan I. Kalau ada catatan untuk tanggal itu,
catatannya terbuka di jendela "Historical Information" yang kamu baca dengan browse mode.
Kalau tidak ada, Hariku bilang "No historical info available for this date."

## Sinkron sekarang

Aksi "Sync with Google Calendar now" (tanpa tombol) langsung mengunduh acaramu. Hariku
bilang "Syncing with Google Calendar..." tapi tidak memberi tahu saat selesai. Kalau
alamat kalender dan kalender hari libur dua-duanya belum diisi, Hariku bilang "Please
configure a Google Calendar URL in settings first."

## Mengimpor dari Hariku V1

Tombol "Import Events from Hariku V1" di halaman pengaturan membaca file acara Hariku V1
dan menambahkan acaranya sebagai acara seharian milikmu; yang dulu berulang tiap tahun
tetap berulang tiap tahun. Setelah itu muncul pesan berisi jumlah acara yang diimpor.
Tekan sekali saja: menekannya lagi menambahkan acara yang sama sekali lagi.

## Pengaturan

Di Pengaturan, Google Calendar:

- "Private iCal URL (.ics):": alamat rahasia kalendermu.
- "Historical Data Country Code (e.g. ID, US):": negara untuk catatan sejarah.
- "Public Holidays Calendar:": hari libur yang ditampilkan, atau "None".
- "Import Events from Hariku V1": lihat bagian Mengimpor dari Hariku V1.

Kalau kamu mengubah salah satu dari tiga yang pertama lalu menekan Oke, Hariku langsung
mengunduh lagi.

## Tombol dan perintah

Di jendela utama Hariku:

- Shift+C: Read events for selected date (tap twice for all), baca acara tanggal yang
  dipilih; tekan dua kali untuk semuanya.
- I: View Historical Context, lihat catatan sejarah.
- Shift+A: Add a new event, tambah acara (Enter di sebuah tanggal juga sama).
- Shift+E: Edit a local event, ubah acaramu.
- Delete or hide an event: tanpa tombol.
- Sync with Google Calendar now: tanpa tombol.

Semuanya ada di bawah "Google Calendar" di Pengaturan, Pintasan Keyboard, dan tombolnya
bisa kamu ganti atau tambah di situ. Aruna menjalankannya lewat nama bahasa Inggrisnya,
misalnya "sync with google calendar now".

## Privasi

Setiap kali mengunduh, Google Calendar Reader terhubung ke:

- server alamat kalendermu, yaitu Google untuk Google Calendar, untuk mengambil acaramu;
- Google Calendar (calendar.google.com), untuk kalender hari libur yang kamu pilih;
- GitHub Pages (infiartt.github.io), untuk catatan sejarah negara yang kamu isi.

Permintaan ini hanya meminta file-file itu; tidak ada yang dikirim tentang dirimu selain
apa yang dibawa setiap permintaan web, seperti alamat IP-mu. Acaramu sendiri, acara yang
kamu sembunyikan, dan salinan hasil unduhan tetap di komputermu.
