import base64
import cv2
import numpy as np
import easyocr
import re # Importante para limpiar el texto

class HelpersPlate:
    def __init__(self):
        # Inicializamos el lector de EasyOCR
        self.reader = easyocr.Reader(['es', 'en'], gpu=False)

    def base64_to_cv2(self, b64_str: str):
        try:
            if "," in b64_str:
                b64_str = b64_str.split(",")[1]
            img_bytes = base64.b64decode(b64_str)
            arr = np.frombuffer(img_bytes, np.uint8)
            return cv2.imdecode(arr, cv2.IMREAD_COLOR)
        except Exception:
            return None

    def get_plate_text(self, img) -> str | None:
        """
        Analiza la imagen, filtra las palabras genéricas y devuelve el texto de la placa.
        """
        results = self.reader.readtext(img)
        if not results:
            return None
        
        valid_plates = []

        # Analizar cada texto detectado en la imagen
        for bbox, text, conf in results:
            # 1. Limpiar el texto: quitar espacios, guiones y dejar solo letras mayúsculas y números
            clean_text = re.sub(r'[^A-Z0-9]', '', text.upper())

            # 2. Aplicar reglas (Heurística) de una placa vehicular
            # - Debe medir entre 5 y 9 caracteres
            # - Debe contener al menos un número (descarta palabras como "GUANAJUATO" o "MEXICO")
            # - Debe contener al menos una letra
            tiene_longitud = 5 <= len(clean_text) <= 9
            tiene_numeros = any(char.isdigit() for char in clean_text)
            tiene_letras = any(char.isalpha() for char in clean_text)

            if tiene_longitud and tiene_numeros and tiene_letras:
                valid_plates.append((clean_text, conf))

        # Si después de filtrar no quedó ninguna placa válida, retornamos None
        if not valid_plates:
            return None
        
        # De las placas válidas encontradas, seleccionamos la que tenga mayor nivel de confianza
        best_match = max(valid_plates, key=lambda x: x[1])
        
        return best_match[0]