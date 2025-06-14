from fastapi import FastAPI, UploadFile, File, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from PIL import Image
import io
import os
import base64
import anthropic

app = FastAPI()
os.makedirs("templates", exist_ok=True)
templates = Jinja2Templates(directory="templates")

def analyze_image_with_claude(image_data: bytes, filename: str) -> str:
    """Анализирует изображение с помощью Claude и возвращает описание"""
    try:
        print(f"🔍 НАЧИНАЕМ АНАЛИЗ ИЗОБРАЖЕНИЯ: {filename}")
        
        # Проверяем что API ключ настроен
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            error_msg = "❌ API ключ Anthropic не настроен в переменных окружения"
            print(error_msg)
            return error_msg
        
        print(f"✅ API ключ найден: {api_key[:15]}...{api_key[-4:]}")
        
        # Инициализация клиента здесь для надёжности
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
            max_tokens=1500,
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
                            "text": """Проанализируйте это изображение товара для создания объявления о продаже. Опишите подробно на русском языке:

🏷️ ТОВАР И КАТЕГОРИЯ:
- Что это за товар/предмет
- К какой категории относится

📝 ДЕТАЛЬНОЕ ОПИСАНИЕ:
- Материал, цвет, размер (если видно)
- Состояние товара (новый/б/у, повреждения)
- Особенности и характеристики
- Бренд или производитель (если различимо)

💰 ДЛЯ ОБЪЯВЛЕНИЯ:
- Ключевые слова для поиска
- Привлекательные особенности товара
- На что обратить внимание покупателя

Отвечайте структурированно и подробно, чтобы можно было создать качественное объявление о продаже."""
                        }
                    ],
                }
            ],
        )
        
        description = message.content[0].text
        print(f"✅ ПОЛУЧЕН ОТВЕТ ОТ CLAUDE! Длина: {len(description)} символов")
        return description
        
    except Exception as e:
        error_msg = f"❌ ОШИБКА: {str(e)}"
        print(error_msg)
        return error_msg

@app.get("/", response_class=HTMLResponse)
async def upload_form(request: Request):
    return templates.TemplateResponse("upload.html", {"request": request})

@app.post("/upload", response_class=HTMLResponse) 
async def handle_upload(request: Request, file: UploadFile = File(...)):
    print(f"📁 ПОЛУЧЕН ФАЙЛ: {file.filename}")
    
    contents = await file.read()
    image = Image.open(io.BytesIO(contents))
    width, height = image.size
    
    print(f"📊 Размер изображения: {width}x{height}")
    print(f"💾 Размер файла: {len(contents)} байт")
    
    # Анализируем изображение с помощью Claude
    description = analyze_image_with_claude(contents, file.filename)
    
    return templates.TemplateResponse("upload.html", {
        "request": request,
        "filename": file.filename,
        "width": width,
        "height": height,
        "description": description,
    })
