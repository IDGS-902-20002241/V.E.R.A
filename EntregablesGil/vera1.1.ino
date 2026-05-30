#include <WiFi.h>
#include <WebServer.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// 1. Configuración de tu red WiFi (Puede ser el hotspot de tu celular para la escuela)
const char* ssid = "RedVera";
const char* password = "MasterKey!";

// 2. Configuración del Servidor Oracle
// El puerto 80 sigue manejando la validación original de tu api_vera.py
const String ORACLE_URL = "http://139.177.98.253:80/validar";

// Nueva URL apuntando al puerto 8080 de tu nuevo panel_control.py
const String ORACLE_URL_AMARILLO = "http://139.177.98.253:8080/status_amarillo";

// 3. Configuración de los pines de los LEDs
const int PIN_LED_VERDE = 12; // Conecta el LED Verde al pin D12
const int PIN_LED_ROJO = 14;  // Conecta el LED Rojo al pin D14
const int PIN_LED_AMARILLO = 25; // Conecta el LED Amarillo al pin D25

// --- VARIABLES PARA TEMPORIZADORES ASÍNCRONOS ---
// Para el LED Amarillo (Polling cada 3 segundos)
unsigned long tiempoUltimaConsulta = 0;
const unsigned long intervaloConsulta = 3000; 

// Para el auto-apagado de los LEDs Verde/Rojo (3 segundos)
unsigned long tiempoEncendidoVR = 0;
bool temporizadorVRActivo = false;
const unsigned long tiempoApagadoVR = 3000; 
// ------------------------------------------------

// Inicializamos el servidor web del ESP32 en el puerto 80
WebServer server(80);

void setup() {
  Serial.begin(115200);
  
  // Configurar pines como salida
  pinMode(PIN_LED_VERDE, OUTPUT);
  pinMode(PIN_LED_ROJO, OUTPUT);
  pinMode(PIN_LED_AMARILLO, OUTPUT); // Configuración del nuevo LED amarillo
  
  // Apagar los LEDs al iniciar
  digitalWrite(PIN_LED_VERDE, LOW);
  digitalWrite(PIN_LED_ROJO, LOW);
  digitalWrite(PIN_LED_AMARILLO, LOW);

  // Conectar al WiFi
  Serial.println("\nConectando a la red WiFi...");
  WiFi.begin(ssid, password);

  while (WiFi.status() != WL_CONNECTED) {
    delay(500);
    Serial.print(".");
  }

  Serial.println("\n¡Conectado al WiFi!");
  Serial.print("Esta es la IP del ESP32 (Cópiala en tu app_laptop.py): ");
  Serial.println(WiFi.localIP());

  // Configurar la ruta que recibirá los datos de la laptop
  server.on("/recibir", HTTP_POST, handleRecibirDatos);

  // Iniciar el servidor del ESP32
  server.begin();
  Serial.println("Servidor ESP32 iniciado y esperando datos...");
}

void loop() {
  // Escuchar peticiones entrantes todo el tiempo (No se interrumpe)
  server.handleClient();

  // CICLO DE CONSULTA AUTOMÁTICA: Revisa el LED Amarillo cada 3 segundos
  if (millis() - tiempoUltimaConsulta >= intervaloConsulta) {
    tiempoUltimaConsulta = millis(); 
    verificarLedAmarilloCloud();     
  }

  // NUEVO CICLO DE APAGADO: Apaga el Verde o Rojo si ya pasaron 3 segundos desde que se encendió
  if (temporizadorVRActivo && (millis() - tiempoEncendidoVR >= tiempoApagadoVR)) {
    digitalWrite(PIN_LED_VERDE, LOW);
    digitalWrite(PIN_LED_ROJO, LOW);
    temporizadorVRActivo = false; // Detenemos el temporizador hasta la próxima petición
    Serial.println("LED Verde/Rojo apagado automáticamente.");
  }
}

// Función exclusiva para consultar el estado del switch en el puerto 8080 (INTACTA)
void verificarLedAmarilloCloud() {
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(ORACLE_URL_AMARILLO);
    
    int httpCode = http.GET(); 
    if (httpCode == 200) {
      String respuesta = http.getString();
      
      StaticJsonDocument<100> doc;
      DeserializationError error = deserializeJson(doc, respuesta);
      
      if (!error) {
        bool statusAmarillo = doc["led_amarillo"];
        
        if (statusAmarillo) {
          digitalWrite(PIN_LED_AMARILLO, HIGH);
        } else {
          digitalWrite(PIN_LED_AMARILLO, LOW);
        }
      }
    }
    http.end();
  }
}

// Función que se ejecuta cuando la laptop manda los datos
void handleRecibirDatos() {
  if (server.hasArg("plain") == false) {
    server.send(400, "application/json", "{\"error\": \"No se recibieron datos\"}");
    return;
  }

  // 1. Leer el JSON que mandó la laptop
  String jsonRecibido = server.arg("plain");
  Serial.println("Datos recibidos de la laptop: " + jsonRecibido);

  // 2. Reenviar esos datos al servidor de Oracle
  if (WiFi.status() == WL_CONNECTED) {
    HTTPClient http;
    http.begin(ORACLE_URL);
    http.addHeader("Content-Type", "application/json");

    Serial.println("Consultando a la base de datos en Oracle...");
    int httpResponseCode = http.POST(jsonRecibido);

    if (httpResponseCode > 0) {
      // 3. Leer la respuesta de Oracle
      String respuestaOracle = http.getString();
      Serial.println("Respuesta de Oracle: " + respuestaOracle);

      // 4. Analizar la respuesta para prender los LEDs usando ArduinoJson
      StaticJsonDocument<200> doc;
      DeserializationError error = deserializeJson(doc, respuestaOracle);

      if (!error) {
        bool accesoPermitido = doc["acceso_permitido"];

        if (accesoPermitido) {
          digitalWrite(PIN_LED_VERDE, HIGH);
          digitalWrite(PIN_LED_ROJO, LOW);
          Serial.println("CONTRASEÑA CORRECTA -> LED VERDE ENCENDIDO");
        } else {
          digitalWrite(PIN_LED_VERDE, LOW);
          digitalWrite(PIN_LED_ROJO, HIGH);
          Serial.println("CONTRASEÑA INCORRECTA -> LED ROJO ENCENDIDO");
        }

        // NUEVO: Arrancamos el cronómetro de 3 segundos
        tiempoEncendidoVR = millis();
        temporizadorVRActivo = true;
      }

      // 5. Devolverle la respuesta a la laptop para que la muestre en pantalla
      server.send(200, "application/json", respuestaOracle);

    } else {
      Serial.print("Error en la petición a Oracle: ");
      Serial.println(httpResponseCode);
      server.send(500, "application/json", "{\"error\": \"Falla al conectar con Oracle\"}");
    }
    http.end();
  } else {
    server.send(500, "application/json", "{\"error\": \"ESP32 sin conexión WiFi\"}");
  }
}