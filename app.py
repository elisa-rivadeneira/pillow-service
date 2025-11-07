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
    # Busca negritas (***texto*** o **texto** o *texto*)
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

def draw_formatted_line(draw, x, y, line, fonts, color, max_width_px=None):
    """Dibuja línea con markdown, y JUSTIFICA si max_width_px es proporcionado."""
    segments = parse_markdown_line(line)
    current_x = x
    
    # Lógica de JUSTIFICACIÓN
    extra_space_per_gap = 0
    
    if max_width_px:
        # 1. Calcular ancho total del texto y número de espacios
        total_text_width_with_default_spaces = 0
        num_spaces = 0
        
        for seg_text, seg_style in segments:
            font = fonts.get(seg_style, fonts['normal'])
            bbox = draw.textbbox((0, 0), seg_text, font=font)
            total_text_width_with_default_spaces += bbox[2] - bbox[0]
            num_spaces += seg_text.count(' ')
        
        # Aplicar justificación si el texto es significativo y necesita rellenar el ancho
        if num_spaces > 0 and (total_text_width_with_default_spaces / max_width_px > 0.7):
            remaining_width = max_width_px - total_text_width_with_default_spaces
            extra_space_per_gap = remaining_width / num_spaces
    
    # 2. Dibujar y distribuir el espacio extra
    for text, style in segments:
        font = fonts.get(style, fonts['normal'])
        
        draw.text((current_x, y), text, font=font, fill=color)
        
        bbox = draw.textbbox((0, 0), text, font=font)
        text_width = bbox[2] - bbox[0]
        
        current_x += text_width
        
        if extra_space_per_gap > 0:
            spaces_in_segment = text.count(' ')
            current_x += spaces_in_segment * extra_space_per_gap
            
    return max_width_px if extra_space_per_gap > 0 else (current_x - x)

def wrap_text_with_markdown(text, fonts, max_width_px, draw):
    """Divide texto respetando markdown Y PÁRRAFOS"""
    
    text_normalized = re.sub(r'\n{3,}', '\n\n', text)
    paragraphs = text_normalized.split('\n\n')
    
    all_lines = []
    
    for para_idx, para in enumerate(paragraphs):
        if not para.strip():
            continue
        
        para_lines = para.split('\n')
        
        for line_idx, line in enumerate(para_lines):
            if not line.strip():
                continue
            
            words = line.strip().split()
            current_line_words = []
            
            for word in words:
                test_line = ' '.join(current_line_words + [word])
                segments = parse_markdown_line(test_line)
                
                total_width = 0
                for seg_text, seg_style in segments:
                    font = fonts.get(seg_style, fonts['normal'])
                    # Usar el bbox para calcular el ancho total
                    try:
                        bbox = draw.textbbox((0, 0), seg_text, font=font)
                    except Exception:
                        # Fallback simple si la fuente no está cargada correctamente
                        bbox = (0, 0, len(seg_text) * 20, 0) 
                        
                    total_width += bbox[2] - bbox[0]
                
                if total_width <= max_width_px:
                    current_line_words.append(word)
                else:
                    if current_line_words:
                        all_lines.append((' '.join(current_line_words), 'text'))
                    current_line_words = [word]
            
            if current_line_words:
                all_lines.append((' '.join(current_line_words), 'text'))
        
        # AGREGAR LÍNEA VACÍA ENTRE PÁRRAFOS (excepto después del último)
        if para_idx < len(paragraphs) - 1:
            all_lines.append(('', 'paragraph_break'))
    
    return all_lines

def draw_wavy_border(draw, a4_width, a4_height):
    """Dibuja borde ondulado infantil"""
    import math
    colors = ['#FF6B9D', '#FFA07A', '#FFD93D', '#6BCF7F', '#4ECDC4', '#95E1D3']
    margin = 60
    wave_width = 40
    
    # Dibujar semicírculos decorativos en el borde
    for x in range(margin, a4_width - margin, 10):
        wave_y_top = margin + wave_width * math.sin(x * 0.05)
        draw.ellipse([x, wave_y_top - 5, x + 10, wave_y_top + 5], fill=colors[x % len(colors)])
    
    for x in range(margin, a4_width - margin, 10):
        wave_y_bottom = a4_height - margin - wave_width * math.sin(x * 0.05)
        draw.ellipse([x, wave_y_bottom - 5, x + 10, wave_y_bottom + 5], fill=colors[x % len(colors)])

@app.post("/crear-ficha")
async def crear_ficha(
    imagen: UploadFile = File(...),
    texto_cuento: str = Form(...),
    titulo: str = Form(default=""),
    header_height: int = Form(default=1150),
    estilo: str = Form(default="infantil"),
    imagen_modo: str = Form(default="crop")
):
    logger.info(f"📥 v5.3-DROP-CAP: {len(texto_cuento)} chars, header={header_height}px")
    
    try:
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        a4_width = 2480
        a4_height = 3508
        canvas = Image.new('RGB', (a4_width, a4_height), '#FFFEF0' if estilo == "infantil" else 'white')
        
        # PROCESAMIENTO DE IMAGEN
        # ... (La lógica de recorte y estiramiento se mantiene) ...
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
                top_crop = max(0, (new_height - header_height) // 2)
                bottom_crop = top_crop + header_height
                header_img_final = header_img_resized.crop((0, top_crop, a4_width, bottom_crop))
                logger.info(f"📐 Imagen vertical centrada (recorte: top={top_crop}px)")
            
            canvas.paste(header_img_final, (0, 0))
        
        draw = ImageDraw.Draw(canvas)
        
        # FUENTES
        try:
            # Fuentes de texto normal y negrita
            font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 52)
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            # Fuente del título
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 75)
            # Fuente para la Letra Capital (se usa Serif para contraste)
            font_drop_cap = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 150)
            logger.info("✅ Fuentes cargadas")
        except Exception as e:
            logger.error(f"❌ Error fuentes: {e}")
            font_normal = ImageFont.load_default()
            font_bold = ImageFont.load_default()
            font_titulo = ImageFont.load_default()
            font_drop_cap = ImageFont.load_default()
        
        fonts = {
            'normal': font_normal,
            'bold': font_bold,
            'italic': font_bold,
            'bold_italic': font_bold
        }
        
        # LAYOUT
        margin_left = 160
        margin_right = 160
        line_spacing = 80 # Altura de línea normal
        paragraph_spacing = 40  
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3380

        # Coordenada Y donde empieza el texto
        y_text = header_height + 85 
        
        # TÍTULO (Superpuesto en la imagen)
        if titulo:
            title_x = 100 
            title_y = 100
            shadow_color = (0, 0, 0)
            title_color = (255, 255, 255) 
            
            draw.text((title_x + 3, title_y + 3), titulo, font=font_titulo, fill=shadow_color)
            draw.text((title_x, title_y), titulo, font=font_titulo, fill=title_color)
            
        # ----------------------------------------------------------------------
        # LÓGICA DE DIBUJADO DE TEXTO CON LETRA CAPITAL
        # ----------------------------------------------------------------------
        
        text_color = '#2C3E50' if estilo == "infantil" else '#2c2c2c'
        
        # 1. Procesar el texto completo en líneas
        temp_draw = ImageDraw.Draw(Image.new('RGB', (1, 1))) # Objeto para cálculo de ancho
        texto_lines = wrap_text_with_markdown(texto_cuento, fonts, max_width_px, temp_draw)
        
        # 2. Encontrar la primera línea de texto
        first_text_line_index = -1
        for i, (line, line_type) in enumerate(texto_lines):
            if line_type == 'text' and line.strip():
                first_text_line_index = i
                break

        start_index_for_main_loop = 0 # Por defecto, si no hay Drop Cap
        
        if first_text_line_index != -1:
            full_first_line_content, _ = texto_lines[first_text_line_index]
            drop_cap_char = full_first_line_content[0]
            
            # Unir el resto de la primera línea con el resto de líneas del primer párrafo
            first_paragraph_content_lines = []
            
            # Obtener todas las líneas de texto del primer párrafo (desde la primera línea)
            idx_end_first_para = first_text_line_index
            while idx_end_first_para < len(texto_lines) and texto_lines[idx_end_first_para][1] != 'paragraph_break':
                first_paragraph_content_lines.append(texto_lines[idx_end_first_para][0])
                idx_end_first_para += 1
            
            # Todo el texto a rodear la letra capital
            text_to_reflow = " ".join(first_paragraph_content_lines)[1:].lstrip() # Quitar la letra capital
            
            # --- SETUP DE LETRA CAPITAL ---
            DROP_CAP_LINES = 3 # Número de líneas que ocupa verticalmente
            
            # La altura de la fuente se ajusta para que el baseline coincida con 3 líneas
            drop_cap_size = line_spacing * (DROP_CAP_LINES + 0.8) 
            
            # Dibujar la letra capital
            drop_cap_x = margin_left
            drop_cap_y = y_text
            
            # Recalcular la fuente con el tamaño final
            try:
                font_drop_cap = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", int(drop_cap_size))
            except Exception:
                font_drop_cap = font_titulo 
            
            # Calcular ancho de la Letra Capital
            bbox_cap = draw.textbbox((0, 0), drop_cap_char, font=font_drop_cap)
            cap_width = bbox_cap[2] - bbox_cap[0]
            
            # Colores y Sombra
            cap_color = '#ef4444' 
            shadow_color = (0, 0, 0, 80) 
            
            # 2. DIBUJAR LETRA CAPITAL
            draw.text((drop_cap_x + 3, drop_cap_y + 3), drop_cap_char, font=font_drop_cap, fill=shadow_color)
            draw.text((drop_cap_x, drop_cap_y), drop_cap_char, font=font_drop_cap, fill=cap_color)
            
            # 3. RE-WRAPPING para el texto que va junto a la cap
            rest_x = drop_cap_x + cap_width + 20 
            rest_max_width = a4_width - rest_x - margin_right
            
            # Re-envolver el texto restante, ahora con un ancho reducido
            wrapped_reflow_text = wrap_text_with_markdown(text_to_reflow, fonts, rest_max_width, temp_draw)
            
            y_current_temp = drop_cap_y + 0.1 * line_spacing 
            
            # 3a. Dibuja las líneas que van AL LADO de la Letra Capital
            lines_drawn_around_cap = 0
            
            for j, (line_content, _) in enumerate(wrapped_reflow_text):
                if lines_drawn_around_cap < DROP_CAP_LINES:
                    # Dibujar con ancho reducido y justificación
                    draw_formatted_line(draw, rest_x, y_current_temp, line_content, fonts, text_color, max_width_px=rest_max_width)
                    y_current_temp += line_spacing
                    lines_drawn_around_cap += 1
                else:
                    break

            # 3b. Mover el punto de inicio para el resto del cuento
            y_text = drop_cap_y + DROP_CAP_LINES * line_spacing + paragraph_spacing 
            
            # 3c. Dibujar el resto de las líneas del primer párrafo (si hubo overflow)
            for j in range(lines_drawn_around_cap, len(wrapped_reflow_text)):
                line_content, _ = wrapped_reflow_text[j]
                if y_text > max_height: break
                
                # Usar ancho completo para el resto del párrafo
                x_pos = margin_left
                draw_formatted_line(draw, x_pos, y_text, line_content, fonts, text_color, max_width_px=max_width_px)
                y_text += line_spacing
            
            # Si el primer párrafo original terminó con un salto de línea, avanzar
            if idx_end_first_para < len(texto_lines) and texto_lines[idx_end_first_para][1] == 'paragraph_break':
                y_text += paragraph_spacing
                idx_end_first_para += 1 
            
            # El bucle principal debe empezar a dibujar a partir del segundo párrafo
            start_index_for_main_loop = idx_end_first_para 
            lines_drawn = 1
        
        # ----------------------------------------------------------------------
        # BUCLE PRINCIPAL PARA EL RESTO DEL CUENTO (PÁRRAFOS SIGUIENTES)
        # ----------------------------------------------------------------------

        for i in range(start_index_for_main_loop, len(texto_lines)):
            line, line_type = texto_lines[i]
            
            if y_text > max_height:
                logger.warning(f"⚠️ Truncado en línea {i+1}/{len(texto_lines)}")
                break
            
            if line_type == 'paragraph_break':
                y_text += paragraph_spacing  
                continue

            x_pos = margin_left
            
            draw_formatted_line(draw, x_pos, y_text, line, fonts, text_color, 
                                max_width_px=max_width_px)
            
            y_text += line_spacing
            lines_drawn += 1

        logger.info(f"✅ {lines_drawn} líneas de texto dibujadas (incluyendo párrafos reflow)")
        
        if estilo == "infantil":
            draw_wavy_border(draw, a4_width, a4_height)
        
        output_path = "/tmp/ficha_completa.png"
        canvas.save(output_path, quality=95, dpi=(300, 300))
        
        logger.info("✅ Ficha creada con Letra Capital")
        
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

        # Convertir a RGBA para agregar transparencia
        canvas = canvas.convert('RGBA')

        # Crear overlay blanco semitransparente
        overlay = Image.new('RGBA', (a4_width, a4_height), (0, 0, 0, 0))
        overlay_draw = ImageDraw.Draw(overlay)

        # Área del contenido (ajusta márgenes para no tapar decoraciones)
        content_margin_top = 250
        content_margin_bottom = 450
        content_margin_left = 280
        content_margin_right = 280

        # Rectángulo blanco semitransparente
        overlay_draw.rectangle(
            [
                (content_margin_left, content_margin_top),
                (a4_width - content_margin_right, a4_height - content_margin_bottom)
            ],
            fill=(255, 255, 255, 210)
        )

        # Combinar canvas con overlay
        canvas = Image.alpha_composite(canvas, overlay)

        # Volver a RGB
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

            # Si es un array con 1 elemento, separar por \n\n
            if len(preguntas_list) == 1 and '\n\n' in preguntas_list[0]:
                preguntas_list = preguntas_list[0].split('\n\n')

            logger.info(f"✅ {len(preguntas_list)} preguntas parseadas")
        except (json.JSONDecodeError, TypeError) as e:
            logger.error(f"Error parseando JSON: {e}")
            preguntas_list = preguntas.split('\n\n')
        
        # CONFIGURACIÓN DE LAYOUT
        margin_left = 350
        margin_right = 350
        margin_top = 350
        line_spacing = 65
        option_spacing = 55
        question_spacing = 40
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
            
            # Separar pregunta de opciones
            partes = pregunta_completa.split('\n')
            pregunta_principal = partes[0].strip()
            opciones = [p.strip() for p in partes[1:] if p.strip() and p.strip().startswith(('a)', 'b)', 'c)', 'd)'))]
            
            # Limpiar numeración si ya viene
            import re
            pregunta_sin_numero = re.sub(r'^\d+\.\s*', '', pregunta_principal)
            
            # NÚMERO DE PREGUNTA
            numero = str(idx + 1)
            
            if estilo == "infantil":
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
            
            # USAR LA VERSIÓN MEJORADA que respeta saltos de línea
            pregunta_lines_with_type = wrap_text_with_markdown(pregunta_sin_numero, fonts, max_width_pregunta, draw)
            
            for line, line_type in pregunta_lines_with_type:
                if line_type == 'paragraph_break':
                    y_text += 40  # Espacio entre párrafos en preguntas
                    continue
                draw_formatted_line(draw, x_pregunta, y_text, line, fonts, text_color)
                y_text += line_spacing
            
            # OPCIONES (si las hay)
            if opciones:
                y_text += 15
                
                for opcion in opciones:
                    if y_text > max_height:
                        break
                    
                    x_opcion = x_pregunta + 60
                    opcion_lines_with_type = wrap_text_with_markdown(opcion, fonts_opciones, max_width_pregunta - 60, draw)
                    
                    for line, line_type in opcion_lines_with_type:
                        if line_type == 'paragraph_break':
                            continue
                        draw_formatted_line(draw, x_opcion, y_text, line, fonts_opciones, text_color)
                        y_text += option_spacing
                
                y_text += question_spacing
            else:
                y_text += question_spacing + 20
            
            # LÍNEA PARA RESPUESTA
            if y_text + answer_line_height < max_height:
                line_start_x = margin_left + 50
                line_end_x = a4_width - margin_right - 50
                
                if estilo == "infantil":
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
        "version": "5.3-DROP-CAP",
        "features": ["crear_ficha", "crear_hoja_preguntas"],
        "endpoints": {
            "POST /crear-ficha": "Crea ficha de lectura con imagen y texto del cuento (DROP CAP en primer párrafo)",
            "POST /crear-hoja-preguntas": "Crea hoja de preguntas con borde decorativo"
        },
        "message": "Dual service: reading worksheets + question sheets (SOPORTE DE LETRA CAPITAL Y JUSTIFICACIÓN)"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "5.3-DROP-CAP"}
