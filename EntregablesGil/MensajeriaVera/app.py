from flask import Flask, render_template, request
import requests

app = Flask(__name__)

# OJO: Cambia esto por la IP que te dé el ESP32 cuando se conecte al WiFi
ESP32_IP = "http://192.168.137.28"  # <-- AQUÍ AGREGAMOS EL HTTP://

@app.route('/')
def inicio():
    return render_template('index.html')

@app.route('/enviar_a_esp', methods=['POST'])
def enviar_a_esp():
    password = request.form.get('password')
    mensaje = request.form.get('mensaje')

    # Estructuramos el JSON que espera recibir el ESP32
    payload = {
        "password": password,
        "mensaje": mensaje
    }

    try:
        url_esp = f"{ESP32_IP}/recibir"
        respuesta = requests.post(url_esp, json=payload, timeout=5)
        
        if respuesta.status_code == 200:
            datos_respuesta = respuesta.json()
            if datos_respuesta.get("acceso_permitido") == True:
                msg = "¡Acceso Autorizado! LED Verde encendido."
            else:
                msg = "Acceso Denegado. LED Rojo encendido."
        else:
            msg = f"Error en el ESP32: Código {respuesta.status_code}"
            
    except requests.exceptions.RequestException as e:
        msg = f"No se pudo conectar con el ESP32. ¿Está encendido?"

    return render_template('index.html', resultado=msg)

if __name__ == '__main__':
    # Corre localmente en tu laptop en el puerto 5000
    app.run(host='0.0.0.0', port=5000, debug=True)