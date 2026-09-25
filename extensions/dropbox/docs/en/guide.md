# Dropbox

Hear what Dropbox is doing and copy shared links without leaving your work. Hariku tells
you when the files you save are syncing and when they have synced, when someone changes a
file in a folder you share or shares something with you, and it copies a file's Dropbox
link for you. It needs Hariku 2.9 or newer. Hariku never uploads, downloads or reads your
files: the Dropbox desktop app does the syncing.

## Getting started

Install Dropbox from the Extension Store, then connect your account:

1. Open Preferences (Ctrl+P in Hariku's window), choose Dropbox and press "Connect
  Dropbox".
2. Your web browser opens Dropbox's sign-in page. Sign in, then choose Allow.
3. The browser comes back to Hariku by itself; the page says you can close the tab. Hariku
  says "Dropbox connected as" and your name, and the Dropbox account field shows your name
  and email.

You have five minutes to sign in. While Hariku waits, the button is "Cancel signing in".

The news about your own files also needs the Dropbox desktop app on this computer. The
field "Dropbox folder on this computer" shows its folder. If the app isn't installed, or
its folder belongs to another Dropbox account, that news is off, and links and news from
other people still work.

### If Dropbox shows a code

When another program is using the port Hariku listens on, Dropbox shows a code in the
browser instead of coming back to Hariku. Copy the code, paste it into the "Code from
Dropbox" field that appears on the Dropbox page in Preferences, and press "Use the code".

### Disconnecting

"Disconnect Dropbox" on the same page signs Hariku out of Dropbox and forgets the sign-in
on this computer. If Dropbox stops accepting the sign-in, for example because you removed
Hariku's access on the Dropbox website, Hariku says "Dropbox was disconnected" once, and
you can connect again.

## News about your files

When you save or add a file in your Dropbox folder, Hariku waits a moment and asks Dropbox
whether it has that version yet:

- "Syncing laporan.pdf to Dropbox..." while it uploads, then "laporan.pdf is synced."
- For several files: "Syncing 3 files to Dropbox..." and later "Your Dropbox is up to
  date."
- A file that still hasn't synced three minutes after you last changed it is mentioned
  once: "laporan.pdf hasn't synced yet; check the Dropbox app."

Hariku leaves alone the files the desktop app downloads (other people's work, see below),
Office's and other programs' temporary files, desktop.ini and similar system files, and
online-only files, which it never opens so they aren't downloaded.

The exact wording follows Hariku's speaking style.

## News from other people

- "Budi added catatan.txt to the Kelas folder." when someone adds or changes a file in a
  folder you share. Several changes are told together, one sentence per person.
- "Budi shared tugas.docx with you." when someone shares a file or a folder with you.
  Hariku checks this every five minutes; what was already shared when you connected isn't
  announced.

These two stay silent during quiet hours. A soft sound plays with news from other people,
and another with "synced", "up to date" and a copied link.

## Copying a link

### The file you're on in File Explorer

In File Explorer, go to a file in your Dropbox folder, open Aruna and say or type "copy
link" or "salin link" (also "copy this link", "copy dropbox link", "salin link ini",
"bagikan link ini"). Aruna closes, File Explorer gets the focus back, the file's shared
link is copied to the clipboard, and Hariku says "Link to laporan.pdf copied."

- Hariku uses the file you're on when it is selected, otherwise the first selected one.
  With nothing selected, it copies the link of the folder you are in.
- A file that already has a shared link keeps it. Otherwise a new link is made with your
  account's usual link settings.
- Outside your Dropbox folder, Hariku says "This file isn't in your Dropbox folder." The
  Dropbox folder itself can't have a link. For a file Dropbox doesn't have yet, wait until
  it has synced.
- If File Explorer isn't the window you were in, Hariku asks you to open your Dropbox
  folder there and select the file first.

You can also give "Copy the Dropbox link of the file selected in File Explorer" a key (see
Keys and commands). Make it global so it works while File Explorer has the focus.

### A file by its name

To copy the link of a file you're not on, say its name after the command: "copy link to
the budget", "salin link laporan". Dropbox looks it up by name:

- One clear match: its link is copied at once.
- One likely match: Aruna asks first, for example "Do you mean laporan final.pdf in the
  Kelas folder? Copy its link?"
- Several that fit: Aruna reads them out, so you can say the full name.

If the search takes longer than usual, the answer comes a moment later; a likely match is
then only named, and you say its full name to copy its link.

## Checking the sync status

Say "Dropbox status", "status dropbox", "is Dropbox up to date" or just "dropbox". Hariku
says "Your Dropbox is up to date", or which files are still syncing or haven't synced.

## Settings

Open Preferences and choose Dropbox.

- Dropbox account: who is connected, or "Not connected.", with the Connect Dropbox or
  Disconnect Dropbox button.
- Code from Dropbox, and Use the code: only while signing in needs a code.
- Dropbox folder on this computer: the desktop app's folder, or why the news about your
  files is off.
- Announce files syncing and synced.
- Announce when your Dropbox is up to date.
- Announce changes other people make in shared folders.
- Announce files and folders shared with you.
- Play Dropbox sounds.

All of these are on at first. The checkboxes are saved when you press OK or Apply.

## Keys and commands

These have no key by default. You can give them one in Preferences, Input Gestures, where
they are under "Dropbox"; tick "Make this shortcut Global" so the key works in every
window, File Explorer included.

- Copy the Dropbox link of the file selected in File Explorer: "copy link", "copy this
  link", "copy the link", "copy dropbox link", "share this link", "salin link", "salin
  link ini", "salin link dropbox", "salin tautan", "bagikan link ini".
- Dropbox sync status: "dropbox", "Dropbox status", "status dropbox", "dropbox sync
  status", "is dropbox up to date", "sinkronisasi dropbox", "apakah dropbox sudah up to
  date".

Copying the link of a file by name starts with "copy link to", "copy the link to", "copy
link for", "copy link of", "share link to", "salin link", "salin tautan" or "bagikan
link", followed by the name.

## Privacy

The Dropbox extension talks to Dropbox only after you connect it, with your own sign-in,
and Hariku's developer receives nothing. While Hariku runs, it keeps a connection to
Dropbox to hear about changes, until you disconnect.

- Signing in happens in your browser, on Dropbox's own site. Hariku asks for four
  permissions: your name and email, the details of your files and folders (not their
  contents), reading shared links and making shared links.
- What is sent to Dropbox: the paths of the files you change in your Dropbox folder, to
  ask whether Dropbox has that version yet; the path of a file whose link you copy, or the
  name you search for; and requests for what changed, what was shared with you and who did
  it.
- To follow your files, Hariku reads only their names, sizes and times, never their
  contents. To know which file you're on in File Explorer, it asks File Explorer on this
  computer; nothing about that is sent anywhere, except that file's path when you copy its
  link.
- Your sign-in is kept on this computer, encrypted so only your Windows account can read
  it. "Disconnect Dropbox" asks Dropbox to cancel it and deletes it here.
