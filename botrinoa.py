import os
import datetime
import logging
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pandas as pd

# Logger setup
def setup_logger():
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    return logging.getLogger(__name__)

logger = setup_logger()

# Keyboard buttons
buttons = [
    ["VỆ SINH 10P", "VỆ SINH 15P"],
    ["🔙 ĐÃ QUAY LẠI"]
]
keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

# Limits
time_limits = {"VỆ SINH 10P": 10, "VỆ SINH 15P": 15}
max_counts = {"VỆ SINH 10P": 5, "VỆ SINH 15P": 1}

# In-memory data storage: {chat_id: {name: {actions: {...}}}}
data_store = {}

# Utils
def format_seconds(seconds):
    seconds = int(round(seconds))
    minutes, sec = divmod(seconds, 60)
    return f"{minutes} phút {sec} giây" if minutes else f"{sec} giây"

# Error handler
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE) -> None:
    logger.error(f'Update "{update}" gây lỗi "{context.error}"', exc_info=True)

# Handlers
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chào bạn! Vui lòng nhập tên của bạn để bắt đầu.",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    # Ensure chat dict
    user_dict = data_store.setdefault(chat_id, {})
    all_buttons = [b for row in buttons for b in row]

    # If input is a name (not a button)
    if text not in all_buttons and len(text) >= 1:
        name = text.upper()
        context.user_data['current_name'] = name
        user_dict.setdefault(name, {"actions": {}})
        await update.message.reply_text(
            f"Chào {name}! Bạn có thể chọn mục bên dưới để bắt đầu.",
            reply_markup=keyboard
        )
        return

    # Must have a name chosen
    if 'current_name' not in context.user_data:
        await update.message.reply_text(
            "Vui lòng nhập tên trước khi thao tác.", reply_markup=keyboard
        )
        return

    # Ensure name dict exists
    name = context.user_data['current_name']
    user_data = user_dict.setdefault(name, {"actions": {}})

    now = datetime.datetime.now()

    # "🔙 ĐÃ QUAY LẠI" action
    if text == "🔙 ĐÃ QUAY LẠI":
        msg = f"🔚 {name} đã kết thúc. Thống kê:\n"
        for action, info in user_data["actions"].items():
            if info.get("start_time") is not None:
                duration = (now - info["start_time"]).total_seconds()
                info.setdefault("durations", []).append(duration)
                info["total_time"] = info.get("total_time", 0) + duration
                info["last_duration"] = duration
                info["start_time"] = None

            count = info.get("count", 0)
            total_time = info.get("total_time", 0)
            last_duration = info.get("last_duration", 0)

            warn = []
            if count > max_counts.get(action, count):
                warn.append(f"vượt số lần ({count}/{max_counts[action]})")
            if total_time > time_limits.get(action, 0) * 60 * count:
                warn.append(f"vượt thời gian ({format_seconds(total_time)})")

            warning_text = " ⚠️ " + ", ".join(warn) if warn else ""
            msg += (
                f"- {action} lần này: {format_seconds(last_duration)}\n"
                f"  Tổng thời gian: {format_seconds(total_time)} ({count} lần){warning_text}\n"
            )

        await update.message.reply_text(msg, reply_markup=keyboard)
        return

    # If action button pressed
    if text in all_buttons:
        action = text
        info = user_data["actions"].setdefault(action, {
            "count": 0,
            "total_time": 0.0,
            "start_time": None,
            "last_duration": 0
        })

        if info["start_time"] is not None:
            elapsed = (now - info["start_time"]).total_seconds()
            await update.message.reply_text(
                f"⚠️ Bạn đang thực hiện {action}, đã {format_seconds(elapsed)}.",
                reply_markup=keyboard
            )
            return

        if info["count"] >= max_counts.get(action, float('inf')):
            await update.message.reply_text(
                f"⚠️ Bạn đã vượt số lần tối đa cho {action}.",
                reply_markup=keyboard
            )
            return

        info["count"] += 1
        info["start_time"] = now
        msg = f"{name} đã bắt đầu {action} lúc {now.strftime('%H:%M:%S')}"
        if action in time_limits:
            msg += f" (Giới hạn {time_limits[action]} phút mỗi lần)."
        await update.message.reply_text(msg, reply_markup=keyboard)
        return

    # Default fallback
    await update.message.reply_text(
        "Vui lòng nhập tên nếu chưa có hoặc chọn mục bên dưới.",
        reply_markup=keyboard
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    user_dict = data_store.get(chat_id, {})
    rows = []
    now = datetime.datetime.now()

    for name, user_data in user_dict.items():
        for action, info in user_data.get("actions", {}).items():
            if info.get("start_time") is not None:
                duration = (now - info["start_time"]).total_seconds()
                info.setdefault("durations", []).append(duration)
                info["total_time"] += duration
                info["last_duration"] = duration
                info["start_time"] = None

            rows.append({
                "Tên nhân viên": name,
                "Hành động": action,
                "Số lần": info.get("count", 0),
                "Tổng thời gian (phút)": round(info.get("total_time", 0) / 60, 1),
                "Thời gian chi tiết": format_seconds(info.get("total_time", 0)),
                "Danh sách (phút:giây)": ", ".join(format_seconds(d) for d in info.get("durations", []))
            })

    if not rows:
        await update.message.reply_text("Không có dữ liệu để xuất.")
        return

    df = pd.DataFrame(rows)
    fname = f"data_{chat_id}_{now.strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(fname, index=False)

    with open(fname, "rb") as f:
        await update.message.reply_document(f)
    os.remove(fname)
    data_store[chat_id] = {}
    await update.message.reply_text("✅ Đã xuất dữ liệu và reset thống kê.")

if __name__ == "__main__":
    # Setup logging
    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )
    logger = logging.getLogger(__name__)

    # Get token from environment
    TOKEN = os.getenv("TOKEN")
    if not TOKEN:
        logger.error("Bot token not found. Please set the TOKEN environment variable.")
        exit(1)

    # Debug first part of token without causing error
    logger.info(f"Using token: {TOKEN[:8] if len(TOKEN) >= 8 else TOKEN}...")

    # Initialize and run bot
    app = ApplicationBuilder().token(TOKEN).build()
    app.add_error_handler(error_handler)
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    logger.info("Bot is starting...")
    app.run_polling()
