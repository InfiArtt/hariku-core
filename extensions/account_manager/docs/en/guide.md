# Hariku Account Manager

Sign in to Hariku with your InfiArtt account from infiartt.com, so extensions with online
features can know who you are. At the moment no official Hariku extension uses it, so you
only need it when an extension asks you to sign in. Its page is in English.

## Getting started

Open Preferences and go to the "Hariku Cloud" page. Under "Account Status" it shows
"Status: Not logged in", or "Logged in as:" with your user name and "Roles:" with your
roles.

## Signing in

1. Press "Login with Passkey / 2FA". The status says "Status: Waiting for browser
   login...".
2. Your web browser opens the sign-in page of infiartt.com. Sign in there the way the site
   asks. Your password never goes into Hariku.
3. When the browser says "Login Successful!", close that page and go back to Hariku. A
   notification says "Welcome back," with your user name, and the page shows "Logged in
   as:".

The browser hands the sign-in back to Hariku through your own computer (localhost, port
16623). If the sign-in fails or you cancel it on the site, a "Login Failed" notification
appears. If you close the browser without finishing, Hariku keeps waiting; restart Hariku
before you try again.

## Signing out

Press "Logout". Hariku deletes your access token and profile from this computer, and a
notification says "You have been securely logged out." It doesn't sign you out of
infiartt.com in your browser.

## Privacy

The Account Manager connects to infiartt.com only when you sign in. It opens the site's
sign-in page in your browser, then sends infiartt.com the one-time code the site gave
back, receives an access token, and fetches your profile: your user name and roles. It
keeps the token and the profile on your computer until you sign out. When Hariku starts,
it doesn't connect to anything; it only tells your other extensions that you are signed
in. The infiartt.com privacy policy, at infiartt.com/privacy, covers the data the site
keeps.
