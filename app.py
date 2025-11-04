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
                # Imagen más vertical o cuadrada → recorte centrado verticalmente (modo cover)
                new_width = a4_width
                new_height = int(a4_width / aspect_ratio)
                header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)

                # Centramos verticalmente en el header
                top_crop = max(0, (new_height - header_height) // 2)
                bottom_crop = top_crop + header_height

                header_img_final = header_img_resized.crop((0, top_crop, a4_width, bottom_crop))
                logger.info(f"📐 Imagen vertical centrada (recorte: top={top_crop}px)")

            
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




@app.post("/crear-hoja-preguntas")
async def crear_hoja_preguntas(
    imagen_borde: UploadFile = File(...),
    preguntas: str = Form(...),
    titulo_cuento: str = Form(default=""),
    estilo: str = Form(default="infantil")
):
    logger.info(f"📝 v4.0-PREGUNTAS-OPCIONES: {len(preguntas)} caracteres")
    
    try:
        # Leer imagen del borde
        img_bytes = await imagen_borde.read()
        border_img = Image.open(io.BytesIO(img_bytes))
        
        if border_img.mode != 'RGB':
            border_img = border_img.convert('RGB')
        
        # Dimensiones A4
        a4_width = 2480
        a4_height = 3508
        
        # ADAPTAR IMAGEN A A4 (ESTIRAR)
        logger.info(f"📐 Estirando imagen {border_img.width}x{border_img.height} a A4 {a4_width}x{a4_height}")
        canvas = border_img.resize((a4_width, a4_height), Image.Resampling.LANCZOS)
        
        if canvas.mode != 'RGB':
            canvas = canvas.convert('RGB')
        
        draw = ImageDraw.Draw(canvas)
        
        # FUENTES
        try:
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70)
            font_subtitulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 55)
            font_preguntas = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 45)
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 48)
            font_numero = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            font_opciones = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 42)
            logger.info("✅ Fuentes cargadas")
        except Exception as e:
            logger.error(f"❌ Error fuentes: {e}")
            font_titulo = ImageFont.load_default()
            font_subtitulo = ImageFont.load_default()
            font_preguntas = ImageFont.load_default()
            font_bold = ImageFont.load_default()
            font_numero = ImageFont.load_default()
            font_opciones = ImageFont.load_default()
        
        fonts = {
            'normal': font_preguntas,
            'bold': font_bold,
            'italic': font_bold,
            'bold_italic': font_bold
        }
        
        fonts_opciones = {
            'normal': font_opciones,
            'bold': font_opciones,
            'italic': font_opciones,
            'bold_italic': font_opciones
        }
        
        # PROCESAR PREGUNTAS
        try:
            import json
            preguntas_list = json.loads(preguntas)
            if not isinstance(preguntas_list, list):
                preguntas_list = [preguntas]
            logger.info(f"✅ {len(preguntas_list)} preguntas parseadas")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parseando JSON: {e}")
            preguntas_list = preguntas.split('\n\n')
        
        # CONFIGURACIÓN DE LAYOUT
        margin_left = 350
        margin_right = 350
        margin_top = 350
        line_spacing = 65
        option_spacing = 55  # Espacio entre opciones
        question_spacing = 40  # Espacio antes de línea de respuesta
        answer_line_height = 50
        space_after_answer = 70
        max_width_px = a4_width - margin_left - margin_right
        
        y_text = margin_top
        
        # ENCABEZADO
        encabezado = "📚 Comprensión Lectora"
        bbox = draw.textbbox((0, 0), encabezado, font=font_titulo)
        text_width = bbox[2] - bbox[0]
        x_centered = (a4_width - text_width) // 2
        
        if estilo == "infantil":
            draw.text((x_centered + 3, y_text + 3), encabezado, font=font_titulo, fill='#FFB6C1')
            draw.text((x_centered, y_text), encabezado, font=font_titulo, fill='#FF6B9D')
        else:
            draw.text((x_centered, y_text), encabezado, font=font_titulo, fill='#1a5490')
        
        y_text += 85
        
        # TÍTULO DEL CUENTO
        if titulo_cuento:
            cuento_text = f'Cuento: "{titulo_cuento}"'
            bbox = draw.textbbox((0, 0), cuento_text, font=font_subtitulo)
            text_width = bbox[2] - bbox[0]
            x_centered = (a4_width - text_width) // 2
            draw.text((x_centered, y_text), cuento_text, font=font_subtitulo, fill='#2C3E50')
            y_text += 70
        
        # LÍNEA SEPARADORA
        line_margin = 450
        if estilo == "infantil":
            colors = ['#FF6B9D', '#FFD93D', '#6BCF7F', '#4ECDC4']
            segment_width = (a4_width - 2 * line_margin) // len(colors)
            for i, color in enumerate(colors):
                x1 = line_margin + i * segment_width
                x2 = x1 + segment_width
                draw.rectangle([(x1, y_text), (x2, y_text + 6)], fill=color)
        else:
            draw.line([(line_margin, y_text), (a4_width - line_margin, y_text)], fill='#1a5490', width=3)
        
        y_text += 55
        
        # CAMPOS DE NOMBRE Y FECHA
        campos_y = y_text
        draw.text((margin_left, campos_y), "Nombre:", font=font_preguntas, fill='#2C3E50')
        line_x_start = margin_left + 200
        line_x_end = margin_left + 800
        draw.line([(line_x_start, campos_y + 50), (line_x_end, campos_y + 50)], fill='#2C3E50', width=2)
        
        fecha_x = a4_width - margin_right - 400
        draw.text((fecha_x, campos_y), "Fecha:", font=font_preguntas, fill='#2C3E50')
        line_x_start = fecha_x + 140
        line_x_end = a4_width - margin_right
        draw.line([(line_x_start, campos_y + 50), (line_x_end, campos_y + 50)], fill='#2C3E50', width=2)
        
        y_text += 120
        
        # DIBUJAR PREGUNTAS CON OPCIONES Y RESPUESTAS
        text_color = '#2C3E50'
        max_height = 3100
        
        logger.info(f"📝 Dibujando {len(preguntas_list)} preguntas")
        
        questions_drawn = 0
        for idx, pregunta_completa in enumerate(preguntas_list):
            if not pregunta_completa.strip():
                continue
            
            if y_text > max_height:
                logger.warning(f"⚠️ Truncado en pregunta {idx+1}/{len(preguntas_list)}")
                break
            
            # Separar pregunta de opciones (si las tiene)
            # Las opciones están separadas por \n
            partes = pregunta_completa.split('\n')
            pregunta_principal = partes[0].strip()
            opciones = [p.strip() for p in partes[1:] if p.strip() and p.strip().startswith(('a)', 'b)', 'c)', 'd)'))]
            
            # Limpiar numeración si ya viene
            import re
            pregunta_sin_numero = re.sub(r'^\d+\.\s*', '', pregunta_principal)
            
            # NÚMERO DE PREGUNTA
            numero = str(idx + 1)
            
            if estilo == "infantil":
                # Círculo decorativo
                circle_x = margin_left - 35
                circle_y = y_text + 18
                circle_radius = 26
                
                draw.ellipse(
                    [(circle_x - circle_radius, circle_y - circle_radius),
                     (circle_x + circle_radius, circle_y + circle_radius)],
                    fill='#FF6B9D',
                    outline='#E91E63',
                    width=3
                )
                
                bbox = draw.textbbox((0, 0), numero, font=font_numero)
                num_width = bbox[2] - bbox[0]
                num_height = bbox[3] - bbox[1]
                draw.text(
                    (circle_x - num_width//2, circle_y - num_height//2 - 3),
                    numero,
                    font=font_numero,
                    fill='white'
                )
                
                x_pregunta = margin_left + 40
            else:
                draw.text((margin_left - 50, y_text), f"{numero}.", font=font_numero, fill='#1a5490')
                x_pregunta = margin_left
            
            # TEXTO DE LA PREGUNTA
            max_width_pregunta = max_width_px - 40
            pregunta_lines = wrap_text_with_markdown(pregunta_sin_numero, fonts, max_width_pregunta, draw)
            
            for line in pregunta_lines:
                draw_formatted_line(draw, x_pregunta, y_text, line, fonts, text_color)
                y_text += line_spacing
            
            # OPCIONES (si las hay)
            if opciones:
                y_text += 15  # Pequeño espacio antes de opciones
                
                for opcion in opciones:
                    if y_text > max_height:
                        break
                    
                    # Dibujar opción con indentación
                    x_opcion = x_pregunta + 60
                    opcion_lines = wrap_text_with_markdown(opcion, fonts_opciones, max_width_pregunta - 60, draw)
                    
                    for line in opcion_lines:
                        draw_formatted_line(draw, x_opcion, y_text, line, fonts_opciones, text_color)
                        y_text += option_spacing
                
                y_text += question_spacing
            else:
                # Si no hay opciones, es pregunta abierta
                y_text += question_spacing + 20
            
            # LÍNEA PARA RESPUESTA (solo para preguntas sin opciones o después de opciones)
            if y_text + answer_line_height < max_height:
                line_start_x = margin_left + 50
                line_end_x = a4_width - margin_right - 50
                
                if estilo == "infantil":
                    # Línea punteada
                    dot_spacing = 20
                    dot_radius = 3
                    for x in range(line_start_x, line_end_x, dot_spacing):
                        color = ['#FF6B9D', '#FFD93D', '#6BCF7F', '#4ECDC4'][idx % 4]
                        draw.ellipse([(x - dot_radius, y_text - dot_radius),
                                      (x + dot_radius, y_text + dot_radius)],
                                    fill=color)
                else:
                    draw.line([(line_start_x, y_text), (line_end_x, y_text)], 
                             fill='#2C3E50', width=2)
                
                y_text += answer_line_height + space_after_answer
            
            questions_drawn += 1
        
        logger.info(f"✅ {questions_drawn}/{len(preguntas_list)} preguntas dibujadas")
        
        # GUARDAR
        output_path = "/tmp/hoja_preguntas.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Hoja de preguntas creada")
        
        return FileResponse(output_path, media_type="image/png", filename="hoja_preguntas.png")
    
    except Exception as e:
        logger.error(f"❌ Error: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        raise HTTPException(status_code=500, detail=str(e))
    
@app.get("/")
def root():
    return {
        "status": "ok",
        "version": "5.0-DUAL",
        "features": ["crear_ficha", "crear_hoja_preguntas"],
        "endpoints": {
            "POST /crear-ficha": "Crea ficha de lectura con imagen y texto del cuento",
            "POST /crear-hoja-preguntas": "Crea hoja de preguntas con borde decorativo"
        },
        "message": "Dual service: reading worksheets + question sheets"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "5.0"}
