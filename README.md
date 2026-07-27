# LocallyFPS ⚡

**LocallyFPS** es una herramienta multiplataforma que utiliza inteligencia artificial para aumentar los **FPS (fotogramas por segundo)** de videos mediante interpolación de cuadros. Emplea el modelo **RIFE (Real-Time Intermediate Flow Estimation)** con aceleración por GPU vía Vulkan. Todo el procesamiento se realiza **localmente**, sin depender de servicios en la nube.

## Cómo funciona

```
Video original → Extraer cuadros PNG → RIFE (IA) → Interpolar cuadros → Reensamblar video → Video mejorado
```

## Características

- **Interpolación con IA** — Usa RIFE v4.6 (rife-ncnn-vulkan) para generar cuadros intermedios realistas
- **Soporte para GPU** — NVIDIA, AMD, Intel y Apple Silicon (M1-M5)
- **Interfaz interactiva** — Menú con teclas de flecha y asistente paso a paso
- **Modo CLI** — Para uso automatizado o por lotes
- **Multiplataforma** — Linux, macOS y Windows
- **Multi-idioma** — Español e Inglés
- **Aceleración por hardware** — Soporte para NVENC, AMF, QSV, VAAPI, VideoToolbox
- **Auto-instalación** — Descarga e instala ffmpeg y rife-ncnn-vulkan automáticamente

## Plataformas

| Plataforma | Iniciador |
|---|---|
| Linux | `LocallyFPS_Linux/start.sh` |
| macOS | `LocallyFPS_macOS/start.command` |
| Windows | `LocallyFPS_Windows/start.bat` |

## Requisitos

- **Python 3.8+**
- **GPU compatible con Vulkan** (para rendimiento óptimo)
- **8 GB+ RAM** recomendados
- Espacio en disco para cuadros temporales

## Uso rápido

```bash
# Linux
cd LocallyFPS_Linux && bash start.sh

# macOS
Haz doble clic en LocallyFPS_macOS/start.command

# Windows
Haz doble clic en LocallyFPS_Windows/start.bat
```

Sigue el asistente interactivo:
1. Selecciona el archivo de video
2. Elige los FPS objetivo
3. Ajusta la configuración (opcional)
4. ¡Espera a que se procese!

## CLI (Linux/macOS)

```bash
python3 fps_enhancer.py --input video.mp4 --fps 60 --encoder libx264
```

## Configuración

El archivo `config.json` permite personalizar:
- `encoder` — Códec de video (libx264, libx265, h264_nvenc, etc.)
- `crf` — Calidad (menor = mejor, recomendado 16-20)
- `preset` — Velocidad de codificación (fast, balanced, quality)
- `model` — Modelo RIFE (rife-v4.6, rife-v4, etc.)
- `rife_threads` — Hilos para RIFE (ej. `2:6:6`)

## Créditos

- [RIFE](https://github.com/hzwer/ECCV2022-RIFE) — Algoritmo de interpolación de cuadros
- [ncnn](https://github.com/Tencent/ncnn) — Framework de inferencia neuronal
- [rife-ncnn-vulkan](https://github.com/nihui/rife-ncnn-vulkan) — Implementación Vulkan de RIFE

## Licencia

Este proyecto es de uso libre.
