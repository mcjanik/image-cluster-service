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

# Создаем папку для логов
os.makedirs("logs", exist_ok=True)

# Настраиваем логирование в файл и консоль
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # Вывод в консоль
        logging.handlers.RotatingFileHandler(
            'logs/app.log',
            maxBytes=10*1024*1024,  # 10MB
            backupCount=5
        )
    ]
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

# Создаем папки
os.makedirs("static", exist_ok=True)
os.makedirs("uploads", exist_ok=True)

# Подключаем статические файлы
app.mount("/static", StaticFiles(directory="static"), name="static")


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
                            "text": """Проанализируйте это изображение товара для создания объявления о продаже на классифайд платформе. Отвечайте ТОЛЬКО на русском языке.

🏷️ ТОВАР И КАТЕГОРИЯ:
- Что это за товар/предмет
- К какой категории относится (одежда, техника, мебель, автомобиль и т.д.)
- Подкатегория товара

📝 ДЕТАЛЬНОЕ ОПИСАНИЕ:
- Материал, цвет, размер (если видно)
- Состояние товара (новый/б/у, видимые повреждения/износ)
- Особенности, характеристики, функции
- Бренд или производитель (если различимо)
- Комплектность (что входит в комплект)

💰 ДЛЯ ОБЪЯВЛЕНИЯ:
- Ключевые слова для поиска покупателями
- Главные преимущества и особенности товара
- На что обратить внимание покупателя
- Рекомендуемая целевая аудитория

Отвечайте структурированно, подробно, но лаконично. Фокусируйтесь на информации которая поможет продать товар."""
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


def analyze_images_batch_with_claude(image_batch: List[tuple[bytes, str]]) -> List[str]:
    """Анализирует batch изображений и группирует их по товарам"""
    try:
        logger.info(f"🔍 НАЧИНАЕМ BATCH АНАЛИЗ: {len(image_batch)} изображений")

        # Проверяем что API ключ настроен
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            error_msg = "❌ API ключ Anthropic не настроен в переменных окружения"
            logger.error(error_msg)
            return [error_msg] * len(image_batch)

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

        # Промпт для группировки товаров
        batch_prompt = f"""Проанализируйте эти {len(image_batch)} изображений товаров и сгруппируйте их по отдельным товарам.

ВАЖНО: 
- Один товар может иметь несколько фотографий с разных ракурсов или одинаковые фото
- Разные цвета, размеры, модели = разные товары
- При сомнениях лучше разделить товары
- Анализируйте не только цвет, но и модель, бренд, состояние, размер

Используйте категории из списка:
{open('code_for_learning/somon-structure.txt', 'r', encoding='utf-8').read()}

Верните ТОЛЬКО JSON массив в формате:
[
  {{
    "title": "Красный детский стул",
    "category": "Детский мир", 
    "subcategory": "Детская мебель",
    "image_indexes": [0, 1, 2]
  }},
  {{
    "title": "Синий детский стул",
    "category": "Детский мир",
    "subcategory": "Детская мебель", 
    "image_indexes": [3, 4]
  }}
]

Где image_indexes - номера изображений (начиная с 0), которые показывают ОДИН товар.

ОБЯЗАТЕЛЬНО включите ВСЕ {len(image_batch)} изображений в группы!

ВЕРНИТЕ ТОЛЬКО JSON, БЕЗ ДОПОЛНИТЕЛЬНОГО ТЕКСТА."""

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

        # Парсим JSON ответ
        try:
            # Извлекаем JSON из ответа (может быть обернут в ```json```)
            json_start = response_text.find('[')
            json_end = response_text.rfind(']') + 1

            logger.info(f"🔍 JSON позиции: start={json_start}, end={json_end}")

            if json_start == -1 or json_end == 0:
                raise ValueError("JSON не найден в ответе")

            json_str = response_text[json_start:json_end]
            logger.info(
                f"🔍 ИЗВЛЕЧЕННЫЙ JSON (первые 500 символов): {json_str[:500]}")

            products = json.loads(json_str)

            logger.info(f"✅ Распознано {len(products)} товаров")

            # ЛОГИРУЕМ КАЖДЫЙ ТОВАР
            for i, product in enumerate(products):
                title = product.get('title', 'Товар')
                image_indexes = product.get('image_indexes', [])
                logger.info(
                    f"🔍 Товар {i+1}: '{title}' -> изображения {image_indexes}")

            # Подсчитываем общее количество изображений в группах
            total_images_in_groups = sum(
                len(product.get('image_indexes', [])) for product in products)
            logger.info(
                f"🔍 ВСЕГО изображений в группах: {total_images_in_groups} из {len(image_batch)}")

            # Создаем описания для каждого изображения
            descriptions = [""] * len(image_batch)

            for product in products:
                title = product.get('title', 'Товар')
                category = product.get('category', 'Разное')
                subcategory = product.get('subcategory', '')
                image_indexes = product.get('image_indexes', [])

                description = f"""🏷️ ТОВАР: {title}
📂 КАТЕГОРИЯ: {category}
📂 ПОДКАТЕГОРИЯ: {subcategory}
📝 ОПИСАНИЕ: {title} - качественный товар в категории {category}
💰 РЕКОМЕНДАЦИИ: Укажите состояние товара, размер (если применимо) и цену"""

                # Применяем описание ко всем изображениям этого товара
                for idx in image_indexes:
                    if 0 <= idx < len(descriptions):
                        descriptions[idx] = description
                        logger.info(
                            f"🔍 Применили описание к изображению {idx}: {title}")
                    else:
                        logger.warning(
                            f"⚠️ Неверный индекс изображения: {idx} (максимум {len(descriptions)-1})")

            # Заполняем пустые описания
            empty_count = 0
            for i, desc in enumerate(descriptions):
                if not desc:
                    descriptions[i] = f"🏷️ ТОВАР: Товар {i+1}\n📂 КАТЕГОРИЯ: Разное\n📝 ОПИСАНИЕ: Товар требует дополнительного анализа"
                    empty_count += 1
                    logger.warning(
                        f"⚠️ Изображение {i} не было сгруппировано, создали fallback описание")

            logger.info(
                f"✅ Batch анализ завершен! Обработано {len(descriptions)} изображений, {empty_count} fallback описаний")
            return descriptions

        except (json.JSONDecodeError, ValueError) as e:
            logger.error(f"❌ Ошибка парсинга JSON: {e}")
            logger.error(f"Ответ Claude: {response_text[:500]}...")

            # Fallback - возвращаем простые описания
            fallback_descriptions = []
            for i, (_, filename) in enumerate(image_batch):
                fallback_descriptions.append(
                    f"🏷️ ТОВАР: Товар из изображения {filename}\n📂 КАТЕГОРИЯ: Разное\n📝 ОПИСАНИЕ: Требует ручной категоризации")

            return fallback_descriptions

    except Exception as e:
        error_msg = f"❌ ОШИБКА BATCH АНАЛИЗА: {str(e)}"
        logger.error(error_msg)
        return [error_msg] * len(image_batch)


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


@app.post("/api/analyze-multiple")
async def analyze_multiple_images(files: List[UploadFile] = File(...)):
    """Анализ нескольких изображений"""
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

        # Batch анализ всех изображений
        descriptions = analyze_images_batch_with_claude(image_batch)

        # Формируем результаты
        results = []
        for i, (description, info) in enumerate(zip(descriptions, file_info)):
            # Кодируем изображение для браузера
            image_base64 = base64.b64encode(info['contents']).decode('utf-8')

            results.append({
                "id": f"{info['filename']}_{info['size']}_{i}",
                "filename": info['filename'],
                "width": 800,  # Временные значения
                "height": 600,
                "size_bytes": info['size'],
                "image_preview": f"data:image/{info['filename'].split('.')[-1]};base64,{image_base64}",
                "description": description
            })

        logger.info(
            f"✅ Batch анализ завершен! Обработано {len(results)} изображений")

        return JSONResponse({
            "success": True,
            "results": results,
            "processed_count": len(results),
            "total_files": len(files),
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

    return JSONResponse({
        "status": "healthy",
        "api_key_configured": bool(api_key),
        "api_key_preview": f"{api_key[:10]}...{api_key[-4:]}" if api_key else None,
        "claude_status": claude_status,
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
        log_file = "logs/app.log"
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


if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Запускаем сервер AIТовар.tj...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
