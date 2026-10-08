# Servidor HTTP en Python

Servidor que atiende conexiones TCP y procesa peticiones HTTP para servir archivos de un directorio web.

## Funcionalidades

- Procesamiento de peticiones GET y POST.
- Entrega de páginas y recursos estáticos.
- Comprobación de elementos de la petición, incluida la cabecera Host para HTTP/1.1.
- Respuestas de error 400, 403, 404, 405 y 505 con imágenes incluidas.
- Tratamiento de cookies y del formulario del ejemplo.

## Ejecución local

Requiere Python 3 y un entorno Unix o Linux por el uso de `os.fork`. Desde esta carpeta:

```bash
python3 web_sstt.py -ip 127.0.0.1 -p 8080 -wb "$(pwd)/"
```

Abre `http://127.0.0.1:8080/` en un navegador. La ruta pasada a `-wb` debe terminar en `/`, tal como espera la construcción de rutas del programa.

## Archivos

`web_sstt.py` contiene el servidor; `index.html` y las imágenes permiten comprobar la entrega de contenido y las respuestas de error.

[Volver a SSTT](../README.md)
