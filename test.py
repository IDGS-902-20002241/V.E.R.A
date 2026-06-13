import base64
import requests

# Función para convertir un archivo de audio .wav a texto Base64
def audio_a_base64(ruta_archivo):
    with open(ruta_archivo, "rb") as archivo_audio:
        encoded_string = base64.b64encode(archivo_audio.read())
        return encoded_string.decode('utf-8')

# URL de tu API local (Puerto 5001)
URL_REGISTRO = "http://localhost:5001/register_voice"
URL_MATCH = "http://localhost:5001/match_voice"

# --- PRUEBA 1: REGISTRAR UNA VOZ ---
print("--- Registrando usuario en la Base de Datos ---")
audio_reg_b64 = audio_a_base64("mi_voz_registro.wav") 

payload_registro = {
    "voices": [
        {"id": "alumno_20002241", "base64": audio_reg_b64}
    ]
}

response_reg = requests.post(URL_REGISTRO, json=payload_registro)
print("Respuesta Servidor:", response_reg.json())


# --- PRUEBA 2: INTENTAR ACCESO (MATCH) ---
print("\n--- Intentando marcar acceso ---")
audio_match_b64 = audio_a_base64("mi_voz_intento.wav") 

payload_match = {
    "target_audio": audio_match_b64
}

response_match = requests.post(URL_MATCH, json=payload_match)
print("Respuesta Servidor:", response_match.json())