import datetime
from telegram import Update, ReplyKeyboardMarkup
from telegram.ext import ApplicationBuilder, CommandHandler, MessageHandler, filters, ContextTypes
import pandas as pd
import os

buttons = [
    ["VỆ SINH 10P", "VỆ SINH 15P"],
    ["🔙 ĐÃ QUAY LẠI"]
]
keyboard = ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

time_limits = {
    "VỆ SINH 10P": 10,
    "VỆ SINH 15P": 15
}

max_counts = {
    "VỆ SINH 10P": 5,
    "VỆ SINH 15P": 1
}

data_store = {}

def format_duration(minutes):
    seconds = int(minutes * 60)
    return str(datetime.timedelta(seconds=seconds))

def format_seconds(seconds):
    seconds = int(round(seconds))
    minutes, sec = divmod(seconds, 60)
    return f"{minutes} phút {sec} giây" if minutes else f"{sec} giây"

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chào bạn! Vui lòng nhập tên của bạn để bắt đầu.",
        reply_markup=keyboard
    )

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id
    text = update.message.text.strip()

    if chat_id not in data_store:
        data_store[chat_id] = {}

    if text not in sum(buttons, []) and len(text) >= 1:
        context.user_data['current_name'] = text.upper()
        name = context.user_data['current_name']
        if name not in data_store[chat_id]:
            data_store[chat_id][name] = {"actions": {}}
        await update.message.reply_text(
            f"Chào {name}! Bạn có thể chọn mục bên dưới để bắt đầu.",
            reply_markup=keyboard
        )
        return

    if 'current_name' not in context.user_data:
        await update.message.reply_text("Vui lòng nhập tên trước khi thao tác.", reply_markup=keyboard)
        return

    name = context.user_data['current_name']
    user_data = data_store[chat_id][name]

    now = datetime.datetime.now()

    if text == "🔙 ĐÃ QUAY LẠI":
        msg = f"🔚 {name} đã kết thúc. Thống kê:\n"
        for action, info in user_data["actions"].items():
            if info.get("start_time") is not None:
                # Cập nhật thời gian còn dang dở
                duration_sec = (now - info["start_time"]).total_seconds()
                info["last_duration"] = duration_sec
                info["durations"].append(duration_sec)
                info["total_time"] += duration_sec
                info["start_time"] = None

            count = info.get("count", 0)
            total_time = info.get("total_time", 0)
            last_duration = info.get("last_duration", 0)

            warn = []
            max_count = max_counts.get(action)
            max_time = time_limits.get(action)
            if max_count is not None and count > max_count:
                warn.append(f"vượt số lần ({count}/{max_count})")
            if max_time is not None and total_time > max_time * 60 * count:
                warn.append(f"vượt thời gian ({format_seconds(total_time)})")

            warning_text = " ⚠️ " + ", ".join(warn) if warn else ""

            msg += (
                f"- {action} lần này là: {format_seconds(last_duration)}\n"
                f"  Tổng thời gian đã sử dụng: {format_seconds(total_time)} ({count} lần){warning_text}\n"
            )

        await update.message.reply_text(msg, reply_markup=keyboard)
        return

    if text in sum(buttons, []):
        action = text
        now = datetime.datetime.now()

        if action not in user_data["actions"]:
            user_data["actions"][action] = {
                "count": 0,
                "total_time": 0.0,
                "start_time": None,
                "last_duration": 0.0,
                "durations": []
            }

        info = user_data["actions"][action]

        # Nếu đã đang thực hiện hành động này
        if info["start_time"] is not None:
            elapsed_sec = (now - info["start_time"]).total_seconds()
            start_str = info["start_time"].strftime("%H:%M:%S")
            await update.message.reply_text(
                f"⚠️ Bạn đang thực hiện {action} từ {start_str}, đã được {format_seconds(elapsed_sec)}.",
                reply_markup=keyboard
            )
            return

        # Nếu vượt quá số lần
        if max_counts.get(action) is not None and info["count"] >= max_counts[action]:
            await update.message.reply_text(
                f"⚠️ Bạn đã vượt số lần tối đa cho {action}.",
                reply_markup=keyboard
            )
            return

        info["count"] += 1
        info["start_time"] = now

        msg = f"{name} đã bắt đầu {action} lúc {now.strftime('%H:%M:%S')}."
        max_time = time_limits.get(action)
        if max_time:
            msg += f" Giới hạn {max_time} phút mỗi lần."

        await update.message.reply_text(msg, reply_markup=keyboard)
        return

    await update.message.reply_text(
        "Vui lòng nhập tên nếu chưa có hoặc chọn mục bên dưới.",
        reply_markup=keyboard
    )

async def export_data(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = update.effective_chat.id

    if chat_id not in data_store or not data_store[chat_id]:
        await update.message.reply_text("Không có dữ liệu để xuất.")
        return

    rows = []
    now = datetime.datetime.now()

    for name, user_data in data_store[chat_id].items():
        for action, info in user_data.get("actions", {}).items():
            # Nếu vẫn đang thực hiện, cập nhật thêm thời gian
            if info.get("start_time") is not None:
                duration_sec = (now - info["start_time"]).total_seconds()
                info["last_duration"] = duration_sec
                info["durations"].append(duration_sec)
                info["total_time"] += duration_sec
                info["start_time"] = None

            count = info.get("count", 0)
            total_time = info.get("total_time", 0)
            durations = [format_seconds(d) for d in info.get("durations", [])]
            rows.append({
                "Tên nhân viên": name,
                "Hành động": action,
                "Số lần": count,
                "Tổng thời gian (phút)": round(total_time / 60, 1),
                "Tổng thời gian chi tiết": format_seconds(total_time),
                "Danh sách thời gian từng lần (hh:mm:ss)": ", ".join(durations)
            })

    if not rows:
        await update.message.reply_text("Không có dữ liệu chi tiết để xuất.")
        return

    df = pd.DataFrame(rows)
    filename = f"data_{chat_id}_{datetime.datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False)

    with open(filename, "rb") as f:
        await update.message.reply_document(f)

    os.remove(filename)
    data_store[chat_id] = {}

    await update.message.reply_text("✅ Đã xuất dữ liệu và reset lại thống kê nhóm.")

if __name__ == "__main__":
    import logging
    from telegram.ext import Application

    logging.basicConfig(
        format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
        level=logging.INFO
    )

    TOKEN = "7842867457:AAHwUVSHYYPGOd94LJzUxM9JvxImRY7fU6Y"

    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("export", export_data))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, handle_message))

    print("Bot đã chạy...")
    app.run_polling()
