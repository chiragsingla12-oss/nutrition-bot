import os
import time
import threading
import telebot
import datetime
import pytz
import sqlite3
import dateparser
from openai import OpenAI
from flask import Flask
from threading import Thread

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in environment variables!")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables!")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)
client = OpenAI(api_key=OPENAI_API_KEY)

IST = pytz.timezone('Asia/Kolkata')
CHAT_ID_FILE = "/tmp/chat_id.txt"
DB_FILE = "/tmp/tasks.db"
active_chat_id = None
workout_done_today = False

scheduler_status = {
    "last_check": None,
    "last_sent": None,
    "is_running": False,
    "error_count": 0
}

meal_schedule = {
    "exercise_morning": "07:00",
    "morning_routine": "08:00",
    "post_workout": "08:30",
    "breakfast": "08:45",
    "water_1": "10:00",
    "midday_hydration": "11:00",
    "water_2": "12:00",
    "lunch": "13:00",
    "water_3": "14:30",
    "water_4": "16:00",
    "snack": "16:30",
    "exercise_backup": "17:00",
    "water_5": "18:00",
    "dinner": "18:30",
    "water_6": "20:00",
    "night_craving": "21:00"
}

# ==========================================
# DATABASE SETUP
# ==========================================
def init_database():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS tasks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            chat_id INTEGER NOT NULL,
            task_description TEXT NOT NULL,
            target_datetime TEXT NOT NULL,
            reminder_datetime TEXT NOT NULL,
            followup_datetime TEXT NOT NULL,
            reminder_sent BOOLEAN DEFAULT 0,
            followup_sent BOOLEAN DEFAULT 0,
            completed BOOLEAN DEFAULT 0,
            created_at TEXT NOT NULL
        )
    ''')
    conn.commit()
    conn.close()
    print("✅ Database initialized")

init_database()

def add_task(chat_id, task_description, target_datetime):
    """Add a new task to database with smart reminder timing"""
    try:
        current_time = datetime.datetime.now(IST)
        time_until_task = (target_datetime - current_time).total_seconds() / 60  # minutes
        
        # Calculate reminder and followup times
        reminder_time = target_datetime - datetime.timedelta(hours=1)
        followup_time = target_datetime + datetime.timedelta(minutes=15)
        
        # Check if task is less than 1 hour away
        send_reminder_immediately = time_until_task < 60
        
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            INSERT INTO tasks (chat_id, task_description, target_datetime, 
                             reminder_datetime, followup_datetime, created_at, reminder_sent)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        ''', (
            chat_id,
            task_description,
            target_datetime.isoformat(),
            reminder_time.isoformat(),
            followup_time.isoformat(),
            current_time.isoformat(),
            1 if send_reminder_immediately else 0  # Mark as sent if immediate
        ))
        task_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        # Send immediate reminder if less than 1 hour away
        if send_reminder_immediately:
            try:
                target_display = target_datetime.strftime("%I:%M %p on %B %d, %Y")
                minutes_away = int(time_until_task)
                
                message = (
                    f"⏰ *IMMEDIATE TASK REMINDER*\n\n"
                    f"📋 {task_description}\n\n"
                    f"⏱️ Scheduled for: {target_display}\n"
                    f"🚨 Only {minutes_away} minutes away!\n\n"
                    f"I'm reminding you NOW since it's less than 1 hour away! 🔔"
                )
                
                bot.send_message(chat_id, message, parse_mode="Markdown")
                print(f"✅ Sent IMMEDIATE reminder for task {task_id} (gap: {minutes_away} min)")
            except Exception as e:
                print(f"❌ Error sending immediate reminder: {e}")
        
        return task_id
        
    except Exception as e:
        print(f"❌ Error adding task: {e}")
        return None


def get_pending_reminders():
    try:
        now = datetime.datetime.now(IST).isoformat()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, chat_id, task_description, target_datetime, reminder_datetime
            FROM tasks
            WHERE reminder_sent = 0 AND reminder_datetime <= ? AND completed = 0
        ''', (now,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks
    except Exception as e:
        print(f"❌ Error getting reminders: {e}")
        return []

def get_pending_followups():
    try:
        now = datetime.datetime.now(IST).isoformat()
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('''
            SELECT id, chat_id, task_description, target_datetime, followup_datetime
            FROM tasks
            WHERE followup_sent = 0 AND reminder_sent = 1 AND followup_datetime <= ? AND completed = 0
        ''', (now,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks
    except Exception as e:
        print(f"❌ Error getting follow-ups: {e}")
        return []

def mark_reminder_sent(task_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET reminder_sent = 1 WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error marking reminder sent: {e}")

def mark_followup_sent(task_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET followup_sent = 1 WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error marking follow-up sent: {e}")

def mark_task_completed(task_id):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        cursor.execute('UPDATE tasks SET completed = 1 WHERE id = ?', (task_id,))
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"❌ Error marking task completed: {e}")

def get_user_tasks(chat_id, include_completed=False):
    try:
        conn = sqlite3.connect(DB_FILE)
        cursor = conn.cursor()
        if include_completed:
            cursor.execute('''
                SELECT id, task_description, target_datetime, completed
                FROM tasks
                WHERE chat_id = ?
                ORDER BY target_datetime DESC
                LIMIT 10
            ''', (chat_id,))
        else:
            cursor.execute('''
                SELECT id, task_description, target_datetime, completed
                FROM tasks
                WHERE chat_id = ? AND completed = 0
                ORDER BY target_datetime ASC
            ''', (chat_id,))
        tasks = cursor.fetchall()
        conn.close()
        return tasks
    except Exception as e:
        print(f"❌ Error getting user tasks: {e}")
        return []

def parse_reminder_request(text):
    """Parse natural language reminder request"""
    try:
        text = text.lower()
        for prefix in ['remind me to ', 'remind me ', 'reminder to ', 'reminder ']:
            if text.startswith(prefix):
                text = text[len(prefix):]
                break
        
        time_indicators = ['at', 'on', 'tomorrow', 'today', 'next', 'in']
        
        time_start_idx = len(text)
        for indicator in time_indicators:
            idx = text.rfind(' ' + indicator + ' ')
            if idx != -1 and idx < time_start_idx:
                time_start_idx = idx
        
        if time_start_idx < len(text):
            task_desc = text[:time_start_idx].strip()
            time_phrase = text[time_start_idx:].strip()
        else:
            task_desc = text
            time_phrase = text
        
        # Get current IST time for reference
        ist_now = datetime.datetime.now(IST)
        
        # Parse with explicit settings
        parsed_date = dateparser.parse(
            time_phrase,
            settings={
                'TIMEZONE': 'Asia/Kolkata',
                'RETURN_AS_TIMEZONE_AWARE': True,
                'PREFER_DATES_FROM': 'future',
                'RELATIVE_BASE': ist_now.replace(tzinfo=None)  # Use IST as base
            }
        )
        
        if parsed_date is None:
            return None, None
        
        # Ensure timezone is IST
        if parsed_date.tzinfo is None:
            # If no timezone, assume IST
            target_time = IST.localize(parsed_date)
        else:
            # Convert to IST
            target_time = parsed_date.astimezone(IST)
        
        # If parsed time is in the past but user said "at X PM today", add to today
        if target_time <= ist_now:
            # Check if user specified a time without date
            if 'tomorrow' not in time_phrase.lower() and 'next' not in time_phrase.lower():
                # Try parsing just the time
                time_only = dateparser.parse(
                    time_phrase,
                    settings={'PARSERS': ['absolute-time']}
                )
                if time_only:
                    # Combine today's date with parsed time
                    target_time = ist_now.replace(
                        hour=time_only.hour,
                        minute=time_only.minute,
                        second=0,
                        microsecond=0
                    )
                    # If still in past, add one day
                    if target_time <= ist_now:
                        target_time = target_time + datetime.timedelta(days=1)
        
        # Extract task description if needed
        if not task_desc or len(task_desc) < 3:
            original_lower = text.lower()
            for word in time_phrase.split():
                idx = original_lower.find(word)
                if idx > 0:
                    task_desc = text[:idx].strip()
                    break
        
        return task_desc, target_time
        
    except Exception as e:
        print(f"❌ Error parsing reminder: {e}")
        return None, None

# ==========================================
# HELPER FUNCTIONS
# ==========================================
def get_ist_time():
    return datetime.datetime.now(IST)

def get_ist_time_str():
    return get_ist_time().strftime("%H:%M")

def get_ist_display():
    return get_ist_time().strftime("%I:%M:%S %p IST")

def save_chat_id(chat_id):
    global active_chat_id
    active_chat_id = chat_id
    try:
        with open(CHAT_ID_FILE, "w") as f:
            f.write(str(chat_id))
        print(f"✅ Saved chat_id: {chat_id}")
    except Exception as e:
        print(f"❌ Error saving chat_id: {e}")

def load_chat_id():
    global active_chat_id
    try:
        if os.path.exists(CHAT_ID_FILE):
            with open(CHAT_ID_FILE, "r") as f:
                chat_id = int(f.read().strip())
                active_chat_id = chat_id
                print(f"✅ Loaded chat_id: {chat_id}")
                return chat_id
    except Exception as e:
        print(f"⚠️ Error loading chat_id: {e}")
    return None

load_chat_id()

def get_water_reminder():
    import random
    messages = [
        "💧 *Water Time!*\n\nDrink 1 glass of water RIGHT NOW.\n\n💡 Tip: NOT during meals! Drink 30 min before or after eating.",
        "💧 *Hydration Check!*\n\nHave you had water recently?\n\nDrink 1 glass now! Goal: 8-10 glasses daily. 🚰",
        "💧 *Water Break!*\n\n1 glass of water = better metabolism!\n\nDrink it now! 💪",
        "💧 *Thirsty?*\n\nEven if not, drink 1 glass NOW.\n\nProper hydration helps with weight loss!",
        "💧 *Water Alert!*\n\nYour body needs water every 1-2 hours.\n\nDrink 1 glass right now!",
        "💧 *Hydrate Now!*\n\n1 glass of water helps:\n• Reduce hunger\n• Boost metabolism\n• Flush toxins\n\nDrink up! 🚰"
    ]
    return random.choice(messages)

def get_exercise_reminder(time_of_day):
    if time_of_day == "morning":
        return (
            "🏋️ *Morning Workout Time!*\n\n"
            "⏰ 7:00 AM - Perfect time for your workout!\n\n"
            "Today's plan: HIIT + Weights (30-60 min)\n\n"
            "💡 Tips:\n"
            "• Light snack if needed (banana/5-6 almonds)\n"
            "• Drink water before starting\n"
            "• This consistency will help break your plateau!\n\n"
            "✅ Reply 'workout done' after your workout!"
        )
    else:
        return (
            "⚠️ *Workout Reminder!*\n\n"
            "🏋️ It's 5:00 PM - Haven't seen your workout today!\n\n"
            "If morning got busy, let's do it now:\n"
            "• Even 20-30 min is better than skipping!\n"
            "• Quick option: 3 rounds of:\n"
            "  - 20 squats\n"
            "  - 15 push-ups\n"
            "  - 30 sec plank\n"
            "  - 20 jumping jacks\n\n"
            "💪 Consistency is key to breaking your plateau!\n\n"
            "✅ Reply 'workout done' when finished!"
        )

def get_food_options(meal):
    options_map = {
        "morning_routine": [
            "💧 Warm water/lemon water/ajwain-jeera water",
            "🏋️ Pre-workout: Banana/5-6 almonds (optional)"
        ],
        "post_workout": [
            "💪 Recovery: Fruit/almonds/coconut water/roasted chana"
        ],
        "breakfast": [
            "🥘 *IDEAL OPTIONS:*",
            "• Moong dal chilla (2 medium)",
            "• Besan chilla (2 medium)",
            "• Poha (1.5 cups)",
            "• Upma (1 bowl)",
            "• Paneer bhurji (50g = palm size)",
            "",
            "🏠 *FAMILY MEAL (Dry Sabzi + Roti):*",
            "• 2 multigrain rotis (medium size)",
            "• Dry sabzi: 1 small bowl (1 cup max)",
            "• If potato sabzi: 4-5 pieces max",
            "• Add: 1 small bowl curd/sprouts for protein",
            "",
            "⚡ *QUICK OPTION:*",
            "• 2 toast + 2 tsp peanut butter",
            "• OR Banana + 8-10 almonds"
        ],
        "midday_hydration": [
            "💧 Water/Coconut water/Lemonade (no sugar)",
            "🍎 Optional: Small fruit if hungry"
        ],
        "lunch": [
            "🥘 *IDEAL BALANCED MEAL:*",
            "• Start with salad (cucumber/carrot/sprouts)",
            "• 2 multigrain rotis",
            "• Wet sabzi/dal: 1 SMALL bowl (1 cup)",
            "• OR Rajma/Chole: ½ cup",
            "• Curd: 1 small bowl",
            "",
            "⚠️ *PORTION CONTROL RULES:*",
            "• Sabzi bowl = your fist size (NOT serving bowl!)",
            "• If paneer sabzi: 50-60g paneer max",
            "• Rice option: 1 roti + ½ cup rice + dal",
            "• Ghee in sabzi: Ask for LIGHT hand (1 tsp max)",
            "",
            "🥗 *REMEMBER:* Eat salad FIRST to feel fuller!"
        ],
        "snack": [
            "🥜 *HEALTHY OPTIONS:*",
            "• Roasted chana: 2-3 tbsp",
            "• Makhana: 1 cup",
            "• Mixed nuts: 10-12 pieces",
            "• Apple/Pomegranate",
            "",
            "⚠️ *IF FAMILY HAS NAMKEEN:*",
            "• Your limit: 2 tbsp MAX",
            "• OR Better: Mix 1 tbsp namkeen + 2 tbsp roasted chana",
            "• This is YOUR weak time - stay strong! 💪"
        ],
        "dinner": [
            "🏠 *FAMILY MEAL (Stuffed Roti):*",
            "• 1.5-2 stuffed rotis (medium size)",
            "• If very filling: Just 1.5 roti",
            "• Side: Small bowl curd/raita",
            "",
            "🌙 *LIGHTER OPTIONS (Better for weight loss):*",
            "• Moong dal khichdi: 1 bowl + curd",
            "• Daliya: 1 bowl",
            "• 1 roti + dal + sabzi (small portions)",
            "• Soup + 1 roti",
            "",
            "✨ *IDEAL:* Keep dinner lighter than lunch!"
        ],
        "night_craving": [
            "🍵 *BEST CHOICES:*",
            "• Warm water with ajwain-jeera-haldi",
            "• Warm lemon water",
            "• Cinnamon water",
            "",
            "🥜 *IF REALLY HUNGRY:*",
            "• Makhana: ½ cup",
            "• Roasted chana: 2 tbsp",
            "• 6-8 almonds",
            "• Khakhra: 2 pieces",
            "",
            "🍯 *SWEET CRAVING:*",
            "• Small piece jaggery",
            "• Warm milk + pinch cinnamon",
            "",
            "🚫 *AVOID:* Namkeen, biscuits, apple (at night), fried snacks"
        ]
    }
    return options_map.get(meal, ["Options not found"])

def send_meal_reminder(chat_id, meal):
    global scheduler_status, workout_done_today
    try:
        current_time = get_ist_display()

        if meal.startswith("water_"):
            message = get_water_reminder()
            bot.send_message(chat_id, message, parse_mode="Markdown")
            scheduler_status["last_sent"] = f"{meal} at {current_time}"
            print(f"✅ [{current_time}] Sent water reminder to {chat_id}")
            return True

        if meal == "exercise_morning":
            message = get_exercise_reminder("morning")
            bot.send_message(chat_id, message, parse_mode="Markdown")
            scheduler_status["last_sent"] = f"{meal} at {current_time}"
            print(f"✅ [{current_time}] Sent morning exercise reminder to {chat_id}")
            return True

        if meal == "exercise_backup":
            if not workout_done_today:
                message = get_exercise_reminder("evening")
                bot.send_message(chat_id, message, parse_mode="Markdown")
                scheduler_status["last_sent"] = f"{meal} at {current_time}"
                print(f"✅ [{current_time}] Sent backup exercise reminder to {chat_id}")
            else:
                print(f"⏭️ [{current_time}] Skipped backup - workout already done today!")
            return True

        options = get_food_options(meal)

        titles = {
            "morning_routine": "🌅 GOOD MORNING!",
            "post_workout": "💪 Post-Workout Recovery",
            "breakfast": "🍳 Breakfast Time!",
            "midday_hydration": "💧 Midday Check-in!",
            "lunch": "🍽️ Lunch Time!",
            "snack": "☕ Evening Snack Time!",
            "dinner": "🌆 Dinner Time!",
            "night_craving": "🌙 Night Craving Alert!"
        }

        message = "*{title}*\n⏰ {time}\n\n".format(
            title=titles.get(meal, meal),
            time=current_time
        )
        for item in options:
            message += f"{item}\n"

        if meal in ["lunch", "dinner"]:
            message += "\n💡 Walk 5-10 mins after eating for better digestion!"
        elif meal == "snack":
            message += "\n💪 This is your challenging time - you've got this!"
        elif meal == "night_craving":
            message += "\n✨ Smart choices now = lighter morning tomorrow!"

        bot.send_message(chat_id, message, parse_mode="Markdown")
        scheduler_status["last_sent"] = f"{meal} at {current_time}"
        print(f"✅ [{current_time}] Sent {meal} to {chat_id}")
        return True

    except Exception as e:
        scheduler_status["error_count"] += 1
        print(f"❌ [{get_ist_display()}] Error sending {meal}: {e}")
        return False

# ==========================================
# TASK REMINDER CHECKER
# ==========================================
def task_reminder_checker():
    print("🔔 Task reminder checker started")
    while True:
        try:
            pending_reminders = get_pending_reminders()
            for task in pending_reminders:
                task_id, chat_id, task_desc, target_dt_str, reminder_dt_str = task

                target_dt = datetime.datetime.fromisoformat(target_dt_str)
                target_display = target_dt.strftime("%I:%M %p on %B %d, %Y")

                message = (
                    f"⏰ *TASK REMINDER*\n\n"
                    f"📋 {task_desc}\n\n"
                    f"⏱️ Scheduled for: {target_display}\n\n"
                    f"This is your 1-hour advance notice! 🔔"
                )

                try:
                    bot.send_message(chat_id, message, parse_mode="Markdown")
                    mark_reminder_sent(task_id)
                    print(f"✅ Sent reminder for task {task_id} to {chat_id}")
                except Exception as e:
                    print(f"❌ Error sending reminder for task {task_id}: {e}")

            pending_followups = get_pending_followups()
            for task in pending_followups:
                task_id, chat_id, task_desc, target_dt_str, followup_dt_str = task

                target_dt = datetime.datetime.fromisoformat(target_dt_str)
                target_display = target_dt.strftime("%I:%M %p")

                message = (
                    f"✅ *FOLLOW-UP*\n\n"
                    f"📋 Did you complete: {task_desc}?\n\n"
                    f"⏱️ It was scheduled for {target_display}\n\n"
                    f"Reply 'done' if completed, or let me know if you need to reschedule!"
                )

                try:
                    bot.send_message(chat_id, message, parse_mode="Markdown")
                    mark_followup_sent(task_id)
                    print(f"✅ Sent follow-up for task {task_id} to {chat_id}")
                except Exception as e:
                    print(f"❌ Error sending follow-up for task {task_id}: {e}")

        except Exception as e:
            print(f"❌ Task reminder checker error: {e}")

        time.sleep(30)

threading.Thread(target=task_reminder_checker, daemon=True).start()

# ==========================================
# SCHEDULER
# ==========================================
def scheduler():
    global scheduler_status, workout_done_today
    sent_today = set()
    scheduler_status["is_running"] = True
    print(f"🔄 Scheduler started at {get_ist_display()}")

    while True:
        try:
            ist_now = get_ist_time()
            current_time = ist_now.strftime("%H:%M")
            current_date = ist_now.strftime("%Y-%m-%d")
            scheduler_status["last_check"] = get_ist_display()

            if ist_now.second == 0:
                separator = "=" * 60
                print(f"\n{separator}")
                print(f"🇮🇳 [{get_ist_display()}]")
                print("📱 Active Chat: {chat}".format(chat=active_chat_id or 'NONE'))
                print(f"⏰ Current Time: {current_time}")
                print(f"🏋️ Workout Today: {'✅ Done' if workout_done_today else '❌ Pending'}")

                for meal, time_str in sorted(meal_schedule.items(), key=lambda x: x[1]):
                    if time_str > current_time:
                        try:
                            time_obj = datetime.datetime.strptime(time_str, "%H:%M")
                            current_obj = datetime.datetime.strptime(current_time, "%H:%M")
                            diff = (time_obj - current_obj).seconds // 60
                            print(f"⏰ Next: {meal} in {diff} minutes ({time_str})")
                        except ValueError:
                            pass
                        break
                print(f"📊 Sent today: {len(sent_today)}")
                print(f"{separator}\n")

            if current_time == "00:00":
                sent_today.clear()
                workout_done_today = False
                print(f"🔄 [{get_ist_display()}] Daily tracker reset - new day!")

            if active_chat_id:
                for meal, time_str in meal_schedule.items():
                    meal_key = f"{current_date}_{meal}"
                    if current_time == time_str and meal_key not in sent_today:
                        print(f"\n🔔 TRIGGER: {meal} at {current_time}")
                        if send_meal_reminder(active_chat_id, meal):
                            sent_today.add(meal_key)
                        time.sleep(2)
        except Exception as e:
            scheduler_status["error_count"] += 1
            print(f"❌ Scheduler error: {e}")

        time.sleep(10)

threading.Thread(target=scheduler, daemon=True).start()

# ==========================================
# MESSAGE HANDLERS
# ==========================================

@bot.message_handler(content_types=['voice'])
def handle_voice(message):
    """Handle voice messages - transcribe in English only"""
    try:
        processing_msg = bot.reply_to(message, "🎙️ Transcribing your voice message...")
        
        file_info = bot.get_file(message.voice.file_id)
        downloaded_file = bot.download_file(file_info.file_path)
        
        temp_file = f"/tmp/voice_{message.chat.id}_{int(time.time())}.ogg"
        with open(temp_file, 'wb') as f:
            f.write(downloaded_file)
        
        with open(temp_file, 'rb') as audio_file:
            transcript = client.audio.transcriptions.create(
                model="whisper-1",
                file=audio_file,
                language="en",
                response_format="text"
            )
        
        transcribed_text = transcript if isinstance(transcript, str) else transcript.text
        
        import re
        if re.search(r'[\u0900-\u097F\u0980-\u09FF\u0A00-\u0AFF]', transcribed_text):
            bot.delete_message(message.chat.id, processing_msg.message_id)
            bot.reply_to(message, 
                "⚠️ *Language Note*\n\n"
                "Please speak in English or Hinglish!\n\n"
                "✅ Good: 'mujhe paneer khana hai'\n"
                "❌ Avoid: देवनागरी script\n\n"
                "Try again! 🎙️",
                parse_mode="Markdown")
            if os.path.exists(temp_file):
                os.remove(temp_file)
            return
        
        bot.delete_message(message.chat.id, processing_msg.message_id)
        
        bot.reply_to(message, 
            f"🎙️ *You said:*\n\"{transcribed_text}\"", 
            parse_mode="Markdown")
        
        if os.path.exists(temp_file):
            os.remove(temp_file)
        
        class MockMessage:
            def __init__(self, original_msg, text):
                self.chat = original_msg.chat
                self.text = text
                self.message_id = original_msg.message_id
        
        mock_msg = MockMessage(message, transcribed_text)
        handle_chat(mock_msg)
        
    except Exception as e:
        bot.reply_to(message, f"❌ Sorry, couldn't transcribe: {str(e)[:100]}")
        print(f"❌ Voice transcription error: {e}")


@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Handle text messages"""
    if not message.text:
        return
    
    text = message.text
    chat_id = message.chat.id
    print(f"📨 Received: '{text}' from {chat_id}")
    
    if text == '/start':
        handle_start(message)
    elif text == '/debug':
        handle_debug(message)
    elif text == '/status':
        handle_status(message)
    elif text == '/time':
        handle_time(message)
    elif text == '/test':
        handle_test(message)
    elif text == '/tasks':
        handle_tasks(message)
    elif text.startswith('/trigger'):
        handle_trigger(message)
    elif text.startswith('/'):
        bot.reply_to(message, "❌ Unknown command! Try /start /debug /status /time /test /tasks")
    else:
        handle_chat(message)

# ==========================================
# COMMAND HANDLERS
# ==========================================

def handle_start(message):
    save_chat_id(message.chat.id)
    msg = ("🙏 *Namaste! Your Health & Task Coach!*\n\n"
           "🇮🇳 Activated: {time}\n"
           "👤 Chat ID: {chat_id}\n\n"
           "✅ *Profile:* 84→74kg, Plateau 1.5yr\n\n"
           "🔔 *Daily Reminders:*\n"
           "• 07:00 - Exercise\n"
           "• 08:00-21:00 - Nutrition & Water\n"
           "• 6 water reminders throughout day\n\n"
           "📝 *Task Reminders:*\n"
           "Just tell me naturally:\n"
           "• Remind me to call doctor at 5 PM tomorrow\n"
           "• Remind me to send report on Dec 5 at 3 PM\n\n"
           "💬 *Commands:*\n"
           "/time /status /tasks /debug /test\n\n"
           "Let's achieve your goals! 💪").format(
               time=get_ist_display(),
               chat_id=message.chat.id
           )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_tasks(message):
    tasks = get_user_tasks(message.chat.id, include_completed=False)

    if not tasks:
        bot.reply_to(message, 
            "📝 *Your Tasks*\n\n"
            "No pending tasks!\n\n"
            "Tell me naturally to add one:\n"
            "• Remind me to call John at 5 PM\n"
            "• Remind me to send email tomorrow at 10 AM",
            parse_mode="Markdown")
        return

    msg = "📝 *Your Pending Tasks*\n\n"
    for task in tasks:
        task_id, task_desc, target_dt_str, completed = task
        target_dt = datetime.datetime.fromisoformat(target_dt_str)
        display_time = target_dt.strftime("%I:%M %p, %b %d")
        msg += f"• {task_desc}\n  ⏰ {display_time}\n\n"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_debug(message):
    ist_now = get_ist_time()
    current_time = ist_now.strftime("%H:%M")

    tasks = get_user_tasks(message.chat.id, include_completed=False)
    task_count = len(tasks)

    msg = ("🔍 *Debug Information*\n\n"
           "⏰ Current IST: {ist}\n"
           "🕐 Time String: {time_str}\n"
           "👤 Your Chat ID: {your_id}\n"
           "💾 Stored Chat ID: {stored_id}\n"
           "✅ Match: {match}\n"
           "🏋️ Workout Today: {workout}\n"
           "📝 Pending Tasks: {tasks}\n\n"
           "🔄 *Scheduler Status:*\n"
           "Running: {running}\n"
           "Last Check: {last_check}\n"
           "Last Sent: {last_sent}\n"
           "Errors: {errors}\n\n"
           "📅 *Schedule Check:*\n").format(
               ist=get_ist_display(),
               time_str=current_time,
               your_id=message.chat.id,
               stored_id=active_chat_id or 'None',
               match='YES' if message.chat.id == active_chat_id else 'NO',
               workout='✅ Done' if workout_done_today else '❌ Pending',
               tasks=task_count,
               running=scheduler_status['is_running'],
               last_check=scheduler_status['last_check'] or 'Never',
               last_sent=scheduler_status['last_sent'] or 'None',
               errors=scheduler_status['error_count']
           )

    for meal, time_str in meal_schedule.items():
        match = "✅ NOW!" if current_time == time_str else "⏳"
        msg += f"{match} {time_str} - {meal}\n"

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_status(message):
    tasks = get_user_tasks(message.chat.id, include_completed=False)
    task_count = len(tasks)

    msg = ("📊 *System Status*\n\n"
           "⏰ IST: {ist}\n"
           "👤 Chat: {chat}\n"
           "🏋️ Workout: {workout}\n"
           "📝 Pending Tasks: {tasks}\n"
           "🔄 Scheduler: {scheduler}\n"
           "📡 Last Check: {last_check}\n"
           "📨 Last Sent: {last_sent}\n"
           "❌ Errors: {errors}\n").format(
               ist=get_ist_display(),
               chat=active_chat_id or 'None',
               workout='✅ Done today' if workout_done_today else '❌ Pending',
               tasks=task_count,
               scheduler='✅ Running' if scheduler_status['is_running'] else '❌ Stopped',
               last_check=scheduler_status['last_check'] or 'Never',
               last_sent=scheduler_status['last_sent'] or 'None',
               errors=scheduler_status['error_count']
           )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_time(message):
    ist_now = get_ist_time()
    current_time = ist_now.strftime("%H:%M")

    msg = ("🇮🇳 *Current Time*\n\n"
           "⏰ {display}\n"
           "📅 {date}\n"
           "🏋️ Workout: {workout}\n\n"
           "*Upcoming Today:*\n").format(
               display=get_ist_display(),
               date=ist_now.strftime('%d %B %Y, %A'),
               workout='✅ Done' if workout_done_today else '❌ Pending'
           )

    for meal, time_str in sorted(meal_schedule.items(), key=lambda x: x[1]):
        if time_str > current_time:
            time_obj = datetime.datetime.strptime(time_str, "%H:%M")
            msg += "• {time} - {meal}\n".format(
                time=time_obj.strftime('%I:%M %p'),
                meal=meal.replace('_', ' ').title()
            )

    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_test(message):
    if not active_chat_id:
        bot.reply_to(message, "⚠️ Send /start first!")
        return
    bot.reply_to(message, "🧪 Sending test water reminder...")
    time.sleep(1)
    message_text = get_water_reminder()
    bot.send_message(message.chat.id, message_text, parse_mode="Markdown")

def handle_trigger(message):
    if not active_chat_id:
        bot.reply_to(message, "⚠️ Send /start first!")
        return

    if not message.text:
        return

    parts = message.text.split()
    if len(parts) < 2:
        msg = "Usage: /trigger [meal]\n\nAvailable:\n"
        for meal in meal_schedule.keys():
            msg += f"• {meal}\n"
        bot.reply_to(message, msg)
        return

    meal = parts[1]
    if meal in meal_schedule:
        bot.reply_to(message, f"🔧 Triggering: {meal}")
        send_meal_reminder(active_chat_id, meal)
    else:
        bot.reply_to(message, f"❌ Unknown meal: {meal}")

def handle_chat(message):
    global workout_done_today

    if not message.text:
        return

    user_text = message.text.strip()
    user_lower = user_text.lower()

    workout_keywords = ['workout done', 'exercise done', 'finished workout', 'completed workout', 'gym done', 'training done']
    if user_lower in workout_keywords:
        workout_done_today = True
        bot.reply_to(message, 
            "✅ *Excellent! Workout logged!*\n\n"
            "That's what consistency looks like! 💪\n\n"
            "Tomorrow at 7:00 AM - let's keep the momentum going!\n\n"
            "Regular workouts like this WILL break your plateau!", 
            parse_mode="Markdown")
        print(f"✅ [{get_ist_display()}] Workout marked as done by user {message.chat.id}")
        return

    reminder_triggers = ['remind me', 'reminder', 'remember to', 'don\'t forget']
    if any(trigger in user_lower for trigger in reminder_triggers):
        task_desc, target_time = parse_reminder_request(user_text)

        if task_desc and target_time:
            ist_now = datetime.datetime.now(IST)
print(f"🕐 DEBUG: Current IST: {ist_now}, Target: {target_time}")  # Debug log
if target_time <= ist_now:
                bot.reply_to(message,
                    "⚠️ That time is in the past!\n\n"
                    "Please specify a future time.\n\n"
                    "Examples:\n"
                    "• Remind me at 5 PM today\n"
                    "• Remind me tomorrow at 10 AM\n"
                    "• Remind me on December 5 at 3 PM")
                return

            task_id = add_task(message.chat.id, task_desc, target_time)

            if task_id:
    ist_now = datetime.datetime.now(IST)
    time_until_task = (target_time - ist_now).total_seconds() / 60  # minutes
    
    reminder_time = target_time - datetime.timedelta(hours=1)
    followup_time = target_time + datetime.timedelta(minutes=15)
    
    if time_until_task < 60:
        # Immediate reminder case
        bot.reply_to(message,
            f"✅ *Task Reminder Set!*\n\n"
            f"📋 Task: {task_desc}\n\n"
            f"⏰ Scheduled for: {target_time.strftime('%I:%M %p on %B %d, %Y')}\n\n"
            f"🚨 Immediate reminder sent (less than 1 hour away)!\n"
            f"📨 Follow-up at: {followup_time.strftime('%I:%M %p')}\n\n"
            f"Use /tasks to see all your tasks! 📝",
            parse_mode="Markdown")
    else:
        # Normal case
        bot.reply_to(message,
            f"✅ *Task Reminder Set!*\n\n"
            f"📋 Task: {task_desc}\n\n"
            f"⏰ Scheduled for: {target_time.strftime('%I:%M %p on %B %d, %Y')}\n\n"
            f"I'll remind you:\n"
            f"• 1 hour before: {reminder_time.strftime('%I:%M %p')}\n"
            f"• Follow-up: {followup_time.strftime('%I:%M %p')}\n\n"
            f"Use /tasks to see all your tasks! 📝",
            parse_mode="Markdown")
    
    print(f"✅ Added task {task_id} for user {message.chat.id}: {task_desc} at {target_time}")
                print(f"✅ Added task {task_id} for user {message.chat.id}: {task_desc} at {target_time}")
            else:
                bot.reply_to(message, "❌ Sorry, couldn't save your task. Please try again!")
        else:
            bot.reply_to(message,
                "🤔 I couldn't understand that reminder.\n\n"
                "Try these formats:\n"
                "• Remind me to call doctor at 5 PM\n"
                "• Remind me to send report tomorrow at 3 PM\n"
                "• Remind me to check email on Dec 5 at 10 AM\n\n"
                "Be specific about the time!")
        return

    if len(user_text) <= 3 and not any(word in user_lower for word in ['hi', 'hey', 'yes', 'no', 'ok', 'hmm']):
        bot.reply_to(message,
            "I'm not sure what you mean by that! 😊\n\n"
            "You can:\n"
            "• Ask nutrition questions\n"
            "• Set task reminders\n"
            "• Say 'workout done' after workouts\n\n"
            "I'm here to help!")
        return

    SYSTEM_PROMPT = """**CRITICAL: ALWAYS RESPOND IN ENGLISH ONLY**
- If user writes in Hinglish (romanized Hindi like 'kya mai khana chahiye'), understand it and respond in English
- Never use Devanagari (हिंदी) or any non-English script
- Keep all responses in simple English

You are a supportive but direct Indian vegetarian nutritionist helping a 33-year-old male client reach his goal of 74kg from 84kg. He's been stuck at a plateau for 1.5 years.


CLIENT CONTEXT:
- Lives with wife and 2 kids (elder is 5 years old)
- North Indian Baniya family - joint meals, no separate cooking
- Height: 5'8" | Current: 84kg | Target: 74kg
- Exercises: HIIT + weights 6 days/week at 8:30 AM IST

TYPICAL FAMILY MEALS:
- Breakfast: Dry sabzi (often potato-based) + multigrain roti
- Lunch: Wet sabzi/dal/rajma/chole + multigrain roti
- Evening/Dinner: Stuffed wheat roti (aloo paratha, gobi paratha, etc.)

KEY CHALLENGES:
1. Large sabzi portions (1.5 bowls instead of 1 cup)
2. Heavy ghee in cooking (family preference)
3. Paneer dishes frequently
4. Water during meals (poor habit)
5. Namkeen at 4:30 PM (2-4 spoons daily - his weak time!)
6. Fast food 3 times per week
7. Strong night cravings around 9 PM
8. Dal only 2-3 times per week (needs more protein)

YOUR COACHING STYLE:
- Be direct and clear, but supportive and understanding
- Acknowledge family meal challenges (he can't control cooking)
- Focus on PORTION CONTROL - he can control HIS plate
- Give specific measurements (cups, palm size, pieces)
- Show empathy - living with family is tough for dieting
- Be encouraging but honest about what's holding him back
- Offer practical compromises between ideal and realistic

RESPONSE GUIDELINES:
- Keep it brief (2-4 sentences for simple questions, longer for complex)
- Always give EXACT portions, not vague advice
- When he asks about family meals, give portions for THAT meal
- If he's making excuses, gently call it out but stay supportive
- Celebrate small wins, but keep pushing toward the goal
- Focus on sustainable changes, not perfection"""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": user_text}
            ],
            max_tokens=500,
            temperature=0.7
        )
        reply = completion.choices[0].message.content
        if reply:
            bot.send_message(message.chat.id, reply, parse_mode="Markdown")
    except Exception as e:
        bot.reply_to(message, f"⚠️ Error: {e}")

# ==========================================
# FLASK SERVER
# ==========================================
app = Flask('')

@app.route('/')
def home():
    tasks_count = len(get_user_tasks(active_chat_id, include_completed=False)) if active_chat_id else 0
    html = ("<h1>🇮🇳 Health & Task Bot Running</h1>"
            "<p>IST: {ist}</p>"
            "<p>Chat ID: {chat}</p>"
            "<p>Workout Today: {workout}</p>"
            "<p>Pending Tasks: {tasks}</p>"
            "<p>Scheduler: {scheduler}</p>").format(
                ist=get_ist_display(),
                chat=active_chat_id or 'None',
                workout='✅ Done' if workout_done_today else '❌ Pending',
                tasks=tasks_count,
                scheduler='Running' if scheduler_status['is_running'] else 'Stopped'
            )
    return html

@app.route('/ping')
def ping():
    tasks_count = len(get_user_tasks(active_chat_id, include_completed=False)) if active_chat_id else 0
    return {
        "status": "alive",
        "time": get_ist_display(),
        "workout_done": workout_done_today,
        "pending_tasks": tasks_count
    }

@app.route('/health')
def health():
    return {"status": "ok"}, 200

# ==========================================
# START SEQUENCE
# ==========================================
def start_bot():
    import time
    time.sleep(5)
    print("✅ Starting Telegram bot...")
    bot.infinity_polling()

if __name__ == '__main__':
    print("="*60)
    print("🇮🇳 BOT STARTING")
    print(f"⏰ IST: {get_ist_display()}")
    print(f"👤 Chat: {active_chat_id or 'None'}")
    print("="*60)

    Thread(target=start_bot, daemon=True).start()

    port = int(os.getenv("PORT", 8080))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port)
