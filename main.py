import os
import numpy as np
from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime
import torch
import soundfile as sf
import base64
import io
import speech_recognition as sr
import serial
import time

# Usamos el extractor de características oficial para biometría de voz
from transformers import Wav2Vec2FeatureExtractor, AutoModelForAudioXVector

app = Flask(__name__)

# --- Conexión global única con el Hardware Arduino Uno ---
PUERTO_ARDUINO = 'COM8'
try:
    arduino = serial.Serial(port=PUERTO_ARDUINO, baudrate=115200, timeout=1)
    time.sleep(2)  # Pausa de seguridad para sincronización
    print(f"🤖 [VERA HARDWARE] ¡Conectado exitosamente al Arduino Uno en {PUERTO_ARDUINO}!")
except Exception as e:
    print(f"❌ [VERA HARDWARE] Alerta: No se pudo abrir {PUERTO_ARDUINO}. Detalle: {e}")
    arduino = None

# --- IA para Reconocimiento de Voz ---
processor = Wav2Vec2FeatureExtractor.from_pretrained("microsoft/unispeech-sat-base-plus-sv")
voice_model = AutoModelForAudioXVector.from_pretrained("microsoft/unispeech-sat-base-plus-sv")
reconocedor_texto = sr.Recognizer()

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["face_db"] 
voice_col = db["voice_embeddings"] 

VOICE_THRESHOLD = 0.80
FRASE_CORRECTA = "acceso institucional"

# ── Funciones Auxiliares (Helpers) ──────────────────────────────────────────

def capturar_audio_hardware(duracion_segundos=6):
    if not arduino:
        print("❌ [HARDWARE] No hay conexión con Arduino para grabar.")
        return None, None
        
    # Limpiamos buffers antes de la acción
    arduino.reset_input_buffer()
    arduino.reset_output_buffer()
    
    # 🌟 SINCRO: Avisamos al usuario UN MOMENTO ANTES
    print("\n⏱️ Prepárate...")
    time.sleep(0.4) # Retardo de estabilización de línea serie
    print("🔴 ¡HABLA AHORA! ──► (Di: 'acceso institucional')")
    
    # Disparador inmediato del Hardware
    arduino.write(b'R')
    
    total_muestras = duracion_segundos * 8000
    bytes_puros = bytearray()
    
    while len(bytes_puros) < total_muestras:
        if arduino.in_waiting > 0:
            bytes_puros.extend(arduino.read(arduino.in_waiting))
            
    print(f"⏹️ Grabación finalizada. Muestras recibidas: {len(bytes_puros)}. Reconstruyendo señal...")

    # 1. Convertir bytes puros a arreglo flotante
    muestras_raw = np.array(list(bytes_puros), dtype=np.float32)
    
    # 2. Eliminar el desfase de corriente directa (DC Offset)
    promedio_centro = np.mean(muestras_raw)
    muestras_centradas = muestras_raw - promedio_centro
    
    # 3. Normalizar volumen inicial
    max_val = np.max(np.abs(muestras_centradas))
    
    # 🌟 MÁSTERS EN HARDWARE: Tus prints de diagnóstico analógico
    print(f"📊 [DSP DIAGNOSTIC] Amplitud Máxima Cruda (0.0 a 128.0): {max_val:.2f}")
    print(f"📊 [DSP DIAGNOSTIC] Promedio de la señal (Punto reposo): {promedio_centro:.2f}")

    if max_val > 0:
        audio_8khz = muestras_centradas / max_val
    else:
        audio_8khz = muestras_centradas

    # 🌟 4. FILTRO DE RUIDO AJUSTADO (Compuerta sutil + Ganancia de voz)
    UMBRAL_RUIDO = 0.00
    audio_8khz[np.abs(audio_8khz) < UMBRAL_RUIDO] = 0.0
    
    # Amplificamos un poco la señal limpia resultante para Google
    audio_8khz = audio_8khz * 1.5
    audio_8khz = np.clip(audio_8khz, -1.0, 1.0) # Evitamos distorsión matemática

    # 🌟 SEGUNDO DIAGNÓSTICO: ¿Cuánta señal sobrevivió a la compuerta?
    muestras_no_ceros = np.count_nonzero(audio_8khz)
    porcentaje_vida = (muestras_no_ceros / len(audio_8khz)) * 100
    print(f"📊 [DSP DIAGNOSTIC] Audio que sobrevivió al filtro de ruido: {porcentaje_vida:.1f}%")

    # 5. Resamplear de 8kHz a 16kHz por interpolación lineal para la IA
    x_antiguo = np.linspace(0, len(audio_8khz), num=len(audio_8khz))
    x_nuevo = np.linspace(0, len(audio_8khz), num=len(audio_8khz) * 2)
    audio_np = np.interp(x_nuevo, x_antiguo, audio_8khz).astype(np.float32)

    # 6. Guardar en búfer virtual WAV a 16000 Hz
    buffer_memoria = io.BytesIO()
    sf.write(buffer_memoria, audio_np, 16000, format='WAV', subtype='PCM_16')
    buffer_memoria.seek(0)
    audio_bytes = buffer_memoria.read()
    
    return audio_np, audio_bytes

def base64_to_audio(b64_str: str):
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]
        audio_bytes = base64.b64decode(b64_str)
        data, samplerate = sf.read(io.BytesIO(audio_bytes))
        if len(data.shape) > 1 and data.shape[1] > 1:
            data = np.mean(data, axis=1)
        return data, samplerate, audio_bytes
    except Exception as e:
        print(f"[ERROR DECODIFICACIÓN AUDIO]: {str(e)}")
        return None, None, None

def get_voice_embedding(wav_data):
    try:
        inputs = processor(wav_data, sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.no_grad():
            embeddings = voice_model(**inputs).embeddings
        embeddings = torch.nn.functional.normalize(embeddings, dim=-1)
        return embeddings.numpy()[0].tolist()
    except Exception as e:
        print(f"[ERROR EMBEDDING]: {str(e)}")
        return None

def verificar_texto_audio(audio_bytes):
    try:
        audio_file = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as fuente:
            audio_data = reconocedor_texto.record(fuente)
        texto_detectado = reconocedor_texto.recognize_google(audio_data, language='es-MX').lower()
        print(f"[V.E.R.A - TEXTO] Texto detectado: '{texto_detectado}'")
        return FRASE_CORRECTA in texto_detectado, texto_detectado
    except Exception as e:
        return False, f"Error al procesar texto: {str(e)}"

# ── Rutas API ─────────────────────────────────────────────────────────────────

@app.route('/register_voice_live', methods=['POST'])
def register_voice_live():
    data = request.get_json() or {}
    voice_id = data.get('id', 'alumno_20001575')
    
    print(f"\n🎤 [REGISTRO] Iniciando grabación en vivo para ID: {voice_id}")
    wav_data, audio_bytes = capturar_audio_hardware()
    
    if wav_data is None or len(wav_data) == 0:
        return jsonify({"status": "error", "reason": "No se capturó audio del hardware"}), 500

    emb = get_voice_embedding(wav_data)
    if emb is None:
        return jsonify({"status": "error", "reason": "No se pudo procesar la huella de voz"}), 500

    voice_col.update_one(
        {"voice_id": voice_id},
        {"$set": {
            "voice_id": voice_id,
            "embedding": emb,
            "updated_at": datetime.utcnow()
        }},
        upsert=True
    )
    return jsonify({"id": voice_id, "status": "registered_live"}), 200


@app.route('/match_voice_live', methods=['POST'])
def match_voice_live():
    print("\n🎤 [MATCH] Iniciando verificación de acceso en vivo...")
    wav_data, audio_bytes = capturar_audio_hardware()
    
    if wav_data is None or len(wav_data) == 0:
        return jsonify({"error": "No se capturó audio del hardware"}), 500

    # 1. VERIFICAR QUÉ SE DIJO (Google real sin simulaciones)
    frase_valida, texto_escuchado = verificar_texto_audio(audio_bytes)
    if not frase_valida:
        if arduino:
            arduino.write(b'0')  # Deniega en hardware si falla el texto
        print(f"❌ [TEXTO INCORRECTO] Se escuchó: '{texto_escuchado}'")
        return jsonify({"match": False, "message": f"Frase incorrecta. Se escuchó: '{texto_escuchado}'"}), 200

    # 2. VERIFICAR QUIÉN LO DIJO (Biometría Real por IA)
    target_emb = get_voice_embedding(wav_data)
    if target_emb is None:
        return jsonify({"error": "No se pudo procesar la huella"}), 500

    gallery = list(voice_col.find({}, {"_id": 0, "voice_id": 1, "embedding": 1}))
    if not gallery:
        if arduino:
            arduino.write(b'0')
        return jsonify({"match": False, "message": "Galería vacía"}), 200

    best_id = None
    best_sim = -1.0
    target_emb_np = np.array(target_emb)

    for doc in gallery:
        g_emb = np.array(doc['embedding'])
        sim = float(np.dot(target_emb_np, g_emb))
        if sim > best_sim:
            best_sim = sim
            if sim >= VOICE_THRESHOLD:
                best_id = doc['voice_id']

    if best_id:
        if arduino:
            try:
                arduino.write(b'1')  # Envía bit de éxito por USB (Gira Servo 90° y prende LED Verde)
                print(f"🔓 [HARDWARE SENT] ¡Acceso Concedido a {best_id}!")
            except Exception as e:
                print(f"Error serie: {e}")
        return jsonify({"match": True, "id": best_id, "similarity": best_sim, "texto_detectado": texto_escuchado}), 200
    else:
        if arduino:
            arduino.write(b'0')  # Envía bit de rechazo (Prende LED Rojo)
        return jsonify({"match": False, "message": "Voz no reconocida", "highest_similarity": max(best_sim, 0.0)}), 200



if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)