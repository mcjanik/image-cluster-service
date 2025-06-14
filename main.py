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

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
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
    """Анализирует batch изображений с помощью Claude и возвращает описания"""
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

        # Подготавливаем batch изображений
        image_contents = []
        for img_data, filename in image_batch:
            # Проверяем размер
            if len(img_data) > 20 * 1024 * 1024:  # 20MB лимит
                logger.warning(
                    f"❌ Пропускаем {filename} - слишком большой: {len(img_data)/1024/1024:.1f}MB")
                continue

            # Кодируем в base64
            image_base64 = base64.b64encode(img_data).decode('utf-8')

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

            # Добавляем в контент
            image_contents.append({
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": mime_type,
                    "data": image_base64,
                }
            })

        if not image_contents:
            return []

        logger.info("🚀 ОТПРАВЛЯЕМ BATCH ЗАПРОС В CLAUDE API...")

        # Формируем промпт для batch анализа
        batch_prompt = """Проанализируйте эти изображения товаров для создания объявлений о продаже на классифайд платформе. 
Отвечайте ТОЛЬКО на русском языке.

Для КАЖДОГО изображения предоставьте структурированный анализ в следующем формате:

=== ИЗОБРАЖЕНИЕ {N} ===

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

=== КОНЕЦ ИЗОБРАЖЕНИЯ {N} ===

Отвечайте структурированно, подробно, но лаконично. Фокусируйтесь на информации которая поможет продать товар."""

        # Отправляем batch запрос к Claude
        message = client.messages.create(
            model="claude-3-5-sonnet-20241022",
            max_tokens=70000,  # Увеличиваем лимит для обработки большого количества изображений
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

        # Разбираем ответ на отдельные описания
        full_response = message.content[0].text
        descriptions = []
        current_desc = []

        for line in full_response.split('\n'):
            if line.startswith('=== ИЗОБРАЖЕНИЕ'):
                if current_desc:
                    descriptions.append('\n'.join(current_desc))
                    current_desc = []
            elif line.startswith('=== КОНЕЦ ИЗОБРАЖЕНИЯ'):
                if current_desc:
                    descriptions.append('\n'.join(current_desc))
                    current_desc = []
            else:
                current_desc.append(line)

        # Добавляем последнее описание если есть
        if current_desc:
            descriptions.append('\n'.join(current_desc))

        logger.info(
            f"✅ ПОЛУЧЕН BATCH ОТВЕТ ОТ CLAUDE! {len(descriptions)} описаний")
        return descriptions

    except Exception as e:
        error_msg = f"❌ ОШИБКА BATCH АНАЛИЗА: {str(e)}"
        logger.error(f"{error_msg}\nПолная ошибка: {traceback.format_exc()}")
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

if __name__ == "__main__":
    import uvicorn
    logger.info("🚀 Запускаем сервер AIТовар.tj...")
    uvicorn.run(app, host="0.0.0.0", port=8000)
