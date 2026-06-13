import os
from flask import Flask, request, jsonify
from pymongo import MongoClient
from datetime import datetime

# Importamos desde 'service.py' porque conservaste el nombre original
from service import HelpersPlate

app = Flask(__name__)

helpers = HelpersPlate()

# --- Configuración de MongoDB (Atlas vs Local) ---
USAR_ATLAS = True

ATLAS_URI = "mongodb+srv://karlilloz100:Utl.4545@cluster0.udtm7nn.mongodb.net/?retryWrites=true&w=majority&appName=Cluster0"
LOCAL_URI = "mongodb://localhost:27017"

try:
    if USAR_ATLAS:
        MONGO_URI = os.getenv("MONGO_URI", ATLAS_URI)
        print("🟢 Iniciando conexión a MongoDB Atlas (Nube)...")
    else:
        MONGO_URI = os.getenv("MONGO_URI", LOCAL_URI)
        print("🟡 Iniciando conexión a MongoDB Local...")

    client = MongoClient(MONGO_URI)
    # Usamos una base de datos/colección distinta a la de los rostros
    db = client["plate_db"]
    plates_col = db["plates"]
    
    # Hacemos un ping para confirmar que la conexión fue exitosa
    client.admin.command('ping')
    print("¡Conexión a la base de datos exitosa!")
except Exception as e:
    print(f"❌ Error al conectar a la base de datos: {e}")


# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route('/register_plate', methods=['POST'])
def register_plate():
    data = request.get_json()
    if not data or 'plates' not in data:
        return jsonify({"error": "Se requiere el campo 'plates'"}), 400

    results = []
    for item in data['plates']:
        plate_id = item.get('id')
        b64_str = item.get('base64')

        if not plate_id or not b64_str:
            results.append({"id": plate_id, "status": "error", "reason": "Falta id o base64"})
            continue

        img = helpers.base64_to_cv2(b64_str)
        if img is None:
            results.append({"id": plate_id, "status": "error", "reason": "Imagen inválida"})
            continue

        plate_text = helpers.get_plate_text(img)
        if plate_text is None:
            results.append({"id": plate_id, "status": "error", "reason": "No se detectó ninguna placa legible"})
            continue

        # Guardar en base de datos
        plates_col.update_one(
            {"plate_id": plate_id},
            {"$set": {
                "plate_id":   plate_id,
                "plate_text": plate_text,
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
        results.append({"id": plate_id, "status": "registered", "detected_text": plate_text})

    return jsonify({"results": results}), 200


@app.route('/match_plate', methods=['POST'])
def match_plate():
    data = request.get_json()
    if not data or 'target_image' not in data:
        return jsonify({"error": "Se requiere 'target_image'"}), 400

    target_img = helpers.base64_to_cv2(data['target_image'])
    if target_img is None:
        return jsonify({"error": "No se pudo decodificar la imagen objetivo"}), 400

    detected_text = helpers.get_plate_text(target_img)
    if detected_text is None:
        return jsonify({"error": "No se detectó placa en la imagen objetivo"}), 400

    # Buscar coincidencia exacta en la colección de placas
    match = plates_col.find_one({"plate_text": detected_text}, {"_id": 0, "plate_id": 1, "plate_text": 1})

    if match:
        return jsonify({"match": True, "id": match['plate_id'], "plate": match['plate_text']}), 200
    else:
        return jsonify({"match": False, "message": "Placa no registrada en el sistema", "detected_plate": detected_text}), 200


@app.route('/delete_plate/<plate_id>', methods=['DELETE'])
def delete_plate(plate_id: str):
    result = plates_col.delete_one({"plate_id": plate_id})
    if result.deleted_count:
        return jsonify({"status": "deleted", "id": plate_id}), 200
    return jsonify({"error": "ID no encontrado"}), 404


@app.route('/list_plates', methods=['GET'])
def list_plates():
    docs = list(plates_col.find({}, {"_id": 0, "plate_id": 1, "plate_text": 1}))
    return jsonify({"count": len(docs), "plates": docs}), 200


if __name__ == '__main__':
    # Puerto 5002 para no chocar ni con rostros (5000) ni con voz (5001)
    app.run(host='0.0.0.0', port=5002, debug=False)