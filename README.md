# LocallyFPS

Aumentá el FPS de tus videos con IA, todo en tu PC. Sin subir nada a la nube.

Usa el modelo RIFE para interpolar frames y ffmpeg para el encoding. Soporta Linux, Windows y macOS.

## Qué hace

- Extrae los frames del video con ffmpeg
- RIFE genera frames intermedios con IA (ej: de 24 a 60 fps)
- ffmpeg reensambla todo con audio

## Requisitos

- GPU con soporte Vulkan (NVIDIA, AMD, Intel)
- Python 3.8+
- ffmpeg (se descarga automático si no lo tenés)

## Uso rápido

```bash
# Linux/macOS
./start.sh

# Windows
start.bat
```

Seguí los pasos del menú: elegí el video, el FPS target y listo.

### Por consola

```bash
python fps_enhancer.py video.mp4 --target-fps 60
```

## Idiomas

Inglés, Español, Alemán, Francés, Portugués, Ruso, Árabe, Chino, Japonés, Coreano.

## Licencia

MIT
