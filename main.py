from fastapi import FastAPI, UploadFile, File, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
import io
import os
import base64
import anthropic
import json
import traceback
from typing import List
import logging
import logging.handlers
import time
from datetime import datetime

# Временная настройка логирования (будет обновлена после определения STORAGE_BASE)
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[logging.StreamHandler()]  # Пока только консоль
)
logger = logging.getLogger(__name__)

app = FastAPI(title="Somon.tj",
              description="ИИ анализ товаров для объявлений")

# CORS для развития
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Определяем базовую папку для хранения (используем примонтированный диск Render)
STORAGE_BASE = "/var/data" if os.path.exists("/var/data") else "."

# Создаем папки
os.makedirs("static", exist_ok=True)
os.makedirs(os.path.join(STORAGE_BASE, "uploads"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_BASE, "debug_images"), exist_ok=True)
os.makedirs(os.path.join(STORAGE_BASE, "logs"), exist_ok=True)

logger.info(f"📁 Базовая папка для хранения: {STORAGE_BASE}")
logger.info(
    f"💾 Постоянный диск {'ПОДКЛЮЧЕН' if STORAGE_BASE != '.' else 'НЕ НАЙДЕН'}")

# Настраиваем логирование в файл после определения STORAGE_BASE
log_file_path = os.path.join(STORAGE_BASE, "logs", "app.log")
file_handler = logging.handlers.RotatingFileHandler(
    log_file_path,
    maxBytes=10*1024*1024,  # 10MB
    backupCount=5
)
file_handler.setFormatter(logging.Formatter(
    '%(asctime)s - %(name)s - %(levelname)s - %(message)s'))
logger.addHandler(file_handler)
logger.info(f"📝 Логи сохраняются в: {log_file_path}")

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")

# Структура категорий Somon.tj
SOMON_CATEGORIES = """Телефоны и связь
-- Мобильные телефоны
-- Аксессуары для телефонов
-- Ремонт и сервис телефонов
-- Запчасти и инструменты для телефонов
-- Стационарные телефоны
-- Другая техника связи

Детский мир
-- Детская одежда
-- Детская обувь
-- Детская мебель
-- Детские коляски, качели
-- Детские автокресла
-- Детский транспорт
-- Детские часы
-- Игрушки
-- Товары для мам
-- Товары для кормления
-- Товары для школьников
-- Товары для детского купания
-- Постельные принадлежности
-- Другие детские товары

Одежда и личные вещи
-- Мужская одежда
-- Женская одежда
-- Обувь
-- Аксессуары, шарфы, головные уборы
-- Парфюмерия и косметика
-- Часы и украшения
-- Для свадьбы
-- Одежда на прокат
-- Другие товары
-- Потери и находки
-- Чемоданы, сумки, клатчи
-- Ткани и материалы для пошива одежды

Компьютеры и оргтехника
-- Ноутбуки
-- Персональные компьютеры
-- Игровые приставки
-- Программы и игры
-- Планшеты и букридеры
-- Принтеры и сканеры
-- Мониторы и проекторы
-- Модемы и сетевое оборудование
-- Комплектующие и аксессуары
-- Ремонт
-- Серверы
-- Другая техника

Электроника и бытовая техника
-- Фото и видеокамеры
-- TV, DVD и видео
-- Аудио и стерео
-- Техника для дома и кухни
-- Для личного ухода
-- Принадлежности и аппараты для здоровья
-- Аксессуары и комплектующие
-- Электронные компоненты и радиодетали
-- Системы видеонаблюдения, охраны, "Умный дом"
-- Другая техника
-- Климатическая техника

Все для дома
-- Мебель
-- Текстиль и интерьер
-- Пищевые продукты
-- Посуда и кухонная утварь
-- Хозяйственный инвентарь и бытовая химия
-- Сад и огород
-- Сейфы
-- Канцтовары
-- Другие товары для дома
-- Товары для праздников

Строительство, сырье и ремонт
-- Электроинструмент
-- Ручной инструмент
-- Строительные и отделочные материалы

Хобби, музыка и спорт
-- Спорт и инвентарь
-- Велосипеды и принадлежности
-- Музыкальные инструменты
-- Книги и журналы
-- CD, DVD, пластинки и кассеты
-- Антиквариат и коллекции
-- Билеты

Животные и растения
-- Собаки
-- Кошки
-- Кролики
-- Птицы
-- Вязка
-- Садовые растения
-- Сельхоз животные
-- Аквариумные
-- Комнатные растения
-- Товары для животных
-- Другие животные
-- Отдам даром
-- Утерянные животные
-- Корм для животных
-- Пчёлы и инвентарь для пчеловодства

Все для бизнеса
-- Бизнес на продажу
-- Оборудование
-- Сырьё и материалы для бизнеса
-- Готовый бизнес в аренду"""


def save_debug_files(files_data: List[tuple], session_id: str) -> str:
    """Сохраняет файлы для отладки и возвращает путь к папке"""
    try:
        # Создаем папку для этой сессии
        session_folder = os.path.join(STORAGE_BASE, "debug_images", session_id)
        os.makedirs(session_folder, exist_ok=True)

        # Сохраняем каждый файл с индексом
        for idx, (contents, filename) in enumerate(files_data):
            # Определяем расширение
            ext = filename.split('.')[-1] if '.' in filename else 'jpg'
            debug_filename = f"{idx:02d}_{filename}"
            debug_path = os.path.join(session_folder, debug_filename)

            with open(debug_path, 'wb') as f:
                f.write(contents)

            logger.info(
                f"💾 Сохранен файл {idx}: {debug_filename} ({len(contents)} байт)")

        # Создаем файл с метаданными
        metadata = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "total_files": len(files_data),
            "files": [
                {
                    "index": idx,
                    "original_filename": filename,
                    "debug_filename": f"{idx:02d}_{filename}",
                    "size_bytes": len(contents)
                }
                for idx, (contents, filename) in enumerate(files_data)
            ]
        }

        metadata_path = os.path.join(session_folder, "metadata.json")
        with open(metadata_path, 'w', encoding='utf-8') as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

        logger.info(f"📋 Создан файл метаданных: {metadata_path}")
        return session_folder

    except Exception as e:
        logger.error(f"❌ Ошибка сохранения отладочных файлов: {e}")
        return ""


def analyze_image_with_claude(image_data: bytes, filename: str) -> str:
    """Анализирует изображение с помощью Claude и возвращает описание"""
    try:
        logger.info(
            f"🔍 НАЧИНАЕМ АНАЛИЗ ИЗОБРАЖЕНИЯ: {filename}, размер: {len(image_data)} байт")

        # Проверяем что API ключ настроен
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            error_msg = "❌ API ключ Anthropic не настроен в переменных окружения"
            logger.error(error_msg)
            return error_msg

        logger.info(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")

        # Проверяем размер изображения
        if len(image_data) > 20 * 1024 * 1024:  # 20MB лимит
            error_msg = f"❌ Изображение слишком большое: {len(image_data)/1024/1024:.1f}MB (максимум 20MB)"
            logger.error(error_msg)
            return error_msg

        # Инициализация клиента
        logger.info("🔧 Инициализируем Anthropic клиент...")
        client = anthropic.Anthropic(
            api_key=api_key,
            # Убираем проксирование для Render
            timeout=60.0
        )

        # Кодируем изображение в base64
        logger.info("🔄 Кодируем изображение в base64...")
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        logger.info(f"✅ Base64 готов, длина: {len(image_base64)} символов")

        # Определяем MIME тип
        file_extension = filename.lower().split(
            '.')[-1] if '.' in filename else 'jpg'
        mime_type_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg',
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        mime_type = mime_type_map.get(file_extension, 'image/jpeg')
        logger.info(f"📎 MIME тип: {mime_type}")

        logger.info("🚀 ОТПРАВЛЯЕМ ЗАПРОС В CLAUDE API...")

        # Отправляем запрос к Claude
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=2000,
            messages=[
                {
                    "role": "user",
                    "content": [
                        {
                            "type": "image",
                            "source": {
                                "type": "base64",
                                "media_type": mime_type,
                                "data": image_base64,
                            },
                        },
                        {
                            "type": "text",
                            "text": """Проанализируйте это изображение товара для создания объявления о продаже. Отвечайте ТОЛЬКО на русском языке.

Дайте краткую информацию:

🏷️ ТОВАР:
- Название товара (максимум 5-7 слов)
- Основная категория (одежда, техника, мебель, автомобиль и т.д.)
- Подкатегория товара
- Основной цвет товара

📝 КРАТКОЕ ОПИСАНИЕ:
- Материал и состояние (новый/б/у)
- Бренд (если различимо)
- 1-2 ключевые особенности

Отвечайте кратко и по делу. Фокусируйтесь только на основной информации для объявления."""
                        }
                    ],
                }
            ],
        )

        description = message.content[0].text
        logger.info(
            f"✅ ПОЛУЧЕН ОТВЕТ ОТ CLAUDE! Длина: {len(description)} символов")

        return description

    except Exception as e:
        error_msg = f"❌ ОШИБКА АНАЛИЗА {filename}: {str(e)}"
        logger.error(f"{error_msg}\nПолная ошибка: {traceback.format_exc()}")
        return error_msg


def load_categories_from_file() -> dict:
    """Загружает категории из файла somon_categories.txt"""
    try:
        categories = {}
        current_category = None

        with open('somon_categories.txt', 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue

                if line.startswith('--'):
                    # Это подкатегория
                    if current_category:
                        subcategory = line[2:].strip()
                        categories[current_category].append(subcategory)
                else:
                    # Это основная категория
                    current_category = line
                    categories[current_category] = []

        logger.info(f"Загружено {len(categories)} категорий из файла")
        return categories

    except Exception as e:
        logger.error(f"Ошибка загрузки категорий: {e}")
        # Возвращаем базовые категории как fallback
        return {
            'Одежда и личные вещи': ['Мужская одежда', 'Женская одежда', 'Обувь'],
            'Электроника и бытовая техника': ['Телефоны и связь', 'Компьютеры и оргтехника'],
            'Детский мир': ['Детская одежда', 'Игрушки'],
            'Все для дома': ['Мебель', 'Бытовая техника']
        }


def analyze_images_batch_with_claude(image_batch: List[tuple[bytes, str]]) -> str:
    """Анализирует batch изображений и группирует их по товарам, возвращает JSON строку"""
    try:
        logger.info(f"🔍 НАЧИНАЕМ BATCH АНАЛИЗ: {len(image_batch)} изображений")

        # Проверяем что API ключ настроен
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            error_msg = "❌ API ключ Anthropic не настроен в переменных окружения"
            logger.error(error_msg)
            return ""

        logger.info(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")

        # Инициализация клиента
        logger.info("🔧 Инициализируем Anthropic клиент...")
        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=60.0
        )

        # Подготавливаем изображения для batch запроса
        image_contents = []
        for i, (image_data, filename) in enumerate(image_batch):
            # Кодируем изображение в base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # Определяем MIME тип
            mime_type = "image/jpeg"
            if filename.lower().endswith('.png'):
                mime_type = "image/png"
            elif filename.lower().endswith('.webp'):
                mime_type = "image/webp"

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

        # Максимально четкий промпт
        batch_prompt = f"""Проанализируйте изображения и определите РАЗНЫЕ товары. Каждый уникальный предмет = отдельный товар.

ПРАВИЛА:
1. Внимательно смотрите на каждое изображение
2. Разные типы техники = разные товары (кондиционер ≠ плита ≠ стиральная машина)
3. Группируйте только ОДИНАКОВЫЕ предметы с разных ракурсов
4. При малейшем сомнении - разделяйте на отдельные товары

ВАЖНО: НЕ объединяйте разные устройства в один товар!

Используйте категории: {SOMON_CATEGORIES}

Формат ответа - ТОЛЬКО JSON:
[
  {{
    "title": "Название товара",
    "category": "Категория",
    "subcategory": "Подкатегория",
    "color": "цвет",
    "image_indexes": [номера_изображений]
  }}
]

ВЕРНИТЕ ТОЛЬКО JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА."""

        logger.info("🚀 ОТПРАВЛЯЕМ BATCH ЗАПРОС В CLAUDE API...")

        # Отправляем batch запрос к Claude
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=8192,
            messages=[
                {
                    "role": "user",
                    "content": [
                        *image_contents,
                        {
                            "type": "text",
                            "text": batch_prompt
                        }
                    ],
                }
            ],
        )

        response_text = message.content[0].text
        logger.info(
            f"✅ ПОЛУЧЕН BATCH ОТВЕТ ОТ CLAUDE! Длина: {len(response_text)} символов")

        # ДЕТАЛЬНОЕ ЛОГИРОВАНИЕ ДЛЯ ДИАГНОСТИКИ
        logger.info(f"🔍 ПЕРВЫЕ 1000 СИМВОЛОВ ОТВЕТА: {response_text[:1000]}")
        logger.info(f"🔍 ПОСЛЕДНИЕ 500 СИМВОЛОВ ОТВЕТА: {response_text[-500:]}")

        return response_text

    except Exception as e:
        error_msg = f"❌ ОШИБКА BATCH АНАЛИЗА: {str(e)}"
        logger.error(error_msg)
        return ""


@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница с React приложением"""
    try:
        return FileResponse('static/index.html')
    except Exception as e:
        logger.error(f"Ошибка загрузки главной страницы: {e}")
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Ошибка</title></head>
        <body>
            <h1>Ошибка загрузки</h1>
            <p>Файл index.html не найден</p>
            <p>Убедитесь что файл static/index.html существует</p>
        </body>
        </html>
        """, status_code=500)


@app.post("/api/analyze-single")
async def analyze_single_image(file: UploadFile = File(...)):
    """Анализ одного изображения"""
    try:
        logger.info(
            f"📥 Получен файл для анализа: {file.filename}, тип: {file.content_type}")

        # Проверяем тип файла
        if not file.content_type.startswith('image/'):
            logger.warning(f"⚠️ Неверный тип файла: {file.content_type}")
            raise HTTPException(
                status_code=400, detail="Файл должен быть изображением")

        # Читаем файл
        contents = await file.read()
        logger.info(f"📂 Размер файла: {len(contents)} байт")

        # Временные размеры изображения (без PIL)
        width, height = 800, 600

        # Анализируем с Claude
        description = analyze_image_with_claude(
            contents, file.filename)

        # Кодируем изображение для возврата в браузер
        image_base64 = base64.b64encode(contents).decode('utf-8')

        return JSONResponse({
            "success": True,
            "result": {
                "id": f"{file.filename}_{int(io.BytesIO(contents).tell())}",
                "filename": file.filename,
                "width": width,
                "height": height,
                "size_bytes": len(contents),
                "image_preview": f"data:image/{file.filename.split('.')[-1]};base64,{image_base64}",
                "description": description
            }
        })

    except Exception as e:
        logger.error(
            f"❌ Ошибка анализа одного изображения: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.post("/api/analyze-grouping")
async def analyze_grouping_diagnostic(files: List[UploadFile] = File(...)):
    """ДИАГНОСТИКА ГРУППИРОВКИ: показывает как Claude группирует изображения"""
    try:
        logger.info(f"🔍 ДИАГНОСТИКА ГРУППИРОВКИ: Получено {len(files)} файлов")

        # Собираем все валидные изображения
        image_batch = []
        file_info = []

        logger.info(f"📋 Порядок получения файлов:")
        for i, file in enumerate(files):
            logger.info(f"  {i}: {file.filename} ({file.content_type})")

        for file in files:
            if not file.content_type or not file.content_type.startswith('image/'):
                logger.warning(
                    f"⚠️ Пропускаем {file.filename} - неверный тип: {file.content_type}")
                continue

            try:
                contents = await file.read()
                if len(contents) > 20 * 1024 * 1024:  # 20MB
                    logger.warning(
                        f"⚠️ Пропускаем {file.filename} - слишком большой: {len(contents)/1024/1024:.1f}MB")
                    continue

                image_batch.append((contents, file.filename))
                file_info.append({
                    'filename': file.filename,
                    'content_type': file.content_type,
                    'size': len(contents),
                    'contents': contents
                })

            except Exception as file_error:
                logger.error(
                    f"❌ Ошибка чтения файла {file.filename}: {file_error}")
                continue

        if not image_batch:
            raise HTTPException(
                status_code=400, detail="Нет валидных изображений")

        # Сохраняем отладочные файлы
        session_id = f"diag_{int(time.time())}_{len(image_batch)}"
        debug_folder = save_debug_files(image_batch, session_id)

        # Подготавливаем изображения для batch запроса
        image_contents = []
        for i, (image_data, filename) in enumerate(image_batch):
            # Кодируем изображение в base64
            base64_image = base64.b64encode(image_data).decode('utf-8')

            # Определяем MIME тип
            mime_type = "image/jpeg"
            if filename.lower().endswith('.png'):
                mime_type = "image/png"
            elif filename.lower().endswith('.webp'):
                mime_type = "image/webp"

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

        # ДИАГНОСТИЧЕСКИЙ промпт для группировки
        diagnostic_prompt = f"""ДИАГНОСТИКА ГРУППИРОВКИ: Проанализируйте эти {len(image_batch)} изображений и сгруппируйте ОДИНАКОВЫЕ товары.

ЗАДАЧА: Найти изображения которые показывают ОДИН И ТОТ ЖЕ товар с разных ракурсов.

ПРАВИЛА:
1. Внимательно сравните каждое изображение
2. Группируйте только ИДЕНТИЧНЫЕ предметы (одна и та же стиральная машина, один и тот же кондиционер)
3. Разные модели/цвета/размеры = разные товары
4. Если сомневаетесь - лучше разделить

ФОРМАТ ОТВЕТА - детальный JSON с объяснениями:
[
  {{
    "group_id": 1,
    "title": "Название товара",
    "reasoning": "Почему эти изображения сгруппированы вместе",
    "image_indexes": [0, 3],
    "description": "Детальное описание товара"
  }},
  {{
    "group_id": 2,
    "title": "Другой товар",
    "reasoning": "Почему это отдельный товар",
    "image_indexes": [1],
    "description": "Описание второго товара"
  }}
]

ВАЖНО: Объясните свои решения в поле "reasoning"!

ВЕРНИТЕ ТОЛЬКО JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА."""

        try:
            # Инициализация клиента
            api_key = os.getenv("ANTHROPIC_API_KEY")
            client = anthropic.Anthropic(api_key=api_key, timeout=60.0)

            logger.info("🚀 ОТПРАВЛЯЕМ ДИАГНОСТИЧЕСКИЙ ЗАПРОС В CLAUDE API...")

            # Отправляем batch запрос к Claude
            message = client.messages.create(
                model="claude-3-5-sonnet-20241022",
                max_tokens=8192,
                messages=[
                    {
                        "role": "user",
                        "content": [
                            *image_contents,
                            {
                                "type": "text",
                                "text": diagnostic_prompt
                            }
                        ],
                    }
                ],
            )

            response_text = message.content[0].text
            logger.info(
                f"✅ ПОЛУЧЕН ДИАГНОСТИЧЕСКИЙ ОТВЕТ! Длина: {len(response_text)} символов")
            logger.info(f"🔍 ПОЛНЫЙ ОТВЕТ: {response_text}")

            # Пытаемся распарсить JSON
            try:
                import json
                groups = json.loads(response_text)

                return JSONResponse({
                    "success": True,
                    "diagnostic_mode": "grouping",
                    "total_images": len(image_batch),
                    "groups": groups,
                    "raw_response": response_text,
                    "debug_folder": debug_folder,
                    "session_id": session_id,
                    "file_order": [{"index": i, "filename": info['filename']} for i, info in enumerate(file_info)],
                    "message": "Диагностика группировки завершена"
                })

            except json.JSONDecodeError as e:
                logger.error(f"❌ Ошибка парсинга JSON: {e}")
                return JSONResponse({
                    "success": False,
                    "error": f"Ошибка парсинга JSON: {e}",
                    "raw_response": response_text,
                    "debug_folder": debug_folder,
                    "session_id": session_id
                })

        except Exception as e:
            logger.error(f"❌ Ошибка запроса к Claude: {e}")
            return JSONResponse({
                "success": False,
                "error": f"Ошибка Claude API: {str(e)}"
            }, status_code=500)

    except Exception as e:
        logger.error(
            f"❌ Ошибка диагностики группировки: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "error": f"Ошибка сервера: {str(e)}"
        }, status_code=500)


@app.post("/api/analyze-individual")
async def analyze_individual_images(files: List[UploadFile] = File(...)):
    """ДИАГНОСТИЧЕСКИЙ эндпоинт: анализ каждого изображения отдельно"""
    try:
        logger.info(
            f"🔍 ДИАГНОСТИКА: Получено {len(files)} файлов для индивидуального анализа")

        # Собираем все валидные изображения
        image_batch = []
        file_info = []

        logger.info(f"📋 Порядок получения файлов:")
        for i, file in enumerate(files):
            logger.info(f"  {i}: {file.filename} ({file.content_type})")

        for file in files:
            if not file.content_type or not file.content_type.startswith('image/'):
                logger.warning(
                    f"⚠️ Пропускаем {file.filename} - неверный тип: {file.content_type}")
                continue

            try:
                contents = await file.read()
                if len(contents) > 20 * 1024 * 1024:  # 20MB
                    logger.warning(
                        f"⚠️ Пропускаем {file.filename} - слишком большой: {len(contents)/1024/1024:.1f}MB")
                    continue

                image_batch.append((contents, file.filename))
                file_info.append({
                    'filename': file.filename,
                    'content_type': file.content_type,
                    'size': len(contents),
                    'contents': contents
                })

            except Exception as file_error:
                logger.error(
                    f"❌ Ошибка чтения файла {file.filename}: {file_error}")
                continue

        if not image_batch:
            raise HTTPException(
                status_code=400, detail="Нет валидных изображений")

        # Сохраняем отладочные файлы
        session_id = f"{int(time.time())}_{len(image_batch)}"
        debug_folder = save_debug_files(image_batch, session_id)

        # Создаем промпт для индивидуального анализа
        individual_descriptions = []

        for i, (image_data, filename) in enumerate(image_batch):
            logger.info(f"🔍 Анализируем изображение {i}: {filename}")

            # Кодируем изображение в base64
            image_base64 = base64.b64encode(image_data).decode('utf-8')

            # Определяем MIME тип
            mime_type = "image/jpeg"
            if filename.lower().endswith('.png'):
                mime_type = "image/png"
            elif filename.lower().endswith('.webp'):
                mime_type = "image/webp"

            # Простой промпт для описания одного изображения
            simple_prompt = f"""Опишите что изображено на этой фотографии одним предложением.

Формат ответа:
"Индекс {i}: [Название товара] - [краткое описание]"

Например: "Индекс 0: Стиральная машина LG - белая стиральная машина с фронтальной загрузкой"

ВЕРНИТЕ ТОЛЬКО ОДНО ПРЕДЛОЖЕНИЕ."""

            try:
                # Инициализация клиента
                api_key = os.getenv("ANTHROPIC_API_KEY")
                client = anthropic.Anthropic(api_key=api_key, timeout=60.0)

                # Отправляем запрос к Claude
                message = client.messages.create(
                    model="claude-3-5-sonnet-20241022",
                    max_tokens=200,
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": mime_type,
                                        "data": image_base64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": simple_prompt
                                }
                            ],
                        }
                    ],
                )

                description = message.content[0].text.strip()
                individual_descriptions.append({
                    "index": i,
                    "filename": filename,
                    "description": description
                })

                logger.info(f"✅ Индекс {i}: {description}")

            except Exception as e:
                error_desc = f"Ошибка анализа: {str(e)}"
                individual_descriptions.append({
                    "index": i,
                    "filename": filename,
                    "description": error_desc
                })
                logger.error(f"❌ Ошибка анализа изображения {i}: {e}")

        return JSONResponse({
            "success": True,
            "diagnostic_mode": True,
            "total_images": len(image_batch),
            "descriptions": individual_descriptions,
            "debug_folder": debug_folder,
            "session_id": session_id,
            "message": "Диагностический анализ завершен - каждое изображение описано отдельно"
        })

    except Exception as e:
        logger.error(
            f"❌ Ошибка диагностического анализа: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "error": f"Ошибка сервера: {str(e)}"
        }, status_code=500)


@app.post("/api/analyze-multiple")
async def analyze_multiple_images(files: List[UploadFile] = File(...)):
    """Анализ нескольких изображений с группировкой по товарам"""
    try:
        logger.info(f"📥 Получено {len(files)} файлов для анализа")

        # Ограничиваем количество файлов
        if len(files) > 14:
            logger.warning(
                f"⚠️ Слишком много файлов: {len(files)}, максимум 14")
            raise HTTPException(
                status_code=400, detail="Максимум 14 файлов за раз")

        # Собираем все валидные изображения
        image_batch = []
        file_info = []  # Сохраняем информацию о файлах в том же порядке

        logger.info(f"📋 Порядок получения файлов:")
        for i, file in enumerate(files):
            logger.info(f"  {i}: {file.filename} ({file.content_type})")

        for file in files:
            if not file.content_type or not file.content_type.startswith('image/'):
                logger.warning(
                    f"⚠️ Пропускаем {file.filename} - неверный тип: {file.content_type}")
                continue

            try:
                contents = await file.read()

                if len(contents) > 20 * 1024 * 1024:  # 20MB
                    logger.warning(
                        f"⚠️ Пропускаем {file.filename} - слишком большой: {len(contents)/1024/1024:.1f}MB")
                    continue

                image_batch.append((contents, file.filename))
                file_info.append({
                    'filename': file.filename,
                    'content_type': file.content_type,
                    'size': len(contents),
                    'contents': contents  # Сохраняем для превью
                })

            except Exception as file_error:
                logger.error(
                    f"❌ Ошибка чтения файла {file.filename}: {file_error}")
                continue

        if not image_batch:
            raise HTTPException(
                status_code=400, detail="Нет валидных изображений для обработки")

        # Сохраняем файлы для отладки
        session_id = f"{int(time.time())}_{len(image_batch)}"
        debug_folder = save_debug_files(image_batch, session_id)
        logger.info(f"🗂️ Отладочные файлы сохранены в: {debug_folder}")

        # Batch анализ всех изображений
        claude_response = analyze_images_batch_with_claude(image_batch)

        # Парсим результаты группировки из Claude
        try:
            # Пытаемся извлечь JSON из ответа Claude

            # Ищем JSON в ответе
            json_start = claude_response.find('[')
            json_end = claude_response.rfind(']') + 1

            if json_start != -1 and json_end > json_start:
                json_str = claude_response[json_start:json_end]
                products = json.loads(json_str)
                logger.info(
                    f"✅ Найдено {len(products)} сгруппированных товаров")

                # Формируем результаты по группам товаров
                results = []
                # Умная валидация индексов с отслеживанием использованных
                max_index = len(file_info) - 1
                used_indexes = set()
                logger.info(
                    f"🔧 Валидация индексов для {len(products)} товаров (максимальный индекс: {max_index})")

                for product in products:
                    original_indexes = product.get('image_indexes', [])
                    valid_indexes = []

                    # Проверяем каждый индекс
                    for idx in original_indexes:
                        if 0 <= idx <= max_index and idx not in used_indexes:
                            valid_indexes.append(idx)
                            used_indexes.add(idx)
                        else:
                            logger.warning(
                                f"⚠️ Пропускаем неверный/занятый индекс {idx} для товара '{product.get('title', 'Неизвестно')}'")

                    # Если нет валидных индексов, найдем первый свободный
                    if not valid_indexes and file_info:
                        for idx in range(max_index + 1):
                            if idx not in used_indexes:
                                valid_indexes = [idx]
                                used_indexes.add(idx)
                                logger.info(
                                    f"✅ Fallback: назначен свободный индекс {idx} для товара '{product.get('title', 'Неизвестно')}'")
                                break

                    product['image_indexes'] = valid_indexes
                    product['original_indexes'] = original_indexes

                for product_idx, product in enumerate(products):
                    title = product.get('title', f'Товар {product_idx + 1}')
                    category = product.get('category', 'Разное')
                    subcategory = product.get('subcategory', '')
                    color = product.get('color', '')
                    image_indexes = product.get('image_indexes', [])
                    original_indexes = product.get('original_indexes', [])

                    logger.info(
                        f"🔍 Обрабатываем товар {product_idx}: '{title}' с индексами {image_indexes} (оригинальные: {original_indexes})")

                    # Собираем изображения для этого товара
                    product_images = []
                    valid_indexes = []
                    image_filenames = []  # Для отладки

                    # Индексы уже проверены и исправлены, просто обрабатываем их
                    for img_idx in image_indexes:
                        info = file_info[img_idx]
                        image_base64 = base64.b64encode(
                            info['contents']).decode('utf-8')
                        product_images.append(
                            f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}")
                        valid_indexes.append(img_idx)
                        image_filenames.append(info['filename'])
                        logger.info(
                            f"  ✅ Добавлено изображение {img_idx}: {info['filename']}")

                    if not product_images:  # Если нет изображений, берем первое доступное
                        logger.warning(
                            f"⚠️ Товар '{title}' не имеет валидных изображений, используем fallback")
                        if file_info:
                            info = file_info[0]
                            image_base64 = base64.b64encode(
                                info['contents']).decode('utf-8')
                            product_images.append(
                                f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}")
                            valid_indexes = [0]
                            image_filenames = [info['filename']]

                    logger.info(
                        f"  📸 Итого изображений для '{title}': {len(product_images)} ({image_filenames})")

                    # Создаем краткое описание товара
                    description_parts = [f"🏷️ {title}"]
                    if color:
                        description_parts.append(f"🎨 Цвет: {color}")
                    description_parts.append(f"📂 {category}")
                    if subcategory:
                        description_parts.append(f"📂 {subcategory}")

                    description = "\n".join(description_parts)

                    results.append({
                        "id": f"product_{product_idx}_{int(time.time())}",
                        "filename": f"grouped_product_{product_idx}",
                        "width": 800,
                        "height": 600,
                        "size_bytes": sum(file_info[i]['size'] for i in valid_indexes),
                        "images": product_images,  # Массив изображений для товара
                        # Первое изображение для совместимости
                        "image_preview": product_images[0] if product_images else "",
                        "description": description,
                        "title": title,
                        "category": category,
                        "subcategory": subcategory,
                        "color": color,
                        "image_indexes": valid_indexes,  # Используем только валидные индексы
                        "original_indexes": image_indexes  # Сохраняем оригинальные для отладки
                    })

                logger.info(f"✅ Сформировано {len(results)} товарных групп")

                return JSONResponse({
                    "success": True,
                    "results": results,
                    "processed_count": len(results),
                    "total_files": len(files),
                    "grouped": True,
                    "debug_folder": debug_folder,
                    "session_id": session_id,
                    "summary": {
                        "total_images": len(files),
                        "processed_images": len(file_info),
                        "grouped_products": len(results)
                    }
                })

        except (json.JSONDecodeError, ValueError) as e:
            logger.warning(
                f"⚠️ Не удалось распарсить группировку: {e}, используем fallback")

        # Fallback - возвращаем как отдельные изображения
        results = []
        for i, info in enumerate(file_info):
            # Создаем простое описание для каждого изображения
            description = f"🏷️ ТОВАР: Товар из изображения {info['filename']}\n📂 КАТЕГОРИЯ: Разное\n📝 ОПИСАНИЕ: Требует ручной категоризации"
            # Кодируем изображение для браузера
            image_base64 = base64.b64encode(info['contents']).decode('utf-8')

            results.append({
                "id": f"{info['filename']}_{info['size']}_{i}",
                "filename": info['filename'],
                "width": 800,  # Временные значения
                "height": 600,
                "size_bytes": info['size'],
                "images": [f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}"],
                "image_preview": f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}",
                "description": description
            })

        logger.info(
            f"✅ Fallback анализ завершен! Обработано {len(results)} изображений")

        return JSONResponse({
            "success": True,
            "results": results,
            "processed_count": len(results),
            "total_files": len(files),
            "grouped": False,
            "debug_folder": debug_folder,
            "session_id": session_id,
            "summary": {
                "total_images": len(files),
                "processed_images": len(results)
            }
        })

    except Exception as e:
        logger.error(f"❌ Ошибка batch анализа: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "error": f"Ошибка сервера: {str(e)}"
        }, status_code=500)


@app.get("/api/health")
async def health_check():
    """Проверка работоспособности API"""
    api_key = os.getenv("ANTHROPIC_API_KEY")

    # Проверяем доступность Claude API
    claude_status = "unknown"
    try:
        if api_key:
            client = anthropic.Anthropic(
                api_key=api_key,
                timeout=60.0
            )
            # Не делаем реальный запрос, просто проверяем что клиент создается
            claude_status = "configured"
    except Exception as e:
        claude_status = f"error: {str(e)}"

    # Проверяем статус диска
    disk_status = {
        "persistent_disk_mounted": STORAGE_BASE != ".",
        "storage_path": STORAGE_BASE,
        "folders": {
            "debug_images": os.path.exists(os.path.join(STORAGE_BASE, "debug_images")),
            "logs": os.path.exists(os.path.join(STORAGE_BASE, "logs")),
            "uploads": os.path.exists(os.path.join(STORAGE_BASE, "uploads"))
        }
    }

    return JSONResponse({
        "status": "healthy",
        "api_key_configured": bool(api_key),
        "api_key_preview": f"{api_key[:10]}...{api_key[-4:]}" if api_key else None,
        "claude_status": claude_status,
        "disk_status": disk_status,
        "message": "🚀 Somon.tj API работает!"
    })


@app.get("/api/test")
async def test_endpoint():
    """Простой тестовый эндпоинт"""
    return JSONResponse({
        "message": "✅ API работает!",
        "timestamp": "2025-06-14",
        "service": "Somon.tj"
    })


@app.get("/api/categories")
async def get_categories():
    """Получить структуру категорий Somon.tj"""
    try:
        categories = load_categories_from_file()
        return JSONResponse({
            "success": True,
            "categories": categories,
            "total_categories": len(categories),
            "message": "Категории успешно загружены"
        })
    except Exception as e:
        logger.error(f"Ошибка получения категорий: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "categories": {}
        }, status_code=500)


@app.get("/diagnostic", response_class=HTMLResponse)
async def diagnostic_page():
    """Диагностическая страница для анализа отдельных изображений"""
    try:
        return FileResponse('static/diagnostic.html')
    except Exception as e:
        logger.error(f"Ошибка загрузки диагностической страницы: {e}")
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Диагностика</title></head>
        <body>
            <h1>🔍 Диагностика изображений</h1>
            <p>Страница недоступна. Используйте API: POST /api/analyze-individual</p>
        </body>
        </html>
        """, status_code=500)


@app.get("/debug", response_class=HTMLResponse)
async def debug_page():
    """Отладочная страница"""
    try:
        return FileResponse('static/debug.html')
    except Exception as e:
        logger.error(f"Ошибка загрузки отладочной страницы: {e}")
        # Возвращаем встроенную отладочную страницу
        return HTMLResponse("""
        <!DOCTYPE html>
        <html>
        <head><title>Быстрая отладка</title></head>
        <body>
            <h1>🔧 Быстрая отладка Somon.tj</h1>
            <button onclick="fetch('/api/health').then(r=>r.json()).then(d=>alert(JSON.stringify(d,null,2)))">
                Проверить API
            </button>
            <hr>
            <div>
                <h3>Файлы статики:</h3>
                <ul>
                    <li><a href="/static/index.html">index.html</a></li>
                    <li><a href="/static/debug.html">debug.html</a></li>
                </ul>
            </div>
            <script>
                console.log('Быстрая отладка загружена');
                fetch('/api/health')
                    .then(r => r.json())
                    .then(data => console.log('API Health:', data))
                    .catch(e => console.error('API Error:', e));
            </script>
        </body>
        </html>
        """, status_code=200)


@app.get("/api/logs")
async def get_logs(lines: int = 100):
    """Получить последние строки логов"""
    try:
        log_file = os.path.join(STORAGE_BASE, "logs", "app.log")
        if not os.path.exists(log_file):
            return JSONResponse({
                "success": False,
                "message": "Файл логов не найден",
                "logs": []
            })

        # Читаем последние N строк
        with open(log_file, 'r', encoding='utf-8') as f:
            all_lines = f.readlines()
            recent_lines = all_lines[-lines:] if len(
                all_lines) > lines else all_lines

        return JSONResponse({
            "success": True,
            "total_lines": len(all_lines),
            "returned_lines": len(recent_lines),
            "logs": [line.strip() for line in recent_lines]
        })

    except Exception as e:
        logger.error(f"Ошибка чтения логов: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e),
            "logs": []
        }, status_code=500)


@app.get("/logs", response_class=HTMLResponse)
async def logs_page():
    """Веб-страница для просмотра логов"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Логи Somon.tj</title>
        <meta charset="utf-8">
        <style>
            body { font-family: monospace; margin: 20px; background: #1a1a1a; color: #00ff00; }
            .log-container { background: #000; padding: 20px; border-radius: 5px; max-height: 80vh; overflow-y: auto; }
            .log-line { margin: 2px 0; white-space: pre-wrap; }
            .error { color: #ff4444; }
            .warning { color: #ffaa00; }
            .info { color: #00ff00; }
            .controls { margin-bottom: 20px; }
            button { padding: 10px 20px; margin: 5px; background: #333; color: #fff; border: none; border-radius: 3px; cursor: pointer; }
            button:hover { background: #555; }
            select { padding: 8px; background: #333; color: #fff; border: 1px solid #555; }
        </style>
    </head>
    <body>
        <h1>📋 Логи Somon.tj</h1>
        
        <div class="controls">
            <button onclick="loadLogs()">🔄 Обновить</button>
            <button onclick="autoRefresh()">⏰ Авто-обновление</button>
            <button onclick="clearLogs()">🗑️ Очистить экран</button>
            <select id="lineCount">
                <option value="50">50 строк</option>
                <option value="100" selected>100 строк</option>
                <option value="200">200 строк</option>
                <option value="500">500 строк</option>
            </select>
        </div>
        
        <div class="log-container" id="logContainer">
            <div class="log-line">Загрузка логов...</div>
        </div>

        <script>
            let autoRefreshInterval = null;
            
            function loadLogs() {
                const lines = document.getElementById('lineCount').value;
                fetch(`/api/logs?lines=${lines}`)
                    .then(r => r.json())
                    .then(data => {
                        const container = document.getElementById('logContainer');
                        if (data.success) {
                            container.innerHTML = data.logs.map(line => {
                                let className = 'info';
                                if (line.includes('ERROR') || line.includes('❌')) className = 'error';
                                else if (line.includes('WARNING') || line.includes('⚠️')) className = 'warning';
                                
                                return `<div class="log-line ${className}">${escapeHtml(line)}</div>`;
                            }).join('');
                            container.scrollTop = container.scrollHeight;
                        } else {
                            container.innerHTML = `<div class="log-line error">Ошибка: ${data.error || data.message}</div>`;
                        }
                    })
                    .catch(e => {
                        document.getElementById('logContainer').innerHTML = 
                            `<div class="log-line error">Ошибка загрузки: ${e.message}</div>`;
                    });
            }
            
            function autoRefresh() {
                if (autoRefreshInterval) {
                    clearInterval(autoRefreshInterval);
                    autoRefreshInterval = null;
                    document.querySelector('button[onclick="autoRefresh()"]').textContent = '⏰ Авто-обновление';
                } else {
                    autoRefreshInterval = setInterval(loadLogs, 3000);
                    document.querySelector('button[onclick="autoRefresh()"]').textContent = '⏹️ Остановить';
                }
            }
            
            function clearLogs() {
                document.getElementById('logContainer').innerHTML = '<div class="log-line">Экран очищен. Нажмите "Обновить" для загрузки логов.</div>';
            }
            
            function escapeHtml(text) {
                const div = document.createElement('div');
                div.textContent = text;
                return div.innerHTML;
            }
            
            // Загружаем логи при старте
            loadLogs();
        </script>
    </body>
    </html>
    """)


@app.get("/debug-files/{session_id}")
async def get_debug_files(session_id: str):
    """Получить список отладочных файлов для сессии"""
    try:
        debug_folder = os.path.join(STORAGE_BASE, "debug_images", session_id)
        if not os.path.exists(debug_folder):
            raise HTTPException(status_code=404, detail="Сессия не найдена")

        # Читаем метаданные
        metadata_path = os.path.join(debug_folder, "metadata.json")
        if os.path.exists(metadata_path):
            with open(metadata_path, 'r', encoding='utf-8') as f:
                metadata = json.load(f)
        else:
            metadata = {"files": []}

        # Получаем список файлов
        files = []
        for filename in os.listdir(debug_folder):
            if filename != "metadata.json":
                file_path = os.path.join(debug_folder, filename)
                files.append({
                    "filename": filename,
                    "size": os.path.getsize(file_path),
                    "url": f"/debug-files/{session_id}/{filename}"
                })

        return JSONResponse({
            "success": True,
            "session_id": session_id,
            "metadata": metadata,
            "files": files
        })

    except Exception as e:
        logger.error(f"Ошибка получения отладочных файлов: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.get("/debug-files/{session_id}/{filename}")
async def get_debug_file(session_id: str, filename: str):
    """Получить конкретный отладочный файл"""
    try:
        file_path = os.path.join(
            STORAGE_BASE, "debug_images", session_id, filename)
        if not os.path.exists(file_path):
            raise HTTPException(status_code=404, detail="Файл не найден")

        return FileResponse(file_path)

    except Exception as e:
        logger.error(f"Ошибка получения файла: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/file-structure")
async def get_file_structure():
    """Получить структуру файлов проекта"""
    try:
        def scan_directory(path, max_depth=3, current_depth=0):
            items = []
            if current_depth >= max_depth:
                return items

            try:
                for item in sorted(os.listdir(path)):
                    if item.startswith('.'):
                        continue

                    item_path = os.path.join(path, item)
                    if os.path.isdir(item_path):
                        items.append({
                            "name": item,
                            "type": "directory",
                            "path": item_path,
                            "children": scan_directory(item_path, max_depth, current_depth + 1)
                        })
                    else:
                        try:
                            size = os.path.getsize(item_path)
                            items.append({
                                "name": item,
                                "type": "file",
                                "path": item_path,
                                "size": size
                            })
                        except:
                            items.append({
                                "name": item,
                                "type": "file",
                                "path": item_path,
                                "size": 0
                            })
            except PermissionError:
                pass

            return items

        # Сканируем текущую директорию
        current_dir = os.getcwd()
        structure = {
            "current_directory": current_dir,
            "structure": scan_directory(current_dir),
            "disk_usage": {}
        }

        # Добавляем информацию о дисковом пространстве
        try:
            import shutil
            total, used, free = shutil.disk_usage(current_dir)
            structure["disk_usage"] = {
                "total_gb": round(total / (1024**3), 2),
                "used_gb": round(used / (1024**3), 2),
                "free_gb": round(free / (1024**3), 2)
            }
        except:
            pass

        return JSONResponse({
            "success": True,
            "data": structure
        })

    except Exception as e:
        logger.error(f"Ошибка получения структуры файлов: {e}")
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)


@app.get("/file-browser", response_class=HTMLResponse)
async def file_browser():
    """Веб-браузер файлов"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Файловый браузер - Somon.tj</title>
        <meta charset="utf-8">
        <style>
            body { font-family: Arial, sans-serif; margin: 20px; background: #f5f5f5; }
            .container { max-width: 1200px; margin: 0 auto; background: white; padding: 20px; border-radius: 8px; }
            .file-tree { margin: 20px 0; }
            .file-item { margin: 5px 0; padding: 8px; border-radius: 4px; cursor: pointer; }
            .file-item:hover { background: #f0f0f0; }
            .directory { font-weight: bold; color: #2196F3; }
            .file { color: #666; }
            .file-size { color: #999; font-size: 0.9em; margin-left: 10px; }
            .indent-1 { margin-left: 20px; }
            .indent-2 { margin-left: 40px; }
            .indent-3 { margin-left: 60px; }
            .disk-info { background: #e3f2fd; padding: 15px; border-radius: 4px; margin-bottom: 20px; }
            .refresh-btn { background: #4CAF50; color: white; padding: 10px 20px; border: none; border-radius: 4px; cursor: pointer; }
            .refresh-btn:hover { background: #45a049; }
        </style>
    </head>
    <body>
        <div class="container">
            <h1>📁 Файловый браузер Somon.tj</h1>
            <button class="refresh-btn" onclick="loadFileStructure()">🔄 Обновить</button>
            
            <div id="diskInfo" class="disk-info">Загрузка информации о диске...</div>
            <div id="fileTree" class="file-tree">Загрузка структуры файлов...</div>
        </div>
        
        <script>
            function formatBytes(bytes) {
                if (bytes === 0) return '0 B';
                const k = 1024;
                const sizes = ['B', 'KB', 'MB', 'GB'];
                const i = Math.floor(Math.log(bytes) / Math.log(k));
                return parseFloat((bytes / Math.pow(k, i)).toFixed(2)) + ' ' + sizes[i];
            }
            
            function renderFileTree(items, depth = 0) {
                let html = '';
                for (const item of items) {
                    const indentClass = `indent-${Math.min(depth, 3)}`;
                    if (item.type === 'directory') {
                        html += `<div class="file-item directory ${indentClass}">📁 ${item.name}/</div>`;
                        if (item.children && item.children.length > 0) {
                            html += renderFileTree(item.children, depth + 1);
                        }
                    } else {
                        const size = item.size ? formatBytes(item.size) : '';
                        html += `<div class="file-item file ${indentClass}">📄 ${item.name}<span class="file-size">${size}</span></div>`;
                    }
                }
                return html;
            }
            
            async function loadFileStructure() {
                try {
                    const response = await fetch('/api/file-structure');
                    const data = await response.json();
                    
                    if (data.success) {
                        const structure = data.data;
                        
                        // Обновляем информацию о диске
                        const diskInfo = document.getElementById('diskInfo');
                        if (structure.disk_usage && structure.disk_usage.total_gb) {
                            diskInfo.innerHTML = `
                                <strong>💾 Дисковое пространство:</strong><br>
                                📊 Всего: ${structure.disk_usage.total_gb} GB<br>
                                📈 Использовано: ${structure.disk_usage.used_gb} GB<br>
                                📉 Свободно: ${structure.disk_usage.free_gb} GB<br>
                                📍 Текущая папка: ${structure.current_directory}
                            `;
                        } else {
                            diskInfo.innerHTML = `📍 Текущая папка: ${structure.current_directory}`;
                        }
                        
                        // Обновляем дерево файлов
                        const fileTree = document.getElementById('fileTree');
                        fileTree.innerHTML = renderFileTree(structure.structure);
                        
                    } else {
                        document.getElementById('fileTree').innerHTML = `<p>Ошибка: ${data.error}</p>`;
                    }
                } catch (error) {
                    document.getElementById('fileTree').innerHTML = `<p>Ошибка загрузки: ${error.message}</p>`;
                }
            }
            
            // Загружаем при старте
            loadFileStructure();
        </script>
    </body>
    </html>
    """)


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Запускаем сервер AIТовар.tj...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
