import requests

URL_REGISTRO_LIVE = "http://localhost:5001/register_voice_live"
URL_MATCH_LIVE = "http://localhost:5001/match_voice_live"

print("🤖 --- MÓDULO DE PRUEBAS 100% HARDWARE (VERA) ---")
print("1. Registrar mi voz (Desde el micrófono del Arduino)")
print("2. Intentar acceso (Evaluar en tiempo real)")
opcion = input("Selecciona una opción (1 o 2): ")

payload = {"id": "alumno_20001575"}

if opcion == "1":
    print("\nSolicitando al servidor que lea el pin A0 para REGISTRO...")
    res = requests.post(URL_REGISTRO_LIVE, json=payload)
    print("Respuesta Servidor:", res.json())
elif opcion == "2":
    print("\nSolicitando al servidor que lea el pin A0 para VERIFICACIÓN...")
    res = requests.post(URL_MATCH_LIVE, json=payload)
    print("Respuesta Servidor:", res.json())