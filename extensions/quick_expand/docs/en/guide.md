# Quick Expand

Quick Expand types long text for you. Set up a short abbreviation, such as addr, and
whenever you type it in any program followed by Space, Tab or Enter, Hariku replaces it
with the full text, such as your home address.

## Getting started

Quick Expand has no keys and no window of its own. You set it up in Preferences (Ctrl+P),
on the Quick Expand page. The list of abbreviations starts empty.

## Adding an abbreviation

1. Open Preferences (Ctrl+P) and go to the Quick Expand page.
2. In "Abbreviation", type the short form, such as addr.
3. In "Replacement text", type the full text. It can have several lines.
4. Press "Add / Update". Hariku says "Abbreviation addr added or updated."
5. Press OK to save. The abbreviation works at once.

An abbreviation may use lowercase letters a to z, the digits 0 to 9, hyphens and
underscores; capitals you type in the field become lowercase. Choose something you won't
type as an ordinary word, such as addr1 or sig-work.

## Using an abbreviation

Type the abbreviation as a word of its own, right after a space, a Tab or a new line,
then press Space, Tab or Enter. Hariku erases the abbreviation, types the replacement
text, and then the Space, Tab or Enter you pressed. A new line in the text is typed as
Enter. Keys you press while it types wait until it has finished.

Quick Expand listens only for letters, digits, the hyphen key and Backspace. Any other
key, Shift included, and switching to another window make it start over. So pressing
Shift partway through an abbreviation, for a capital letter or an underscore, stops it
from expanding: use a hyphen rather than an underscore, as in my-mail.

## Changing or deleting an abbreviation

The list on the Quick Expand page has two columns, "Abbreviation" and "Replacement text";
a new line shows there as [LF]. Selecting an abbreviation fills in both fields.

- To change the text, select the abbreviation, edit "Replacement text", and press "Add /
  Update".
- To delete one, select it and press "Delete selected".

Changing the abbreviation itself adds a new one; delete the old one if you don't need
it. Press OK in Preferences to save your changes, or Cancel to drop them.

## Good to know

- Quick Expand works only while Hariku is running.
- It watches the keyboard only while you have at least one abbreviation. What you type is
  kept in memory just long enough to spot an abbreviation; it is never saved or sent
  anywhere.
- It has no keys or Aruna commands of its own: Space, Tab and Enter after an abbreviation
  are all it needs.
