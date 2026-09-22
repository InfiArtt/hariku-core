# Introducing the Hariku V2 Developer SDK: Build Your Own Extensions

Welcome to the new era of Hariku. 

With the release of Hariku V2, we have fundamentally shifted our architecture. Hariku is no longer a monolithic application where every feature is hardcoded into the core executable. Instead, we have stripped the core down to the absolute minimum and rebuilt the entire platform around a powerful, modular Extension Ecosystem. 

Today, we are thrilled to announce the official release of the **Hariku V2 Developer SDK**. Whether you want to build a simple habit tracker, a complex project management tool, or a completely custom integration, this SDK gives you the keys to the Hariku ecosystem.

Here is everything you need to know about building for Hariku V2, what’s inside the SDK, and how you can get started today.

---

## Why Build for Hariku V2?

If you are a developer, you know the pain of working with fragile plugin systems where one bad line of code from a third-party script crashes the entire host application. We engineered Hariku V2 specifically to solve this.

### 1. The Decoupled Event Bus (Pub/Sub)
Hariku V2 operates on a robust Event Bus system. Extensions never call each other directly. Instead, you subscribe to and emit events. Want to know when the user presses 'Enter' on the calendar? Subscribe to `on_enter_pressed`. Want to intercept the screen reader before it speaks? Hook into `on_before_speak`. 
Because everything is decoupled, if your extension crashes, the core application simply catches the exception, logs the traceback, and keeps running seamlessly. Your code will never bring down the main app.

### 2. Powerful Native APIs & Isolated Web Views
We give you deep access to the OS without the heavy lifting. You can spawn native Windows Toast notifications, listen to clipboard changes, or detect when the user switches active windows (Context Awareness). 
Need to display complex UI? We built an Isolated Web View system. You can render full HTML/CSS/JS documents inside a Hariku window. Because it runs in an isolated subprocess, your HTML rendering will never interfere with Hariku's low-level global keyboard hooks.

### 3. Industry-Grade Security (Centralized Hash Registry)
We take our users' safety very seriously. Instead of forcing developers to deal with complex Public Key Infrastructure (PKI) and digital signatures, we utilize a Centralized Hash Registry. When you publish an extension (.hrk), our servers compute its SHA256 hash. The Hariku client verifies every third-party extension against this server-side registry before executing a single line of code. It's lightweight for you, and highly secure for our users.

---

## What's Inside the SDK?

We have bundled everything you need into a single, lightweight ZIP file. You don't need to install any heavy CLI tools. Just extract the SDK and you are ready to write code.

Here is what you will find inside:

### 1. `DEVELOPERS.md` (The Holy Grail)
This is the comprehensive, official API documentation. It covers everything from registering custom hotkeys, injecting your own panels into the Core Preferences dialog, interacting with the i18n translation engine, to utilizing background thread managers like `core.api.run_thread`. If the core can do it, it’s documented here.

### 2. VS Code Ready (`.vscode/`)
We want your developer experience to be frictionless. The SDK comes with a pre-configured `.vscode` directory containing `launch.json`, `tasks.json`, and `settings.json`. Simply open the SDK folder in Visual Studio Code, and your debugging environment is instantly configured. No fiddling with Python paths or workspace settings required.

### 3. `template_extension/`
Nobody likes starting with a blank file. We have included a boilerplate template extension. It comes pre-packaged with a valid `manifest.json`, a properly structured `main.py` entry point, and examples of basic event subscriptions. You can literally rename this folder, modify the code, and have a working extension in five minutes.

### 4. `store_guidelines/`
If you plan on publishing your extension to the official Hariku Store, these are the rules of the road. This folder contains our public-facing governance documents:
- **`coding_standards.txt`**: Best practices for writing performant, accessible Python code for Hariku.
- **`security_policy.txt`**: What you can and cannot do (e.g., no arbitrary `exec()` calls, respecting path boundaries).
- **`code_of_conduct.txt`**: Our community standards.
- **`submission_guide.txt`**: The step-by-step process of packaging your folder into a `.hrk` file and submitting it to our review team.

*(Note: Internal review guidelines have been strictly excluded from this SDK to maintain the integrity of our security audits).*

---

## Ready to Start Building?

The Hariku community is growing, and we can't wait to see the incredible tools, integrations, and "kitchen appliances" you will build for this ecosystem. Whether you are building something just for yourself or planning to publish it to thousands of users on the Extension Store, this SDK is your starting line.

Download the SDK below, extract the ZIP, open it in VS Code, and let your imagination run wild.

Happy Coding!

**Download the Developer SDK here:**
![Hariku_V2_Developer_SDK.zip](@media:hariku-sdk)
