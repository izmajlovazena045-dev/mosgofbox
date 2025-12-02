from math import *
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, CallbackQuery
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CREDENTIALS_PATH = os.path.join(BASE_DIR, "credentials.json")
SPREADSHEET_ID = "1iR7Qs7hK6kbUADjWSCrCnY3xb9IDSiDxQgB-zbSDFo8"  # вставь свой ID таблицы
RANGE_NAME = "Лист1!A:B"
def add_or_update_user_message(a, b):
    # Подключаемся к Google Sheets API
    creds = Credentials.from_service_account_file(
    CREDENTIALS_PATH,
    scopes=["https://www.googleapis.com/auth/spreadsheets"]
)
    service = build("sheets", "v4", credentials=creds)
    sheet = service.spreadsheets()

    # Получаем все данные
    result = sheet.values().get(spreadsheetId=SPREADSHEET_ID, range=RANGE_NAME).execute()
    values = result.get("values", [])

    # Ищем юзернейм
    row_index = None
    for i, row in enumerate(values):
        if len(row) > 0 and row[0] == a:
            row_index = i
            break

    if row_index is not None:
        # Если юзер уже есть — обновляем сообщение
        old_message = values[row_index][1] if len(values[row_index]) > 1 else ""
        new_message = (old_message + "\n" + b).strip()
        update_range = f"Лист1!B{row_index + 1}"
        sheet.values().update(
            spreadsheetId=SPREADSHEET_ID,
            range=update_range,
            valueInputOption="RAW",
            body={"values": [[new_message]]}
        ).execute()
        print(f"Сообщение для пользователя {a} обновлено.")
    else:
        # Если юзера нет — добавляем новую строку
        sheet.values().append(
            spreadsheetId=SPREADSHEET_ID,
            range=RANGE_NAME,
            valueInputOption="RAW",
            body={"values": [[a, b]]}
        ).execute()
        print(f"Добавлен новый пользователь {a} с сообщением.")
# Настройка логирования для отладки
logging.basicConfig(level=logging.INFO)

# Замените 'ВАШ_БОТ_ТОКЕН' на токен вашего бота
BOT_TOKEN = '8091561490:AAFnG3qzjXLCw9Pkz0z9VHDT6GbtCYscamc'

# Инициализация хранилища для состояний FSM
storage = MemoryStorage()
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=storage)

# Определение состояний (шагов) диалога
class BoxOrder(StatesGroup):
    getting_dimensions = State()
    getting_material_code = State()
    is_self_assembling = State()
    knows_punch_form = State()
    final_calculations = State()

# --- КЛАВИАТУРЫ ---

# Приветственное сообщение
def get_welcome_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Далее", callback_data="next_step_1")]
    ])
    return keyboard

# Кнопки "Да" / "Нет"
def get_yes_no_keyboard(yes_callback, no_callback):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="Да", callback_data=yes_callback),
            InlineKeyboardButton(text="Нет", callback_data=no_callback)
        ]
    ])
    return keyboard

# Кнопка "Вернуться к приветственному сообщению"
def get_restart_keyboard():
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Вернуться к приветственному сообщению", callback_data="restart")]
    ])
    return keyboard


# --- ОБРАБОТЧИКИ СООБЩЕНИЙ (ХЭНДЛЕРЫ) ---

# 1. Обработчик команды /start
@dp.message(CommandStart())
async def send_welcome(message: Message, state: FSMContext):
    """
    Отправляет приветственное сообщение и кнопку "Далее".
    """
    await state.clear() # Сбрасываем состояние при рестарте
    await message.answer(
        "Привет! Я бот для расчета стоимости коробки. Нажмите 'Далее', чтобы начать.",
        reply_markup=get_welcome_keyboard()
    )
    

# Обработчик для кнопки "Вернуться к приветственному сообщению"
@dp.callback_query(lambda c: c.data == 'restart')
async def process_callback_restart(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await state.clear()
    await callback_query.message.answer(
        "Привет! Я бот для расчета стоимости коробки. Нажмите 'Далее', чтобы начать.",
        reply_markup=get_welcome_keyboard()
    )

# 2. Обработчик кнопки "Далее" (начало ввода данных)
@dp.callback_query(lambda c: c.data == 'next_step_1')
async def process_callback_next_step_1(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    await callback_query.message.edit_text("Введите ширину, высоту и глубину коробки в миллиметрах через запятую (например: 100,200,300).")
    await state.set_state(BoxOrder.getting_dimensions)

# 2.1. Получение размеров и запись в список
@dp.message(BoxOrder.getting_dimensions)
async def process_dimensions(message: Message, state: FSMContext):
    username = str(message.from_user.username)
    ms = str(message.text)
    add_or_update_user_message(username, ms)
    try:
        dimensions = [int(x.strip()) for x in message.text.split(',')]
        if len(dimensions) != 3:
            raise ValueError
        # Сохраняем данные в FSM
        await state.update_data(dimensions=dimensions)
        await message.answer(
            "Отлично! Теперь скажите, знаете ли вы код материала?",
            reply_markup=get_yes_no_keyboard(yes_callback="knows_material_yes", no_callback="knows_material_no")
        )
    except (ValueError, IndexError):
        await message.answer("Неверный формат. Пожалуйста, введите ширину, высоту и глубину через запятую (например: 100,200,300).")

# 3. Обработчик ответа про код материала
@dp.callback_query(lambda c: c.data.startswith('knows_material_'))
async def process_knows_material(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    if callback_query.data == 'knows_material_yes':
        await callback_query.message.edit_text("Пожалуйста, введите код материала.")
        print(1)
        await state.set_state(BoxOrder.getting_material_code)
    else:
        await state.update_data(material_code=[34,3,15,2200])
        await callback_query.message.edit_text(
            "Понятно. Коробка самосборная?",
            reply_markup=get_yes_no_keyboard(yes_callback="self_assembling_no", no_callback="self_assembling_yes")
        )
        await state.set_state(BoxOrder.is_self_assembling)

# 3.1. Получение кода материала от пользователя
@dp.message(BoxOrder.getting_material_code)
async def process_material_code(message: Message, state: FSMContext):
    username = str(message.from_user.username)
    ms = str(message.text)
    add_or_update_user_message(username, ms)
    try:
      material_code = [(x.strip()) for x in message.text.split('_')]
      print(2)
      if len(material_code) != 4:
        raise ValueError
      a=material_code[0]
      b=material_code[2]
      c=material_code[1]
      d=material_code[3]
      if a[0] == "0":
        material_code[0] = int(a[1:3])
      if b[0] == "0":
        material_code[2] = int(b[1:3])
      if (c)[0] == "0":
        material_code[1] = float((c)[1:3])/10
      else:
        material_code[1] = float(c)/10
      material_code[3] = int(d)
      print (material_code)
      await state.update_data(material_code=material_code)
      await message.answer(
          "Спасибо! Коробка самосборная?",
          reply_markup=get_yes_no_keyboard(yes_callback="self_assembling_no", no_callback="self_assembling_yes")
      )
      await state.set_state(BoxOrder.is_self_assembling)
    except ():
        print(3)
        await message.answer("Неверный формат. Пожалуйста, введите корректный код (например: 010_020_030_4000).")

# 4. Обработчик ответа "самосборная или нет"
@dp.callback_query(BoxOrder.is_self_assembling)
async def process_is_self_assembling(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()
    user_data = await state.get_data()

    if callback_query.data == 'self_assembling_yes':
        dimensions = user_data.get('dimensions')
        material_code = user_data.get('material_code')
        a=dimensions[0]
        b=dimensions[1]
        c=dimensions[2]
        d=material_code[1]
        korton = material_code[0]
        udar = material_code[2]
        dlina = (((a+b)*2+38*d)/1000)
        shirina = (a+c+8)/1000
        S = dlina*shirina
        price = S*1.5*korton
        minpart = (1000/(dlina*shirina))
        price1 = (udar)+(price)
        await callback_query.message.edit_text(
            f"Расчет.\n"
            f"- Цена коробки {round(price1,2)}\n"
            f"- Минимальная партия: {round(minpart)}\n",
            reply_markup=get_restart_keyboard()
        )
        await state.clear()
    else:
        await callback_query.message.edit_text(
            "Понятно. Знаете ли вы, что такое штанцформа?",
            reply_markup=get_yes_no_keyboard(yes_callback="knows_punch_form_yes", no_callback="knows_punch_form_no")
        )
        await state.set_state(BoxOrder.knows_punch_form)

# 5. Обработчик ответа про штанцформу
@dp.callback_query(BoxOrder.knows_punch_form)
async def process_knows_punch_form(callback_query: CallbackQuery, state: FSMContext):
    await callback_query.answer()

    async def show_final_message():
        user_data = await state.get_data()
        dimensions = user_data.get('dimensions')
        material_code = user_data.get('material_code')
        a=dimensions[0]
        b=dimensions[1]
        c=dimensions[2]
        d=material_code[1]
        korton = material_code[0]
        udar = material_code[2]
        pogoni =material_code[3]
        if b-a>=a-c:
          R = 3.14
          nr = ((c*R)+(a+d*2)*2+c*2+d*2*2+d*3*6+d*4+(b+d/2)*4+(c-d)*2+(b+d)*2+(b+d*2)*2+c*4+(c-d/2)*2+b*4+4*d+b+d*6)
          ns = (((c*6)+(a+d*7)*4+b*2+(b+d)*4)*0.97)
          dlina = ((c+b+c+b+c+d*6))
          shirina = (a+b+b+d*9)
        else:
          R = 1.28  # скругление (запятая заменена на точку)
          K = 14  # под палец рез
          F = 0.17  # вставлялки
          J = 1.18  # Триугольник
          R2 = 1.083  # скругление 2 (запятая заменена на точку)
          Storona = (b - (sqrt(c * R2 * c * R2 - c * c)) * 2)
          nr = ((d * 2) * 4 + ((d * 3 + b * F) * 2) * 4 + (a + d * 8) + K + (c * J * R) * 2 + c * 2 + d * 3 * 2 + (c * 2 * R2) * 2 + Storona * 2 + b * 0.5 * 2 + c * 2 + (c + d) * 4 + d * 4 + d * 3 + d * 12 + (b / 2 - c - d - d - d * 1.5) * 2 + (c + 2) * 4 + (b / 2 + d) * 2 + c * 2 + ((b / 2) + d - c - d - d - d) * 2 + d * 4 + b * 2 + d * 3 * 4+(a+d*9-d*4))
          ns = (((c+d/2)*4+a*2+b*2+c*2+(a+d*9)*2-(4*6)+(b+d)*4+(b-d)*2)*0.97)
          dlina = (a+c+c+c+c+d*21)
          shirina = (c+c+c+b+b+d*5)
        n = nr+ns
        rg = (round((1000/dlina)))
        rv = (round((1000/shirina)))
        sem = rg*rv
        S = (dlina/1000)*(shirina/1000)
        price = S*korton
        minpart = (1000/(dlina*shirina))
        if sem == 1:
            await callback_query.message.answer(
                f"Расчет.\n"
                f"- Штанцформа на 1 съём:\n"
                f"Стоимость штанцформы {round(n*pogoni/1000)}\n"
                f"Цена коробки {round(((udar)+(price)),2)}\n\n",
                reply_markup=get_restart_keyboard()
                )
            await state.clear()
        elif sem ==2:
            await callback_query.message.answer(
                f"Расчет.\n"
                f"- Штанцформа на 1 съём:\n"
                "Стоимость штанцформы {round(n*pogoni/1000)}\n"
                f"Цена коробки {round(((udar)+(price)),2)}\n\n"
                f"- Штанцформа на {sem} съёма:\n"
                f"Стоимость штанцформы {round(sem*n*pogoni/1000)}\n"
                f"Цена коробки {round(((udar)/sem+(price)),2)}\n\n",
                reply_markup=get_restart_keyboard()
                )
            await state.clear()
        else:
            await callback_query.message.answer(
                f"Расчет.\n"
                f"- Штанцформа на 1 съём:\n"
                f"Стоимость штанцформы {round(n*pogoni/1000)}\n"
                f"Цена коробки {round(((udar)+(price)),2)}\n\n"
                f"- Штанцформа на {round(sem/2)} съёма:\n"
                f"Стоимость штанцформы {round((round(sem/2)*n*pogoni/1000))}\n"
                f"Цена коробки {round(((udar)/round(sem/2)+(price)),2)}\n\n"
                f"- Штанцформа на {sem} съёмов:\n"
                f"Стоимость штанцформы {round(sem*n*pogoni/1000)}\n"
                f"Цена коробки {round(((udar)/sem+(price)),2)}\n\n",
                reply_markup=get_restart_keyboard()
                )
            await state.clear()

    if callback_query.data == 'knows_punch_form_no':
        await callback_query.message.edit_text(
            "Штанцформа — это форма с режущими элементами для вырубки изделий из листовых материалов. "
            "Она необходима для производства коробок сложной формы."
        )
        await asyncio.sleep(2) # Небольшая задержка для прочтения
        await show_final_message()

    else: # Если 'knows_punch_form_yes'
        await callback_query.message.delete() # Удаляем предыдущее сообщение с кнопками
        await show_final_message()

async def main():
    print("Бот запущен...")
    await dp.start_polling(bot)

asyncio.run(main())