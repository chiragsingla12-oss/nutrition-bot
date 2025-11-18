# LifeOS Food Coach Bot

## Overview
A personal Telegram bot that sends automatic meal reminders and provides AI-powered nutritional advice. The bot helps users maintain healthy eating habits by sending scheduled notifications for breakfast, lunch, snacks, and dinner, and responds to food-related questions using OpenAI's GPT model.

**Project Type:** Telegram Bot (Backend only - no frontend)
**Status:** Active and running in Replit environment
**Last Updated:** November 17, 2025

## Features
- **Comprehensive Daily Schedule**: 8 automated reminders throughout the day
  - 8:00 AM - Morning Routine (Hydration + Pre-Workout)
  - 9:15 AM - Post-Workout Mini Meal
  - 9:30 AM - Breakfast
  - 12:00 PM - Midday Hydration
  - 1:30 PM - Lunch (Balanced Indian Thali)
  - 5:00 PM - Evening Snack
  - 7:00 PM - Dinner
  - 9:00 PM - Night Craving Control
- **AI Nutritionist**: Uses OpenAI GPT-4o-mini to provide personalized food recommendations
- **Multiple Options**: Each meal has 10+ options organized by categories
- **Flexible Lifestyle Plan**: Choose ANY ONE option from each section daily
- **User Registration**: Users automatically register when they send /start command
- **24/7 Operation**: Runs continuously in the background

## Project Architecture

### Main Components
- `bot.py`: Main application file containing all bot logic
- `requirements.txt`: Python dependencies
- `.gitignore`: Excludes environment files and Python cache
- `Procfile`: Original deployment configuration for Railway (not used in Replit)

### How It Works
1. Bot runs continuously using Telegram's polling mechanism
2. Background scheduler thread checks time every 30 seconds
3. When scheduled time matches, sends meal reminders to registered users
4. All user messages are processed by OpenAI for nutritional advice
5. Responses are sent back through Telegram

### Daily Schedule & Options
- **8:00 AM - Morning Routine**: Hydration (warm water options) + Pre-Workout fuel (banana, almonds, apple)
- **9:15 AM - Post-Workout**: Fruits, almonds, coconut slice, roasted chana
- **9:30 AM - Breakfast**: Veg Indian options (chilla, poha, upma, idli), Protein-boost (yogurt, paneer), Quick options
- **12:00 PM - Midday Hydration**: Water, coconut water, lemonade
- **1:30 PM - Lunch**: Build-your-thali (Base: roti/rice, Sabzi: 8 options, Protein: dal/rajma/chole, Salad)
- **5:00 PM - Evening Snack**: Healthy crunch (roasted chana, makhana), Fruits, Protein options
- **7:00 PM - Dinner**: Light options (khichdi, dalia), High-protein (paneer bhurji, tofu), Very light (soup, salad)
- **9:00 PM - Night Craving**: Warm drinks (ajwain-jeera water, lemon water), Healthy munch, Sweet craving fix

## Environment Setup

### Required Secrets
These are already configured in Replit Secrets:
- `TELEGRAM_TOKEN`: Telegram bot token from @BotFather
- `OPENAI_API_KEY`: OpenAI API key for GPT access

### Dependencies
All Python packages are managed via `requirements.txt`:
- pyTelegramBotAPI==4.16.1
- openai==1.11.0
- python-dotenv
- httpx==0.24.0

## Recent Changes
- **2025-11-17**: Comprehensive full-day diet plan implementation
  - Expanded to 8 daily reminders covering entire day (8 AM - 9 PM)
  - Added 10+ options per meal with categorized sections
  - Implemented flexible lifestyle plan from OpenAI-generated diet
  - Includes hydration reminders, post-workout meals, and night craving control
  - All options follow Indian diet preferences with balanced nutrition
  - Fixed OpenAI API call (changed from dict access to attribute access)
  - Improved scheduler to track multiple registered users with duplicate prevention
  - Added proper .gitignore entries for Replit environment
  - Configured workflow to run bot continuously

## How to Use

### For Users
1. Open Telegram and search for your bot (using the token you created)
2. Send `/start` to register and begin receiving reminders
3. Ask any food-related questions and get AI-powered nutritional advice
4. Example: "Should I eat roti or rice for lunch?"

### For Development
- The bot runs automatically via the "Telegram Bot" workflow
- Check console logs to see bot activity
- Bot will automatically reconnect if interrupted
- No frontend - all interaction happens through Telegram

## Technical Notes
- Bot uses long polling (infinity_polling) to receive messages
- Scheduler runs in a daemon thread to avoid blocking
- Registered users are stored in memory (resets on bot restart)
- All API keys are securely managed through Replit Secrets
- No database required - stateless operation

## User Preferences
None specified yet.
