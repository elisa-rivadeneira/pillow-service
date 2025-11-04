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
    texto_cuento: str = Form(...),
    titulo: str = Form(default=""),
    header_height: int = Form(default=1300),
    con_borde: bool = Form(default=False)
):
    logger.info(f"📥 v3.0: titulo='{titulo}', borde={con_borde}")
    
    try:
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        a4_width = 2480
        a4_height = 3508
        canvas = Image.new('RGB', (a4_width, a4_height), 'white')
        
        header_img.thumbnail((a4_width, header_height), Image.Resampling.LANCZOS)
        x_offset = (a4_width - header_img.width) // 2
        canvas.paste(header_img, (x_offset, 0))
        
        draw = ImageDraw.Draw(canvas)
        
        try:
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 65)
            font_texto = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 46)
        except:
            font_titulo = ImageFont.load_default()
            font_texto = ImageFont.load_default()
        
        margin_left = 220
        margin_right = 220
        margin_top = header_height + 120
        line_spacing = 75
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3300
        
        y_text = margin_top
        
        if titulo:
            titulo_lines = wrap_text_smart(titulo, font_titulo, max_width_px, draw)
            for line in titulo_lines:
                bbox = draw.textbbox((0, 0), line, font=font_titulo)
                text_width = bbox[2] - bbox[0]
                x_centered = (a4_width - text_width) // 2
                
                draw.text((x_centered + 3, y_text + 3), line, font=font_titulo, fill='#cccccc')
                draw.text((x_centered, y_text), line, font=font_titulo, fill='#1a5490')
                y_text += 85
            
            y_text += 30
            line_margin = 500
            draw.line(
                [(line_margin, y_text), (a4_width - line_margin, y_text)],
                fill='#1a5490',
                width=3
            )
            y_text += 70
        
        texto_lines = wrap_text_smart(texto_cuento, font_texto, max_width_px, draw)
        
        for i, line in enumerate(texto_lines):
            if y_text > max_height:
                break
            
            x_pos = margin_left + 100 if i == 0 else margin_left
            draw.text((x_pos, y_text), line, font=font_texto, fill='#2c2c2c')
            y_text += line_spacing
        
        if con_borde:
            border_margin = 80
            draw.rectangle(
                [(border_margin, border_margin), (a4_width - border_margin, a4_height - border_margin)],
                outline='#1a5490',
                width=4
            )
            inner_border = border_margin + 15
            draw.rectangle(
                [(inner_border, inner_border), (a4_width - inner_border, a4_height - inner_border)],
                outline='#1a5490',
                width=2
            )
        
        output_path = "/tmp/ficha_completa.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Ficha creada")
        
        return FileResponse(output_path, media_type="image/png", filename="ficha_educativa.png")
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {"status": "ok", "version": "3.0", "source": "github"}

@app.get("/health")
def health():
    return {"status": "healthy"}