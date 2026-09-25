# Routines

Routines menjalankan serangkaian aksi untukmu saat waktunya tiba, ala iOS Shortcuts.
Setiap rutinitas punya kondisi, yang menentukan kapan, dan aksi, yang menentukan apa:
"jam 07:00 di hari kerja, ucapkan selamat pagi lalu buka situs berita langgananku". Butuh
Hariku 2.7 atau yang lebih baru.

Jendela Routines hanya dalam bahasa Inggris, jadi label di panduan ini ditulis seperti
yang muncul di layar.

## Mulai

Awalnya Routines belum punya tombol. Buka Aruna (Ctrl+Alt+Backspace), ketik "manage
routines", lalu tekan Enter. Jendela "Routines" terbuka di daftar rutinitasmu,
masing-masing dengan statusnya, misalnya "Selamat pagi — On".

Untuk memberinya tombol, buka Pengaturan (Ctrl+P), Pintasan Keyboard, lalu cari "Manage
Routines (Shortcuts)" di kelompok Routines.

## Membuat rutinitas pertamamu

Rutinitas ini menyapamu jam 07:00 di hari kerja.

1. Di jendela Routines, tekan "Add". Jendela "Edit Routine" terbuka di "Name". Ketik
  Selamat pagi.
2. Tekan Tab sampai ke "Add condition", lalu tekan. Di "Type", pilih "At a specific time
  (HH:MM)". Tab ke "Time (HH:MM)", ketik 07:00, lalu tekan OK.
3. Tab lagi ke "Add condition" dan tekan. Pilih "On certain days of the week", centang Mon
  sampai Fri, lalu tekan OK.
4. Tab ke "Add action" dan tekan. "Speak text" sudah terpilih. Di "Text to speak", ketik:
  Selamat pagi, %myname%. Sekarang jam %time%. Tekan OK.
5. Tekan OK untuk menyimpan rutinitasnya.

Mulai saat itu, setiap jam 07:00 di hari kerja, pembaca layarmu bilang "Selamat pagi,
Rafli. Sekarang jam 07:00."

## Jendela Routines

- "Add" membuat rutinitas baru.
- "Edit", atau Enter di daftar, mengubah rutinitas yang dipilih.
- "Delete" menghapusnya, setelah bertanya dulu.
- "Toggle On/Off" mematikannya, atau menyalakannya lagi. Rutinitas yang mati tidak
  pernah jalan sendiri.
- "Run Now" langsung menjalankan aksinya, apa pun kondisinya, bahkan saat rutinitasnya
  mati.
- "Close", atau Escape, menutup jendela.

Setiap perubahan langsung tersimpan.

## Mengubah rutinitas

Jendela "Edit Routine" berisi, sesuai urutan Tab:

- "Name", dan "Enabled" (aktif).
- "When ALL of these are true" (kalau SEMUA ini benar): kondisi-kondisinya. Setiap kondisi
  berupa grup yang dinamai sesuai isinya, misalnya "1. At a specific time (HH:MM) →
  07:00", dengan tombol "Edit", "Remove" (hapus), "Move Up" (naikkan) dan "Move Down"
  (turunkan). Tombol "Add condition" ada setelahnya.
- "Then do (in order)" (lalu lakukan, berurutan): aksi-aksinya, sesuai urutan jalannya,
  dengan tombol yang sama, dan "Add action".
- OK menyimpan rutinitas, dan Cancel membiarkannya seperti semula.

Menambah atau mengubah kondisi atau aksi membuka jendela kecil: pilih "Type" dulu, lalu
Tab ke pengaturannya, dan tekan OK. Rutinitas tanpa nama disimpan sebagai "Untitled
routine".

## Kapan rutinitas jalan

- Rutinitas jalan saat semua kondisinya benar pada saat yang sama.
- Rutinitas jalan sekali saat kondisinya menjadi benar, dan baru jalan lagi setelah
  kondisinya sempat tidak benar lalu benar lagi. "Battery at or below (%)" dengan angka
  20 jalan sekali saat baterai turun ke 20%, bukan setiap menit sesudahnya.
- Tiga kondisi adalah momen, bukan keadaan: "When Hariku starts up", "When a date is
  selected" dan "When a reminder fires". Rutinitas dengan salah satunya jalan setiap kali
  momen itu datang, asalkan kondisi lainnya benar.
- Rutinitas tanpa kondisi tidak pernah jalan sendiri; pakai "Run Now".
- Rutinitas diperiksa setiap menit, dan setiap kali ada yang berubah, misalnya jendela
  yang sedang fokus, clipboard, daya, atau jaringan. Rutinitas hanya jalan selama Hariku
  berjalan.
- Jam tenang tidak membungkam rutinitas.

## Kondisi

- "At a specific time (HH:MM)": jamnya, format 24 jam, dengan dua angka untuk jam: 07:00,
  bukan 7:00.
- "On certain days of the week": centang harinya, Mon (Senin) sampai Sun (Minggu).
- "Battery at or below (%)" dan "Battery at or above (%)": persen baterai. Di komputer
  tanpa baterai, kondisi ini tidak pernah benar.
- "While charging / not charging": centang "Must be charging" untuk saat mengisi daya,
  atau hapus centangnya untuk saat tidak mengisi daya.
- "After idle for N minutes": berapa menit tanpa memakai keyboard atau mouse.
- "When an app is in focus": sebagian nama file programnya, misalnya chrome.exe atau
  winword.
- "When the window title contains": sebagian judul jendela yang sedang fokus.
- "When the clipboard contains": teks di clipboard. Di sini huruf besar kecil harus sama.
- "When online / offline": centang "Must be online" untuk saat online, atau hapus
  centangnya untuk saat offline.
- "Run every N minutes": rutinitas jalan setiap sekian menit, mulai dari pemeriksaan
  pertama setelah Hariku dibuka atau setelah kamu menambahkannya.
- "A reminder exists today": hari ini ada pengingat. Kalau "Title contains (optional)"
  diisi kata, hanya pengingat yang judulnya mengandung kata itu yang dihitung.
- "Connected to Wi-Fi network": sebagian nama jaringan Wi-Fi.
- "RAM usage at or above (%)" dan "CPU usage at or above (%)": persennya.
- "When Hariku starts up": saat Hariku dibuka.
- "When a date is selected": setiap kali kamu pindah ke suatu tanggal di kalender.
- "When a reminder fires": setiap kali pengingat muncul. Kalau "Reminder title contains
  (optional)" diisi kata, hanya pengingat yang judulnya mengandung kata itu yang
  dihitung.

Selain clipboard, huruf besar kecil tidak berpengaruh pada teks yang dicari.

## Aksi

- "Speak text": pembaca layarmu mengucapkan teksnya.
- "Show a notification": notifikasi Windows dengan "Title" (judul) dan "Message" (pesan).
- "Open a URL": membuka halaman web di browsermu. Alamatnya harus diawali http:// atau
  https://.
- "Play a sound": salah satu suara Hariku, dengan nama filenya, misalnya move.wav atau
  info.wav.
- "Set a variable": menyimpan nilai dengan sebuah nama, untuk aksi-aksi sesudahnya
  (lihat Placeholder dan variabel).
- "Wait (seconds)": jeda sebelum aksi berikutnya, paling lama 60 detik.
- "Open an app or command": menjalankan program, dengan argumennya kalau perlu, misalnya
  `notepad`. Tulis path lengkap di dalam tanda kutip dua:
  `"C:\Program Files\App\app.exe"`. Variabel Windows seperti %USERPROFILE% bisa dipakai.
  Tautan seperti `spotify:` membuka aplikasinya. Ini bukan command prompt, jadi pipe dan
  trik shell lainnya tidak jalan.
- "Open a file": membuka file dengan program biasanya, misalnya
  `%USERPROFILE%\Documents\daftar.txt`.
- "Lock the screen": mengunci Windows.
- "Set system volume": walau namanya begitu, aksi ini mengatur volume suara Hariku
  sendiri, 0 sampai 100, volume yang sama dengan yang diubah F5 dan F6.
- "Copy text to clipboard": menyalin teks ke clipboard.
- "Type text into focused field": mengetikkan teksnya, sesaat kemudian, ke mana pun fokus
  sedang berada. Baris baru diketik sebagai Enter.
- "Add a Hariku reminder": "Reminder title" (judul), "Time (HH:MM)", yang jadi 09:00
  kalau dikosongkan, dan "Date (YYYY-MM-DD, blank = today)", yang jadi hari ini kalau
  dikosongkan.
- "Go to a date in the calendar": memilih tanggal itu di kalender, hari ini kalau
  dikosongkan.
- "Speak the agenda for a day": membacakan pengingat di tanggal itu, hari ini kalau
  dikosongkan. Kalimatnya dalam bahasa Inggris.
- "Run another routine": menjalankan aksi-aksi rutinitas dengan nama itu; huruf besar
  kecil tidak berpengaruh. Rutinitas yang saling menjalankan berhenti setelah 5 langkah,
  jadi tidak bisa berputar tanpa akhir.

Aksi-aksinya jalan satu per satu, di latar belakang.

## Placeholder dan variabel

Di teks sebuah aksi, kamu bisa menulis placeholder, yang diisi saat rutinitas jalan:

- %time% (jam, JJ:MM), %date% (hari ini, TTTT-BB-HH), %battery% (persen baterai), %app%
  (program yang sedang fokus), %clipboard% (teks di clipboard), %ssid% (nama jaringan
  Wi-Fi), %ram% dan %cpu% (pemakaian memori dan prosesor dalam persen), dan %events%
  (jumlah pengingat hari ini)
- placeholder profilmu, seperti %myname% dan %mynickname%, placeholder buatanmu dari
  Pengaturan, Profil, dan milik Hariku serta ekstensimu, seperti %greeting% atau %weather%
- %var:NAMA%, nilai variabel yang disimpan aksi "Set a variable" dengan nama NAMA

Tombol "Insert placeholder" di jendela aksi menampilkan semuanya, lalu menaruh pilihanmu
di posisi kursor pada kolom teks yang terakhir kamu pakai. Bentuk lama dengan kurung
kurawal, seperti {time}, tetap jalan.

Variabel menyimpan nilainya sampai Hariku ditutup, dan rutinitasmu yang lain juga bisa
membacanya.

## Log Routines

"View Routines Log" membuka "Routines Log", berisi 100 kali jalan terakhir, dari yang
terbaru. Tiap baris menyebut waktunya, nama rutinitasnya, "auto" kalau jalan sendiri atau
"manual" untuk Run Now, lalu "ok", atau error-nya kalau ada aksi yang gagal. "Clear"
mengosongkannya. Log ini disimpan sampai Hariku ditutup.

Awalnya log ini belum punya tombol; ketik "view routines log" di Aruna, atau beri tombol
di Pintasan Keyboard.

## Tombol dan perintah

Kedua aksi Routines awalnya tanpa tombol. Di Pengaturan, Pintasan Keyboard, di kelompok
Routines, kamu bisa memberi tombol untuk "Manage Routines (Shortcuts)" dan "View Routines
Log", dan menjadikannya global supaya bisa dipakai di luar Hariku juga.

Di Aruna (Ctrl+Alt+Backspace), ketik "manage routines" untuk membuka jendela Routines,
atau "view routines log" untuk log-nya.
