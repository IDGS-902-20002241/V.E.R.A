import os
import numpy as np
from flask import Flask, request, jsonify
from insightface.app import FaceAnalysis
from pymongo import MongoClient
from datetime import datetime
from service import Helpers

app = Flask(__name__)

# --- InsightFace ---
face_app = FaceAnalysis(providers=['CPUExecutionProvider'])
face_app.prepare(ctx_id=0, det_size=(640, 640))

# --- Helpers ---
helpers = Helpers(face_app)

# --- MongoDB ---
MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017")
client = MongoClient(MONGO_URI)
db = client["face_db"]
embeddings_col = db["embeddings"]

THRESHOLD = 0.45

# ── Rutas ─────────────────────────────────────────────────────────────────────

@app.route('/register_face', methods=['POST'])
def register_face():
    data = request.get_json()
    if not data or 'faces' not in data:
        return jsonify({"error": "Se requiere el campo 'faces'"}), 400

    results = []
    for item in data['faces']:
        face_id = item.get('id')
        b64_str = item.get('base64')

        if not face_id or not b64_str:
            results.append({"id": face_id, "status": "error", "reason": "Falta id o base64"})
            continue

        img = helpers.base64_to_cv2(b64_str)
        if img is None:
            results.append({"id": face_id, "status": "error", "reason": "Imagen inválida"})
            continue

        emb = helpers.get_embedding(img)
        if emb is None:
            results.append({"id": face_id, "status": "error", "reason": "No se detectó rostro"})
            continue

        embeddings_col.update_one(
            {"face_id": face_id},
            {"$set": {
                "face_id":    face_id,
                "embedding":  helpers.embedding_to_list(emb),
                "updated_at": datetime.utcnow()
            }},
            upsert=True
        )
        results.append({"id": face_id, "status": "registered"})

    return jsonify({"results": results}), 200


@app.route('/match_face', methods=['POST'])
def match_face():
    data = request.get_json()
    if not data or 'target_image' not in data:
        return jsonify({"error": "Se requiere 'target_image'"}), 400

    target_img = helpers.base64_to_cv2(data['target_image'])
    if target_img is None:
        return jsonify({"error": "No se pudo decodificar la imagen objetivo"}), 400

    target_emb = helpers.get_embedding(target_img)
    if target_emb is None:
        return jsonify({"error": "No se detectó rostro en la imagen objetivo"}), 400

    query = {}
    if 'face_ids' in data and data['face_ids']:
        query = {"face_id": {"$in": data['face_ids']}}

    gallery = list(embeddings_col.find(query, {"_id": 0, "face_id": 1, "embedding": 1}))
    if not gallery:
        return jsonify({"match": False, "message": "Galería vacía"}), 200

    best_id  = None
    best_sim = -1.0

    for doc in gallery:
        g_emb = helpers.list_to_embedding(doc['embedding'])
        sim   = float(np.dot(target_emb, g_emb))

        if sim > best_sim:
            best_sim = sim
            if sim >= THRESHOLD:
                best_id = doc['face_id']

    if best_id:
        return jsonify({"match": True, "id": best_id, "similarity": best_sim}), 200
    else:
        return jsonify({"match": False, "message": "Sin coincidencias sobre el umbral",
                        "highest_similarity": max(best_sim, 0.0)}), 200


@app.route('/delete_face/<face_id>', methods=['DELETE'])
def delete_face(face_id: str):
    result = embeddings_col.delete_one({"face_id": face_id})
    if result.deleted_count:
        return jsonify({"status": "deleted", "id": face_id}), 200
    return jsonify({"error": "ID no encontrado"}), 404


@app.route('/list_faces', methods=['GET'])
def list_faces():
    ids = [doc['face_id'] for doc in embeddings_col.find({}, {"_id": 0, "face_id": 1})]
    return jsonify({"count": len(ids), "face_ids": ids}), 200


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)