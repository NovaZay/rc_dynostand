# 🧭 Dyno Stand RC — Python Dashboard

Un **panel de control en tiempo real** hecho con **Tkinter + Matplotlib**, diseñado pa’ registrar y visualizar datos de un **banco de pruebas para motores RC (Dyno Stand)**.  
El programa se conecta por **puerto serie** (Arduino o similar) y muestra **RPM, velocidad, torque y potencia**, además de generar **gráficas y un PDF resumen** con los resultados de los tests.

---

## ⚙️ Características principales

- 📡 **Lectura en tiempo real** de RPM desde el puerto serie.  
- ⚙️ Cálculo de **torque**, **potencia (HP)** y **velocidad (km/h)**.  
- 📈 **Gráficas dinámicas** de RPM y km/h durante cada test.  
- 📊 **Tabla de resultados** de hasta `NUM_TESTS` pruebas consecutivas.  
- 🧮 Cálculo automático de **medias** entre tests.  
- 🧾 Exportación a **PDF** con:
  - Tabla resumen de todos los tests  
  - Gráficas individuales (RPM y velocidad) por test  
- 💡 **Interfaz minimalista oscura tipo VSCode**, totalmente funcional con Tkinter.

---

## 🔧 Configuración inicial

Abre el archivo `rpm_dashboard.py` y revisa esta parte de la config:

```python
PUERTO = "COM7"         # Puerto serie de tu Arduino
BAUDIOS = 9600          # Velocidad de transmisión
J = 0.000055776625      # Momento de inercia (kg·m²)
D = 0.055               # Diámetro del rodillo (m)
SAMPLE_INTERVAL = 0.05  # Intervalo de muestreo (s)
TEST_DURATION = 15      # Duración por test (s)
NUM_TESTS = 5           # Número total de tests
```

Modifica el puerto y los valores físicos según tu montaje.

---

## 🚀 Cómo usarlo

1. Conecta el dispositivo (Arduino, sensor, etc.) que envíe datos tipo:
   ```
   RPM: 1234
   ```
2. Ejecuta el programa:
   ```bash
   python rpm_dashboard.py
   ```
3. Pulsa **“Iniciar Test 1”** para empezar.
4. Realiza tus tests consecutivos (hasta 5 por defecto).
5. Cuando termines, pulsa **“Descargar PDF”** para guardar el informe completo.

---

## 🖥️ Dependencias

Instálalas con:

```bash
pip install matplotlib pyserial
```

Tkinter ya viene incluido con Python normalmente.

---

## 📸 Interfaz

Diseño moderno tipo VSCode con:
- Gauge circular de RPM  
- Gráficas en tiempo real (RPM y velocidad)  
- Tabla lateral con resultados  
- Botones para iniciar, reiniciar y exportar PDF  

---

## 📘 Créditos

Proyecto creado por **Zay** 🧠  
Desarrollado 100% en **Python**, con mucho cariño y estilo.  

