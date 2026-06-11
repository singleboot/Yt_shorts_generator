# How to Setup the Telegram Bot Agent (Step-by-Step)

This guide walks you through creating a Telegram bot, obtaining your credentials, and configuring the AI Shorts Creator to generate videos directly from Telegram messages.

---

## Step 1: Create a Bot via @BotFather
1. Open your **Telegram** app.
2. Search for the official account **`@BotFather`** (make sure it has the blue verification tick) and click **Start** or send `/start`.
3. Send the command:
   ```text
   /newbot
   ```
4. BotFather will ask you for a **name** for your bot (e.g., `My Shorts Creator`).
5. Next, it will ask for a **username** for your bot. This username must end in `_bot` (e.g., `ai_shorts_creator_bot`).
6. Once a unique username is accepted, BotFather will message you a success text containing your **API Token** (e.g., `123456789:ABCdefGhIJKlmNoPQRsTUVwxyZ`). Copy this token.

---

## Step 2: Configure the Bot in the App Settings
1. Open the **AI Shorts Creator** web application in your browser.
2. Go to the **Settings** page (found on the left sidebar).
3. Scroll down to the **Telegram Bot Agent** section.
4. Paste your copied **API Token** into the **Telegram Bot Token** field.
5. Click **Save Settings** at the bottom of the page.
   * *Note: The application dynamically reloads and boots up the Telegram polling loop automatically. No manual server restart is needed!*

---

## Step 3: (Optional) Find Your Telegram Chat ID
If you want to secure your bot so only *you* can trigger video generations, you can configure your Chat ID:
1. On Telegram, search for the account **`@userinfobot`** and click **Start**.
2. It will instantly reply with your profile details, including your numeric **`Id`** (e.g., `987654321`).
3. Copy this number.
4. Go back to the **Settings** page in the AI Shorts Creator, paste it into the **Telegram Chat ID (Optional)** field, and click **Save Settings**.

---

## Step 4: Interact with Your Bot
1. Search for your bot's username on Telegram and open the chat.
2. Click **Start** or send `/start`.
3. To trigger a generation, you can:
   * **Use the command**: `/generate topic="A fun fact about black holes"`
   * **Or simply send raw text**: *“Three amazing facts about Mount Everest”* (The bot treats raw text as the topic and defaults to your most recently active project).
4. The bot will acknowledge your message, begin generation, send progress updates (e.g. Script, Visuals, TTS), and automatically deliver the finished `.mp4` video directly to your chat once it's complete!
