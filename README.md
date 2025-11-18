# LifeOS Food Coach Bot

A personal Telegram bot that sends meal reminders and AI-powered food choices.

## Features
- 4 daily notifications (breakfast, lunch, snack, dinner)
- AI chat support using OpenAI
- Learns from personal eating patterns
- Suggests portions based on available food
- Google Sheet logging (optional)
- Fully private: API keys stored only in Railway variables

## How it works
1. Telegram sends message → bot receives
2. Bot sends text to OpenAI GPT model
3. OpenAI returns personalized meal suggestions
4. Bot replies in Telegram

## Files
- `bot.py` — main bot code  
- `requirements.txt` — library list  
- `Procfile` — tells Railway how to run the bot  
- `.gitignore` — protects `.env` from uploading  

## Deployment
We deploy on **Railway** using environment variables:
- `TELEGRAM_BOT_TOKEN`
- `OPENAI_API_KEY`

## Important
**Do NOT upload your .env file.**  
Secrets must be added only inside Railway → Variables.
