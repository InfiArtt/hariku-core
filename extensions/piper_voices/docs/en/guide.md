# Piper Voices

Piper Voices adds Piper neural voices to Hariku Voice. They speak on your computer,
without the internet, and there is an Indonesian voice too. You download only the voices
you want; the Piper program comes along with the first one.

## Getting started

1. Open Preferences, Piper Voices, and download a voice (see the next section).
2. Open Preferences, Hariku Voice, and in "Source" choose "Piper neural voices
   (offline)".
3. Choose the "Language" and the "Voice", and press Test to hear it.
4. Tick what Hariku Voice should read, such as "Read reminders with Hariku Voice when
   they are due", and press OK.

## Downloading a voice

1. In Preferences, Piper Voices, choose a language in "Language". Your own language
   comes first; "All languages" shows every voice.
2. In the "Voices" list, each row gives the voice's name, language, quality (Extra low,
   Low, Medium or High), size, and whether it is installed. "Details" says more about
   the selected voice.
3. Press Download... (or Enter on the voice). Hariku first gets the voice's model card,
   then the "Download a Piper voice" window tells you the voice, its quality, the
   download size and its dataset license. The "Model card" box has the details from the
   card.
4. Press Download to go ahead, or Cancel.

The first time, the Piper program (21.4 MB, from GitHub) is downloaded along with the
voice, and the window includes it in the size. Hariku says the progress at 25, 50, 75
and 100 percent, then that the voice is ready. "Cancel download" stops a download; one
runs at a time. Status and "Download progress" on the page show where it is.

When the model card doesn't name a clear license for the voice's dataset, Hariku says
so. Check the dataset's own page before you rely on that voice.

## Removing a voice

Select an installed voice and press Remove (or Delete). Hariku asks first. You can
download it again later.

## The voice list

The list of voices comes from Hugging Face when you first open the page, and Hariku
keeps it for a week. Press "Refresh catalogue" to get the newest list now. Without the
internet, Hariku shows the list it saved last time, and your installed voices are
always shown.

## How Piper speaks

A long text, such as the Briefing, is spoken sentence by sentence: the first sentence
plays while Piper makes the next. While you use it, Piper keeps the voice loaded (about
100 MB of memory) and frees it after ten quiet minutes. What a voice has said is saved,
up to 30 MB, so a phrase it says again plays at once.

## Privacy

Piper voices speak on your computer: the text they read never leaves it. Piper Voices
connects only for its Preferences page:

- When you open the page, it gets the list of voices from Hugging Face, at most once a
  week, or when you press "Refresh catalogue". Browsing the list sends nothing.
- When you press Download, it gets the voice's model card from Hugging Face, and if you
  go ahead, the voice's files from Hugging Face. With your first voice, it also gets
  the Piper program from GitHub.

These requests carry no account and none of your data. Hariku downloads only from
GitHub and Hugging Face, and deletes any file whose checksum doesn't match.

The program and the voices are in `%APPDATA%\Hariku2\piper`, the saved speech in
`%APPDATA%\Hariku2\voice_cache\piper`. Remove a voice on the Piper Voices page, or
delete those folders to remove everything.
