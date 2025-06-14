from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from PIL import Image
import io
import os
import base64
import anthropic
import json
from typing import List

app = FastAPI(title="AIТовар.tj", description="ИИ анализ товаров для объявлений")

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

def calculate_api_cost(image_size_bytes: int, response_text: str) -> dict:
    """Расчет стоимости API запроса к Claude"""
    # Базовая стоимость Claude API (примерные значения)
    INPUT_COST_PER_1M_TOKENS = 3.0  # $3 за 1M input токенов
    OUTPUT_COST_PER_1M_TOKENS = 15.0  # $15 за 1M output токенов
    USD_TO_RUB = 95.0  # Примерный курс доллара
    
    # Расчет токенов для изображения (примерно)
    image_size_kb = image_size_bytes / 1024
    # Изображения обычно занимают 1000-2000 токенов в зависимости от размера
    image_tokens = max(1000, min(2500, int(image_size_kb * 1.5)))
    
    # Расчет токенов для текста (примерно 1.3 токена на символ для русского)
    output_tokens = int(len(response_text) * 1.3)
    
    # Расчет стоимости в долларах
    input_cost_usd = (image_tokens / 1_000_000) * INPUT_COST_PER_1M_TOKENS
    output_cost_usd = (output_tokens / 1_000_000) * OUTPUT_COST_PER_1M_TOKENS
    total_cost_usd = input_cost_usd + output_cost_usd
    
    # Конвертация в рубли
    total_cost_rub = total_cost_usd * USD_TO_RUB
    
    return {
        "image_tokens": image_tokens,
        "output_tokens": output_tokens,
        "input_cost_usd": round(input_cost_usd, 6),
        "output_cost_usd": round(output_cost_usd, 6),
        "total_cost_usd": round(total_cost_usd, 6),
        "total_cost_rub": round(total_cost_rub, 4),
        "usd_to_rub_rate": USD_TO_RUB
    }

def analyze_image_with_claude(image_data: bytes, filename: str) -> tuple[str, dict]:
    """Анализирует изображение с помощью Claude и возвращает описание + стоимость"""
    try:
        print(f"🔍 НАЧИНАЕМ АНАЛИЗ ИЗОБРАЖЕНИЯ: {filename}")
        
        # Проверяем что API ключ настроен
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            error_msg = "❌ API ключ Anthropic не настроен в переменных окружения"
            print(error_msg)
            cost_info = calculate_api_cost(len(image_data), error_msg)
            return error_msg, cost_info
        
        print(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")
        
        # Инициализация клиента
        client = anthropic.Anthropic(api_key=api_key)
        
        # Кодируем изображение в base64
        print("🔄 Кодируем изображение...")
        image_base64 = base64.b64encode(image_data).decode('utf-8')
        print(f"✅ Base64 готов, длина: {len(image_base64)} символов")
        
        # Определяем MIME тип
        file_extension = filename.lower().split('.')[-1] if '.' in filename else 'jpg'
        mime_type_map = {
            'jpg': 'image/jpeg',
            'jpeg': 'image/jpeg', 
            'png': 'image/png',
            'gif': 'image/gif',
            'webp': 'image/webp'
        }
        mime_type = mime_type_map.get(file_extension, 'image/jpeg')
        print(f"📎 MIME тип: {mime_type}")
        
        print("🚀 ОТПРАВЛЯЕМ ЗАПРОС В CLAUDE API...")
        
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
        print(f"✅ ПОЛУЧЕН ОТВЕТ ОТ CLAUDE! Длина: {len(description)} символов")
        
        # Расчет стоимости
        cost_info = calculate_api_cost(len(image_data), description)
        print(f"💰 Стоимость запроса: ₽{cost_info['total_cost_rub']}")
        
        return description, cost_info
        
    except Exception as e:
        error_msg = f"❌ ОШИБКА: {str(e)}"
        print(error_msg)
        cost_info = calculate_api_cost(len(image_data), error_msg)
        return error_msg, cost_info

@app.get("/", response_class=HTMLResponse)
async def root():
    """Главная страница с React приложением"""
    return FileResponse('static/index.html')

@app.post("/api/analyze-single")
async def analyze_single_image(file: UploadFile = File(...)):
    """Анализ одного изображения"""
    try:
        # Читаем файл
        contents = await file.read()
        
        # Получаем размеры изображения
        image = Image.open(io.BytesIO(contents))
        width, height = image.size
        
        # Анализируем с Claude
        description, cost_info = analyze_image_with_claude(contents, file.filename)
        
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
                "description": description,
                "api_cost": cost_info
            }
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.post("/api/analyze-multiple")
async def analyze_multiple_images(files: List[UploadFile] = File(...)):
    """Анализ нескольких изображений"""
    try:
        results = []
        total_cost_rub = 0
        
        for file in files:
            # Читаем файл
            contents = await file.read()
            
            # Получаем размеры изображения
            image = Image.open(io.BytesIO(contents))
            width, height = image.size
            
            # Анализируем с Claude
            description, cost_info = analyze_image_with_claude(contents, file.filename)
            
            # Кодируем изображение для возврата в браузер
            image_base64 = base64.b64encode(contents).decode('utf-8')
            
            total_cost_rub += cost_info['total_cost_rub']
            
            results.append({
                "id": f"{file.filename}_{len(contents)}_{int(len(results))}",
                "filename": file.filename,
                "width": width,
                "height": height,
                "size_bytes": len(contents),
                "image_preview": f"data:image/{file.filename.split('.')[-1]};base64,{image_base64}",
                "description": description,
                "api_cost": cost_info
            })
        
        return JSONResponse({
            "success": True,
            "results": results,
            "total_cost_rub": round(total_cost_rub, 4),
            "processed_count": len(files),
            "summary": {
                "total_images": len(files),
                "total_tokens_used": sum(r["api_cost"]["image_tokens"] + r["api_cost"]["output_tokens"] for r in results),
                "average_cost_per_image": round(total_cost_rub / len(files), 4) if files else 0
            }
        })
        
    except Exception as e:
        return JSONResponse({
            "success": False,
            "error": str(e)
        }, status_code=500)

@app.get("/api/health")
async def health_check():
    """Проверка работоспособности API"""
    api_key = os.getenv("ANTHROPIC_API_KEY")
    return JSONResponse({
        "status": "healthy",
        "api_key_configured": bool(api_key),
        "api_key_preview": f"{api_key[:10]}...{api_key[-4:]}" if api_key else None
    })

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
