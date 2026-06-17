#include <Servo.h>

const int MIC_PIN = A0;
const int LED_VERDE = 13;
const int LED_ROJO = 12;
const int SERVO_PIN = 9;

Servo miServo;
bool grabando = false;
unsigned long muestrasObjetivo = 48000; // 6 segundos * 8000 Hz

void setup() {
  Serial.begin(115200);
  
  pinMode(LED_VERDE, OUTPUT);
  pinMode(LED_ROJO, OUTPUT);
  miServo.attach(SERVO_PIN);
  miServo.write(0); // Cerrado por defecto
}

void loop() {
  if (Serial.available() > 0) {
    char comando = Serial.read();
    
    // Comando 'R': Iniciar transmisión de audio (Grabar)
    if (comando == 'R') {
      // Período para 8000Hz: 1,000,000 microsegundos / 8000 = 125 microsegundos
      // Restamos ~20 microsegundos que tarda el analogRead() en procesar
      for (unsigned long i = 0; i < muestrasObjetivo; i++) {
        int val = analogRead(MIC_PIN);
        uint8_t muestra = val >> 2; // Convertir 10 bits a 1 byte
        Serial.write(muestra);
        delayMicroseconds(105); 
      }
    }
    // Comando '1': Acceso Concedido
    else if (comando == '1') {
      digitalWrite(LED_VERDE, HIGH);
      miServo.write(90);
      delay(5000);
      miServo.write(0);
      digitalWrite(LED_VERDE, LOW);
    } 
    // Comando '0': Acceso Denegado
    else if (comando == '0') {
      digitalWrite(LED_ROJO, HIGH);
      delay(3000);
      digitalWrite(LED_ROJO, LOW);
    }
  }
}