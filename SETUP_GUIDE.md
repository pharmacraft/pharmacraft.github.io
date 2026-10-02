# PharmaCraft Daily Telegram Automation, Setup Guide

This posts one MCQ (as a quiz with the correct answer and an explanation) and one
note to your Telegram channel every day, automatically. It runs for free on GitHub
Actions, so nothing needs to stay open on your computer.

## What is in this folder
- post_daily.py                     the script that posts to Telegram
- content.json                      your MCQs and notes (edit this to add more)
- .github/workflows/daily-telegram.yml   the daily scheduler

## One-time setup (about 10 minutes)

### Step 1, Make the bot
1. In Telegram, open @BotFather.
2. Send /newbot, give it a name and a username ending in "bot".
3. BotFather gives you a TOKEN (a long string like 123456:ABC...). Keep it secret.

### Step 2, Add the bot to your channel as admin
1. Open your channel @pharmacraft_official.
2. Channel settings, Administrators, Add Administrator, search your bot, add it.
3. Give it permission to Post Messages. Save.

### Step 3, Put the files in your GitHub repo
1. Copy post_daily.py and content.json into a folder named "telegram-bot" at the
   top of your repo.
2. Copy the .github/workflows/daily-telegram.yml file into your repo, keeping the
   same folder path: .github/workflows/daily-telegram.yml
   (You can use the SAME pharmacraft.github.io repo, or a separate repo. Either works.)

### Step 4, Add your secrets to GitHub (so the token is never public)
1. In your repo on GitHub, go to: Settings, Secrets and variables, Actions.
2. Click "New repository secret" and add TWO secrets:
   - Name: BOT_TOKEN      Value: the token from BotFather
   - Name: CHANNEL        Value: @pharmacraft_official
3. Save both.

### Step 5, Test it right now
1. In your repo, go to the Actions tab.
2. Open "PharmaCraft Daily Telegram", click "Run workflow".
3. In a few seconds, check your channel, the note and the MCQ quiz should appear.

Done. From now on it posts automatically every day at 6:00 PM IST.

## How the daily content works
Day 1 posts the first MCQ and note, day 2 the second, and so on. When the list
ends it loops back to the start. Add as many as you like in content.json.

## Change the posting time
In daily-telegram.yml, edit the cron line. Times are in UTC.
- 6:00 PM IST  = '30 12 * * *'
- 7:00 AM IST  = '30 1 * * *'
- 9:00 PM IST  = '30 15 * * *'

## Add more MCQs and notes
Open content.json and add items to "mcqs" and "notes".
- For a quiz, "correct" is the option number starting from 0 (first option = 0).
- The quiz "explanation" must be 200 characters or less.
