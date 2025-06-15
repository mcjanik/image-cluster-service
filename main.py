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
import io
from PIL import Image

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


def resize_image_for_claude(image_data: bytes, max_size: int = 2000) -> tuple[bytes, str]:
    """Изменяет размер изображения для соответствия ограничениям Claude API"""
    try:
        # Открываем изображение
        image = Image.open(io.BytesIO(image_data))

        # Получаем текущие размеры
        width, height = image.size
        logger.info(f"📐 Исходный размер изображения: {width}x{height}")

        # Проверяем нужно ли изменять размер
        if width <= max_size and height <= max_size:
            logger.info(
                f"✅ Размер изображения в пределах нормы ({max_size}px)")
            # Определяем MIME тип исходного изображения
            original_mime = "image/jpeg"
            if image.format == 'PNG':
                original_mime = "image/png"
            elif image.format == 'WEBP':
                original_mime = "image/webp"
            return image_data, original_mime

        # Вычисляем новые размеры с сохранением пропорций
        if width > height:
            new_width = max_size
            new_height = int((height * max_size) / width)
        else:
            new_height = max_size
            new_width = int((width * max_size) / height)

        logger.info(f"🔄 Изменяем размер до: {new_width}x{new_height}")

        # Изменяем размер
        resized_image = image.resize(
            (new_width, new_height), Image.Resampling.LANCZOS)

        # Сохраняем в байты
        output = io.BytesIO()

        # Определяем формат для сохранения с улучшенным сжатием
        output_mime = "image/jpeg"  # По умолчанию
        if image.format in ['JPEG', 'JPG']:
            resized_image.save(output, format='JPEG',
                               quality=75, optimize=True)  # Уменьшили quality для меньшего размера
            output_mime = "image/jpeg"
        elif image.format == 'PNG':
            resized_image.save(output, format='PNG', optimize=True)
            output_mime = "image/png"
        else:
            # Для WebP и других форматов сохраняем как JPEG с хорошим сжатием
            if resized_image.mode in ('RGBA', 'LA', 'P'):
                # Конвертируем в RGB для JPEG
                rgb_image = Image.new(
                    'RGB', resized_image.size, (255, 255, 255))
                if resized_image.mode == 'P':
                    resized_image = resized_image.convert('RGBA')
                rgb_image.paste(resized_image, mask=resized_image.split(
                )[-1] if resized_image.mode in ('RGBA', 'LA') else None)
                resized_image = rgb_image
            resized_image.save(output, format='JPEG',
                               quality=75, optimize=True)  # Уменьшили quality
            output_mime = "image/jpeg"

        resized_data = output.getvalue()
        size_change = len(resized_data)/len(image_data)*100
        logger.info(
            f"✅ Размер изменен: {len(image_data)} → {len(resized_data)} байт ({size_change:.1f}%)")
        logger.info(f"📎 Формат: {image.format} → {output_mime}")

        # Предупреждение если размер сильно увеличился
        if size_change > 150:
            logger.warning(
                f"⚠️ Размер файла увеличился на {size_change-100:.1f}% из-за конвертации {image.format} → JPEG")

        return resized_data, output_mime

    except ImportError:
        logger.warning("⚠️ PIL не установлен, пропускаем изменение размера")
        return image_data, "image/jpeg"
    except Exception as e:
        logger.error(f"❌ Ошибка изменения размера изображения: {e}")
        return image_data, "image/jpeg"


def save_debug_files(files_data: List[tuple], session_id: str) -> str:
    """Сохраняет файлы для отладки и возвращает путь к папке"""
    try:
        # Создаем папку для этой сессии
        session_folder = os.path.join(STORAGE_BASE, "debug_images", session_id)
        os.makedirs(session_folder, exist_ok=True)

        # Сохраняем каждый файл с индексом
        for idx, (contents, filename) in enumerate(files_data):
            # Всегда используем .webp расширение для единообразия
            debug_filename = f"{idx:02d}.webp"
            debug_path = os.path.join(session_folder, debug_filename)

            with open(debug_path, 'wb') as f:
                f.write(contents)

            logger.info(
                f"💾 Сохранен файл {idx}: {debug_filename} (оригинал: {filename}, {len(contents)} байт)")

        # Создаем файл с метаданными
        metadata = {
            "session_id": session_id,
            "timestamp": datetime.now().isoformat(),
            "total_files": len(files_data),
            "files": [
                {
                    "index": idx,
                    "original_filename": filename,
                    "debug_filename": f"{idx:02d}.webp",
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
            model="claude-sonnet-4-20250514",
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


def smart_group_products(descriptions: List[dict]) -> List[dict]:
    """Умная группировка товаров на основе их описаний"""
    groups = []
    used_indices = set()

    for i, desc1 in enumerate(descriptions):
        if i in used_indices:
            continue

        # Начинаем новую группу
        group = {
            "title": desc1.get("title", "Товар"),
            "category": desc1.get("category", "Разное"),
            "subcategory": desc1.get("subcategory", ""),
            "color": desc1.get("color", ""),
            "image_indexes": [i],
            "descriptions": [desc1.get("description", "")]
        }
        used_indices.add(i)

        # Ищем похожие товары
        for j, desc2 in enumerate(descriptions):
            if j <= i or j in used_indices:
                continue

            # Простое сравнение по названию и категории
            if (desc1.get("title", "").lower() == desc2.get("title", "").lower() and
                    desc1.get("category", "").lower() == desc2.get("category", "").lower()):
                group["image_indexes"].append(j)
                group["descriptions"].append(desc2.get("description", ""))
                used_indices.add(j)

        groups.append(group)

    return groups


def process_claude_results_with_filenames(products: List[dict], image_batch: List[tuple[bytes, str]], file_info: List[dict]) -> List[dict]:
    """
    Обрабатывает результаты Claude с использованием имен файлов вместо индексов
    Возвращает список товаров с изображениями
    """
    # Создаем словарь filename -> index для обратного поиска
    filename_to_index = {filename: i for i,
                         (_, filename) in enumerate(image_batch)}
    all_filenames = set(filename_to_index.keys())

    logger.info(
        f"🔧 Валидация имен файлов: всего файлов = {len(all_filenames)}")
    logger.info(f"📋 Доступные файлы: {sorted(all_filenames)}")

    # Собираем все использованные имена файлов
    all_used_filenames = []
    for product in products:
        original_filenames = product.get('image_filenames', [])
        valid_filenames = []

        for filename in original_filenames:
            if filename in filename_to_index:
                valid_filenames.append(filename)
                all_used_filenames.append(filename)
            else:
                logger.warning(
                    f"⚠️ Товар {product.get('title', '?')}: неверное имя файла '{filename}'")
                logger.warning(f"   Доступные файлы: {sorted(all_filenames)}")

        product['image_filenames'] = valid_filenames
        # Конвертируем в индексы для обратной совместимости
        product['image_indexes'] = [filename_to_index[f]
                                    for f in valid_filenames]

        if original_filenames != valid_filenames:
            logger.info(
                f"✅ Товар {product.get('title', '?')}: исправлены файлы {original_filenames} → {valid_filenames}")

    # Проверяем на пропущенные и дублированные файлы
    used_filenames = set(all_used_filenames)
    missing_filenames = all_filenames - used_filenames
    duplicate_filenames = [
        f for f in all_used_filenames if all_used_filenames.count(f) > 1]

    if missing_filenames:
        logger.warning(
            f"⚠️ Пропущенные файлы: {sorted(missing_filenames)}")
    if duplicate_filenames:
        logger.warning(
            f"⚠️ Дублированные файлы: {sorted(set(duplicate_filenames))}")

    logger.info(
        f"📊 Статистика файлов: использовано {len(used_filenames)}/{len(all_filenames)}")

    # Формируем результаты по группам товаров
    results = []

    for product_idx, product in enumerate(products):
        title = product.get('title', f'Товар {product_idx + 1}')
        category = product.get('category', 'Разное')
        subcategory = product.get('subcategory', '')
        color = product.get('color', '')
        image_filenames = product.get('image_filenames', [])
        image_indexes = product.get(
            'image_indexes', [])  # Уже валидированы выше

        logger.info(
            f"🔍 Обрабатываем товар {product_idx}: '{title}' с файлами {image_filenames}")

        # Используем уже валидированные индексы без повторной проверки
        valid_indexes = image_indexes

        # Если нет валидных индексов, используем первый доступный
        if not valid_indexes and file_info:
            valid_indexes = [0]
            image_filenames = [file_info[0]['filename']]
            logger.info(
                f"✅ Fallback: назначен файл {file_info[0]['filename']} для товара '{title}'")

        # Собираем изображения для этого товара
        product_images = []
        actual_filenames = []

        for img_idx in valid_indexes:
            if img_idx < len(file_info):
                info = file_info[img_idx]
                image_base64 = base64.b64encode(
                    info['contents']).decode('utf-8')
                product_images.append(
                    f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}")
                actual_filenames.append(info['filename'])
                logger.info(
                    f"  ✅ Добавлено изображение: {info['filename']}")

        if not product_images and file_info:  # Fallback если нет изображений
            info = file_info[0]
            image_base64 = base64.b64encode(
                info['contents']).decode('utf-8')
            product_images.append(
                f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}")
            valid_indexes = [0]
            actual_filenames = [info['filename']]

        logger.info(
            f"  📸 Итого изображений для '{title}': {len(product_images)} ({actual_filenames})")

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
            "size_bytes": sum(file_info[i]['size'] for i in valid_indexes if i < len(file_info)),
            "images": product_images,
            "image_preview": product_images[0] if product_images else "",
            "description": description,
            "title": title,
            "category": category,
            "subcategory": subcategory,
            "color": color,
            "image_indexes": valid_indexes,
            "image_filenames": actual_filenames
        })

    logger.info(f"✅ Сформировано {len(results)} товарных групп")
    return results


def analyze_images_batch_with_claude(image_batch: List[tuple[bytes, str]]) -> str:
    """
    Анализирует batch изображений с Claude API для группировки товаров
    Теперь использует имена файлов вместо индексов для большей надежности
    """
    try:
        # Инициализация клиента
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            logger.error("❌ API ключ Anthropic не настроен!")
            raise ValueError(
                "API ключ Anthropic не настроен в переменных окружения")

        client = anthropic.Anthropic(
            api_key=api_key,
            timeout=120.0,  # Увеличиваем таймаут до 2 минут
            max_retries=2   # Ограничиваем количество повторных попыток
        )
        logger.info(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")

        # Подготавливаем изображения для batch запроса
        image_contents = []
        file_list = []

        for i, (image_data, filename) in enumerate(image_batch):
            logger.info(f"🖼️ Обработка изображения: {filename}")

            # Изменяем размер изображения для соответствия ограничениям Claude
            resized_image_data, mime_type = resize_image_for_claude(
                image_data, max_size=2000)

            # Кодируем изображение в base64
            base64_image = base64.b64encode(resized_image_data).decode('utf-8')

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

            file_list.append(filename)

        # НОВЫЙ ПРОМПТ: используем имена файлов вместо индексов
        batch_prompt = f"""ГРУППИРОВКА ТОВАРОВ: Проанализируйте эти {len(image_batch)} изображений и сгруппируй ОДИНАКОВЫЕ товары.

СПИСОК ФАЙЛОВ (используйте ТОЧНЫЕ имена файлов):
{chr(10).join([f"- {filename}" for filename in file_list])}

ЗАДАЧА: Найти изображения которые показывают ОДИН И ТОТ ЖЕ товар с разных ракурсов.

ПРАВИЛА:
1. Внимательно сравните каждое изображение
2. Группируйте только ИДЕНТИЧНЫЕ предметы (одна и та же стиральная машина, один и тот же кондиционер)
3. Разные модели/цвета/размеры = разные товары
4. При малейшем сомнении - лучше разделить
5. ИСПОЛЬЗУЙТЕ ТОЧНЫЕ ИМЕНА ФАЙЛОВ из списка выше

Используйте категории: {SOMON_CATEGORIES}

ФОРМАТ ОТВЕТА - детальный JSON с объяснениями:
[
  {{
    "group_id": 1,
    "title": "Название товара",
    "category": "Категория",
    "subcategory": "Подкатегория",
    "color": "цвет",
    "reasoning": "Почему эти изображения сгруппированы вместе",
    "image_filenames": ["точное_имя_файла1.jpg", "точное_имя_файла2.jpg"],
    "description": "Детальное описание товара"
  }}
]

ВАЖНО:
- Используйте только имена файлов из списка выше
- Каждое имя файла должно использоваться РОВНО ОДИН РАЗ
- Объясните свои решения в поле "reasoning"!

ВЕРНИТЕ ТОЛЬКО JSON БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА."""

        logger.info("🚀 ОТПРАВЛЯЕМ BATCH ЗАПРОС В CLAUDE API...")

        # Отправляем batch запрос к Claude с параметрами как на claude.ai
        message = client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=8192,
            temperature=0,  # Делаем ответы более детерминированными
            system="You are a helpful assistant that analyzes images accurately. When grouping images, be EXTREMELY careful with filenames. Use EXACT filenames from the provided list. Each filename must be used exactly once.",
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
            f"✅ ПОЛУЧЕН ОТВЕТ ОТ CLAUDE! Длина: {len(response_text)} символов")

        return response_text

    except anthropic.APITimeoutError as e:
        logger.error(f"❌ ТАЙМАУТ Claude API: {e}")
        raise ValueError(f"Таймаут Claude API: {str(e)}")
    except anthropic.RateLimitError as e:
        logger.error(f"❌ ЛИМИТ ЗАПРОСОВ Claude API: {e}")
        raise ValueError(f"Превышен лимит запросов Claude API: {str(e)}")
    except anthropic.APIError as e:
        logger.error(f"❌ ОШИБКА Claude API: {e}")
        raise ValueError(f"Ошибка Claude API: {str(e)}")
    except Exception as e:
        logger.error(
            f"❌ Неожиданная ошибка при анализе batch: {e}\n{traceback.format_exc()}")
        raise ValueError(f"Ошибка анализа изображений: {str(e)}")


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

        # ИСПРАВЛЕНИЕ: НЕ сортируем файлы, сохраняем исходный порядок от пользователя
        # Проблема была в том что сортировка ломала соответствие индексов!
        logger.info(f"📋 Сохраняем исходный порядок файлов (БЕЗ сортировки):")
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

        logger.info(f"🔍 ДЕТАЛЬНАЯ ДИАГНОСТИКА:")
        logger.info(f"  📁 Всего файлов получено: {len(files)}")
        logger.info(f"  ✅ Валидных изображений: {len(image_batch)}")
        logger.info(f"  📋 Порядок валидных файлов:")
        for i, (_, filename) in enumerate(image_batch):
            saved_filename = f"{i:02d}.webp"
            logger.info(
                f"    Индекс {i}: {saved_filename} (оригинал: {filename})")

        # Подготавливаем изображения для batch запроса
        image_contents = []
        for i, (image_data, filename) in enumerate(image_batch):
            logger.info(f"🖼️ Диагностика изображения {i}: {filename}")

            # Изменяем размер изображения для соответствия ограничениям Claude
            resized_image_data, mime_type = resize_image_for_claude(
                image_data, max_size=2000)

            # Кодируем изображение в base64
            base64_image = base64.b64encode(resized_image_data).decode('utf-8')

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

        # Создаем список файлов для промпта
        file_list = [filename for _, filename in image_batch]

        # Упрощенный промпт для точного анализа товаров - ТЕПЕРЬ ИСПОЛЬЗУЕТ ИМЕНА ФАЙЛОВ
        diagnostic_prompt = f"""Проанализируй эти {len(image_batch)} изображений товаров и сгруппируй ОДИНАКОВЫЕ товары.

СПИСОК ФАЙЛОВ (используйте ТОЧНЫЕ имена файлов):
{chr(10).join([f"- {filename}" for filename in file_list])}

ВАЖНО: Группируй только абсолютно идентичные товары:
- Одинаковая модель, бренд, артикул
- Одинаковый цвет и размер  
- Одинаковая комплектация
- Разные ракурсы одного товара = одна группа
- Разные модели/цвета = разные группы
- ИСПОЛЬЗУЙТЕ ТОЧНЫЕ ИМЕНА ФАЙЛОВ из списка выше

Верни результат в JSON формате:
[
  {{
    "group_id": 1,
    "title": "Точное название товара с моделью",
    "category": "Категория",
    "subcategory": "Подкатегория", 
    "color": "основной цвет",
    "reasoning": "Почему эти фото в одной группе",
    "image_filenames": ["точное_имя_файла1.jpg", "точное_имя_файла2.jpg"],
    "description": "Подробное описание товара"
  }}
]

Каждое имя файла должно использоваться только один раз."""

        try:
            # Инициализация клиента
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("❌ API ключ Anthropic не настроен!")
                raise ValueError(
                    "API ключ Anthropic не настроен в переменных окружения")

            client = anthropic.Anthropic(
                api_key=api_key,
                timeout=120.0,  # Увеличиваем таймаут до 2 минут
                max_retries=2   # Ограничиваем количество повторных попыток
            )
            logger.info(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")

            logger.info("🚀 ОТПРАВЛЯЕМ ДИАГНОСТИЧЕСКИЙ ЗАПРОС В CLAUDE API...")

            # Отправляем batch запрос к Claude с оптимальными параметрами для анализа товаров
            try:
                message = client.messages.create(
                    model="claude-sonnet-4-20250514",  # Оставляем эту модель
                    max_tokens=8192,
                    temperature=0.3,  # Увеличиваем для более вдумчивого анализа
                    system="""Ты эксперт по анализу товаров для интернет-магазина. Твоя задача:
1. Внимательно изучить каждое изображение
2. Сгруппировать фотографии одного и того же товара
3. Определить точные названия, модели, цвета
4. Создать структурированное описание для каждой группы
5. Указать подходящие категории для сайта объявлений

Основные принципы:
- Внимательно изучать детали на каждом изображении
- Идентифицировать бренды, модели, артикулы, надписи
- Различать цвета, размеры, варианты одного товара
- Группировать только идентичные товары
- Обращать внимание на упаковку, этикетки, состояние товара

КРИТИЧЕСКИ ВАЖНО - ТОЧНОСТЬ ГРУППИРОВКИ:
- Разные модели = разные группы (даже одного бренда)
- Разные цвета = разные группы (даже одной модели)
- Разные размеры = разные группы
- Разные категории товаров = разные группы
- Только абсолютно идентичные товары в одной группе

ПРИНЦИПЫ АНАЛИЗА:
✅ Внимательно сравнивай каждую деталь
✅ Читай надписи, бренды, модели на товарах
✅ Различай даже похожие товары разных категорий
✅ При сомнениях - создавай отдельные группы
❌ НЕ объединяй похожие, но разные товары
❌ НЕ игнорируй различия в цвете, размере, модели

Анализируй изображения с максимальной точностью. Группируй только абсолютно идентичные товары.""",
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
            except anthropic.APITimeoutError as timeout_error:
                logger.error(f"❌ ТАЙМАУТ CLAUDE API: {timeout_error}")
                raise ValueError(
                    f"Таймаут Claude API (попробуйте позже): {str(timeout_error)}")
            except anthropic.RateLimitError as rate_error:
                logger.error(
                    f"❌ ПРЕВЫШЕН ЛИМИТ ЗАПРОСОВ CLAUDE API: {rate_error}")
                raise ValueError(
                    f"Превышен лимит запросов Claude API: {str(rate_error)}")
            except anthropic.APIError as api_error:
                logger.error(f"❌ ОШИБКА CLAUDE API: {api_error}")
                raise ValueError(f"Ошибка Claude API: {str(api_error)}")
            except Exception as api_error:
                logger.error(
                    f"❌ НЕИЗВЕСТНАЯ ОШИБКА ВЫЗОВА CLAUDE API: {api_error}")
                raise ValueError(
                    f"Неизвестная ошибка вызова Claude API: {str(api_error)}")

            # Проверяем что ответ содержит контент
            if not message.content or len(message.content) == 0:
                logger.error("❌ ПУСТОЙ CONTENT В ОТВЕТЕ CLAUDE!")
                raise ValueError("Claude вернул пустой content")

            response_text = message.content[0].text
            logger.info(
                f"✅ ПОЛУЧЕН ДИАГНОСТИЧЕСКИЙ ОТВЕТ! Длина: {len(response_text)} символов")
            logger.info(f"🔍 ПОЛНЫЙ ОТВЕТ: {response_text}")

            # Проверяем что ответ не пустой
            if not response_text or not response_text.strip():
                logger.error("❌ ПУСТОЙ ОТВЕТ ОТ CLAUDE!")
                raise ValueError("Claude вернул пустой ответ")

            # Проверяем что ответ не является HTML (ошибка сети)
            if response_text.strip().startswith('<'):
                logger.error(
                    "❌ ДИАГНОСТИКА: ПОЛУЧЕН HTML ВМЕСТО JSON! Возможно ошибка сети или перегрузка API")
                logger.error(f"🔍 HTML ответ: {response_text[:500]}...")
                raise ValueError(
                    "Claude вернул HTML вместо JSON (ошибка сети или перегрузка API)")

            # Парсим JSON ответ - ИСПРАВЛЕННАЯ ЛОГИКА ИЗВЛЕЧЕНИЯ ИЗ MARKDOWN
            if response_text.strip().startswith('```'):
                # Извлекаем JSON из markdown блока
                lines = response_text.strip().split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip() == '```json' or (line.strip() == '```' and in_json):
                        in_json = not in_json
                        continue
                    if in_json:  # ИСПРАВЛЕНО: добавляем строки ТОЛЬКО когда внутри JSON блока
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)
                logger.info(
                    f"🔧 Извлечен JSON из markdown блока, новая длина: {len(response_text)}")
                # Показываем первые 200 символов
                logger.info(f"🔧 Извлеченный JSON: {response_text[:200]}...")
            else:
                # Если нет markdown блоков, пытаемся найти JSON в тексте
                # Ищем первый '[' и последний ']' для извлечения JSON массива
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx:end_idx+1]
                    logger.info(
                        f"🔧 Извлечен JSON без markdown, длина: {len(response_text)}")
                    logger.info(
                        f"🔧 Извлеченный JSON: {response_text[:200]}...")

            # Проверяем что после извлечения из markdown у нас есть контент
            if not response_text.strip():
                logger.error("❌ ПУСТОЙ JSON ПОСЛЕ ИЗВЛЕЧЕНИЯ ИЗ MARKDOWN!")
                raise ValueError("Не удалось извлечь JSON из ответа Claude")

            # ДЕТАЛЬНАЯ ДИАГНОСТИКА ПЕРЕД ПАРСИНГОМ JSON
            logger.info(f"🔍 ДИАГНОСТИЧЕСКАЯ ФИНАЛЬНАЯ ДИАГНОСТИКА JSON:")
            logger.info(f"  📏 Длина: {len(response_text)}")
            logger.info(f"  🔤 Первые 10 символов: {repr(response_text[:10])}")
            logger.info(
                f"  🔤 Последние 10 символов: {repr(response_text[-10:])}")
            logger.info(f"  ✂️ После strip(): {len(response_text.strip())}")
            logger.info(
                f"  🎯 Начинается с '[': {response_text.strip().startswith('[')}")
            logger.info(
                f"  🎯 Заканчивается на ']': {response_text.strip().endswith(']')}")

            # Попытка парсинга с детальной диагностикой
            try:
                products = json.loads(response_text)
                logger.info(
                    f"✅ ДИАГНОСТИКА: JSON успешно распарсен! Тип: {type(products)}, длина: {len(products) if isinstance(products, list) else 'не список'}")
            except json.JSONDecodeError as json_error:
                logger.error(
                    f"❌ ДИАГНОСТИКА: ОШИБКА JSON ПАРСИНГА: {json_error}")
                logger.error(
                    f"🔍 Позиция ошибки: строка {json_error.lineno}, колонка {json_error.colno}")
                logger.error(
                    f"🔍 Проблемный фрагмент: {repr(response_text[max(0, json_error.pos-20):json_error.pos+20])}")
                raise

            if not isinstance(products, list):
                raise ValueError("Ответ Claude не является списком")

            # Используем новую функцию для обработки результатов с именами файлов
            results = process_claude_results_with_filenames(
                products, image_batch, file_info)

            return JSONResponse({
                "success": True,
                "diagnostic_mode": "grouping",
                "total_images": len(image_batch),
                "groups": results,
                "raw_response": response_text,
                "debug_folder": debug_folder,
                "session_id": session_id,
                "file_order": [{"index": i, "filename": filename} for i, (_, filename) in enumerate(image_batch)],
                "image_urls": [f"/debug-files/{session_id}/{i:02d}.webp" for i, (_, filename) in enumerate(image_batch)],
                "message": "Диагностика группировки завершена"
            })

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПАРСИНГА JSON: {e}")
            logger.error(f"🔍 ПОЛНЫЙ ОТВЕТ CLAUDE: {response_text}")
            logger.error(f"🔍 ТИП ОТВЕТА: {type(response_text)}")
            logger.error(f"🔍 ДЛИНА ОТВЕТА: {len(response_text)} символов")
            # НЕ ИСПОЛЬЗУЕМ FALLBACK! Возвращаем ошибку как в диагностике
            return JSONResponse({
                "success": False,
                "error": f"Ошибка парсинга JSON от Claude: {str(e)}",
                "raw_response": response_text,
                "debug_folder": debug_folder,
                "session_id": session_id
            }, status_code=500)

        # НЕТ FALLBACK! Если дошли сюда, значит есть ошибка в логике
        logger.error("❌ НЕДОСТИЖИМЫЙ КОД: дошли до конца функции без return")
        return JSONResponse({
            "success": False,
            "error": "Внутренняя ошибка: недостижимый код выполнен"
        }, status_code=500)

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

            # Изменяем размер изображения для соответствия ограничениям Claude
            resized_image_data, mime_type = resize_image_for_claude(
                image_data, max_size=2000)

            # Кодируем изображение в base64
            image_base64 = base64.b64encode(resized_image_data).decode('utf-8')

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
                    model="claude-sonnet-4-20250514",
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
            "image_urls": [f"/debug-files/{session_id}/{i:02d}.webp" for i, (_, filename) in enumerate(image_batch)],
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
    """Основная функция группировки товаров - использует проверенную логику диагностики"""
    try:
        logger.info(f"🔍 ОСНОВНАЯ ГРУППИРОВКА: Получено {len(files)} файлов")

        # Собираем все валидные изображения
        image_batch = []
        file_info = []

        logger.info(f"📋 Порядок получения файлов:")
        for i, file in enumerate(files):
            logger.info(f"  {i}: {file.filename} ({file.content_type})")

        # НЕ сортируем файлы, сохраняем исходный порядок от пользователя
        logger.info(f"📋 Сохраняем исходный порядок файлов (БЕЗ сортировки):")
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
        session_id = f"main_{int(time.time())}_{len(image_batch)}"
        debug_folder = save_debug_files(image_batch, session_id)

        logger.info(f"🔍 ДЕТАЛЬНАЯ ДИАГНОСТИКА:")
        logger.info(f"  📁 Всего файлов получено: {len(files)}")
        logger.info(f"  ✅ Валидных изображений: {len(image_batch)}")
        logger.info(f"  📋 Порядок валидных файлов:")
        for i, (_, filename) in enumerate(image_batch):
            saved_filename = f"{i:02d}.webp"
            logger.info(
                f"    Индекс {i}: {saved_filename} (оригинал: {filename})")

        # Подготавливаем изображения для batch запроса
        image_contents = []
        for i, (image_data, filename) in enumerate(image_batch):
            logger.info(f"🖼️ Обработка изображения {i}: {filename}")

            # Изменяем размер изображения для соответствия ограничениям Claude
            resized_image_data, mime_type = resize_image_for_claude(
                image_data, max_size=2000)

            # Кодируем изображение в base64
            base64_image = base64.b64encode(resized_image_data).decode('utf-8')

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

        # Упрощенный промпт для точного анализа товаров
        main_prompt = f"""Проанализируй эти {len(image_batch)} изображений товаров и сгруппируй ОДИНАКОВЫЕ товары.

Изображения пронумерованы от 0 до {len(image_batch)-1}.

ВАЖНО: Группируй только абсолютно идентичные товары:
- Одинаковая модель, бренд, артикул
- Одинаковый цвет и размер  
- Одинаковая комплектация
- Разные ракурсы одного товара = одна группа
- Разные модели/цвета = разные группы

Верни результат в JSON формате:
[
  {{
    "group_id": 1,
    "title": "Точное название товара с моделью",
    "category": "Категория",
    "subcategory": "Подкатегория", 
    "color": "основной цвет",
    "reasoning": "Почему эти фото в одной группе",
    "image_indexes": [список_номеров_фото],
    "description": "Подробное описание товара"
  }}
]

Каждый номер фото должен использоваться только один раз."""

        try:
            # Инициализация клиента
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("❌ API ключ Anthropic не настроен!")
                raise ValueError(
                    "API ключ Anthropic не настроен в переменных окружения")

            client = anthropic.Anthropic(
                api_key=api_key,
                timeout=120.0,  # Увеличиваем таймаут до 2 минут
                max_retries=2   # Ограничиваем количество повторных попыток
            )
            logger.info(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")

            logger.info("🚀 ОТПРАВЛЯЕМ ОСНОВНОЙ ЗАПРОС В CLAUDE API...")

            # Отправляем batch запрос к Claude с оптимальными параметрами для анализа товаров
            try:
                message = client.messages.create(
                    model="claude-sonnet-4-20250514",  # Оставляем эту модель
                    max_tokens=8192,
                    temperature=0.3,  # Увеличиваем для более вдумчивого анализа
                    system="""Ты эксперт по анализу товаров для интернет-магазина. Твоя задача:
1. Внимательно изучить каждое изображение
2. Сгруппировать фотографии одного и того же товара
3. Определить точные названия, модели, цвета
4. Создать структурированное описание для каждой группы
5. Указать подходящие категории для сайта объявлений

Основные принципы:
- Внимательно изучать детали на каждом изображении
- Идентифицировать бренды, модели, артикулы, надписи
- Различать цвета, размеры, варианты одного товара
- Группировать только идентичные товары
- Обращать внимание на упаковку, этикетки, состояние товара

КРИТИЧЕСКИ ВАЖНО - ТОЧНОСТЬ ГРУППИРОВКИ:
- Разные модели = разные группы (даже одного бренда)
- Разные цвета = разные группы (даже одной модели)
- Разные размеры = разные группы
- Разные категории товаров = разные группы
- Только абсолютно идентичные товары в одной группе

ПРИНЦИПЫ АНАЛИЗА:
✅ Внимательно сравнивай каждую деталь
✅ Читай надписи, бренды, модели на товарах
✅ Различай даже похожие товары разных категорий
✅ При сомнениях - создавай отдельные группы
❌ НЕ объединяй похожие, но разные товары
❌ НЕ игнорируй различия в цвете, размере, модели

Анализируй изображения с максимальной точностью. Группируй только абсолютно идентичные товары.""",
                    messages=[
                        {
                            "role": "user",
                            "content": [
                                *image_contents,
                                {
                                    "type": "text",
                                    "text": main_prompt
                                }
                            ],
                        }
                    ],
                )
            except anthropic.APITimeoutError as timeout_error:
                logger.error(f"❌ ТАЙМАУТ CLAUDE API: {timeout_error}")
                raise ValueError(
                    f"Таймаут Claude API (попробуйте позже): {str(timeout_error)}")
            except anthropic.RateLimitError as rate_error:
                logger.error(
                    f"❌ ПРЕВЫШЕН ЛИМИТ ЗАПРОСОВ CLAUDE API: {rate_error}")
                raise ValueError(
                    f"Превышен лимит запросов Claude API: {str(rate_error)}")
            except anthropic.APIError as api_error:
                logger.error(f"❌ ОШИБКА CLAUDE API: {api_error}")
                raise ValueError(f"Ошибка Claude API: {str(api_error)}")
            except Exception as api_error:
                logger.error(
                    f"❌ НЕИЗВЕСТНАЯ ОШИБКА ВЫЗОВА CLAUDE API: {api_error}")
                raise ValueError(
                    f"Неизвестная ошибка вызова Claude API: {str(api_error)}")

            # Проверяем что ответ содержит контент
            if not message.content or len(message.content) == 0:
                logger.error("❌ ПУСТОЙ CONTENT В ОТВЕТЕ CLAUDE!")
                raise ValueError("Claude вернул пустой content")

            response_text = message.content[0].text
            logger.info(
                f"✅ ПОЛУЧЕН ОСНОВНОЙ ОТВЕТ! Длина: {len(response_text)} символов")
            logger.info(f"🔍 ПОЛНЫЙ ОТВЕТ: {response_text}")

            # Проверяем что ответ не пустой
            if not response_text or not response_text.strip():
                logger.error("❌ ПУСТОЙ ОТВЕТ ОТ CLAUDE!")
                raise ValueError("Claude вернул пустой ответ")

            # Проверяем что ответ не является HTML (ошибка сети)
            if response_text.strip().startswith('<'):
                logger.error(
                    "❌ ПОЛУЧЕН HTML ВМЕСТО JSON! Возможно ошибка сети или перегрузка API")
                logger.error(f"🔍 HTML ответ: {response_text[:500]}...")
                raise ValueError(
                    "Claude вернул HTML вместо JSON (ошибка сети или перегрузка API)")

            # Парсим JSON ответ - ИСПРАВЛЕННАЯ ЛОГИКА ИЗВЛЕЧЕНИЯ ИЗ MARKDOWN
            if response_text.strip().startswith('```'):
                # Извлекаем JSON из markdown блока
                lines = response_text.strip().split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip() == '```json' or (line.strip() == '```' and in_json):
                        in_json = not in_json
                        continue
                    if in_json:  # ИСПРАВЛЕНО: добавляем строки ТОЛЬКО когда внутри JSON блока
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)
                logger.info(
                    f"🔧 Извлечен JSON из markdown блока, новая длина: {len(response_text)}")
                # Показываем первые 200 символов
                logger.info(f"🔧 Извлеченный JSON: {response_text[:200]}...")
            else:
                # Если нет markdown блоков, пытаемся найти JSON в тексте
                # Ищем первый '[' и последний ']' для извлечения JSON массива
                start_idx = response_text.find('[')
                end_idx = response_text.rfind(']')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx:end_idx+1]
                    logger.info(
                        f"🔧 Извлечен JSON без markdown, длина: {len(response_text)}")
                    logger.info(
                        f"🔧 Извлеченный JSON: {response_text[:200]}...")

            # Проверяем что после извлечения из markdown у нас есть контент
            if not response_text.strip():
                logger.error("❌ ПУСТОЙ JSON ПОСЛЕ ИЗВЛЕЧЕНИЯ ИЗ MARKDOWN!")
                raise ValueError("Не удалось извлечь JSON из ответа Claude")

            # ДЕТАЛЬНАЯ ДИАГНОСТИКА ПЕРЕД ПАРСИНГОМ JSON
            logger.info(f"🔍 ФИНАЛЬНАЯ ДИАГНОСТИКА JSON:")
            logger.info(f"  📏 Длина: {len(response_text)}")
            logger.info(f"  🔤 Первые 10 символов: {repr(response_text[:10])}")
            logger.info(
                f"  🔤 Последние 10 символов: {repr(response_text[-10:])}")
            logger.info(f"  ✂️ После strip(): {len(response_text.strip())}")
            logger.info(
                f"  🎯 Начинается с '[': {response_text.strip().startswith('[')}")
            logger.info(
                f"  🎯 Заканчивается на ']': {response_text.strip().endswith(']')}")

            # Попытка парсинга с детальной диагностикой
            try:
                products = json.loads(response_text)
                logger.info(
                    f"✅ JSON успешно распарсен! Тип: {type(products)}, длина: {len(products) if isinstance(products, list) else 'не список'}")
            except json.JSONDecodeError as json_error:
                logger.error(f"❌ ОШИБКА JSON ПАРСИНГА: {json_error}")
                logger.error(
                    f"🔍 Позиция ошибки: строка {json_error.lineno}, колонка {json_error.colno}")
                logger.error(
                    f"🔍 Проблемный фрагмент: {repr(response_text[max(0, json_error.pos-20):json_error.pos+20])}")
                raise

            if not isinstance(products, list):
                raise ValueError("Ответ Claude не является списком")

            # Используем новую функцию для обработки результатов с именами файлов
            results = process_claude_results_with_filenames(
                products, image_batch, file_info)

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
            logger.error(f"❌ КРИТИЧЕСКАЯ ОШИБКА ПАРСИНГА JSON: {e}")
            logger.error(f"🔍 ПОЛНЫЙ ОТВЕТ CLAUDE: {response_text}")
            logger.error(f"🔍 ТИП ОТВЕТА: {type(response_text)}")
            logger.error(f"🔍 ДЛИНА ОТВЕТА: {len(response_text)} символов")
            return JSONResponse({
                "success": False,
                "error": f"Ошибка парсинга JSON от Claude: {str(e)}",
                "raw_response": response_text,
                "debug_folder": debug_folder,
                "session_id": session_id
            }, status_code=500)

    except Exception as e:
        logger.error(
            f"❌ Ошибка основного анализа: {e}\n{traceback.format_exc()}")
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


@app.post("/api/analyze-product-detailed")
async def analyze_product_detailed(files: List[UploadFile] = File(...)):
    """Детальный анализ одного товара с множественными фотографиями"""
    try:
        logger.info(
            f"🔍 ДЕТАЛЬНЫЙ АНАЛИЗ ТОВАРА: Получено {len(files)} фотографий")

        # Собираем все валидные изображения
        image_batch = []
        file_info = []

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
        session_id = f"detailed_{int(time.time())}_{len(image_batch)}"
        debug_folder = save_debug_files(image_batch, session_id)

        # Подготавливаем изображения для анализа
        image_contents = []
        for i, (image_data, filename) in enumerate(image_batch):
            logger.info(f"🖼️ Обработка изображения {i}: {filename}")

            resized_image_data, mime_type = resize_image_for_claude(
                image_data, max_size=2000)
            base64_image = base64.b64encode(resized_image_data).decode('utf-8')

            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": base64_image
                }
            })

        # Детальный промпт для анализа товара
        detailed_prompt = f"""Проанализируй эти {len(image_batch)} фотографий ОДНОГО товара и заполни максимально подробную информацию.

ЗАДАЧА: Создать детальное описание товара для объявления на сайте Somon.tj

Верни результат в JSON формате:
{{
  "title": "Точное название товара с брендом и моделью",
  "brand": "Бренд/производитель",
  "model": "Модель/артикул",
  "category": "Основная категория",
  "subcategory": "Подкатегория",
  "condition": "Состояние (новый/б/у/отличное/хорошее/удовлетворительное)",
  "color": "Основной цвет",
  "material": "Материал изготовления",
  "size": "Размер/габариты",
  "weight": "Вес (если видно)",
  "year": "Год выпуска (если определим)",
  "country": "Страна производства (если видно)",
  "features": ["список", "ключевых", "особенностей", "и", "функций"],
  "included": ["что", "входит", "в", "комплект"],
  "defects": ["видимые", "дефекты", "или", "износ"],
  "description": "Подробное описание товара для объявления",
  "keywords": ["ключевые", "слова", "для", "поиска"],
  "estimated_price_range": "Примерная ценовая категория",
  "target_audience": "Целевая аудитория",
  "usage_tips": "Советы по использованию",
  "care_instructions": "Инструкции по уходу",
  "compatibility": "Совместимость с другими товарами",
  "technical_specs": {{
    "spec1": "значение1",
    "spec2": "значение2"
  }},
  "photo_analysis": {{
    "main_photo": "номер лучшего фото для главного изображения (0-{len(image_batch)-1})",
    "photo_descriptions": ["описание фото 0", "описание фото 1", "..."]
  }}
}}

ВАЖНО:
- Анализируй ВСЕ детали на фотографиях
- Читай все надписи, этикетки, бирки
- Определяй технические характеристики
- Оценивай состояние и дефекты
- Предлагай лучшее фото для главного изображения
- Если информация не видна, указывай "не определено"
"""

        try:
            # Инициализация клиента
            api_key = os.getenv("ANTHROPIC_API_KEY")
            if not api_key:
                logger.error("❌ API ключ Anthropic не настроен!")
                raise ValueError(
                    "API ключ Anthropic не настроен в переменных окружения")

            client = anthropic.Anthropic(
                api_key=api_key,
                timeout=120.0,
                max_retries=2
            )

            logger.info("🚀 ОТПРАВЛЯЕМ ДЕТАЛЬНЫЙ ЗАПРОС В CLAUDE API...")

            message = client.messages.create(
                model="claude-sonnet-4-20250514",
                max_tokens=8192,
                temperature=0.1,  # Низкая температура для точности
                system="""Ты эксперт по анализу товаров для интернет-магазина. Твоя задача - создать максимально подробное и точное описание товара на основе фотографий.

Принципы анализа:
- Внимательно изучай каждую деталь на фотографиях
- Читай все видимые надписи, этикетки, бирки
- Определяй бренд, модель, технические характеристики
- Оценивай состояние и выявляй дефекты
- Анализируй материалы, цвета, размеры
- Определяй комплектность и аксессуары
- Предлагай ключевые слова для поиска
- Создавай привлекательное описание для покупателей

Будь максимально точным и детальным в анализе.""",
                messages=[
                    {
                        "role": "user",
                        "content": [
                            *image_contents,
                            {
                                "type": "text",
                                "text": detailed_prompt
                            }
                        ],
                    }
                ],
            )

            response_text = message.content[0].text
            logger.info(
                f"✅ ПОЛУЧЕН ДЕТАЛЬНЫЙ ОТВЕТ! Длина: {len(response_text)} символов")

            # Проверяем что ответ не является HTML
            if response_text.strip().startswith('<'):
                logger.error("❌ ПОЛУЧЕН HTML ВМЕСТО JSON!")
                raise ValueError("Claude вернул HTML вместо JSON")

            # Извлекаем JSON
            if response_text.strip().startswith('```'):
                lines = response_text.strip().split('\n')
                json_lines = []
                in_json = False
                for line in lines:
                    if line.strip() == '```json' or (line.strip() == '```' and in_json):
                        in_json = not in_json
                        continue
                    if in_json:
                        json_lines.append(line)
                response_text = '\n'.join(json_lines)
            else:
                # Ищем JSON в тексте
                start_idx = response_text.find('{')
                end_idx = response_text.rfind('}')
                if start_idx != -1 and end_idx != -1 and end_idx > start_idx:
                    response_text = response_text[start_idx:end_idx+1]

            product_data = json.loads(response_text)

            # Добавляем изображения к результату
            product_images = []
            for i, info in enumerate(file_info):
                image_base64 = base64.b64encode(
                    info['contents']).decode('utf-8')
                product_images.append({
                    "index": i,
                    "filename": info['filename'],
                    "data": f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}",
                    "size": info['size']
                })

            result = {
                "success": True,
                "product": product_data,
                "images": product_images,
                "total_images": len(product_images),
                "debug_folder": debug_folder,
                "session_id": session_id
            }

            logger.info(
                f"✅ Детальный анализ завершен: {product_data.get('title', 'Товар')}")
            return JSONResponse(result)

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ ОШИБКА ПАРСИНГА JSON: {e}")
            return JSONResponse({
                "success": False,
                "error": f"Ошибка парсинга ответа Claude: {str(e)}",
                "raw_response": response_text,
                "debug_folder": debug_folder,
                "session_id": session_id
            }, status_code=500)

    except Exception as e:
        logger.error(
            f"❌ Ошибка детального анализа: {e}\n{traceback.format_exc()}")
        return JSONResponse({
            "success": False,
            "error": f"Ошибка сервера: {str(e)}"
        }, status_code=500)


@app.get("/product-analyzer", response_class=HTMLResponse)
async def product_analyzer_page():
    """Страница детального анализа товара"""
    return HTMLResponse("""
    <!DOCTYPE html>
    <html lang="ru">
    <head>
        <meta charset="UTF-8">
        <meta name="viewport" content="width=device-width, initial-scale=1.0">
        <title>Анализатор товаров - Somon.tj</title>
        <style>
            * {
                margin: 0;
                padding: 0;
                box-sizing: border-box;
            }
            
            body {
                font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                min-height: 100vh;
                padding: 20px;
            }
            
            .container {
                max-width: 1200px;
                margin: 0 auto;
                background: white;
                border-radius: 20px;
                box-shadow: 0 20px 40px rgba(0,0,0,0.1);
                overflow: hidden;
            }
            
            .header {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                padding: 30px;
                text-align: center;
            }
            
            .header h1 {
                font-size: 2.5rem;
                margin-bottom: 10px;
            }
            
            .header p {
                font-size: 1.1rem;
                opacity: 0.9;
            }
            
            .content {
                padding: 40px;
            }
            
            .upload-section {
                background: #f8f9fa;
                border: 3px dashed #dee2e6;
                border-radius: 15px;
                padding: 40px;
                text-align: center;
                margin-bottom: 30px;
                transition: all 0.3s ease;
            }
            
            .upload-section:hover {
                border-color: #667eea;
                background: #f0f2ff;
            }
            
            .upload-section.dragover {
                border-color: #667eea;
                background: #e3f2fd;
                transform: scale(1.02);
            }
            
            .upload-icon {
                font-size: 4rem;
                color: #667eea;
                margin-bottom: 20px;
            }
            
            .upload-text {
                font-size: 1.2rem;
                color: #495057;
                margin-bottom: 20px;
            }
            
            .file-input {
                display: none;
            }
            
            .upload-btn {
                background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
                color: white;
                border: none;
                padding: 15px 30px;
                border-radius: 25px;
                font-size: 1.1rem;
                cursor: pointer;
                transition: transform 0.2s ease;
            }
            
            .upload-btn:hover {
                transform: translateY(-2px);
            }
            
            .preview-section {
                display: none;
                margin-bottom: 30px;
            }
            
            .preview-grid {
                display: grid;
                grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
                gap: 15px;
                margin-bottom: 20px;
            }
            
            .preview-item {
                position: relative;
                border-radius: 10px;
                overflow: hidden;
                box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            }
            
            .preview-img {
                width: 100%;
                height: 150px;
                object-fit: cover;
            }
            
            .remove-btn {
                position: absolute;
                top: 5px;
                right: 5px;
                background: rgba(255,0,0,0.8);
                color: white;
                border: none;
                border-radius: 50%;
                width: 25px;
                height: 25px;
                cursor: pointer;
                font-size: 12px;
            }
            
            .analyze-btn {
                background: linear-gradient(135deg, #28a745 0%, #20c997 100%);
                color: white;
                border: none;
                padding: 15px 40px;
                border-radius: 25px;
                font-size: 1.2rem;
                cursor: pointer;
                width: 100%;
                margin-bottom: 20px;
                transition: transform 0.2s ease;
            }
            
            .analyze-btn:hover {
                transform: translateY(-2px);
            }
            
            .analyze-btn:disabled {
                background: #6c757d;
                cursor: not-allowed;
                transform: none;
            }
            
            .loading {
                display: none;
                text-align: center;
                padding: 40px;
            }
            
            .spinner {
                border: 4px solid #f3f3f3;
                border-top: 4px solid #667eea;
                border-radius: 50%;
                width: 50px;
                height: 50px;
                animation: spin 1s linear infinite;
                margin: 0 auto 20px;
            }
            
            @keyframes spin {
                0% { transform: rotate(0deg); }
                100% { transform: rotate(360deg); }
            }
            
            .results {
                display: none;
            }
            
            .result-section {
                background: #f8f9fa;
                border-radius: 15px;
                padding: 25px;
                margin-bottom: 20px;
            }
            
            .result-title {
                font-size: 1.3rem;
                font-weight: bold;
                color: #495057;
                margin-bottom: 15px;
                border-bottom: 2px solid #667eea;
                padding-bottom: 5px;
            }
            
            .field-group {
                display: grid;
                grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
                gap: 20px;
                margin-bottom: 20px;
            }
            
            .field {
                background: white;
                padding: 15px;
                border-radius: 10px;
                border-left: 4px solid #667eea;
            }
            
            .field-label {
                font-weight: bold;
                color: #495057;
                margin-bottom: 5px;
            }
            
            .field-value {
                color: #6c757d;
                line-height: 1.5;
            }
            
            .tags {
                display: flex;
                flex-wrap: wrap;
                gap: 8px;
            }
            
            .tag {
                background: #e9ecef;
                color: #495057;
                padding: 5px 12px;
                border-radius: 15px;
                font-size: 0.9rem;
            }
            
            .error {
                background: #f8d7da;
                color: #721c24;
                padding: 15px;
                border-radius: 10px;
                margin: 20px 0;
                border-left: 4px solid #dc3545;
            }
            
            .back-btn {
                background: #6c757d;
                color: white;
                border: none;
                padding: 10px 20px;
                border-radius: 20px;
                text-decoration: none;
                display: inline-block;
                margin-bottom: 20px;
                transition: background 0.2s ease;
            }
            
            .back-btn:hover {
                background: #5a6268;
                color: white;
                text-decoration: none;
            }
        </style>
    </head>
    <body>
        <div class="container">
            <div class="header">
                <h1>🔍 Анализатор товаров</h1>
                <p>Загрузите фотографии одного товара для детального анализа</p>
            </div>
            
            <div class="content">
                <a href="/" class="back-btn">← Назад к главной</a>
                
                <div class="upload-section" id="uploadSection">
                    <div class="upload-icon">📸</div>
                    <div class="upload-text">
                        Перетащите фотографии сюда или нажмите для выбора
                    </div>
                    <button class="upload-btn" onclick="document.getElementById('fileInput').click()">
                        Выбрать фотографии
                    </button>
                    <input type="file" id="fileInput" class="file-input" multiple accept="image/*">
                </div>
                
                <div class="preview-section" id="previewSection">
                    <div class="preview-grid" id="previewGrid"></div>
                    <button class="analyze-btn" id="analyzeBtn" onclick="analyzeProduct()">
                        🔍 Анализировать товар
                    </button>
                </div>
                
                <div class="loading" id="loading">
                    <div class="spinner"></div>
                    <p>Анализируем ваш товар... Это может занять до 2 минут</p>
                </div>
                
                <div class="results" id="results"></div>
            </div>
        </div>

        <script>
            let selectedFiles = [];
            
            // Обработка drag & drop
            const uploadSection = document.getElementById('uploadSection');
            
            uploadSection.addEventListener('dragover', (e) => {
                e.preventDefault();
                uploadSection.classList.add('dragover');
            });
            
            uploadSection.addEventListener('dragleave', () => {
                uploadSection.classList.remove('dragover');
            });
            
            uploadSection.addEventListener('drop', (e) => {
                e.preventDefault();
                uploadSection.classList.remove('dragover');
                handleFiles(e.dataTransfer.files);
            });
            
            // Обработка выбора файлов
            document.getElementById('fileInput').addEventListener('change', (e) => {
                handleFiles(e.target.files);
            });
            
            function handleFiles(files) {
                selectedFiles = Array.from(files);
                displayPreviews();
            }
            
            function displayPreviews() {
                const previewGrid = document.getElementById('previewGrid');
                const previewSection = document.getElementById('previewSection');
                
                previewGrid.innerHTML = '';
                
                if (selectedFiles.length === 0) {
                    previewSection.style.display = 'none';
                    return;
                }
                
                previewSection.style.display = 'block';
                
                selectedFiles.forEach((file, index) => {
                    const reader = new FileReader();
                    reader.onload = (e) => {
                        const previewItem = document.createElement('div');
                        previewItem.className = 'preview-item';
                        previewItem.innerHTML = `
                            <img src="${e.target.result}" class="preview-img" alt="Preview ${index + 1}">
                            <button class="remove-btn" onclick="removeFile(${index})">×</button>
                        `;
                        previewGrid.appendChild(previewItem);
                    };
                    reader.readAsDataURL(file);
                });
            }
            
            function removeFile(index) {
                selectedFiles.splice(index, 1);
                displayPreviews();
            }
            
            async function analyzeProduct() {
                if (selectedFiles.length === 0) {
                    alert('Пожалуйста, выберите фотографии для анализа');
                    return;
                }
                
                const analyzeBtn = document.getElementById('analyzeBtn');
                const loading = document.getElementById('loading');
                const results = document.getElementById('results');
                
                analyzeBtn.disabled = true;
                loading.style.display = 'block';
                results.style.display = 'none';
                
                try {
                    const formData = new FormData();
                    selectedFiles.forEach(file => {
                        formData.append('files', file);
                    });
                    
                    const response = await fetch('/api/analyze-product-detailed', {
                        method: 'POST',
                        body: formData
                    });
                    
                    const data = await response.json();
                    
                    if (data.success) {
                        displayResults(data);
                    } else {
                        throw new Error(data.error || 'Ошибка анализа');
                    }
                } catch (error) {
                    console.error('Ошибка:', error);
                    results.innerHTML = `<div class="error">❌ Ошибка: ${error.message}</div>`;
                    results.style.display = 'block';
                } finally {
                    analyzeBtn.disabled = false;
                    loading.style.display = 'none';
                }
            }
            
            function displayResults(data) {
                const results = document.getElementById('results');
                const product = data.product;
                
                results.innerHTML = `
                    <div class="result-section">
                        <div class="result-title">📋 Основная информация</div>
                        <div class="field-group">
                            <div class="field">
                                <div class="field-label">Название товара</div>
                                <div class="field-value">${product.title || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Бренд</div>
                                <div class="field-value">${product.brand || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Модель</div>
                                <div class="field-value">${product.model || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Категория</div>
                                <div class="field-value">${product.category || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Подкатегория</div>
                                <div class="field-value">${product.subcategory || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Состояние</div>
                                <div class="field-value">${product.condition || 'Не определено'}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="result-section">
                        <div class="result-title">🎨 Характеристики</div>
                        <div class="field-group">
                            <div class="field">
                                <div class="field-label">Цвет</div>
                                <div class="field-value">${product.color || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Материал</div>
                                <div class="field-value">${product.material || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Размер</div>
                                <div class="field-value">${product.size || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Вес</div>
                                <div class="field-value">${product.weight || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Год выпуска</div>
                                <div class="field-value">${product.year || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Страна производства</div>
                                <div class="field-value">${product.country || 'Не определено'}</div>
                            </div>
                        </div>
                    </div>
                    
                    <div class="result-section">
                        <div class="result-title">📝 Описание</div>
                        <div class="field">
                            <div class="field-value">${product.description || 'Описание не создано'}</div>
                        </div>
                    </div>
                    
                    <div class="result-section">
                        <div class="result-title">⭐ Особенности</div>
                        <div class="tags">
                            ${(product.features || []).map(feature => `<span class="tag">${feature}</span>`).join('')}
                        </div>
                    </div>
                    
                    <div class="result-section">
                        <div class="result-title">📦 Комплектация</div>
                        <div class="tags">
                            ${(product.included || []).map(item => `<span class="tag">${item}</span>`).join('')}
                        </div>
                    </div>
                    
                    <div class="result-section">
                        <div class="result-title">🔍 Ключевые слова</div>
                        <div class="tags">
                            ${(product.keywords || []).map(keyword => `<span class="tag">${keyword}</span>`).join('')}
                        </div>
                    </div>
                    
                    ${product.defects && product.defects.length > 0 ? `
                    <div class="result-section">
                        <div class="result-title">⚠️ Дефекты</div>
                        <div class="tags">
                            ${product.defects.map(defect => `<span class="tag" style="background: #f8d7da; color: #721c24;">${defect}</span>`).join('')}
                        </div>
                    </div>
                    ` : ''}
                    
                    <div class="result-section">
                        <div class="result-title">💡 Дополнительная информация</div>
                        <div class="field-group">
                            <div class="field">
                                <div class="field-label">Ценовая категория</div>
                                <div class="field-value">${product.estimated_price_range || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Целевая аудитория</div>
                                <div class="field-value">${product.target_audience || 'Не определено'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Советы по использованию</div>
                                <div class="field-value">${product.usage_tips || 'Не указано'}</div>
                            </div>
                            <div class="field">
                                <div class="field-label">Уход</div>
                                <div class="field-value">${product.care_instructions || 'Не указано'}</div>
                            </div>
                        </div>
                    </div>
                `;
                
                results.style.display = 'block';
            }
        </script>
    </body>
    </html>
    """)


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Запускаем сервер AIТовар.tj...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
