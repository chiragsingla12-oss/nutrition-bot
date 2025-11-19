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
workout_done_today = False  # Track if workout completed

scheduler_status = {
    "last_check": None,
    "last_sent": None,
    "is_running": False,
    "error_count": 0
}

# ==========================================
# MEAL SCHEDULE + REMINDERS (IST)
# ==========================================
meal_schedule = {
    "exercise_morning": "07:00",     # 🏋️ Morning workout reminder
    "morning_routine": "08:00",      # 🌅 Hydration + Pre-Workout fuel
    "post_workout": "08:30",         # 💪 Post-Workout Mini Meal
    "breakfast": "08:45",            # 🍳 Breakfast reminder
    "water_1": "10:00",              # 💧 Water reminder 1
    "midday_hydration": "11:00",     # 💧 Midday Hydration + craving check
    "water_2": "12:00",              # 💧 Water reminder 2
    "lunch": "13:00",                # 🍽️ Lunch (1:00 PM)
    "water_3": "14:30",              # 💧 Water reminder 3
    "water_4": "16:00",              # 💧 Water reminder 4
    "snack": "16:30",                # ☕ Evening Snack (4:30 PM)
    "exercise_backup": "17:00",      # 🏋️ Exercise backup (if morning missed)
    "water_5": "18:00",              # 💧 Water reminder 5
    "dinner": "18:30",               # 🍛 Dinner (6:30 PM)
    "water_6": "20:00",              # 💧 Water reminder 6
    "night_craving": "21:00"         # 🌙 Night Craving Control (9:00 PM)
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

def get_water_reminder():
    """Generate water reminder message"""
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
    """Generate exercise reminder message"""
    if time_of_day == "morning":
        return (
            "🏋️ *Morning Workout Time!*\n\n"
            "⏰ 7:00 AM - Perfect time for your workout!\n\n"
            "Today's plan: HIIT + Weights (30-60 min)\n\n"
            "💡 Tips:\n"
            "• Light snack if needed (banana/5-6 almonds)\n"
            "• Drink water before starting\n"
            "• This consistency will help break your plateau!\n\n"
            "✅ Reply 'done' after your workout!"
        )
    else:  # backup evening
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
            "✅ Reply 'done' when finished!"
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
        
        # Handle water reminders
        if meal.startswith("water_"):
            message = get_water_reminder()
            bot.send_message(chat_id, message, parse_mode="Markdown")
            scheduler_status["last_sent"] = f"{meal} at {current_time}"
            print(f"✅ [{current_time}] Sent water reminder to {chat_id}")
            return True
        
        # Handle exercise reminders
        if meal == "exercise_morning":
            message = get_exercise_reminder("morning")
            bot.send_message(chat_id, message, parse_mode="Markdown")
            scheduler_status["last_sent"] = f"{meal} at {current_time}"
            print(f"✅ [{current_time}] Sent morning exercise reminder to {chat_id}")
            return True
        
        if meal == "exercise_backup":
            # Only send if morning workout wasn't done
            if not workout_done_today:
                message = get_exercise_reminder("evening")
                bot.send_message(chat_id, message, parse_mode="Markdown")
                scheduler_status["last_sent"] = f"{meal} at {current_time}"
                print(f"✅ [{current_time}] Sent backup exercise reminder to {chat_id}")
            else:
                print(f"⏭️ [{current_time}] Skipped backup - workout already done today!")
            return True
        
        # Handle regular meal reminders
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

            # Reset at midnight
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
           "🔔 *Daily Schedule (IST):*\n"
           "• 07:00 - Exercise reminder\n"
           "• 08:00 - Morning routine\n"
           "• 08:30 - Post-workout\n"
           "• 08:45 - Breakfast\n"
           "• 10:00, 12:00, 14:30, 16:00, 18:00, 20:00 - Water reminders\n"
           "• 11:00 - Midday check\n"
           "• 13:00 - Lunch\n"
           "• 16:30 - Snack\n"
           "• 17:00 - Exercise backup (if needed)\n"
           "• 18:30 - Dinner\n"
           "• 21:00 - Night craving support\n\n"
           "💬 *Commands:*\n"
           "/time /status /debug /test /trigger\n\n"
           "💪 Let's reach 74kg together!").format(
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
           "✅ Match: {match}\n"
           "🏋️ Workout Today: {workout}\n\n"
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
           "🏋️ Workout: {workout}\n"
           "🔄 Scheduler: {scheduler}\n"
           "📡 Last Check: {last_check}\n"
           "📨 Last Sent: {last_sent}\n"
           "❌ Errors: {errors}\n").format(
               ist=get_ist_display(),
               chat=active_chat_id or 'None',
               workout='✅ Done today' if workout_done_today else '❌ Pending',
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
    """Regular AI chat - with workout tracking and gibberish detection"""
    global workout_done_today
    
    if not message.text:
        return
    
    user_text = message.text.strip()
    
    # Check for workout completion
    workout_keywords = ['done', 'workout done', 'exercise done', 'finished workout', 'completed workout', 'finished', 'completed']
    if user_text.lower() in workout_keywords:
        workout_done_today = True
        bot.reply_to(message, 
            "✅ *Excellent! Workout logged!*\n\n"
            "That's what consistency looks like! 💪\n\n"
            "Tomorrow at 7:00 AM - let's keep the momentum going!\n\n"
            "Regular workouts like this WILL break your plateau!", 
            parse_mode="Markdown")
        print(f"✅ [{get_ist_display()}] Workout marked as done by user {message.chat.id}")
        return
    
    # Detect gibberish (very short, no real content, just symbols/dots)
    if len(user_text) <= 3 and not any(word in user_text.lower() for word in ['hi', 'hey', 'yes', 'no', 'ok', 'hmm']):
        bot.reply_to(message,
            "I'm not sure what you mean by that! 😊\n\n"
            "You can ask me:\n"
            "• Nutrition questions\n"
            "• About specific foods\n"
            "• For portion advice\n"
            "• Help with cravings\n\n"
            "I'm here to help you reach 74kg!")
        return
    
    # AI coaching for real questions
    SYSTEM_PROMPT = """You are a supportive but direct Indian nutritionist helping a 33-year-old male client reach his goal of 74kg from 84kg. He's been stuck at a plateau for 1.5 years.

**CLIENT CONTEXT:**
- Lives with wife and 2 kids (elder is 5 years old)
- North Indian Baniya family - joint meals, no separate cooking
- Height: 5'8" | Current: 84kg | Target: 74kg
- Exercises: HIIT + weights 6 days/week at 8:30 AM IST

**TYPICAL FAMILY MEALS:**
- Breakfast: Dry sabzi (often potato-based) + multigrain roti
- Lunch: Wet sabzi/dal/rajma/chole + multigrain roti
- Evening/Dinner: Stuffed wheat roti (aloo paratha, gobi paratha, etc.)

**KEY CHALLENGES:**
1. Large sabzi portions (1.5 bowls instead of 1 cup)
2. Heavy ghee in cooking (family preference)
3. Paneer dishes frequently
4. Water during meals (poor habit)
5. Namkeen at 4:30 PM (2-4 spoons daily - his weak time!)
6. Fast food 3 times per week
7. Strong night cravings around 9 PM
8. Dal only 2-3 times per week (needs more protein)

**YOUR COACHING STYLE:**
- Be direct and clear, but supportive and understanding
- Acknowledge family meal challenges (he can't control cooking)
- Focus on PORTION CONTROL - he can control HIS plate
- Give specific measurements (cups, palm size, pieces)
- Show empathy - living with family is tough for dieting
- Be encouraging but honest about what's holding him back
- Offer practical compromises between ideal and realistic

**RESPONSE GUIDELINES:**
- Keep it brief (2-4 sentences for simple questions, longer for complex)
- Always give EXACT portions, not vague advice
- When he asks about family meals, give portions for THAT meal
- If he's making excuses, gently call it out but stay supportive
- Celebrate small wins, but keep pushing toward the goal
- Focus on sustainable changes, not perfection

**EXAMPLES:**

User: "Can I eat aloo sabzi for breakfast?"
You: "Yes, but keep it to 4-5 pieces max and 2 multigrain rotis. Add a small bowl of curd or sprouts on the side for protein - this keeps you full longer. The potato itself isn't the enemy; overeating it is!"

User: "Why am I not losing weight?"
You: "Let's be honest - if you're eating 1.5 bowls of sabzi with heavy ghee (that's 300+ extra calories), namkeen daily (150 cal), and fast food 3x/week (1500 cal weekly), you're consuming 3000+ extra calories per week. That equals 0.4kg weight GAIN monthly. The solution? Cut your sabzi portion to 1 cup, skip the namkeen or replace with roasted chana, and reduce fast food to once weekly. These three changes alone can get you losing again!"

User: "Family is making paneer tonight"
You: "Paneer is fine! Your rule: 50-60g max (palm-sized portion). Take 2 rotis, small bowl of paneer sabzi, and load up on salad first. Ask for light ghee if you can, but if not, just control YOUR portion. You can enjoy family meals AND lose weight!"

User: "I ate namkeen at 4:30 PM again"
You: "That's your challenging time, I know! Here's the thing - 4 spoons of namkeen = 150 calories = 16kg yearly gain if daily. Tomorrow, try this: 1 spoon namkeen mixed with 2-3 spoons roasted chana. You get the taste but half the damage. Small switches like this add up to big results!"

**IMPORTANT:**
- Never make him feel guilty - he's trying his best in a tough situation
- Always acknowledge family meal constraints
- Offer practical solutions he can actually implement
- Show him the math so he understands WHY changes matter
- Be his ally, not his critic"""

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
# FLASK SERVER (Must start FIRST for Render)
# ==========================================
app = Flask('')

@app.route('/')
def home():
    html = ("<h1>🇮🇳 Nutrition Bot Running</h1>"
            "<p>IST: {ist}</p>"
            "<p>Chat ID: {chat}</p>"
            "<p>Workout Today: {workout}</p>"
            "<p>Scheduler: {scheduler}</p>").format(
                ist=get_ist_display(),
                chat=active_chat_id or 'None',
                workout='✅ Done' if workout_done_today else '❌ Pending',
                scheduler='Running' if scheduler_status['is_running'] else 'Stopped'
            )
    return html

@app.route('/ping')
def ping():
    return {"status": "alive", "time": get_ist_display(), "workout_done": workout_done_today}

@app.route('/health')
def health():
    return {"status": "ok"}, 200

# ==========================================
# START SEQUENCE (Flask first, then bot)
# ==========================================
def start_bot():
    """Start Telegram bot in background after Flask is ready"""
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
    
    # Start bot in background thread
    Thread(target=start_bot, daemon=True).start()
    
    # Start Flask in MAIN thread (Render needs this)
    port = int(os.getenv("PORT", 8080))
    print(f"🌐 Starting Flask on port {port}")
    app.run(host='0.0.0.0', port=port)
