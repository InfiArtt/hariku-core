# Voice Control

Voice Control lets you talk to Aruna, Hariku's command bar, instead of typing, in
Indonesian or English. Your speech is recognised on your computer by whisper.cpp, and it
is never saved or sent anywhere. You can also open Aruna just by saying a wake phrase,
such as "Hey Aruna".

## Getting started

Voice Control needs a speech model before it can listen. You download it once:

1. Open Preferences, Voice Control.
2. In the "Program and speech models" list, "Tiny speech model (fastest, for commands)"
   is already selected. Press Download... (or Enter on the row).
3. Hariku asks first, and tells you the size and where it comes from: the tiny model is
   77.7 MB from Hugging Face, and the speech recognition program, whisper.cpp (8.6 MB
   from GitHub), comes along with it. Answer Yes.
4. Hariku says the progress at 25, 50, 75 and 100 percent. When it's done, the Status
   field says "Voice Control is ready. Press Ctrl+Alt+Backspace and speak after the
   tone."

A headset works best. With speakers, the microphone can hear your screen reader.

## Talking to Aruna

1. Press Ctrl+Alt+Backspace. Aruna opens, a tone plays, and Aruna listens.
2. Say your command, such as "latest earthquake", "what time is it" or "remind me to
   take medicine tomorrow at 8". In Indonesian: "gempa terbaru", "jam berapa" or
   "ingatkan aku minum obat besok jam 8".
3. Stop talking. After a moment of silence another tone plays, and what you said goes
   into Aruna and runs as if you had typed it.

While it listens, Hariku silences your screen reader and Hariku Voice, so they don't
talk into the microphone.

- If Aruna is already open, or you turned off "Start listening as soon as Aruna opens",
  press Ctrl+Alt+Backspace again (or the Listen button in Aruna) and speak after the
  tone.
- To finish at once, press Ctrl+Alt+Backspace or Enter when you're done.
- Escape stops listening and throws away what you said.
- Listening stops by itself after 12 seconds. If you say nothing for 5 seconds, it
  stops and tells you it didn't hear anything.
- When Aruna asks you something, such as "... Save?" after a reminder, it listens again
  once the question has been said: answer "yes" or "no".

## Speech models

The list at the top of the Voice Control page has the program and three speech models,
each with its size and status:

- "Speech recognition program (whisper.cpp)", 8.6 MB, from GitHub. It comes along with
  your first model.
- "Tiny speech model (fastest, for commands)", 77.7 MB.
- "Base speech model (more accurate, for reminders)", 148.0 MB.
- "Small speech model (most accurate, slow on older computers)", 487.6 MB. On an older
  computer, a short command can take 15 seconds or more.

The models are OpenAI's Whisper models, made for whisper.cpp, and come from Hugging
Face. The tiny model is enough for commands; add the base model if you often speak
reminders.

To download one, select it and press Download... (or Enter). "Cancel download" stops a
download. To remove one, select it and press Remove (or Delete).

"Recognition model" chooses which model listens. With "Automatic (recommended)", Hariku
times each model the first time it uses it (the Status column then says, for example,
"Installed, about 1.6 s per command"). It then uses the most accurate model that is
quick enough for a command, and when what you said looks like a reminder, it recognises
it once more with a more accurate model, if you have one. You can also choose "Tiny:
fastest", "Base: more accurate" or "Small: most accurate, slow on older computers".

## When Aruna doesn't hear you well

If Aruna misses what you say, or you have to speak loudly, let Hariku measure your
microphone:

1. On the Voice Control page, press "Test microphone".
2. Hariku says "After the tone, say a sentence at your normal volume." After the tone,
   say one sentence.
3. Hariku measures your voice and the room, chooses the "Microphone sensitivity" that
   suits them and tells you. If your voice is too quiet or the room too noisy, it says
   how to help.
4. Press OK or Apply to keep the new sensitivity.

The test recording is only measured: it isn't played back or saved. You can also choose
"Microphone sensitivity" yourself: Low, Normal, High or Very high.

In a noisy home, high sounds such as birdsong never count as speech. If the noise keeps
Aruna listening for the full 12 seconds, it still tries to recognise what you said, and
only when that fails does it tell you the room was too noisy. Next time, press Enter as
soon as you finish, or choose a lower sensitivity.

If Windows blocks the microphone, Hariku tells you which switch to turn on in Windows
Settings, Privacy, Microphone.

## The wake phrase

Say a wake phrase, "Hey Aruna" or one you choose, and Aruna opens and listens to your
command, without a key. It is off until you turn it on.

### Setting up the wake phrase

1. In Preferences, Voice Control, select "Wake phrase listener (sherpa-onnx and an
   English keyword model)" in the list at the top, and press Download... It is 42.4 MB,
   from GitHub.
2. Tick "Listen for a wake phrase", and type your phrase in "Wake phrase". "About this
   phrase" tells you when a phrase is one word, very short, long or common (easily
   heard by mistake). English words work best with this model; names like Aruna may
   need the High sensitivity.
3. Press "Test the wake phrase...". After the tone, say the phrase a few times in 20
   seconds. Hariku says "Heard it" each time it hears you, then how many times it heard
   you. Press the button again to stop early.
4. If it missed you, choose High in "Wake phrase sensitivity" and test again. If it
   wakes up by mistake, choose Low.
5. Press OK.

A phrase can be up to 40 characters long, and the model hears only the letters A to Z:
write numbers as words. If the phrase can't be heard, OK keeps Preferences open and
tells you why.

### What the wake phrase does

Choose it in "When you say the wake phrase":

- "Open Aruna": Aruna opens with the tone, gets the focus and listens to your command.
- "Listen without opening a window": the window you're in keeps the focus, and your
  screen reader stays there. You talk, Aruna answers aloud, asks and hears "yes" or
  "no" by voice, and closes by itself when it's done.

If Aruna is open already, the wake phrase makes it listen.

### When the wake phrase listens

The Status field on the Voice Control page says whether Hariku is listening for your
phrase. It doesn't listen:

- while Hariku, or your screen reader through Hariku, is speaking
- while Voice Control listens to a command, or while you test the microphone or the
  wake phrase
- during quiet hours, if you tick "Pause the wake phrase during quiet hours"
- while Windows blocks the microphone
- while you have paused it

To pause it, run "Pause or resume the wake phrase" (see Keys and commands). It stays
paused until you run it again or restart Hariku.

Your screen reader's voice from speakers can reach the microphone; a headset stops that.

## Settings

Preferences, Voice Control. Download, Remove, Cancel download and the two tests act at
once; everything else is saved when you press OK or Apply.

- "Recognition model": which speech model listens (see Speech models).
- "Start listening as soon as Aruna opens": on by default. Turn it off if you'd rather
  type first; then press Ctrl+Alt+Backspace again when you want to speak.
- "Stop listening after this much silence": 0.6, 0.8, 1.0, 1.5 or 2.0 seconds. The
  default is 1.0.
- "Microphone sensitivity" and "Test microphone": see When Aruna doesn't hear you well.
- "Listen for a wake phrase", "Wake phrase", "Wake phrase sensitivity" (Low, Normal or
  High), "When you say the wake phrase", "Pause the wake phrase during quiet hours" and
  "Test the wake phrase...": see The wake phrase.

## Keys and commands

- Ctrl+Alt+Backspace, Hariku's key for Aruna, works everywhere. It opens Aruna, which
  listens at once (unless you turned off "Start listening as soon as Aruna opens").
  Pressed again while Aruna is open, it starts or stops listening.
- Enter, while Aruna listens: stop now and recognise what you said.
- Escape, while Aruna listens: stop and throw away what you said.
- "Pause or resume the wake phrase" has no key. Give it one in Preferences, Input
  Gestures, or ask Aruna for it: "pause the wake phrase", "resume the wake phrase",
  "wake phrase", "jeda frasa pemanggil" or "lanjutkan frasa pemanggil". Each of these
  pauses the wake phrase when it is listening, and resumes it when it is paused.
- On the Voice Control page, Enter on a row of the list downloads it, and Delete removes
  it.

## Privacy

- Your speech stays on your computer. While Voice Control listens, the sound is kept in
  memory only, handed to the whisper.cpp program on your computer through a local
  connection that nothing outside your computer can reach, and then dropped. It is
  never saved or sent anywhere. What was recognised is handled like text you typed.
- The microphone is on only while Voice Control listens to a command, during the tests
  on its page, and, if you turned the wake phrase on, in the background for your phrase.
  The wake phrase listener can only tell whether your phrase was said: it turns nothing
  else into text, and nothing is recorded, saved or sent. Turn the wake phrase off, or
  remove its listener, and the microphone is closed.
- Voice Control connects to the internet only when you press Download: whisper.cpp and
  the wake phrase listener come from GitHub, the speech models from Hugging Face. These
  requests carry no account and none of your data. Hariku downloads only from these
  sites, and deletes any file that doesn't match its checksum.
- The program, the models and the wake phrase listener are stored in
  `%APPDATA%\Hariku2\voice_control`. Its settings keep how fast each model was, never
  what you said. Remove the program, a model or the wake phrase listener on the Voice
  Control page, or delete that folder to remove everything.
