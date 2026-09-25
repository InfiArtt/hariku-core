# Tema Suara

Tema Suara mengganti suara-suara yang diputar Hariku, seperti tema warna, tapi untuk
telinga. Buat tema dari berkas WAV-mu sendiri, berganti tema kapan saja, dan impor atau
ekspor tema sebagai berkas ZIP. Tema suara dari Hariku 1 juga bisa diimpor.

## Mulai

Buka Pengaturan, Tema Suara. Halamannya punya dua daftar, masing-masing dengan
tombolnya:

- "Tema": paling atas "Bawaan, suara asli Hariku", lalu tema-temamu. Tiap baris
  menyebutkan apakah tema itu sedang dipakai dan berapa suara sendiri yang dimilikinya.
- "Suara di", diikuti nama tema yang terpilih: semua suara Hariku beserta gunanya,
  misalnya "confirm, konfirmasi". Untuk tema buatanmu, barisnya juga menyebutkan "suara
  tema ini" atau "suara bawaan".

Tombol-tombolnya langsung bekerja, jadi tidak ada yang perlu disimpan dengan Oke.

## Memakai tema

Pilih tema di daftar "Tema" lalu tekan "Gunakan tema ini" (atau Enter). Hariku bilang,
misalnya, "Tema Laut diterapkan." Tema itu terus dipakai, juga setelah Hariku dibuka
ulang: Hariku bahkan menyala dengan suara pembuka dari temamu. Untuk kembali ke suara
asli Hariku, gunakan Bawaan.

Untuk berganti tema dengan cepat, tekan Shift+S di jendela utama Hariku, atau minta ke
Aruna: "ganti tema suara". Hariku pindah ke tema berikutnya (setelah tema terakhir,
kembali ke Bawaan), menyebutkan namanya, lalu memutar suara pembukanya.

## Membuat tema sendiri

1. Tekan "Tema baru...", ketik nama di "Nama tema", lalu tekan OK. Tema baru belum punya
   suara sendiri, jadi bunyinya masih sama persis dengan Bawaan.
2. Di daftar "Suara di", pilih sebuah suara lalu tekan Putar (atau Enter) untuk
   mendengarnya.
3. Tekan "Ganti dengan berkas WAV..." lalu pilih suaramu. Sekarang tema itu memutar
   berkasmu untuk suara tersebut.
4. Lakukan hal yang sama untuk setiap suara yang mau kamu ganti, lalu gunakan temanya.

"Kembalikan ke bawaan" (atau Delete di daftar suara) menghapus salinan suara terpilih
milik tema itu, jadi suara aslinya dari Hariku terdengar lagi.

Suara harus berupa berkas WAV PCM tanpa kompresi, paling besar 5 MB. Nama tema paling
panjang 60 karakter, tidak boleh berisi `< > : " / \ | ? *`, tidak boleh diawali atau
diakhiri titik, dan tidak boleh Default.

Bawaan adalah suara asli Hariku dan tidak bisa diubah. Untuk membuat tema dari tema
lain, termasuk Bawaan, pilih tema itu lalu tekan "Salin...": salinannya dimulai dengan
suara yang sama.

Di daftar suara juga ada dua suara Aruna, aruna_send dan aruna_reply, serta listen dan
listen_end, nada yang diputar Voice Control saat mulai dan selesai mendengarkan.

## Folder tema

Setiap tema adalah sebuah folder di `%APPDATA%\Hariku2\sound_themes`, berisi berkas WAV
yang namanya sama dengan suara Hariku, misalnya `confirm.wav`. Suara yang tidak ada di
folder itu memakai suara asli Hariku. "Buka folder tema" membuka folder tema yang
terpilih, jadi kamu juga bisa menyalin suara ke sana sendiri.

## Mengganti nama dan menghapus tema

"Ubah nama..." memberi tema terpilih nama baru; tema yang sedang dipakai tetap dipakai.
"Hapus" (atau Delete di daftar tema) menghapus tema beserta semua suaranya, setelah
bertanya dulu. Tema yang sedang dipakai tidak bisa dihapus: gunakan tema lain dulu.

## Impor dan ekspor

Tekan "Impor..." lalu pilih berkas ZIP berisi suara WAV, atau tema suara Hariku 1
(`.hrk`). Hariku membuat tema baru dengan nama berkasnya dan memberi tahu berapa suara
yang diimpor. Hanya berkas WAV yang namanya sama dengan suara Hariku yang dipakai, dari
folder mana pun di dalam ZIP-nya; Hariku juga menyebutkan berapa berkas lain yang tidak
dipakai. Satu berkas paling banyak berisi 20 MB suara. Dari tema Hariku 1, suara yang
sama persis dengan suara asli Hariku dilewati, jadi tetap "suara bawaan".

Tekan "Ekspor..." untuk menyimpan suara-suara milik tema terpilih sebagai berkas ZIP,
untuk dibagikan atau disimpan sebagai cadangan. Kalau kamu mengekspor Bawaan, semua
suara asli Hariku ikut tersimpan, pas sebagai bahan awal tema buatanmu.

## Tombol dan perintah

- Shift+S, di jendela utama Hariku: "Beralih ke tema suara berikutnya". Tombolnya bisa
  kamu ganti di Pengaturan, Pintasan Keyboard.
- Aruna mengerti "ganti tema suara", "tema suara berikutnya", dan "next sound theme".
- Di daftar "Tema": Enter memakai tema, Delete menghapusnya.
- Di daftar "Suara di": Enter memutar suara, Delete mengembalikannya ke bawaan.
