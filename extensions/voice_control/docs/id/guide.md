# Voice Control

Dengan Voice Control, kamu bisa bicara ke Aruna, bilah perintah Hariku, tanpa perlu
mengetik, dalam bahasa Indonesia atau Inggris. Ucapanmu dikenali di komputermu sendiri
oleh whisper.cpp, dan tidak pernah disimpan atau dikirim ke mana pun. Kamu juga bisa
membuka Aruna cukup dengan mengucapkan frasa pemanggil, misalnya "Hey Aruna".

## Mulai

Voice Control butuh model ucapan sebelum bisa mendengarkan. Cukup unduh sekali:

1. Buka Pengaturan, Voice Control.
2. Di daftar "Program dan model ucapan", "Model ucapan tiny (paling cepat, untuk
   perintah)" sudah terpilih. Tekan Unduh... (atau Enter di barisnya).
3. Hariku bertanya dulu, lengkap dengan ukuran dan asal unduhannya: model tiny 77,7 MB
   dari Hugging Face, dan program pengenal ucapan, whisper.cpp (8,6 MB dari GitHub),
   ikut terunduh. Jawab ya.
4. Hariku menyebutkan kemajuannya di 25, 50, 75, dan 100 persen. Setelah selesai, kolom
   Status berbunyi "Voice Control siap. Tekan Ctrl+Alt+Backspace lalu bicara setelah
   nada."

Paling enak pakai headset. Kalau pakai speaker, mikrofon bisa ikut mendengar screen
reader-mu.

## Bicara ke Aruna

1. Tekan Ctrl+Alt+Backspace. Aruna terbuka, nada berbunyi, lalu Aruna mendengarkan.
2. Ucapkan perintahmu, misalnya "gempa terbaru", "jam berapa", atau "ingatkan aku minum
   obat besok jam 8". Dalam bahasa Inggris: "latest earthquake", "what time is it",
   atau "remind me to take medicine tomorrow at 8".
3. Berhenti bicara. Setelah hening sebentar, nada kedua berbunyi, dan ucapanmu masuk ke
   Aruna lalu dijalankan seperti kalau kamu mengetiknya.

Selama mendengarkan, Hariku mendiamkan screen reader-mu dan Suara Hariku, supaya
suaranya tidak masuk ke mikrofon.

- Kalau Aruna sudah terbuka, atau kamu mematikan "Langsung mendengarkan saat Aruna
  dibuka", tekan Ctrl+Alt+Backspace lagi (atau tombol Dengarkan di Aruna) lalu bicara
  setelah nada.
- Untuk langsung selesai, tekan Ctrl+Alt+Backspace atau Enter begitu kamu selesai
  bicara.
- Escape membuat Aruna berhenti mendengarkan dan membuang apa yang kamu ucapkan.
- Aruna berhenti mendengarkan sendiri setelah 12 detik. Kalau kamu diam selama 5 detik,
  Aruna berhenti dan bilang tidak mendengar apa-apa.
- Kalau Aruna bertanya sesuatu, misalnya "... Simpan?" setelah pengingat, Aruna
  mendengarkan lagi begitu pertanyaannya selesai diucapkan: jawab "ya" atau "tidak".

## Model ucapan

Daftar di bagian atas halaman Voice Control berisi programnya dan tiga model ucapan,
masing-masing dengan ukuran dan statusnya:

- "Program pengenal ucapan (whisper.cpp)", 8,6 MB, dari GitHub. Program ini ikut
  terunduh bersama model pertamamu.
- "Model ucapan tiny (paling cepat, untuk perintah)", 77,7 MB.
- "Model ucapan base (lebih akurat, untuk pengingat)", 148,0 MB.
- "Model ucapan small (paling akurat, lambat di komputer lama)", 487,6 MB. Di komputer
  lama, satu perintah pendek bisa butuh 15 detik atau lebih.

Model-model ini adalah model Whisper dari OpenAI, yang dibuat untuk whisper.cpp, dan
diunduh dari Hugging Face. Model tiny sudah cukup untuk perintah; tambahkan model base
kalau kamu sering mengucapkan pengingat.

Untuk mengunduh, pilih barisnya lalu tekan Unduh... (atau Enter). "Batalkan unduhan"
menghentikan unduhan. Untuk menghapus, pilih barisnya lalu tekan Hapus (atau Delete).

"Model pengenal" menentukan model mana yang mendengarkan. Dengan "Otomatis
(disarankan)", Hariku mengukur kecepatan tiap model saat pertama kali dipakai (kolom
Status lalu berbunyi, misalnya, "Terpasang, sekitar 1,6 detik per perintah"). Setelah
itu Hariku memakai model paling akurat yang masih cukup cepat untuk perintah, dan kalau
ucapanmu terdengar seperti pengingat, Hariku mengenalinya sekali lagi dengan model yang
lebih akurat, kalau kamu punya. Kamu juga bisa memilih "Tiny: paling cepat", "Base:
lebih akurat", atau "Small: paling akurat, lambat di komputer lama".

## Kalau Aruna kurang jelas mendengarmu

Kalau Aruna salah dengar, atau kamu harus bicara keras, biarkan Hariku mengukur
mikrofonmu:

1. Di halaman Voice Control, tekan "Tes mikrofon".
2. Hariku bilang "Setelah nada, ucapkan satu kalimat dengan suara biasa." Setelah
   nada, ucapkan satu kalimat.
3. Hariku mengukur suaramu dan ruangan, memilih "Kepekaan mikrofon" yang cocok, lalu
   memberitahumu. Kalau suaramu terlalu pelan atau ruangannya terlalu bising, Hariku
   memberi saran.
4. Tekan Oke atau Terapkan untuk menyimpan kepekaan yang baru.

Rekaman tes ini hanya diukur: tidak diputar ulang dan tidak disimpan. Kamu juga bisa
memilih "Kepekaan mikrofon" sendiri: Rendah, Normal, Tinggi, atau Sangat tinggi.

Di rumah yang ramai, bunyi bernada tinggi seperti kicauan burung tidak pernah dianggap
ucapan. Kalau bisingnya membuat Aruna terus mendengarkan sampai 12 detik penuh, Aruna
tetap mencoba mengenali ucapanmu, dan baru bilang ruangannya terlalu bising kalau itu
gagal. Lain kali, tekan Enter begitu kamu selesai bicara, atau pilih kepekaan yang
lebih rendah.

Kalau Windows memblokir mikrofon, Hariku memberi tahu pengaturan mana yang harus
dinyalakan di Pengaturan Windows, Privasi, Mikrofon.

## Frasa pemanggil

Ucapkan frasa pemanggil, "Hey Aruna" atau frasa pilihanmu, lalu Aruna terbuka dan
mendengarkan perintahmu, tanpa menekan tombol. Fitur ini mati sampai kamu
menyalakannya.

### Menyiapkan frasa pemanggil

1. Di Pengaturan, Voice Control, pilih "Pendengar frasa pemanggil (sherpa-onnx dan
   model kata kunci bahasa Inggris)" di daftar paling atas, lalu tekan Unduh...
   Ukurannya 42,4 MB, dari GitHub.
2. Centang "Dengarkan frasa pemanggil", lalu ketik frasamu di "Frasa pemanggil".
   "Tentang frasa ini" memberi tahu kalau frasamu cuma satu kata, terlalu pendek,
   terlalu panjang, atau kata sehari-hari (gampang salah terdengar). Kata bahasa
   Inggris paling mudah didengar model ini; nama seperti Aruna mungkin butuh kepekaan
   Tinggi.
3. Tekan "Tes frasa pemanggil...". Setelah nada, ucapkan frasanya beberapa kali dalam
   20 detik. Hariku bilang "Terdengar." setiap kali mendengarmu, lalu menyebutkan
   berapa kali ia mendengarmu. Tekan tombolnya lagi untuk berhenti lebih awal.
4. Kalau ia tidak mendengarmu, pilih Tinggi di "Kepekaan frasa pemanggil" lalu tes
   lagi. Kalau ia sering terbuka tanpa sengaja, pilih Rendah.
5. Tekan Oke.

Frasa paling panjang 40 karakter, dan model ini hanya mendengar huruf A sampai Z: tulis
angka sebagai kata. Kalau frasamu tidak bisa didengar, Oke tidak menutup Pengaturan dan
Hariku menjelaskan alasannya.

### Apa yang terjadi saat frasa diucapkan

Pilih di "Saat kamu mengucapkan frasa pemanggil":

- "Buka Aruna": Aruna terbuka dengan nada, mendapat fokus, lalu mendengarkan
  perintahmu.
- "Dengarkan tanpa membuka jendela": jendela yang sedang kamu pakai tetap memegang
  fokus, dan screen reader-mu tetap di sana. Kamu bicara, Aruna menjawab dengan suara,
  bertanya dan mendengar "ya" atau "tidak" lewat suara, lalu menutup sendiri setelah
  selesai.

Kalau Aruna sudah terbuka, frasa pemanggil membuatnya mulai mendengarkan.

### Kapan frasa pemanggil mendengarkan

Kolom Status di halaman Voice Control memberi tahu apakah Hariku sedang mendengarkan
frasamu. Hariku tidak mendengarkan frasa pemanggil:

- selama Hariku, atau screen reader-mu lewat Hariku, sedang berbicara
- selama Voice Control mendengarkan perintah, atau selama kamu mengetes mikrofon atau
  frasa pemanggil
- selama jam tenang, kalau kamu mencentang "Jeda frasa pemanggil selama jam tenang"
- selama Windows memblokir mikrofon
- selama kamu menjedanya

Untuk menjedanya, jalankan "Jeda atau lanjutkan frasa pemanggil" (lihat Tombol dan
perintah). Frasa pemanggil tetap dijeda sampai kamu menjalankannya lagi atau membuka
ulang Hariku.

Suara screen reader dari speaker bisa masuk ke mikrofon; headset mencegahnya.

## Pengaturan

Pengaturan, Voice Control. Unduh, Hapus, Batalkan unduhan, dan kedua tes langsung
bekerja; sisanya disimpan saat kamu menekan Oke atau Terapkan.

- "Model pengenal": model ucapan mana yang mendengarkan (lihat Model ucapan).
- "Langsung mendengarkan saat Aruna dibuka": menyala dari awal. Matikan kalau kamu
  lebih suka mengetik dulu; lalu tekan Ctrl+Alt+Backspace lagi saat mau bicara.
- "Berhenti mendengarkan setelah hening selama": 0,6, 0,8, 1,0, 1,5, atau 2,0 detik.
  Bawaannya 1,0 detik.
- "Kepekaan mikrofon" dan "Tes mikrofon": lihat Kalau Aruna kurang jelas mendengarmu.
- "Dengarkan frasa pemanggil", "Frasa pemanggil", "Kepekaan frasa pemanggil" (Rendah,
  Normal, atau Tinggi), "Saat kamu mengucapkan frasa pemanggil", "Jeda frasa pemanggil
  selama jam tenang", dan "Tes frasa pemanggil...": lihat Frasa pemanggil.

## Tombol dan perintah

- Ctrl+Alt+Backspace, tombol Hariku untuk Aruna, bisa dipakai di mana saja. Tombol ini
  membuka Aruna yang langsung mendengarkan (kecuali kamu mematikan "Langsung
  mendengarkan saat Aruna dibuka"). Kalau ditekan lagi saat Aruna terbuka, Aruna mulai
  atau berhenti mendengarkan.
- Enter, saat Aruna mendengarkan: berhenti sekarang dan kenali ucapanmu.
- Escape, saat Aruna mendengarkan: berhenti dan buang ucapanmu.
- "Jeda atau lanjutkan frasa pemanggil" tidak punya tombol. Beri tombol di Pengaturan,
  Pintasan Keyboard, atau minta ke Aruna: "jeda frasa pemanggil", "lanjutkan frasa
  pemanggil", "frasa pemanggil", "pause the wake phrase", atau "resume the wake
  phrase". Semuanya menjeda frasa pemanggil kalau sedang mendengarkan, dan
  melanjutkannya kalau sedang dijeda.
- Di halaman Voice Control, Enter di baris daftar mengunduhnya, dan Delete
  menghapusnya.

## Privasi

- Ucapanmu tetap di komputermu. Selama Voice Control mendengarkan, suaranya hanya
  disimpan di memori, diberikan ke program whisper.cpp di komputermu lewat koneksi
  lokal yang tidak bisa dijangkau dari luar komputermu, lalu dibuang. Suara itu tidak
  pernah disimpan atau dikirim ke mana pun. Hasil pengenalannya diperlakukan seperti
  teks yang kamu ketik.
- Mikrofon hanya menyala selama Voice Control mendengarkan perintah, selama tes di
  halamannya, dan, kalau kamu menyalakan frasa pemanggil, di latar belakang untuk
  frasamu. Pendengar frasa pemanggil hanya bisa tahu apakah frasamu diucapkan: ia tidak
  mengubah ucapan lain menjadi teks, dan tidak ada yang direkam, disimpan, atau
  dikirim. Matikan frasa pemanggil, atau hapus pendengarnya, dan mikrofon ditutup.
- Voice Control hanya terhubung ke internet saat kamu menekan Unduh: whisper.cpp dan
  pendengar frasa pemanggil dari GitHub, model ucapan dari Hugging Face. Permintaan ini
  tidak membawa akun atau data apa pun tentang kamu. Hariku hanya mengunduh dari situs
  itu, dan menghapus berkas yang tidak cocok dengan checksum-nya.
- Program, model, dan pendengar frasa pemanggil disimpan di
  `%APPDATA%\Hariku2\voice_control`. Pengaturannya menyimpan seberapa cepat tiap model,
  tidak pernah apa yang kamu ucapkan. Hapus program, model, atau pendengar frasa
  pemanggil di halaman Voice Control, atau hapus folder itu untuk membuang semuanya.
