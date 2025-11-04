from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
import io
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

def parse_markdown_line(line):
    """Parsea markdown en una línea"""
    segments = []
    pattern = r'(\*\*\*[^\*]+\*\*\*|\*\*[^\*]+\*\*|\*[^\*]+\*)'
    
    last_end = 0
    for match in re.finditer(pattern, line):
        if match.start() > last_end:
            segments.append((line[last_end:match.start()], 'normal'))
        
        matched_text = match.group(0)
        if matched_text.startswith('***') and matched_text.endswith('***'):
            segments.append((matched_text[3:-3], 'bold'))
        elif matched_text.startswith('**') and matched_text.endswith('**'):
            segments.append((matched_text[2:-2], 'bold'))
        elif matched_text.startswith('*') and matched_text.endswith('*'):
            segments.append((matched_text[1:-1], 'bold'))
        
        last_end = match.end()
    
    if last_end < len(line):
        segments.append((line[last_end:], 'normal'))
    
    return segments if segments else [(line, 'normal')]

def draw_formatted_line(draw, x, y, line, fonts, color):
    """Dibuja línea con markdown"""
    segments = parse_markdown_line(line)
    current_x = x
    
    for text, style in segments:
        font = fonts.get(style, fonts['normal'])
        draw.text((current_x, y), text, font=font, fill=color)
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        current_x += text_width
    
    return current_x - x

def wrap_text_with_markdown(text, fonts, max_width_px, draw):
    """Divide texto respetando markdown"""
    words = text.split()
    lines = []
    current_line_words = []
    
    for word in words:
        test_line = ' '.join(current_line_words + [word])
        segments = parse_markdown_line(test_line)
        
        total_width = 0
        for seg_text, seg_style in segments:
            font = fonts.get(seg_style, fonts['normal'])
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            total_width += bbox[2] - bbox[0]
        
        if total_width <= max_width_px:
            current_line_words.append(word)
        else:
            if current_line_words:
                lines.append(' '.join(current_line_words))
            current_line_words = [word]
    
    if current_line_words:
        lines.append(' '.join(current_line_words))
    
    return lines

def draw_stars(draw, a4_width, y_position):
    """Dibuja estrellitas decorativas"""
    star_color = '#FFD700'
    positions = [
        (400, y_position - 20),
        (450, y_position - 40),
        (a4_width - 450, y_position - 40),
        (a4_width - 400, y_position - 20)
    ]
    
    import math
    for x, y in positions:
        points = []
        for i in range(10):
            angle = i * 36
            radius = 25 if i % 2 == 0 else 12
            px = x + radius * math.cos(math.radians(angle - 90))
            py = y + radius * math.sin(math.radians(angle - 90))
            points.append((px, py))
        draw.polygon(points, fill=star_color, outline='#FFA500')

def draw_wavy_border(draw, a4_width, a4_height):
    """Dibuja borde ondulado infantil"""
    import math
    colors = ['#FF6B9D', '#FFA07A', '#FFD93D', '#6BCF7F', '#4ECDC4', '#95E1D3']
    margin = 60
    wave_width = 40
    
    for x in range(margin, a4_width - margin, 10):
        wave_y = margin + wave_width * math.sin(x * 0.05)
        draw.ellipse([x, wave_y - 5, x + 10, wave_y + 5], fill=colors[x % len(colors)])
    
    for x in range(margin, a4_width - margin, 10):
        wave_y = a4_height - margin - wave_width * math.sin(x * 0.05)
        draw.ellipse([x, wave_y - 5, x + 10, wave_y + 5], fill=colors[x % len(colors)])

@app.post("/crear-ficha")
async def crear_ficha(
    imagen: UploadFile = File(...),
    texto_cuento: str = Form(...),
    titulo: str = Form(default=""),
    header_height: int = Form(default=1150),  # ← MÁS PEQUEÑO (antes 1300)
    estilo: str = Form(default="infantil"),
    imagen_modo: str = Form(default="crop")
):
    logger.info(f"📥 v4.6-KIDS: {len(texto_cuento)} chars, header={header_height}px")
    
    try:
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        a4_width = 2480
        a4_height = 3508
        canvas = Image.new('RGB', (a4_width, a4_height), '#FFFEF0' if estilo == "infantil" else 'white')
        
        # PROCESAMIENTO DE IMAGEN
        if imagen_modo == "stretch":
            header_img_final = header_img.resize((a4_width, header_height), Image.Resampling.LANCZOS)
            canvas.paste(header_img_final, (0, 0))
            logger.info("📐 Imagen estirada a ancho completo")
        else:
            aspect_ratio = header_img.width / header_img.height
            target_aspect = a4_width / header_height
            
            if aspect_ratio > target_aspect:
                new_height = header_height
                new_width = int(header_height * aspect_ratio)
                header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                left = (new_width - a4_width) // 2
                header_img_final = header_img_resized.crop((left, 0, left + a4_width, header_height))
                logger.info(f"📐 Imagen horizontal recortada (centrada)")
            else:
                new_width = a4_width
                new_height = int(a4_width / aspect_ratio)
                header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                top_crop = max(0, new_height - header_height)
                header_img_final = header_img_resized.crop((0, top_crop, a4_width, new_height))
                logger.info(f"📐 Imagen vertical anclada abajo (recorte: {top_crop}px)")
            
            canvas.paste(header_img_final, (0, 0))
        
        draw = ImageDraw.Draw(canvas)
        
        # FUENTES MÁS GRANDES PARA NIÑOS DE 8 AÑOS
        try:
            font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 52)
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 75)
            logger.info("✅ Fuentes cargadas (52px texto, 75px título)")
        except Exception as e:
            logger.error(f"❌ Error fuentes: {e}")
            font_normal = ImageFont.load_default()
            font_bold = ImageFont.load_default()
            font_titulo = ImageFont.load_default()
        
        fonts = {
            'normal': font_normal,
            'bold': font_bold,
            'italic': font_bold,
            'bold_italic': font_bold
        }
        
        # LAYOUT OPTIMIZADO PARA NIÑOS
        margin_left = 160
        margin_right = 160
        margin_top = header_height + 85
        line_spacing = 80  # MÁS ESPACIADO
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3380
        
        y_text = margin_top
        
        # TÍTULO
        if titulo:
            logger.info(f"📝 Título: '{titulo}'")
            
            if estilo == "infantil":
                draw_stars(draw, a4_width, y_text + 40)
            
            bbox = draw.textbbox((0, 0), titulo, font=font_titulo)
            text_width = bbox[2] - bbox[0]
            x_centered = (a4_width - text_width) // 2
            
            if estilo == "infantil":
                draw.text((x_centered + 4, y_text + 4), titulo, font=font_titulo, fill='#FFB6C1')
                draw.text((x_centered + 2, y_text + 2), titulo, font=font_titulo, fill='#87CEEB')
                draw.text((x_centered, y_text), titulo, font=font_titulo, fill='#FF6B9D')
            else:
                draw.text((x_centered + 3, y_text + 3), titulo, font=font_titulo, fill='#cccccc')
                draw.text((x_centered, y_text), titulo, font=font_titulo, fill='#1a5490')
            
            y_text += 95
            y_text += 30
            
            if estilo == "infantil":
                colors = ['#FF6B9D', '#FFD93D', '#6BCF7F', '#4ECDC4', '#95E1D3']
                line_margin = 450
                segment_width = (a4_width - 2 * line_margin) // len(colors)
                for i, color in enumerate(colors):
                    x1 = line_margin + i * segment_width
                    x2 = x1 + segment_width
                    draw.rectangle([(x1, y_text), (x2, y_text + 8)], fill=color)
            else:
                line_margin = 500
                draw.line([(line_margin, y_text), (a4_width - line_margin, y_text)], fill='#1a5490', width=3)
            
            y_text += 75
        
        # TEXTO CON MARKDOWN
        text_color = '#2C3E50' if estilo == "infantil" else '#2c2c2c'
        texto_lines = wrap_text_with_markdown(texto_cuento, fonts, max_width_px, draw)
        
        logger.info(f"📝 {len(texto_lines)} líneas de texto")
        
        lines_drawn = 0
        for i, line in enumerate(texto_lines):
            if y_text > max_height:
                logger.warning(f"⚠️ Truncado en {i+1}/{len(texto_lines)} (faltan {len(texto_lines)-i})")
                break
            
            x_pos = margin_left + 120 if i == 0 else margin_left
            draw_formatted_line(draw, x_pos, y_text, line, fonts, text_color)
            y_text += line_spacing
            lines_drawn += 1
        
        logger.info(f"✅ {lines_drawn}/{len(texto_lines)} líneas dibujadas")
        
        if estilo == "infantil":
            draw_wavy_border(draw, a4_width, a4_height)
        
        output_path = "/tmp/ficha_completa.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Ficha creada")
        
        return FileResponse(output_path, media_type="image/png", filename="ficha_educativa.png")
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {
        "status": "ok",
        "version": "4.6-KIDS",
        "features": ["larger_font_52px", "smaller_header_1150px", "kid_friendly"],
        "message": "Optimized for 8-year-old children"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "4.6"}
