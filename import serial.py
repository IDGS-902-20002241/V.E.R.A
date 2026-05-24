import serial
import time
import mysql.connector
from mysql.connector import Error

# 1. Configuración de tu Arduino
PUERTO_ARDUINO = 'COM10'
BAUDIOS = 9600

# 2. Configuración de tu Base de Datos local (WAMP/MySQL)
DB_HOST = 'localhost'
DB_USER = 'root'
DB_PASSWORD = ''  # Por defecto en WAMP es vacío
DB_NAME = 'registro_sensores'

# Variables globales para las conexiones
arduino = None
conexion_db = None

try:
    print("Conectando a la base de datos MySQL...")
    conexion_db = mysql.connector.connect(
        host=DB_HOST,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME
    )
    if conexion_db.is_connected():
        print("✓ Conexión exitosa a MySQL.")
except Error as e:
    print(f"✗ Error al conectar con MySQL: {e}")
    print("Asegúrate de que WAMP esté encendido y que la base de datos 'arduino_local_db' exista.")
    exit()

try:
    print(f"Conectando al Arduino en {PUERTO_ARDUINO}...")
    arduino = serial.Serial(PUERTO_ARDUINO, BAUDIOS, timeout=1)
    print("Esperando a que el Arduino se inicialice...")
    time.sleep(3)  # Espera para el autoreinicio de la placa
    print("✓ Conexión exitosa con Arduino.")
except Exception as e:
    print(f"✗ Error al abrir el puerto {PUERTO_ARDUINO}: {e}")
    if conexion_db and conexion_db.is_connected():
        conexion_db.close()
    exit()

print("\nSistema listo y escuchando. Presiona Ctrl+C para salir.\n")

try:
    cursor = conexion_db.cursor()
    
    while True:
        # Leemos la línea del puerto USB
        linea_cruda = arduino.readline()
        
        if linea_cruda:
            try:
                linea = linea_cruda.decode('utf-8').strip()
            except Exception as e:
                print(f"[Error de Decodificación]: {e}")
                continue
            
            if linea:
                print(f"-> Recibido del USB: '{linea}'")
                
                # Separamos los valores (esperamos 'temperatura,humedad')
                datos = linea.split(',')
                
                if len(datos) == 2:
                    try:
                        temperatura = float(datos[0])
                        humedad = float(datos[1])
                        
                        print(f"   [OK] Separados -> Temp: {temperatura}°C, Hum: {humedad}%")
                        
                        # Consulta SQL directa para insertar los datos
                        query = "INSERT INTO registro_sensores (temperatura, humedad) VALUES (%s, %s)"
                        valores = (temperatura, humidity := humedad)
                        
                        cursor.execute(query, valores)
                        conexion_db.commit() # Confirmar y guardar la transacción
                        
                        print("   [Base de Datos] ¡Registro guardado exitosamente!")
                        
                    except ValueError:
                        print("   [Error] Los datos no pudieron convertirse a números decimales.")
                    except Error as e:
                        print(f"   [Error MySQL] No se pudo guardar en la base de datos: {e}")
                else:
                    print("   [Advertencia] Formato no válido. Se esperaba 'temp,hum' (ej. 24.5,60.2)")

except KeyboardInterrupt:
    print("\nPrograma pausado por el usuario.")

finally:
    # Cerrar el cursor y la conexión de la BD de forma segura
    if 'cursor' in locals() and cursor:
        cursor.close()
    if conexion_db and conexion_db.is_connected():
        conexion_db.close()
        print("Conexión de Base de Datos cerrada de forma segura.")
        
    # Cerrar el puerto serial de Arduino
    if arduino and arduino.is_open:
        arduino.close()
        print(f"Puerto {PUERTO_ARDUINO} cerrado correctamente.")
        
    print("Programa finalizado.")