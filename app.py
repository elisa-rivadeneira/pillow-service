from fastapi import FastAPI, File, UploadFile, Form, HTTPException
from fastapi.responses import FileResponse
from PIL import Image, ImageDraw, ImageFont
import io
import logging
import re

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI()

def to_title_case(text: str) -> str:
    """
    Convierte un string a Title Case (Capitalización de Título), donde la 
    primera letra de cada palabra importante se pone en mayúscula.
    Se mantienen en minúscula artículos, preposiciones cortas y conjunciones.
    """
    if not text:
        return ""

    # Palabras funcionales cortas que deben estar en minúscula (en español)
    minor_words = [
        'el', 'la', 'los', 'las', 'un', 'una', 'unos', 'unas', # Artículos
        'de', 'a', 'en', 'por', 'con', 'sin', 'sobre', 'tras', # Preposiciones
        'y', 'o', 'ni', 'pero', 'mas', 'que' # Conjunciones y relativos
    ]

    words = text.lower().split()
    title_cased_words = []
    
    for i, word in enumerate(words):
        # La primera palabra siempre va capitalizada
        if i == 0 or i == len(words) - 1:
            title_cased_words.append(word.capitalize())
        # Las palabras que no son "menores" se capitalizan
        elif word not in minor_words:
            title_cased_words.append(word.capitalize())
        # Las palabras "menores" (artículos, preposiciones, etc.) se dejan en minúscula
        else:
            title_cased_words.append(word)

    return " ".join(title_cased_words)


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
            segments.append((matched_text[1:-1], 'bold')) # Corregido: asumimos *texto* también es bold si no hay italic separado
        
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
            # Usar textlength para ser más preciso y evitar el overhead de bbox
            try:
                text_width = draw.textlength(seg_text, font=font)
                total_text_width_with_default_spaces += text_width
            except AttributeError:
                # Fallback para versiones antiguas de Pillow o fuentes no cargadas
                bbox = draw.textbbox((0, 0), seg_text, font=font)
                total_text_width_with_default_spaces += bbox[2] - bbox[0]
                
            num_spaces += seg_text.count(' ')
        
        # Aplicar justificación si el texto es significativo y necesita rellenar el ancho
        # (El texto no debe ser demasiado corto para justificar)
        if num_spaces > 0 and (total_text_width_with_default_spaces / max_width_px > 0.7):
            remaining_width = max_width_px - total_text_width_with_default_spaces
            # El espacio extra se divide entre el número de gaps (los espacios)
            extra_space_per_gap = remaining_width / num_spaces
    
    # 2. Dibujar y distribuir el espacio extra
    for text, style in segments:
        font = fonts.get(style, fonts['normal'])
        
        draw.text((current_x, y), text, font=font, fill=color)
        
        # Calcular el ancho del texto dibujado (sin contar espacios)
        try:
            text_width = draw.textlength(text, font=font)
        except AttributeError:
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
                    # Usar bbox para cálculo de ancho dentro del bucle
                    try:
                        bbox = draw.textbbox((0, 0), seg_text, font=font)
                    except Exception:
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
    # Se elimina imagen_modo, ahora es cover centrado por defecto
):
    logger.info(f"📥 v6.8-BG-IMAGEN-100%-CAPA-BLANCA-CENTRAL: {len(texto_cuento)} chars, header={header_height}px")
    
    try:
        img_bytes = await imagen.read()
        header_img = Image.open(io.BytesIO(img_bytes))
        
        if header_img.mode != 'RGB':
            header_img = header_img.convert('RGB')
        
        a4_width = 2480
        a4_height = 3508
        
        # Inicializar canvas en RGBA para poder usar alpha_composite
        canvas = Image.new('RGBA', (a4_width, a4_height), '#FFFEF0' if estilo == "infantil" else 'white')
        
        # PROCESAMIENTO DE IMAGEN: Implementación de COVER CENTRADO
        # -----------------------------------------------------------
        target_aspect = a4_width / header_height
        image_aspect = header_img.width / header_img.height

        if image_aspect < target_aspect:  
            # La imagen es más "alta" (más estrecha) que el contenedor. Escalar por ancho.
            new_width = a4_width
            new_height = int(a4_width / image_aspect)
            header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Recortar verticalmente, centrado: (new_height - header_height) / 2
            top_crop = max(0, (new_height - header_height) // 2)
            bottom_crop = top_crop + header_height
            header_img_final = header_img_resized.crop((0, top_crop, new_width, bottom_crop))
            logger.info(f"📐 Imagen escalada por ancho y recortada verticalmente (cover centrado): top={top_crop}")
        else:  
            # La imagen es más "ancha" (más baja) que el contenedor. Escalar por alto.
            new_height = header_height
            new_width = int(header_height * image_aspect)
            header_img_resized = header_img.resize((new_width, new_height), Image.Resampling.LANCZOS)
            
            # Recortar horizontalmente, centrado: (new_width - a4_width) // 2
            left_crop = max(0, (new_width - a4_width) // 2)
            right_crop = left_crop + a4_width
            header_img_final = header_img_resized.crop((left_crop, 0, right_crop, new_height))
            logger.info(f"📐 Imagen escalada por alto y recortada horizontalmente (cover centrado): left={left_crop}")
            
        # Pegar la imagen de cabecera (RGB) sobre el canvas (RGBA)
        canvas.paste(header_img_final, (0, 0))
        # -----------------------------------------------------------
        
        # Crear un Draw en el canvas (RGBA)
        draw = ImageDraw.Draw(canvas)
        
        # FUENTES
        try:
            # Fuentes del CUENTO 
            font_normal = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 52)
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52)
            
            # Título del Cuento: **DejaVuSerif-Bold es la alternativa manuscrita disponible**
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 100) 
            
            # Letra Capital
            font_drop_cap_base = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", 150) 
            logger.info("✅ Fuentes cargadas (Título actualizado a Serif-Bold)")
        except Exception as e:
            logger.error(f"❌ Error fuentes: {e}")
            font_normal = ImageFont.load_default()
            font_bold = ImageFont.load_default()
            font_titulo = ImageFont.load_default()
            font_drop_cap_base = ImageFont.load_default()
        
        fonts = {
            'normal': font_normal,
            'bold': font_bold,
            'italic': font_bold,
            'bold_italic': font_bold
        }
        
        # LAYOUT
        margin_left = 160
        margin_right = 160
        line_spacing = 80 
        paragraph_spacing = 40  
        max_width_px = a4_width - margin_left - margin_right
        max_height = 3380

        y_text = header_height + 85 
        
        # TÍTULO (Superpuesto en la imagen con fondo semitransparente)
        if titulo:
            # APLICAR CAPITALIZACIÓN DE TÍTULO
            titulo_capitalizado = to_title_case(titulo)
            logger.info(f"Título original: '{titulo}' -> Capitalizado: '{titulo_capitalizado}'")
            
            title_x_bg = 100 # Punto de inicio del fondo
            title_y_bg = 100
            
            # Calcular tamaño del bounding box del título con la nueva fuente
            bbox_title = draw.textbbox((0, 0), titulo_capitalizado, font=font_titulo)
            title_width = bbox_title[2] - bbox_title[0]
            title_height = bbox_title[3] - bbox_title[1]

            # AJUSTE DE MARGEN (CORREGIDO)
            padding_x = 40 
            padding_y = 30
            
            # Coordenadas del rectángulo de fondo
            title_bg_rect = [
                (title_x_bg, title_y_bg),
                (title_x_bg + title_width + 2 * padding_x, title_y_bg + title_height + 2 * padding_y)
            ]
            
            # Coordenadas donde empieza el texto (centrado dentro del padding)
            title_offset_x = title_x_bg + padding_x
            title_offset_y = title_y_bg + padding_y
            
            # Crear una capa temporal para el fondo semitransparente (RGBA)
            alpha_img = Image.new('RGBA', canvas.size, (255, 255, 255, 0)) # Completamente transparente
            alpha_draw = ImageDraw.Draw(alpha_img)
            
            # Dibuja el rectángulo BLANCO semitransparente (180 de opacidad)
            alpha_draw.rectangle(title_bg_rect, fill=(255, 255, 255, 180)) 
            
            # Componer la capa semitransparente sobre el canvas (Ambos son RGBA)
            canvas = Image.alpha_composite(canvas, alpha_img) 

            # Volver a obtener el Draw después de alpha_composite
            draw = ImageDraw.Draw(canvas)
            
            # APLICAR EFECTO INFANTIL AL TÍTULO DEL CUENTO (ROSA FUERTE/PÚRPURA)
            title_main_color = '#E91E63'  # Rosa Fuerte/Fucsia
            title_outline_color = '#8E24AA' # Púrpura Profundo (Para sombra/contorno)
            outline_width = 4
            
            # Dibujar contorno para efecto de dulzura/dibujo animado
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    # Dibujar contorno circular
                    if dx * dx + dy * dy >= outline_width * outline_width: 
                        draw.text((title_offset_x + dx, title_offset_y + dy), titulo_capitalizado, font=font_titulo, fill=title_outline_color)
            
            # Dibujar Título principal (Playful color)
            draw.text((title_offset_x, title_offset_y), titulo_capitalizado, font=font_titulo, fill=title_main_color)
            
        # Convertir RGBA -> RGB antes del bucle principal de dibujado de texto.
        canvas = canvas.convert('RGB')
        draw = ImageDraw.Draw(canvas) # Vuelve a crear el objeto Draw para el nuevo modo
        # ----------------------------------------------------------------------
        # LÓGICA DE DIBUJADO DE TEXTO CON LETRA CAPITAL
        # ----------------------------------------------------------------------
        
        text_color = '#2C3E50' if estilo == "infantil" else '#2c2c2c'
        
        # 1. Procesar el texto completo en líneas (dummy draw para cálculo de ancho)
        temp_draw = ImageDraw.Draw(Image.new('RGB', (1, 1))) 
        texto_lines = wrap_text_with_markdown(texto_cuento, fonts, max_width_px, temp_draw)
        
        # 2. Encontrar la primera línea de texto real para la letra capital
        first_text_line_index = -1
        for i, (line, line_type) in enumerate(texto_lines):
            if line_type == 'text' and line.strip():
                first_text_line_index = i
                break

        start_index_for_main_loop = 0
        lines_drawn = 0
        
        if first_text_line_index != -1:
            full_first_line_content, _ = texto_lines[first_text_line_index]
            drop_cap_char = full_first_line_content[0]
            
            # 2a. Recolectar todo el texto del primer párrafo (después de la letra capital)
            first_paragraph_content_lines = []
            idx_end_first_para = first_text_line_index
            while idx_end_first_para < len(texto_lines) and texto_lines[idx_end_first_para][1] != 'paragraph_break':
                first_paragraph_content_lines.append(texto_lines[idx_end_first_para][0])
                idx_end_first_para += 1
            
            text_to_reflow = " ".join(first_paragraph_content_lines)[1:].lstrip() # Quitar la letra capital
            
            # --- SETUP DE LETRA CAPITAL ---
            DROP_CAP_LINES = 3 # Ocupará 3 líneas de altura.
            
            # Ajuste de tamaño de fuente para que la altura total de la caja del texto
            drop_cap_size = line_spacing * (DROP_CAP_LINES + 0.3) 
            
            try:
                font_drop_cap = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf", int(drop_cap_size))
            except Exception:
                font_drop_cap = font_drop_cap_base 
            
            # Calcular ancho de la Letra Capital
            bbox_cap = draw.textbbox((0, 0), drop_cap_char, font=font_drop_cap)
            cap_width = bbox_cap[2] - bbox_cap[0]
            
            # Ajuste vertical fino para alinear la parte superior de la cap con la primera línea de texto
            cap_y_adjustment = -15 
            drop_cap_x = margin_left 
            drop_cap_y_final = y_text + cap_y_adjustment
            
            # Colores
            cap_color = '#ef4444' 
            
            # DIBUJAR LETRA CAPITAL
            draw.text((drop_cap_x, drop_cap_y_final), drop_cap_char, font=font_drop_cap, fill=cap_color)
            
            # 3. RE-WRAPPING para el texto que va junto a la cap
            rest_x = drop_cap_x + cap_width + 25 # Margen derecho de la cap
            rest_max_width = a4_width - rest_x - margin_right
            
            wrapped_reflow_text = wrap_text_with_markdown(text_to_reflow, fonts, rest_max_width, temp_draw)
            
            y_current_reflow = y_text 
            
            # 3a. Dibuja las líneas que van AL LADO de la Letra Capital
            lines_drawn_around_cap = 0
            
            for j, (line_content, _) in enumerate(wrapped_reflow_text):
                if lines_drawn_around_cap < DROP_CAP_LINES:
                    if line_content.strip(): 
                        draw_formatted_line(draw, rest_x, y_current_reflow, line_content, fonts, text_color, max_width_px=rest_max_width)
                    y_current_reflow += line_spacing
                    lines_drawn_around_cap += 1
                else:
                    break

            # 3b. Mover el punto de inicio para el resto del cuento
            # El nuevo punto Y empieza después de las 3 líneas ocupadas por la letra capital
            y_text = y_text + DROP_CAP_LINES * line_spacing + paragraph_spacing 
            lines_drawn = lines_drawn_around_cap
            
            # 3c. Dibujar el resto de las líneas del primer párrafo (si hubo overflow)
            for j in range(lines_drawn_around_cap, len(wrapped_reflow_text)):
                line_content, _ = wrapped_reflow_text[j]
                if y_text > max_height: break
                
                # Usar ancho completo para el resto del párrafo
                x_pos = margin_left
                draw_formatted_line(draw, x_pos, y_text, line_content, fonts, text_color, max_width_px=max_width_px)
                y_text += line_spacing
                lines_drawn += 1
            
            # Si el primer párrafo original terminó con un salto de línea, avanzar
            if idx_end_first_para < len(texto_lines) and texto_lines[idx_end_first_para][1] == 'paragraph_break':
                y_text += paragraph_spacing
                idx_end_first_para += 1 
            
            start_index_for_main_loop = idx_end_first_para 
        
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
    # Se añade la versión al logger para seguimiento
    logger.info(f"📝 v6.8-BG-IMAGEN-100%-CAPA-BLANCA-CENTRAL: {len(preguntas)} caracteres")
    
    try:
        # Leer imagen del borde
        img_bytes = await imagen_borde.read()
        border_img = Image.open(io.BytesIO(img_bytes))
        
        # Dimensiones A4
        a4_width = 2480
        a4_height = 3508
        
        # ADAPTAR IMAGEN A A4 (ESTIRAR)
        logger.info(f"📐 Estirando imagen {border_img.width}x{border_img.height} a A4 {a4_width}x{a4_height}")
        # Inicializar canvas como RGBA para permitir la composición de la capa semi-transparente
        # FIX 1: La imagen de fondo cubre 100% de la hoja A4.
        canvas = border_img.resize((a4_width, a4_height), Image.Resampling.LANCZOS)
        
        if canvas.mode != 'RGBA':
            canvas = canvas.convert('RGBA')

        # ----------------------------------------------------------------------
        # PASO CLAVE: DIBUJAR CAPA SEMI-TRANSPARENTE BLANCA CENTRAL
        # FIX 2: La capa blanca solo cubre la zona CENTRAL del texto, 
        # respetando los márgenes para dejar visible el borde temático de la IA.
        # ----------------------------------------------------------------------
        
        # Márgenes para la capa blanca (debe ser más grande que el margen de texto)
        BACKGROUND_MARGIN_X = 180 
        BACKGROUND_MARGIN_Y = 150
        
        # Coordenadas del área de contenido central (el rectangulo blanco)
        content_x1 = BACKGROUND_MARGIN_X
        content_x2 = a4_width - BACKGROUND_MARGIN_X
        content_y1 = BACKGROUND_MARGIN_Y
        content_y2 = a4_height - BACKGROUND_MARGIN_Y
        
        # Rectángulo que solo cubre el centro
        rect_coords = [
            (content_x1, content_y1),
            (content_x2, content_y2)
        ]
        
        # Crear una imagen temporal RGBA para la capa
        alpha_img = Image.new('RGBA', canvas.size, (255, 255, 255, 0)) # Completamente transparente
        alpha_draw = ImageDraw.Draw(alpha_img)
        
        # Dibujar el rectángulo semi-transparente BLANCO (Casi opaco: 230/255)
        fill_color = (255, 255, 255, 230) # Blanco 90% opaco
        
        alpha_draw.rectangle(rect_coords, fill=fill_color)
        
        # Componer la capa sobre el canvas.
        canvas = Image.alpha_composite(canvas, alpha_img)
        # ----------------------------------------------------------------------
        
        # Convertir a RGB y volver a obtener el Draw.
        canvas = canvas.convert('RGB') 
        draw = ImageDraw.Draw(canvas) 
        
        # FUENTES Y ESTILO
        
        # Color del texto (gris oscuro, plomito) para contrastar con el fondo blanco
        text_color = '#333333' 
        
        try:
            # Título principal (Comprensión Lectora) 
            font_titulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 85) 
            
            # Título del Cuento: 
            font_subtitulo = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 70) 
            
            # Fuentes para el texto de las preguntas y opciones (más grandes y dulces)
            font_preguntas = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 50) 
            font_bold = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 52) 
            font_numero = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", 58) 
            font_opciones = ImageFont.truetype("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", 48) 
            
            logger.info("✅ Fuentes cargadas para hoja de preguntas")
        except Exception as e:
            logger.error(f"❌ Error fuentes: {e}. Usando default.")
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
            'bold': font_bold,
            'italic': font_bold,
            'bold_italic': font_bold
        }
        
        # PROCESAR PREGUNTAS
	try:
	    import json
	    import re
	    
	    # Intenta cargar como JSON (lista de preguntas/opciones)
	    preguntas_list = json.loads(preguntas)
	    if not isinstance(preguntas_list, list):
		preguntas_list = [preguntas]

	    # Si es un array con 1 elemento, intentar separar de forma inteligente
	    if len(preguntas_list) == 1:
		texto_completo = str(preguntas_list[0])
		
		# ESTRATEGIA 1: Buscar numeración (1., 2., 3., etc.) - Funciona con \n o \n\n
		# El patrón busca: inicio de línea O salto de línea, seguido de dígito(s) y punto
		partes_numeradas = re.split(r'(?:^|\n+)(?=\d+\.)', texto_completo)
		partes_numeradas = [p.strip() for p in partes_numeradas if p.strip()]
		
		if len(partes_numeradas) > 1:
		    # Si encontró preguntas numeradas, usarlas (maneja \n y \n\n)
		    preguntas_list = partes_numeradas
		    logger.info(f"✅ Separado por numeración: {len(preguntas_list)} preguntas")
		elif '\n\n' in texto_completo:
		    # ESTRATEGIA 2: Fallback a separación por doble salto
		    preguntas_list = [p.strip() for p in texto_completo.split('\n\n') if p.strip()]
		    logger.info(f"✅ Separado por \\n\\n: {len(preguntas_list)} preguntas")
		else:
		    logger.warning("⚠️ No se pudo separar las preguntas, usando como una sola")

	    logger.info(f"✅ {len(preguntas_list)} preguntas parseadas en total")
	except (json.JSONDecodeError, TypeError) as e:
	    logger.error(f"Error parseando JSON: {e}. Cayendo a split inteligente.")
	    # Fallback con el mismo método inteligente
	    texto_completo = str(preguntas)
	    partes_numeradas = re.split(r'(?:^|\n+)(?=\d+\.)', texto_completo)
	    preguntas_list = [p.strip() for p in partes_numeradas if p.strip()]
        
        # CONFIGURACIÓN DE LAYOUT
        
        # Margen de texto interno (ajustado para que el texto NO toque los bordes)
        TEXT_MARGIN_X = 250 
        TEXT_MARGIN_Y_TOP = 200
        
        # El ancho máximo de texto se define por los márgenes
        text_start_x = TEXT_MARGIN_X 
        text_end_x = a4_width - TEXT_MARGIN_X
        max_width_px = text_end_x - text_start_x
        
        margin_top = TEXT_MARGIN_Y_TOP # Iniciar texto con margen superior
        
        line_spacing = 75 
        option_spacing = 65 
        question_spacing = 50
        answer_line_height = 60 
        space_after_answer = 80
        
        # Altura máxima: margen inferior
        max_height = a4_height - TEXT_MARGIN_Y_TOP + 100 

        y_text = margin_top
        
        # ENCABEZADO "Comprensión Lectora" (MANTENIENDO ESTILO 3D AZUL/ROSA)
        encabezado = "📚 Comprensión Lectora"
        bbox = draw.textbbox((0, 0), encabezado, font=font_titulo)
        text_width = bbox[2] - bbox[0]
        x_centered = (a4_width - text_width) // 2
        
        if estilo == "infantil":
            # Estilo original '3D y rosa' restaurado
            shadow_color = '#1a5490' # Azul oscuro para sombra/contorno
            main_color = '#42A5F5' # Azul claro/juguetón
            outline_width = 4
            
            # Dibujar contorno
            for dx in range(-outline_width, outline_width + 1):
                for dy in range(-outline_width, outline_width + 1):
                    if dx * dx + dy * dy >= outline_width * outline_width:
                        draw.text((x_centered + dx, y_text + dy), encabezado, font=font_titulo, fill=shadow_color)
            
            # Dibujar texto principal
            draw.text((x_centered, y_text), encabezado, font=font_titulo, fill=main_color)
        else:
            draw.text((x_centered, y_text), encabezado, font=font_titulo, fill='#1a5490')
        
        y_text += 105
        
        # TÍTULO DEL CUENTO
        if titulo_cuento:
            titulo_capitalizado = to_title_case(titulo_cuento)
            cuento_text = f'Cuento: "{titulo_capitalizado}"'
            bbox = draw.textbbox((0, 0), cuento_text, font=font_subtitulo)
            text_width = bbox[2] - bbox[0]
            x_centered = (a4_width - text_width) // 2
            
            # Subtítulo sin efecto para contraste
            draw.text((x_centered, y_text), cuento_text, font=font_subtitulo, fill='#333333') 
            
            y_text += 80
        
        # LÍNEA SEPARADORA
        line_margin = text_start_x + 80 
        if estilo == "infantil":
            colors = ['#FF6B9D', '#FFD93D', '#6BCF7F', '#4ECDC4']
            segment_width = (text_end_x - line_margin - 80) // len(colors)
            for i, color in enumerate(colors):
                x1 = line_margin + i * segment_width
                x2 = x1 + segment_width
                draw.rectangle([(x1, y_text), (x2, y_text + 6)], fill=color)
        else:
            draw.line([(line_margin, y_text), (text_end_x - 80, y_text)], fill='#1a5490', width=3)
        
        y_text += 55
        
        # CAMPOS DE NOMBRE Y FECHA
        campos_y = y_text
        # Texto de campos en el color principal (gris oscuro)
        draw.text((text_start_x, campos_y), "Nombre:", font=font_preguntas, fill=text_color)
        line_x_start = text_start_x + 200
        line_x_end = text_start_x + 800
        # Dibujar línea un poco debajo del texto
        draw.line([(line_x_start, campos_y + 50), (line_x_end, campos_y + 50)], fill=text_color, width=2)
        
        fecha_x = text_end_x - 400
        draw.text((fecha_x, campos_y), "Fecha:", font=font_preguntas, fill=text_color)
        line_x_start = fecha_x + 140
        line_x_end = text_end_x
        # Dibujar línea un poco debajo del texto
        draw.line([(line_x_start, campos_y + 50), (line_x_end, campos_y + 50)], fill=text_color, width=2)
        
        y_text += 120
        
        # DIBUJAR PREGUNTAS CON OPCIONES Y RESPUESTAS
        
        questions_drawn = 0
        # La posición del círculo se ajusta ligeramente ANTES de donde empieza el texto (text_start_x)
        CIRCLE_START_X = text_start_x - 50 
        
        for idx, pregunta_completa in enumerate(preguntas_list):
            if not pregunta_completa.strip():
                continue
            
            # Verificar si hay espacio para la siguiente pregunta
            estimated_height_needed = line_spacing * 2 + space_after_answer 
            
            if y_text + estimated_height_needed > max_height:
                logger.warning(f"⚠️ Truncado en pregunta {idx+1}/{len(preguntas_list)}")
                break
            
            # Separar pregunta de opciones
            partes = pregunta_completa.split('\n')
            pregunta_principal = partes[0].strip()
            # Filtra opciones que tengan formato a), b), etc.
            opciones = [p.strip() for p in partes[1:] if p.strip() and re.match(r'^[a-dA-D]\)', p.strip())]
            
            # Limpiar numeración si ya viene
            pregunta_sin_numero = re.sub(r'^\d+\.\s*', '', pregunta_principal)
            
            # NÚMERO DE PREGUNTA
            numero = str(idx + 1)
            
            if estilo == "infantil":
                circle_x = CIRCLE_START_X
                circle_y = y_text + 18
                circle_radius = 26
                
                # Círculo 'Dulce' para el número de pregunta
                draw.ellipse(
                    [(circle_x - circle_radius, circle_y - circle_radius),
                     (circle_x + circle_radius, circle_y + circle_radius)],
                    fill='#FF6B9D', # Rosa Fuerte
                    outline='#E91E63', # Rosa más oscuro para el borde
                    width=3
                )
                
                bbox = draw.textbbox((0, 0), numero, font=font_numero)
                num_width = bbox[2] - bbox[0]
                num_height = bbox[3] - bbox[1]
                draw.text(
                    (circle_x - num_width//2, circle_y - num_height//2 - 3),
                    numero,
                    font=font_numero,
                    fill='white' # Blanco para el número
                )
                
                # El texto de la pregunta empieza donde debería iniciar el texto
                x_pregunta = text_start_x
            else:
                # Dibujar número en la posición de inicio del círculo (que está antes del texto)
                draw.text((CIRCLE_START_X + 15, y_text), f"{numero}.", font=font_numero, fill=text_color)
                # El texto principal empieza en el inicio del texto
                x_pregunta = text_start_x 
            
            # TEXTO DE LA PREGUNTA
            max_width_pregunta = max_width_px
            
            temp_draw = ImageDraw.Draw(Image.new('RGB', (1, 1))) 
            pregunta_lines_with_type = wrap_text_with_markdown(pregunta_sin_numero, fonts, max_width_pregunta, temp_draw)
            
            for line, line_type in pregunta_lines_with_type:
                if line_type == 'paragraph_break':
                    y_text += 40  
                    continue
                # Las preguntas se dibujan con el nuevo text_color (gris oscuro)
                draw_formatted_line(draw, x_pregunta, y_text, line, fonts, text_color, max_width_pregunta)
                y_text += line_spacing
            
            # OPCIONES (si las hay)
            if opciones:
                y_text += 15
                
                for opcion in opciones:
                    if y_text > max_height:
                        break
                    
                    x_opcion = x_pregunta + 60
                    max_width_opcion = max_width_px - 60
                    opcion_lines_with_type = wrap_text_with_markdown(opcion, fonts_opciones, max_width_opcion, temp_draw)
                    
                    for line, line_type in opcion_lines_with_type:
                        if line_type == 'paragraph_break':
                            continue
                        # Las opciones se dibujan con el nuevo text_color (gris oscuro) y fuente más amigable
                        draw_formatted_line(draw, x_opcion, y_text, line, fonts_opciones, text_color, max_width_opcion)
                        y_text += option_spacing
                
                y_text += question_spacing
            else:
                y_text += question_spacing + 20
            
            # LÍNEA PARA RESPUESTA
            # La línea se dibuja en la posición actual de y_text
            line_y = y_text 
            
            if line_y < max_height:
                line_start_x = text_start_x + 50
                line_end_x = text_end_x - 50
                
                if estilo == "infantil":
                    dot_spacing = 20
                    dot_radius = 3
                    # Dibuja la línea de puntos
                    for x in range(line_start_x, line_end_x, dot_spacing):
                        color = ['#FF6B9D', '#FFD93D', '#6BCF7F', '#4ECDC4'][idx % 4]
                        draw.ellipse([(x - dot_radius, line_y - dot_radius),
                                     (x + dot_radius, line_y + dot_radius)],
                                     fill=color)
                else:
                    # Dibuja línea sólida
                    draw.line([(line_start_x, line_y), (line_end_x, line_y)], 
                             fill=text_color, width=2)
                
                # Avanzamos y_text *después* de dibujar la línea, para asegurar el espacio.
                y_text += answer_line_height + space_after_answer
            
            questions_drawn += 1
        
        logger.info(f"✅ {questions_drawn}/{len(preguntas_list)} preguntas dibujadas")
        
        # GUARDAR
        canvas = canvas.convert('RGB')
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
        "version": "6.8-BG-IMAGEN-100%-CAPA-BLANCA-CENTRAL",
        "features": ["crear_ficha", "crear_hoja_preguntas"],
        "endpoints": {
            "POST /crear-ficha": "Crea ficha de lectura con imagen y texto del cuento (Soporte para Letra Capital y Justificación)",
            "POST /crear-hoja-preguntas": "Crea hoja de preguntas con borde decorativo (BG Imagen 100% y Capa blanca CENTRAL)"
        },
        "message": "Dual service: reading worksheets + question sheets (SOPORTE DE LETRA CAPITAL, JUSTIFICACIÓN Y CAPITALIZACIÓN DE TÍTULO) - FIX BG IMAGEN 100% Y CAPA BLANCA CENTRAL"
    }

@app.get("/health")
def health():
    return {"status": "healthy", "version": "6.8-BG-IMAGEN-100%-CAPA-BLANCA-CENTRAL"}
