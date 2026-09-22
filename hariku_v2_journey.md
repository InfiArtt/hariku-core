# Growing Up with Hariku: A Solo Developer's Journey Rebuilding from Scratch

*Hey everyone. A quick heads-up before you dive into this post: this one might not be for all of you. Normally, I post updates, tutorials, or fun content, but today I’m writing something a bit like a public diary entry. This is just me wanting to take a step back, take a deep breath, and appreciate all the crazy things I've learned over the past few months. I want to appreciate how much I've grown, both as a creator and as a person. If you're just here for the usual stuff, feel free to skip this one! But if you want to see what happens behind the scenes when a solo creator decides to tear down their biggest project and build it back up from absolute zero, grab a cup of coffee, get comfortable, and stay a while.*

***

*(Oh, before I get into the deep stuff, for anyone new here who might be wondering: What actually is Hariku? The name might sound a bit Japanese, but it's actually an Indonesian word that simply translates to "My Day." In short, Hariku is a minimalist, highly accessible calendar and productivity application designed to make your days infinitely more productive. It’s completely keyboard-friendly (especially for screen-reader users like myself) and helps manage your reminders and schedules without the visual clutter. Believe me, Hariku is worth it. Well... admittedly, right now there aren't a ton of "kitchen appliances" (extensions) built for it yet to make it seem *that* impressive. But trust me, in the future, this Hariku kitchen is going to be incredibly powerful, limited only by your wildest imagination. Alright, let's begin the story!)*

## The Madness of the Past Few Months

If you've noticed that I’ve been a bit quiet lately, it’s because my life has been an absolute blur. If you were to look at my schedule over the last few months, you'd see a chaotic mess of late nights, endless cups of coffee, and a screen reader talking at triple speed to a very tired, but very driven, guy working alone in his room at 3 AM. 

I have been pouring my heart, my soul, and honestly a good chunk of my sanity into rebuilding my biggest project, Hariku, completely from scratch. 

Why rebuild something that already works? Well, to explain that, I need to tell you a story about kitchens.

## The Kitchen Analogy: Why V1 Had to Die

In the software world, people use fancy words like "Monolith" and "Modular." But since we’re just chatting here, let's talk about it like building a kitchen.

When I built the first version of Hariku (V1), I was just excited to get things working. I built an oven, a fridge, a blender, and a toaster. But because I didn't know any better, I essentially superglued them all together into one giant, unbreakable block. It worked fine for a while! But eventually, I ran into a massive problem: if the blender broke, the oven would suddenly catch fire, and the fridge would stop working. And to fix the blender, I had to throw away the entire kitchen and buy a new one.

That’s what V1 was. If one tiny feature broke, the whole application would crash. And if I wanted to release a tiny fix, I had to force everyone to re-download the entire app.

So, for Hariku V2, I took a sledgehammer to the kitchen. I decided to build it properly this time. 

Now, the "Core" of Hariku is just the electrical outlets and the countertop. Everything else, the calendar, the reminders, the tools, are separate appliances that you can plug in or unplug whenever you want. We call these "Extensions." If the blender (an extension) breaks, the rest of the kitchen doesn't care. It just keeps working. You just unplug the broken blender, get a new one, and you're good to go.

It sounds simple, right? But making that transition alone was one of the hardest things I've ever done.

## Dropping My Ego for the Greater Good

When you are working on a project all by yourself, you are the boss, the architect, and the worker. It is incredibly easy to fall into the trap of building things just because they sound "cool" to you. Egos get involved.

Throughout this project, my brain was constantly firing off wild, crazy ideas. I wanted to add overly complex features, weird experimental tools, and all sorts of crazy stuff that sounded cool on paper. But I had to physically force myself to stop, take a step back, and ask: *"Is this what people actually need, or is this just what I want to build to show off?"*

I had to suppress those wild ideas because what people actually need is **stability**. They need something that doesn't break when they click the wrong button. 

The biggest lesson in dropping my ego came when I was working on accessibility. As a blind developer myself, accessibility isn't just a checkbox; it's my daily reality. Blind and visually impaired users (including myself) use software called "Screen Readers" (like NVDA) that read the computer out loud to us. For a sighted person, you just look at the screen and click. For us, we navigate through sound.

In my old app, even though I built it myself, I realized that navigating the settings was a chore. We had to press the 'Tab' key on our keyboard four or five times just to hear the description of a setting before we could actually change it. It was exhausting, even for me. 

I spent weeks, *weeks*, doing crazy, mind-numbing technical gymnastics with the Windows operating system just to fix this. I had to "hack" the way Windows layers its windows and trick the system into injecting hidden text so that the screen reader would read everything smoothly in a single button press. 

It was brutal, tedious work. Nobody can *see* this feature. It doesn't look cool on a visual portfolio. But hearing it function flawlessly, knowing that my fellow blind users out there will have a seamless, zero-lag experience because I decided to put our collective needs above my own desire to build overly complex things? That made every headache worth it. That is what dropping the ego truly means.

## Building a Safety Net (So I Can Finally Sleep)

Have you ever tried building a massive house of cards? You carefully put one card on top, your hands are shaking, and you're terrified that breathing too hard will make the whole thing collapse. That was what updating V1 felt like.

In V2, I learned a concept called "Unit Testing." 
Imagine if, every time you added a card to your house of cards, you had a team of invisible robots that instantly checked every single card in the house to make sure nothing was wobbly. 

I spent a huge chunk of time writing these invisible robots (automated tests). Now, whenever I change a piece of code, I press a button, and in exactly two seconds, the computer runs over 100 checks across the entire app. If I accidentally broke a feature while trying to fix something else, the computer screams at me *before* I release it to the public. For the first time in months, I can actually sleep peacefully knowing I have a safety net.

## Becoming a Digital Bouncer

Because V2 allows people to download "Extensions" (like add-ons), I realized I had a massive new problem: Security. 

Allowing extensions is like inviting strangers into your house. Most of them are friendly, but what if one of them is trying to steal your TV? I had to shift my mindset from being a builder to being a digital bouncer. 

I learned how to write code that acts like a strict security guard. Before an extension is allowed inside, Hariku checks its "ID card" using complex cryptography (SHA256 hashes). I also had to learn how to prevent things like "Path Traversals" and "Zip Slips", which is basically a fancy way of saying I had to make sure the extensions couldn't pick the locks on the doors and sneak into folders on your computer where they don't belong. It was intimidating, but I feel so much safer knowing how to protect my users now.

## The Invisible World of the "Backend"

I also learned that making an app isn't just about what happens on your screen. It's about what happens on the internet behind the scenes. 

I had to dive deep into databases, API pointers, and table structures. If you've never worked with databases, imagine trying to organize a library containing millions of books, where every single book has a string attached to three other books in different rooms, and you have to find a specific book in half a second without tangling all the strings. It was a massive learning curve, but setting up the server infrastructure to handle historical data and extension registries made me feel like a true engineer.

## What Happens When Things Crash (Because They Will)

Here is a secret about software: it will always crash. Always. 

But I learned that *how* an app crashes is just as important as how it runs. Think about cars. Cars get into accidents, which is why we invented airbags. Software needs airbags too.

In the past, if Hariku broke, it would just instantly vanish from your screen. No warning, no explanation. Just *poof*. It was incredibly confusing and frustrating. 

For V2, I built a system of "failsafes." Now, if something goes horribly wrong, the app catches itself before it hits the ground. Instead of disappearing, it gently pauses, shows you a nice window explaining exactly what went wrong, and gives you a button to securely send me a report so I can fix it. 

I even built a "Hardware Safe Mode." If you hold down the 'Shift' key on your keyboard while opening Hariku, it intercepts the hardware signal, gives you a satisfying little "click" sound, and boots up a super-safe, barebones version of the app so you can fix whatever is broken. It's like the emergency hatch on a spaceship.

## Growing Up (And Giving Thanks)

When I look back at the thousands of lines of code I've written, the lonely nights listening to my screen reader read out endless error tracebacks, and the sheer amount of things I had to learn from scratch, I feel a profound sense of gratitude. 

Being a solo developer is lonely. There is no team to catch you when you fall. But going through this project forced me to grow up. Not just technically, but emotionally. Hariku V2 isn't just a software update to me anymore. It is a reflection of my growth. It taught me discipline. It taught me how to architect things that are built to last, and it taught me that true professional growth is about caring enough to build failsafes for when you inevitably make a mistake.

As I sit here typing this, listening to my screen reader echo these final words back to me, I have to admit I'm shedding a few tears. I’m looking back to just about a year ago when Hariku was first born out of a simple idea. To see it grow from that small, fragile app into this massive, robust V2 upgrade is completely overwhelming.

I might have coded V2 alone, but Hariku would never have existed in the first place without the people who stood by me during V1. I want to take a moment to thank them from the bottom of my heart:

*   **AraPearl**: For being the spark. The foundational vision of an accessible, minimalist, heartfelt app was yours. Thank you for your creative direction, your unwavering support, and for translating the entire app into Bahasa Indonesia so it could reach more people.
*   **Charity Gwyne**: For asking, *"If I don't know the shortcut, can I still see the other options?"* That one question transformed the entire user experience and gave birth to our interactive Main Menu.
*   **Claudya Fritsca & Fleycia Tandria**: For your brilliant ideas and encouragement that shaped some of our most powerful tools, the Period Tracker, the Project System, and the Observatory.
*   **Muhammad Saidinas & Algarion**: For your early contributions and support that helped shape this community.

To everyone who has supported me, used the app, reported bugs, or just waited patiently while I locked myself in my room to build this: thank you. We grew up together during this project. I feel like a completely different person than I was a year ago.

I can't wait to see where we go next.