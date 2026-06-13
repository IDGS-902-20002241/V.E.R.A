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
# Usamos el extractor de características oficial para biometría de voz
from transformers import Wav2Vec2FeatureExtractor, AutoModelForAudioXVector

app = Flask(__name__)

# --- IA para Reconocimiento de Voz (Biometría) ---
# Usamos FeatureExtractor para procesar las ondas de sonido sin requerir archivos de texto/vocabulario
processor = Wav2Vec2FeatureExtractor.from_pretrained("microsoft/unispeech-sat-base-plus-sv")
voice_model = AutoModelForAudioXVector.from_pretrained("microsoft/unispeech-sat-base-plus-sv")
reconocedor_texto = sr.Recognizer()

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["face_db"] 
voice_col = db["voice_embeddings"] 

# Configuraciones de seguridad
VOICE_THRESHOLD = 0.80
FRASE_CORRECTA = "acceso institucional"

# ── Funciones Auxiliares (Helpers) ──────────────────────────────────────────

def base64_to_audio(b64_str: str):
    try:
        if "," in b64_str:
            b64_str = b64_str.split(",")[1]
        audio_bytes = base64.b64decode(b64_str)
        
        # Cargamos en memoria los bytes del audio
        data, samplerate = sf.read(io.BytesIO(audio_bytes))
        
        # CONVERSIÓN A MONO: Si el archivo viene en Estéreo (2 canales), promediamos los canales
        if len(data.shape) > 1 and data.shape[1] > 1:
            data = np.mean(data, axis=1)
            
        return data, samplerate, audio_bytes
    except Exception as e:
        print(f"[ERROR DECODIFICACIÓN AUDIO]: {str(e)}")
        return None, None, None

def get_voice_embedding(wav_data):
    try:
        # padding=True asegura que si el audio es ligeramente corto, la IA lo rellene en vez de tronar
        inputs = processor(wav_data, sampling_rate=16000, return_tensors="pt", padding=True)
        with torch.no_grad():
            embeddings = voice_model(**inputs).embeddings
        embeddings = torch.nn.functional.normalize(embeddings, dim=-1)
        return embeddings.numpy()[0].tolist()
    except Exception as e:
        print(f"[ERROR EMBEDDING]: {str(e)}")
        return None

def verificar_texto_audio(audio_bytes):
    """ Convierte los bytes de audio a texto para verificar la frase """
    try:
        audio_file = io.BytesIO(audio_bytes)
        with sr.AudioFile(audio_file) as fuente:
            audio_data = reconocedor_texto.record(fuente)
        # Reconocimiento en español de México
        texto_detectado = reconocedor_texto.recognize_google(audio_data, language='es-MX').lower()
        print(f"[V.E.R.A - TEXTO] Texto detectado: '{texto_detectado}'")
        return FRASE_CORRECTA in texto_detectado, texto_detectado
    except Exception as e:
        return False, f"Error al procesar texto: {str(e)}"

# ── Rutas API ─────────────────────────────────────────────────────────────────

@app.route('/register_voice', methods=['POST'])
def register_voice():
    data = request.get_json()
    if not data or 'voices' not in data:
        return jsonify({"error": "Se requiere el campo 'voices'"}), 400

    results = []
    for item in data['voices']:
        voice_id = item.get('id')
        b64_str = item.get('base64')

        if not voice_id or not b64_str:
            results.append({"id": voice_id, "status": "error", "reason": "Falta id o base64"})
            continue

        wav_data, samplerate, _ = base64_to_audio(b64_str)
        if wav_data is None:
            results.append({"id": voice_id, "status": "error", "reason": "Audio inválido"})
            continue

        emb = get_voice_embedding(wav_data)
        if emb is None:
            results.append({"id": voice_id, "status": "error", "reason": "No se pudo procesar la voz"})
            continue

        voice_col.update_one(
            {"voice_id": voice_id},
            {"$set": {
                "voice_id": voice_id,
                "embedding": emb,
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
        results.append({"id": voice_id, "status": "registered"})

    return jsonify({"results": results}), 200


@app.route('/match_voice', methods=['POST'])
def match_voice():
    data = request.get_json()
    if not data or 'target_audio' not in data:
        return jsonify({"error": "Se requiere 'target_audio'"}), 400

    # 1. Decodificar el audio recibido
    wav_data, samplerate, audio_bytes = base64_to_audio(data['target_audio'])
    if wav_data is None:
        return jsonify({"error": "No se pudo decodificar el audio objetivo"}), 400

    # 2. VALIDACIÓN 1: ¿Qué dice? (Frase secreta usando Google Speech)
    frase_valida, texto_escuchado = verificar_texto_audio(audio_bytes)
    if not frase_valida:
        return jsonify({
            "match": False, 
            "message": f"Frase incorrecta o no detectada. Se escuchó: '{texto_escuchado}'"
        }), 200

    # 3. VALIDACIÓN 2: ¿Quién lo dice? (Biometría de voz con Microsoft)
    target_emb = get_voice_embedding(wav_data)
    if target_emb is None:
        return jsonify({"error": "No se pudo procesar la huella de voz"}), 400

    gallery = list(voice_col.find({}, {"_id": 0, "voice_id": 1, "embedding": 1}))
    if not gallery:
        return jsonify({"match": False, "message": "Galería de voces vacía"}), 200

    best_id = None
    best_sim = -1.0
    target_emb_np = np.array(target_emb)

    for doc in gallery:
        g_emb = np.array(doc['embedding'])
        sim = float(np.dot(target_emb_np, g_emb)) # Similitud de coseno

        if sim > best_sim:
            best_sim = sim
            if sim >= VOICE_THRESHOLD:
                best_id = doc['voice_id']

    if best_id:
        return jsonify({
            "match": True, 
            "id": best_id, 
            "similarity": best_sim, 
            "texto_detectado": texto_escuchado
        }), 200
    else:
        return jsonify({
            "match": False, 
            "message": "Frase correcta, pero la voz no pertenece a ningún usuario registrado.",
            "highest_similarity": max(best_sim, 0.0)
        }), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001, debug=False)