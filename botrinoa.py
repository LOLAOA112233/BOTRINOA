import logging
from datetime import datetime
from collections import defaultdict
import pandas as pd

from telegram import Update, ReplyKeyboardMarkup, ReplyKeyboardRemove
from telegram.ext import (
    ApplicationBuilder,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# --- Cấu hình ---
TOKEN = "7842867457:AAHwUVSHYYPGOd94LJzUxM9JvxImRY7fU6Y"
ADMIN_IDS = {7272736801}

# Các hành động và giới hạn
ACTIONS = {
    "VỆ SINH 10P": {"max_count": 5, "max_minutes": 10},
    "VỆ SINH 15P": {"max_count": 1, "max_minutes": 15},
}

END_ACTION = "🔙 ĐÃ QUAY LẠI"

# --- Biến lưu trạng thái và dữ liệu ---
# user_states lưu hành động đang chạy: key=(chat_id,user_id,name)
user_states = dict()
# data_records lưu danh sách hành động đã hoàn thành
data_records = defaultdict(list)

# Lưu tên người dùng đã nhập cho chat+user (để cho phép nhập nhiều tên)
user_names = defaultdict(set)

# --- Hàm tiện ích ---
def seconds_to_hms(seconds: int) -> str:
    h = seconds // 3600
    m = (seconds % 3600) // 60
    s = seconds % 60
    return f"{h}h {m}p {s}s"

def get_keyboard():
    buttons = [[action] for action in ACTIONS.keys()]
    buttons.append([END_ACTION])
    buttons.append(["Đổi tên"])
    return ReplyKeyboardMarkup(buttons, resize_keyboard=True, one_time_keyboard=False)

def format_summary(records):
    if not records:
        return "Chưa có dữ liệu."

    summary = ""
    action_summary = defaultdict(list)
    for action, start, end in records:
        duration = int((end - start).total_seconds())
        action_summary[action].append(duration)

    for action, durations in action_summary.items():
        total_time = seconds_to_hms(sum(durations))
        count = len(durations)
        max_limit = ACTIONS.get(action, {}).get("max_minutes", 0)
        overtime_count = sum(1 for d in durations if d > max_limit * 60)
        summary += (
            f"- {action}: Đã làm {count} lần, tổng thời gian {total_time}. "
            f"Vượt thời gian: {overtime_count} lần.\n"
        )
    return summary

# --- Handlers ---

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Chào bạn! Vui lòng nhập tên của bạn để bắt đầu.",
        reply_markup=ReplyKeyboardRemove()
    )
    context.user_data["awaiting_name"] = True
    context.user_data["current_name"] = None

async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    text = update.message.text.strip()
    chat_id = update.effective_chat.id
    user_id = update.effective_user.id

    if context.user_data.get("awaiting_name", False):
        # Đang chờ nhập tên
        name = text
        if len(name) < 2:
            await update.message.reply_text("Tên phải có ít nhất 2 ký tự. Vui lòng nhập lại.")
            return
        user_names[(chat_id, user_id)].add(name)
        context.user_data["current_name"] = name
        context.user_data["awaiting_name"] = False
        await update.message.reply_text(
            f"Chào {name}! Bây giờ bạn có thể chọn hành động.",
            reply_markup=get_keyboard()
        )
        return

    # Nếu chưa có tên thì bắt buộc nhập tên
    current_name = context.user_data.get("current_name")
    if not current_name:
        await update.message.reply_text("Vui lòng nhập tên trước khi chọn hành động. Gõ tên của bạn vào đây.")
        context.user_data["awaiting_name"] = True
        return

    key = (chat_id, user_id, current_name)

    if text == "Đổi tên":
        context.user_data["awaiting_name"] = True
        context.user_data["current_name"] = None
        await update.message.reply_text("Vui lòng nhập tên mới:", reply_markup=ReplyKeyboardRemove())
        return

    if text == END_ACTION:
        # Kết thúc hành động đang chạy
        state = user_states.get(key)
        if not state:
            await update.message.reply_text(
                "Bạn chưa bắt đầu hành động nào. Vui lòng chọn hành động.",
                reply_markup=get_keyboard()
            )
            return

        start_time = state["start_time"]
        end_time = datetime.now()
        action = state["action"]

        data_records[key].append((action, start_time, end_time))
        del user_states[key]

        summary = format_summary(data_records[key])

        await update.message.reply_text(
            f"Đã kết thúc hành động: {action}.\n\n"
            f"Tổng kết cho {current_name}:\n{summary}",
            reply_markup=get_keyboard()
        )
        return

    if text in ACTIONS:
        # Bắt đầu hành động mới
        if key in user_states:
            await update.message.reply_text(
                f"Bạn đang trong hành động '{user_states[key]['action']}'. Vui lòng kết thúc trước khi bắt đầu hành động mới.",
                reply_markup=get_keyboard()
            )
            return

        # Kiểm tra số lần đã làm
        records = data_records.get(key, [])
        done_count = sum(1 for r in records if r[0] == text)
        max_count = ACTIONS[text]["max_count"]

        if done_count >= max_count:
            await update.message.reply_text(
                f"Bạn đã làm quá số lần cho hành động '{text}' (tối đa {max_count} lần).",
                reply_markup=get_keyboard()
            )
            return

        # Lưu trạng thái bắt đầu
        user_states[key] = {"action": text, "start_time": datetime.now()}

        await update.message.reply_text(
            f"Bắt đầu hành động '{text}' lúc {user_states[key]['start_time'].strftime('%H:%M:%S')}.\n"
            f"Bạn đã làm {done_count} lần trước đó (tối đa {max_count} lần).\n"
            f"Chọn '{END_ACTION}' để kết thúc hành động này.",
            reply_markup=get_keyboard()
        )
        return

    # Nếu không hiểu input
    await update.message.reply_text(
        "Lựa chọn không hợp lệ. Vui lòng nhập tên hoặc chọn hành động bằng nút bên dưới.",
        reply_markup=get_keyboard()
    )

async def export_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    if user_id not in ADMIN_IDS:
        await update.message.reply_text("Bạn không có quyền sử dụng lệnh này.")
        return

    if not data_records:
        await update.message.reply_text("Chưa có dữ liệu để xuất.")
        return

    rows = []
    for (chat_id, user_id, name), records in data_records.items():
        for action, start, end in records:
            duration = int((end - start).total_seconds())
            rows.append({
                "ChatID": chat_id,
                "UserID": user_id,
                "Name": name,
                "Action": action,
                "Start": start.strftime("%Y-%m-%d %H:%M:%S"),
                "End": end.strftime("%Y-%m-%d %H:%M:%S"),
                "Duration(s)": duration,
            })

    df = pd.DataFrame(rows)
    filename = f"export_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
    df.to_excel(filename, index=False)

    with open(filename, "rb") as f:
        await update.message.reply_document(document=f, filename=filename)

async def help_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    await update.message.reply_text(
        "Dùng /start để bắt đầu.\n"
        "Nhập tên, rồi chọn hành động.\n"
        "Chọn '🔙 ĐÃ QUAY LẠI' để kết thúc hành động.\n"
        "Admin dùng /export để xuất file Excel."
    )

def main():
    app = ApplicationBuilder().token(TOKEN).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_handler))
    app.add_handler(CommandHandler("export", export_handler))
    app.add_handler(MessageHandler(filters.TEXT & (~filters.COMMAND), handle_message))

    app.run_polling()

if __name__ == "__main__":
    main()
