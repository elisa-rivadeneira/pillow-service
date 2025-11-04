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

def draw_stars(draw, a4_width, y_position):
    """Dibuja estrellitas decorativas"""
    star_color = '#FFD700'
    positions = [
        (400, y_position - 20),
        (450, y_position - 40),
        (a4_width - 450, y_position - 40),
        (a4_width - 400, y_position - 20)
    ]
    
    for x, y in positions:
        points = []
        for i in range(10):
            angle = i * 36
            radius = 25 if i % 2 == 0 else 12
            import math
            px = x + radius * math.cos(math.radians(angle - 90))
            py = y + radius * math.sin(math.radians(angle - 90))
            points.append((px, py))
        draw.polygon(points, fill=star_color, outline='#FFA500')

def draw_wavy_border(draw, a4_width, a4_height):
    """Dibuja un borde ondulado infantil"""
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
    header_height: int = Form(default=1450),
    estilo: str = Form(default="infantil"),
    imagen_modo: str = Form(default="crop")  # "crop" o "stretch"
):
    logger.info(f"📥 v4.1: titulo='{titulo}', modo_imagen={imagen_modo}")
    
    try:
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        a4_width = 2480
        a4_height = 3508
        
        if estilo == "infantil":
            canvas = Image.new('RGB', (a4_width, a4_height), '#FFFEF0')
        else:
            canvas = Image.new('RGB', (a4_width, a4_height), 'white')
        
        # PROCESAMIENTO DE IMAGEN - DOS MODOS
        if imagen_modo == "stretch":
            # MODO 1: ESTIRAR (puede distorsionar)
            logger.info("Modo: estirar imagen para llenar ancho")
            header_img_final = header_img.resize((a4_width, header_height), Image.Resampling.LANCZOS)
            canvas.paste(header_img_final, (0, 0))
        
        else:  # modo "crop"
            # MODO 2: RECORTAR (mantiene proporción, recorta lo que sobra)
            logger.info("Modo: recortar imagen para llenar ancho")
            aspect_ratio = header_img.width / header_img.height
            target_aspect = a4_width / header_height
            
            if aspect_ratio > target_aspect:
                # Imagen más ancha: ajustar por altura y recortar ancho
                new_height = header_height
                new_width = int(header_height * aspect_ratio)
                header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Recortar el centro
                left = (new_width - a4_width) // 2
                header_img_final = header_img_resized.crop((left, 0, left + a4_width, header_height))
            else:
                # Imagen más alta: ajustar por ancho y recortar altura
                new_width = a4_width
                new_height = int(a4_width / aspect_ratio)
                header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
                
                # Recortar desde arriba
                header_img_final = header_img_resized.crop((0, 0, a4_width, header_height))
            
            canvas.paste(header_img_final, (0, 0))
        
        draw = ImageDraw.Draw(canvas)
        
        # Fuentes
        try:
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 75)
            font_texto = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 50)
        except:
            font_titulo = ImageFont.load_default()
            font_texto = ImageFont.load_default()
        
        margin_left = 180
        margin_right = 180
        margin_top = header_height + 100
        line_spacing = 85
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3250
        
        y_text = margin_top
        
        # TÍTULO
        if titulo:
            if estilo == "infantil":
                draw_stars(draw, a4_width, y_text + 40)
            
            titulo_lines = wrap_text_smart(titulo, font_titulo, max_width_px, draw)
            
            for line in titulo_lines:
                bbox = draw.textbbox((0, 0), line, font=font_titulo)
                text_width = bbox[2] - bbox[0]
                x_centered = (a4_width - text_width) // 2
                
                if estilo == "infantil":
                    draw.text((x_centered + 4, y_text + 4), line, font=font_titulo, fill='#FFB6C1')
                    draw.text((x_centered + 2, y_text + 2), line, font=font_titulo, fill='#87CEEB')
                    draw.text((x_centered, y_text), line, font=font_titulo, fill='#FF6B9D')
                else:
                    draw.text((x_centered + 3, y_text + 3), line, font=font_titulo, fill='#cccccc')
                    draw.text((x_centered, y_text), line, font=font_titulo, fill='#1a5490')
                
                y_text += 95
            
            # Línea decorativa
            y_text += 35
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
            
            y_text += 80
        
        # TEXTO
        texto_lines = wrap_text_smart(texto_cuento, font_texto, max_width_px, draw)
        
        for i, line in enumerate(texto_lines):
            if y_text > max_height:
                break
            
            x_pos = margin_left + 120 if i == 0 else margin_left
            text_color = '#2C3E50' if estilo == "infantil" else '#2c2c2c'
            draw.text((x_pos, y_text), line, font=font_texto, fill=text_color)
            y_text += line_spacing
        
        # BORDE
        if estilo == "infantil":
            draw_wavy_border(draw, a4_width, a4_height)
        
        output_path = "/tmp/ficha_completa.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Ficha creada")
        
        return FileResponse(output_path, media_type="image/png", filename="ficha_educativa.png")
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
def root():
    return {
        "status": "ok", 
        "version": "4.1-FULLWIDTH",
        "features": ["imagen_ancho_completo", "modo_crop_stretch"]
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "4.1"}