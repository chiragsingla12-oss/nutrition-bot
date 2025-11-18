import os
import time
import threading
import telebot
import datetime
import pytz
from openai import OpenAI
from flask import Flask
from threading import Thread

# ==========================================
# CONFIGURATION
# ==========================================
TELEGRAM_TOKEN = os.getenv("TELEGRAM_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")

# Validate environment variables
if not TELEGRAM_TOKEN:
    raise ValueError("TELEGRAM_TOKEN not found in environment variables!")
if not OPENAI_API_KEY:
    raise ValueError("OPENAI_API_KEY not found in environment variables!")

bot = telebot.TeleBot(TELEGRAM_TOKEN, parse_mode=None)
client = OpenAI(api_key=OPENAI_API_KEY)

IST = pytz.timezone('Asia/Kolkata')
CHAT_ID_FILE = "/tmp/chat_id.txt"
active_chat_id = None

scheduler_status = {
    "last_check": None,
    "last_sent": None,
    "is_running": False,
    "error_count": 0
}

meal_schedule = {
    "morning_routine": "08:00",
    "post_workout": "08:30",
    "breakfast": "08:45",
    "midday_hydration": "11:00",
    "lunch": "13:00",
    "snack": "16:30",
    "dinner": "18:30",
    "night_craving": "21:00"
}

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

def get_food_options(meal):
    options_map = {
        "morning_routine": [
            "💧 Warm water/lemon water/ajwain-jeera water",
            "🏋️ Pre-workout: Banana/almonds (if needed)"
        ],
        "post_workout": ["💪 Fruit/almonds/coconut/roasted chana"],
        "breakfast": [
            "🥘 Moong dal chilla/Besan chilla/Poha/Upma/Idli",
            "💪 Paneer bhurji (small)/Greek yogurt",
            "⚡ Toast + peanut butter/Banana + almonds"
        ],
        "midday_hydration": ["💧 Water/Coconut water/Lemonade (no sugar)"],
        "lunch": [
            "📋 BASE: 2 rotis / 1 roti + ½ rice / 1 bowl rice",
            "🥘 SABZI: Lauki/Tinda/Bhindi/Beans/Mix veg",
            "⚠️ ONLY 1 SMALL BOWL SABZI!",
            "💪 PROTEIN: Dal/Rajma/Chole/Curd (MANDATORY)",
            "🥗 SALAD: Cucumber/carrot/sprouts (FIRST!)"
        ],
        "snack": [
            "🥜 Roasted chana/Makhana/Peanut chaat",
            "🍎 Apple/Pomegranate/Banana",
            "💪 Paneer cubes/Sprouts",
            "⚠️ IF CRAVING NAMKEEN: Mix roasted chana + murmura + peanuts"
        ],
        "dinner": [
            "🌙 LIGHT: Moong dal khichdi/Daliya/1 roti + dal",
            "💪 Paneer bhurji/Tofu/Moong dal + veg",
            "✨ VERY LIGHT: Soup/Khichdi + curd"
        ],
        "night_craving": [
            "🍵 Warm drinks: Ajwain-jeera-haldi/Lemon/Cinnamon water",
            "🥜 Makhana/Roasted chana/6-8 almonds/Khakhra",
            "🍯 Sweet: Small jaggery/Warm milk + cinnamon",
            "🚫 AVOID: Namkeen/Biscuits/Apple/Fried snacks"
        ]
    }
    return options_map.get(meal, ["Options not found"])

def send_meal_reminder(chat_id, meal):
    global scheduler_status
    try:
        options = get_food_options(meal)
        current_time = get_ist_display()

        titles = {
            "morning_routine": "🌅 GOOD MORNING!",
            "post_workout": "💪 Post-Workout Recovery",
            "breakfast": "🍳 Breakfast Time!",
            "midday_hydration": "💧 Midday Check-in!",
            "lunch": "🍽️ Lunch Time!",
            "snack": "☕ Evening Snack! ⚠️ NAMKEEN TIME",
            "dinner": "🌆 Dinner Time!",
            "night_craving": "🌙 Night Craving Alert! ⚠️"
        }

        message = "*{title}*\n⏰ {time}\n\n".format(
            title=titles.get(meal, meal),
            time=current_time
        )
        for item in options:
            message += f"{item}\n"

        if meal in ["lunch", "dinner"]:
            message += "\n💡 Walk 5-10 mins after eating!"
        elif meal == "snack":
            message += "\n🎯 Stay strong - YOUR weak time!"
        elif meal == "night_craving":
            message += "\n✅ Choose wisely = Wake lighter tomorrow!"

        bot.send_message(chat_id, message, parse_mode="Markdown")
        scheduler_status["last_sent"] = "{meal} at {time}".format(meal=meal, time=current_time)
        print(f"✅ [{current_time}] Sent {meal} to {chat_id}")
        return True
    except Exception as e:
        scheduler_status["error_count"] += 1
        print(f"❌ [{get_ist_display()}] Error sending {meal}: {e}")
        return False

# ==========================================
# SCHEDULER
# ==========================================
def scheduler():
    global scheduler_status
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
# SINGLE MESSAGE HANDLER
# ==========================================

@bot.message_handler(func=lambda message: True)
def handle_all_messages(message):
    """Single handler that routes all messages"""

    if not message.text:
        return

    text = message.text
    chat_id = message.chat.id

    print(f"📨 Received: '{text}' from {chat_id}")

    # Route to appropriate handler
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
    elif text.startswith('/trigger'):
        handle_trigger(message)
    elif text.startswith('/'):
        bot.reply_to(message, "❌ Unknown command! Try /start /debug /status /time /test")
    else:
        handle_chat(message)

# ==========================================
# COMMAND HANDLERS
# ==========================================

def handle_start(message):
    save_chat_id(message.chat.id)
    msg = ("🙏 *Namaste! Your Nutrition Coach!*\n\n"
           "🇮🇳 Activated: {time}\n"
           "👤 Chat ID: {chat_id}\n\n"
           "✅ *Profile:* 84→74kg, Plateau 1.5yr\n\n"
           "🔔 *IST Schedule:*\n"
           "• 08:00 - Morning routine\n"
           "• 08:30 - Post-workout\n"
           "• 08:45 - Breakfast\n"
           "• 11:00 - Midday check\n"
           "• 13:00 - Lunch\n"
           "• 16:30 - Snack ⚠️\n"
           "• 18:30 - Dinner\n"
           "• 21:00 - Night craving ⚠️\n\n"
           "💬 *Commands:*\n"
           "/time /status /debug /test /trigger\n\n"
           "Let's break that plateau! 💪").format(
               time=get_ist_display(),
               chat_id=message.chat.id
           )
    bot.send_message(message.chat.id, msg, parse_mode="Markdown")

def handle_debug(message):
    ist_now = get_ist_time()
    current_time = ist_now.strftime("%H:%M")

    msg = ("🔍 *Debug Information*\n\n"
           "⏰ Current IST: {ist}\n"
           "🕐 Time String: {time_str}\n"
           "👤 Your Chat ID: {your_id}\n"
           "💾 Stored Chat ID: {stored_id}\n"
           "✅ Match: {match}\n\n"
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
    msg = ("📊 *System Status*\n\n"
           "⏰ IST: {ist}\n"
           "👤 Chat: {chat}\n"
           "🔄 Scheduler: {scheduler}\n"
           "📡 Last Check: {last_check}\n"
           "📨 Last Sent: {last_sent}\n"
           "❌ Errors: {errors}\n").format(
               ist=get_ist_display(),
               chat=active_chat_id or 'None',
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
           "📅 {date}\n\n"
           "*Upcoming Today:*\n").format(
               display=get_ist_display(),
               date=ist_now.strftime('%d %B %Y, %A')
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
    bot.reply_to(message, "🧪 Sending test reminder...")
    time.sleep(1)
    send_meal_reminder(message.chat.id, "night_craving")

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
    """Regular AI chat"""
    if not message.text:
        return

    SYSTEM_PROMPT = """You are a direct Indian nutritionist coaching a 33yo male: 84kg→74kg goal, stuck 1.5yr. North Indian veg, family eats potato/paneer heavy. Issues: Large sabzi+ghee, water during meals, namkeen at 4:30PM, fast food 3x/week. Exercise: HIIT+weights 6days/week at 8:30AM IST. Be DIRECT (2-4 sentences), give EXACT portions, focus PORTION CONTROL."""

    try:
        completion = client.chat.completions.create(
            model="gpt-4o-mini",
            messages=[
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": message.text}
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
# FLASK SERVER (Must start FIRST for Render)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    html = ("<h1>🇮🇳 Bot Running</h1>"
            "<p>IST: {ist}</p>"
            "<p>Chat ID: {chat}</p>"
            "<p>Scheduler: {scheduler}</p>").format(
                ist=get_ist_display(),
                chat=active_chat_id or 'None',
                scheduler='Running' if scheduler_status['is_running'] else 'Stopped'
            )
    return html

@app.route('/ping')
def ping():
    return {"status": "alive", "time": get_ist_display()}

@app.route('/health')
def health():
    # Quick health check for Render
    return {"status": "ok"}, 200

# ==========================================
# START SEQUENCE (Flask first, then bot)
# ==========================================
def start_bot():
    """Start Telegram bot in background after Flask is ready"""
    import time
    time.sleep(5)  # Wait for Flask to be ready
    print("✅ Starting Telegram bot...")
    bot.infinity_polling()

if __name__ == '__main__':
    print("="*60)
    print("🇮🇳 BOT STARTING")
    print(f"⏰ IST: {get_ist_display()}")
    print(f"👤 Chat: {active_chat_id or 'None'}")
    print("="*60)
    
    # Start bot in background thread
    Thread(target=start_bot, daemon=True).start()
    
    # Start Flask in MAIN thread (Render needs this)
    port = int(os.getenv("PORT", 8080))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port)

bot.infinity_polling()
