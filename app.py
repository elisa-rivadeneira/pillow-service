from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
import io
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

def wrap_text_smart(text, font, max_width_px, draw):
    words = text.split()
    lines = []
    current_line = []
    
    for word in words:
        test_line = ' '.join(current_line + [word])
        bbox = draw.textbbox((0, 0), test_line, font=font)
        if bbox[2] - bbox[0] <= max_width_px:
            current_line.append(word)
        else:
            if current_line:
                lines.append(' '.join(current_line))
            current_line = [word]
    
    if current_line:
        lines.append(' '.join(current_line))
    
    return lines

@app.post("/crear-ficha")
async def crear_ficha(
    imagen: UploadFile = File(...),
    texto_cuento: str = Form(...)  # ← IMPORTANTE: Form, NO Query
):
    logger.info(f"📥 Recibido: {imagen.filename}, texto_len={len(texto_cuento)}")
    
    try:
        # Leer imagen
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        # Canvas A4
        a4_width = 2480
        a4_height = 3508
        canvas = Image.new('RGB', (a4_width, a4_height), 'white')
        
        # Redimensionar manteniendo aspecto
        header_height = 1400
        header_img.thumbnail((a4_width, header_height), Image.Resampling.LANCZOS)
        
        # Centrar
        x_offset = (a4_width - header_img.width) // 2
        canvas.paste(header_img, (x_offset, 0))
        
        draw = ImageDraw.Draw(canvas)
        
        # Fuente
        try:
            font = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48)
        except:
            font = ImageFont.load_default()
        
        # Config
        margin_left = 200
        margin_right = 200
        margin_top = header_height + 100
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3350
        line_spacing = 70
        
        y_text = margin_top
        
        # Texto
        texto_lines = wrap_text_smart(texto_cuento, font, max_width_px, draw)
        for line in texto_lines:
            if y_text > max_height:
                break
            draw.text((margin_left, y_text), line, font=font, fill='#2c2c2c')
            y_text += line_spacing
        
        # Guardar
        output_path = "/tmp/ficha_completa.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Éxito")
        
        return FileResponse(output_path, media_type="image/png", filename="ficha_educativa.png")
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"status": "ok", "version": "2.3", "message": "Form version"}

@app.get("/health")
def health():
    return {"status": "healthy"}
