import os
import cv2
import random
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import Updater, MessageHandler, Filters, CallbackContext, CommandHandler, CallbackQueryHandler
from concurrent.futures import ThreadPoolExecutor, wait
from mtcnn.mtcnn import MTCNN

TOKEN = os.environ['TELEGRAM_BOT_TOKEN']
MAX_THREADS = 5
PIXELATION_FACTOR = 0.03
LIOTTA_RESIZE_FACTOR = 1.5
SKULL_RESIZE_FACTOR = 1.9  # Adjust the resize factor for Skull of Satoshi
CATS_RESIZE_FACTOR = 1.5  # Adjust the resize factor for cats

def start(update: Update, context: CallbackContext) -> None:
    update.message.reply_text('Send me a picture, and I will pixelate faces in it!')

def detect_heads(image):
    mtcnn = MTCNN()
    faces = mtcnn.detect_faces(image)
    head_boxes = [(face['box'][0], face['box'][1], int(LIOTTA_RESIZE_FACTOR * face['box'][2]), int(LIOTTA_RESIZE_FACTOR * face['box'][3])) for face in faces]
    return head_boxes

def pixelate_faces(update: Update, context: CallbackContext) -> None:
    chat_type = update.message.chat.type
    if chat_type in ['group', 'supergroup']:
        context.bot.send_message(
            chat_id=update.message.chat_id,
            text="To process your image, please send it to me in a private message (DM)."
        )
        return

    file_id = update.message.photo[-1].file_id
    file = context.bot.get_file(file_id)
    file_name = file.file_path.split('/')[-1]
    photo_path = f"downloads/{file_name}"
    file.download(photo_path)

    keyboard = [
        [InlineKeyboardButton("Pixelate", callback_data='pixelate')],
        [InlineKeyboardButton("Liotta Overlay", callback_data='liotta')],
        [InlineKeyboardButton("Skull of Satoshi", callback_data='skull_of_satoshi')],
        [InlineKeyboardButton("Cats (press until happy)", callback_data='cats_overlay')],
    ]
    reply_markup = InlineKeyboardMarkup(keyboard)
    update.message.reply_text('Choose an option:', reply_markup=reply_markup)

    context.user_data['photo_path'] = photo_path
    context.user_data['user_id'] = update.message.from_user.id

def process_image(photo_path, user_id, file_id, bot):
    image = cv2.imread(photo_path)
    faces = detect_heads(image)

    def process_face(x, y, w, h):
        face = image[y:y+h, x:x+w]
        pixelated_face = cv2.resize(face, (0, 0), fx=PIXELATION_FACTOR, fy=PIXELATION_FACTOR, interpolation=cv2.INTER_NEAREST)
        image[y:y+h, x:x+w] = cv2.resize(pixelated_face, (w, h), interpolation=cv2.INTER_NEAREST)

    futures = [executor.submit(process_face, x, y, w, h) for (x, y, w, h) in faces]
    wait(futures)

    processed_path = f"processed/{user_id}_{file_id}.jpg"
    cv2.imwrite(processed_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return processed_path

def liotta_overlay(photo_path, user_id, bot):
    image = cv2.imread(photo_path)
    liotta = cv2.imread('liotta.png', cv2.IMREAD_UNCHANGED)
    heads = detect_heads(image)

    for (x, y, w, h) in heads:
        original_aspect_ratio = liotta.shape[1] / liotta.shape[0]
        center_x = x + w // 2
        center_y = y + h // 2
        overlay_x = int(center_x - 0.5 * LIOTTA_RESIZE_FACTOR * w) - int(0.1 * LIOTTA_RESIZE_FACTOR * w)
        overlay_y = int(center_y - 0.5 * LIOTTA_RESIZE_FACTOR * h)
        new_width = int(LIOTTA_RESIZE_FACTOR * w)
        new_height = int(new_width / original_aspect_ratio)
        liotta_resized = cv2.resize(liotta, (new_width, new_height), interpolation=cv2.INTER_AREA)
        image[overlay_y:overlay_y + new_height, overlay_x:overlay_x + new_width, :3] = (
            liotta_resized[:, :, :3] * (liotta_resized[:, :, 3:] / 255.0) +
            image[overlay_y:overlay_y + new_height, overlay_x:overlay_x + new_width, :3] *
            (1.0 - liotta_resized[:, :, 3:] / 255.0)
        )

    processed_path = f"processed/{user_id}_liotta.jpg"
    cv2.imwrite(processed_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return processed_path

def cats_overlay(photo_path, user_id, bot):
    image = cv2.imread(photo_path)
    heads = detect_heads(image)

    for (x, y, w, h) in heads:
        num_cats = len([name for name in os.listdir() if name.startswith('cat_')])
        random_cat = f'cat_{random.randint(1, num_cats)}.png'
        cat = cv2.imread(random_cat, cv2.IMREAD_UNCHANGED)
        original_aspect_ratio = cat.shape[1] / cat.shape[0]
        center_x = x + w // 2
        center_y = y + h // 2
        overlay_x = int(center_x - 0.5 * CATS_RESIZE_FACTOR * w) - int(0.1 * CATS_RESIZE_FACTOR * w)
        overlay_y = int(center_y - 0.5 * CATS_RESIZE_FACTOR * h) - int(0.1 * CATS_RESIZE_FACTOR * w)
        new_width = int(CATS_RESIZE_FACTOR * w)
        new_height = int(new_width / original_aspect_ratio)
        cat_resized = cv2.resize(cat, (new_width, new_height), interpolation=cv2.INTER_AREA)
        overlay_x = max(0, overlay_x)
        overlay_y = max(0, overlay_y)
        roi_start_x = max(0, overlay_x)
        roi_start_y = max(0, overlay_y)
        roi_end_x = min(image.shape[1], overlay_x + new_width)
        roi_end_y = min(image.shape[0], overlay_y + new_height)
        image[roi_start_y:roi_end_y, roi_start_x:roi_end_x, :3] = (
            cat_resized[
                roi_start_y - overlay_y : roi_end_y - overlay_y,
                roi_start_x - overlay_x : roi_end_x - overlay_x,
                :3
            ] * (cat_resized[:, :, 3:] / 255.0) +
            image[roi_start_y:roi_end_y, roi_start_x:roi_end_x, :3] *
            (1.0 - cat_resized[:, :, 3:] / 255.0)
        )

    processed_path = f"processed/{user_id}_cats.jpg"
    cv2.imwrite(processed_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return processed_path

def skull_overlay(photo_path, user_id, bot):
    image = cv2.imread(photo_path)
    skull = cv2.imread('skullofsatoshi.png', cv2.IMREAD_UNCHANGED)
    heads = detect_heads(image)

    for (x, y, w, h) in heads:
        original_aspect_ratio = skull.shape[1] / skull.shape[0]
        center_x = x + w // 2
        center_y = y + h // 2
        overlay_x = max(0, center_x - int(0.5 * SKULL_RESIZE_FACTOR * w)) - int(0.1 * SKULL_RESIZE_FACTOR * w)
        overlay_y = max(0, center_y - int(0.5 * SKULL_RESIZE_FACTOR * h))
        new_width = int(SKULL_RESIZE_FACTOR * w)
        new_height = int(new_width / original_aspect_ratio)

        if new_height <= 0 or new_width <= 0:
            continue

        skull_resized = cv2.resize(skull, (new_width, new_height), interpolation=cv2.INTER_AREA)
        mask = skull_resized[:, :, 3] / 255.0
        mask_inv = 1.0 - mask
        roi = image[overlay_y:overlay_y + new_height, overlay_x:overlay_x + new_width, :3]

        for c in range(3):
            roi[:, :, c] = (mask * skull_resized[:, :, c] + mask_inv * roi[:, :, c])

        image[overlay_y:overlay_y + new_height, overlay_x:overlay_x + new_width, :3] = roi

    processed_path = f"processed/{user_id}_skull_of_satoshi.jpg"
    cv2.imwrite(processed_path, image, [int(cv2.IMWRITE_JPEG_QUALITY), 95])

    return processed_path

def button_callback(update: Update, context: CallbackContext) -> None:
    query = update.callback_query
    query.answer()
    user_data = context.user_data
    photo_path = user_data['photo_path']
    user_id = user_data['user_id']

    if query.data == 'pixelate':
        processed_path = process_image(photo_path, user_id, query.id, context.bot)
    elif query.data == 'liotta':
        processed_path = liotta_overlay(photo_path, user_id, context.bot)
    elif query.data == 'skull_of_satoshi':
        processed_path = skull_overlay(photo_path, user_id, context.bot)
    elif query.data == 'cats_overlay':
        processed_path = cats_overlay(photo_path, user_id, context.bot)

    with open(processed_path, 'rb') as f:
        context.bot.send_photo(chat_id=query.message.chat_id, photo=f)

    os.remove(photo_path)
    os.remove(processed_path)

def main():
    updater = Updater(TOKEN)
    dispatcher = updater.dispatcher

    dispatcher.add_handler(CommandHandler('start', start))
    dispatcher.add_handler(MessageHandler(Filters.photo, pixelate_faces))
    dispatcher.add_handler(CallbackQueryHandler(button_callback))

    updater.start_polling()
    updater.idle()

if __name__ == '__main__':
    executor = ThreadPoolExecutor(max_workers=MAX_THREADS)
    main()
