# coding=utf-8
#!/usr/bin/env python3

import socket
import selectors    #https://docs.python.org/3/library/selectors.html
import select
import types        # Para definir el tipo de datos data
import argparse     # Leer parametros de ejecución
import os           # Obtener ruta y extension
from datetime import datetime, timedelta # Fechas de los mensajes HTTP
import time         # Timeout conexión
import sys          # sys.exit
import re           # Analizador sintáctico
import logging      # Para imprimir logs


BUFSIZE = 8192 # Tamaño máximo del buffer que se puede utilizar
TIMEOUT_CONNECTION = 32 # Timout para la conexión persistente: 6+4+9+3+10=32
MAX_ACCESOS = 10
CORREO_RAFAEL = "rafael.guilleng@um.es"
CORREO_DANIEL = "daniel.f.a@um.es"

# Extensiones admitidas (extension, name in HTTP)
filetypes = {"gif":"image/gif", "jpg":"image/jpg", "jpeg":"image/jpeg", "png":"image/png", "htm":"text/htm", 
             "html":"text/html", "css":"text/css", "js":"text/js"}

# Configuración de logging
logging.basicConfig(level=logging.INFO,
                    format='[%(asctime)s.%(msecs)03d] [%(levelname)-7s] %(message)s',
                    datefmt='%Y-%m-%d %H:%M:%S')
logger = logging.getLogger()

""" Esta función envía datos (data) a través del socket cs
Devuelve el número de bytes enviados. """
def enviar_mensaje(cs, data):
    return cs.send(data.encode('utf-8'))

""" Esta función recibe datos a través del socket cs
Leemos la información que nos llega. recv() devuelve un string con los datos. """
def recibir_mensaje(cs):
    return cs.recv(BUFSIZE).decode('utf-8')

# Esta función cierra una conexión activa.
def cerrar_conexion(cs):
    cs.close()
""" Esta función gestiona el envío de códigos de error HTTP al cliente
Decide si la conexión se cierra (errores 400 y 505) o se mantiene viva (resto de errores)"""
def procesar_error(cs, codigo):
    if codigo == 400:
        mensaje = "Bad Request"
        conexion = "close"
    elif codigo == 403:
        mensaje = "Forbidden"
        conexion = "Keep-Alive"
    elif codigo == 404:
        mensaje = "Not Found"
        conexion = "Keep-Alive"
    elif codigo == 405:
        mensaje = "Method Not Allowed"
        conexion = "Keep-Alive"
    elif codigo == 505:
        mensaje = "HTTP Version Not Supported"
        conexion = "close"

    direccion_imagen = str(codigo) + ".jpg" # Para la imagen del error
    fecha_actual = datetime.now()
    fecha_formateada = fecha_actual.strftime('%Y-%m-%d %H:%M:%S') # El formato del loggin    
    html = "<html><body><h1>Error " + str(codigo) + ": " + mensaje + "</h1> <img src =\"" + direccion_imagen + "\"></body></html>"

    # Construimos la respuesta
    respuesta = "HTTP/1.1 " + str(codigo) + " " + mensaje + "\r\n"
    respuesta += "Server: fontanerosvillanueva6493.org (Ubuntu)\r\n"
    respuesta += "Content-Type: text/html; charset=utf-8\r\n"
    respuesta += "Content-Length: " + str(len(html.encode('utf-8'))) + "\r\n"
    respuesta += "Date: " + fecha_formateada + "\r\n"
    respuesta += "Connection: " + conexion + "\r\n"  

    # Si la conexión se mantiene, informamos al cliente
    if conexion == "Keep-Alive": 
        respuesta += "Keep-Alive: timeout=" + str(TIMEOUT_CONNECTION) + ", max=100\r\n"
    respuesta += "\r\n"
    respuesta += html

    enviar_mensaje(cs, respuesta)

# Esta función procesa la cookie cookie_counter
def process_cookies(headers,  cs):
    # 1. Se analizan las cabeceras en headers para buscar la cabecera Cookie
    er_cookie = re.compile(r'Cookie')
    er_cookie_counter = re.compile(r'(?P<nombre>cookie_counter_6493)=(?P<valor>\d+)')
    for header, valor_header in headers.items(): 
        # 2. Una vez encontrada una cabecera Cookie se comprueba si el valor es cookie_counter
        if er_cookie.fullmatch(header):
            m = er_cookie_counter.search(valor_header)
            if m:
                valor = int(m.group('valor'))
                # 4. Si se encuentra y tiene el valor MAX_ACCESSOS se devuelve MAX_ACCESOS
                if valor >= MAX_ACCESOS:
                    return MAX_ACCESOS
                # 5. Si se encuentra y tiene un valor 1 <= x < MAX_ACCESOS se incrementa en 1 y se devuelve el valor
                elif 1 <= valor < MAX_ACCESOS:
                    valor += 1
                    return valor
    #3. Si no se encuentra cookie_counter , se devuelve 1
    return 1

""" Procesamiento principal de los mensajes recibidos.
Típicamente se seguirá un procedimiento similar al siguiente (aunque el alumno puede modificarlo si lo desea) """
def process_web_request(cs, webroot):
    er_linea1 = re.compile(r'(?P<metodo>GET|POST|[A-Z]+)\s+(?P<ruta>\/\S*)\s+(?P<version>HTTP\/\d\.\d)')
    er_cabecera = re.compile(r'(?P<header>[^:]+):(?P<valor>.+)')
    er_getopost = re.compile(r'GET|POST')
    er_correo = re.compile(r'(?i)correo=([^&]+)') # (?i) es para que ignore mayuscula o minuscula

    # Buffer temporal
    mensaje_acumulado = ""

    # * Bucle para esperar hasta que lleguen datos en la red a través del socket cs con select()
    while True:
        """ * Se comprueba si hay que cerrar la conexión por exceder TIMEOUT_CONNECTION segundos
        sin recibir ningún mensaje o hay datos. Se utiliza select.select """
        rsublist, wsublist, xsublist = select.select([cs], [], [], TIMEOUT_CONNECTION)
        if not rsublist: # Si no hay leibles significa que saltó el timeout
            break

        # * Si no es por timeout y hay datos en el socket cs:
        else:
            # * Leer los datos con recv.
            mensaje = recibir_mensaje(cs)
            if not mensaje:
                break # Para que el bucle se rompa cuando se cierra la conexion

            mensaje_acumulado += mensaje

            # Comprobamos si la petición HTTP está completa (tiene la línea en blanco)
            if "\r\n\r\n" not in mensaje_acumulado:
                continue # si no está completa, esperamos datos

            # Separamos la petición
            partes_mensaje = mensaje_acumulado.split("\r\n\r\n", 1)
            peticion_actual = partes_mensaje[0]

            # Guardamos lo demás por si es de una siguiente petición
            if len(partes_mensaje) > 1:
                mensaje_acumulado = partes_mensaje[1]
            else:
                mensaje_acumulado = ""

            lineas = peticion_actual.split('\r\n') # Dividir el string

            # * Analizar que la línea de solicitud y comprobar está bien formateada según HTTP 1.1
            m = er_linea1.fullmatch(lineas[0])
            if m:
                # * Comprobar si la versión de HTTP es 1.1
                if m.group('version') == "HTTP/1.1":
                    # * Comprobar si es un método GET o POST, si no devolver Error 405 "Method Not Allowed". 
                    metodo = m.group('metodo')
                    if not er_getopost.fullmatch(m.group('metodo')):
                        procesar_error(cs, 405)
                        continue
                    
                    # Diccionario con las cabeceras y atributos
                    cabeceras = {}
                    for linea in lineas[1:]:
                        if linea == "":
                            break # Hemos llegado al fin de cabeceras
                        m_cabecera = er_cabecera.fullmatch(linea)
                        if m_cabecera:
                            nombre = m_cabecera.group('header')
                            valor_cabecera = m_cabecera.group('valor')
                            cabeceras[nombre] = valor_cabecera
                            print(nombre + ": " + valor_cabecera) # Imprimir las cabeceras

                    # Verificar Host
                    if 'Host' not in cabeceras:
                        procesar_error(cs, 400)
                        break # cerrar la conexión                    

                    # * Leer URL y separar parámetros si los hubiera
                    url_completa = m.group('ruta')
                    url = url_completa # Por si no hubiera parametros
                    parametros = ""
                    if '?' in url_completa:
                        partes_url = url_completa.split('?', 1)
                        url = partes_url[0] # Guardamos la ruta
                        parametros = partes_url[1] # GUardamos los parametros
                    
                    # Comprobar formulario del correo
                    m_correo = er_correo.search(parametros)
                    if m_correo:
                        correo = m_correo.group(1).replace('%40', '@') # para decodificar la @
                        # Comprobar si es nuestro correo
                        if correo == CORREO_RAFAEL or correo == CORREO_DANIEL:
                            html_formulario = "<html><body><h1>El correo es correcto</h1></body></html>"
                        else:
                            html_formulario = "<html><body><h1>El correo es incorrecto</h1></body></html>"

                        fecha_actual = datetime.now()
                        fecha_formateada = fecha_actual.strftime('%Y-%m-%d %H:%M:%S') # El formato del loggin

                        respuesta_formulario = "HTTP/1.1 200 OK \r\n"
                        respuesta_formulario += "Server: fontanerosvillanueva6493.org (Ubuntu)\r\n" 
                        respuesta_formulario += "Content-Type: text/html; charset=utf-8\r\n"
                        respuesta_formulario += "Content-Length: " + str(len(html_formulario.encode('utf-8'))) + "\r\n"
                        respuesta_formulario += "Connection: Keep-Alive\r\n"
                        respuesta_formulario += "Keep-Alive: timeout=" + str(TIMEOUT_CONNECTION) + ", max=100\r\n"
                        respuesta_formulario += "\r\n"
                        respuesta_formulario += html_formulario

                        enviar_mensaje(cs, respuesta_formulario)
                        continue # volvemos a escuchar peticiones
                        
                    # * Comprobar si el recurso solicitado es /, En ese caso el recurso es index.html
                    if url == '/':
                        url = "index.html"

                    # * Construir la ruta absoluta del recurso (webroot + recurso solicitado)
                    ruta_absoluta = webroot + url

                    # * Comprobar que el recurso (fichero) existe, si no devolver Error 404 "Not found"
                    if not os.path.isfile(ruta_absoluta):
                        procesar_error(cs, 404)
                        continue # No procesar archivo inexistente

                    """ * Analizar las cabeceras. Imprimir cada cabecera y su valor. Si la cabecera es Cookie comprobar
                    el valor de cookie_counter para ver si ha llegado a MAX_ACCESOS. """
                    contador_cookies = process_cookies(cabeceras, cs)

                    #   Si se ha llegado a MAX_ACCESOS devolver un Error "403 Forbidden".
                    if contador_cookies >= MAX_ACCESOS:
                        procesar_error(cs, 403)
                        continue 
            
                    # * Obtener el tamaño del recurso en bytes.
                    tamano = os.stat(ruta_absoluta).st_size

                    # * Extraer extensión para obtener el tipo de archivo. Necesario para la cabecera Content-Type
                    nombre_fichero = os.path.basename(ruta_absoluta)
                    partes = nombre_fichero.split('.')
                    if len(partes) > 1: # El fichero tiene un punto en el nombre
                        extension = partes[-1] # La extensión es el úñtimo elemento de la lista
                    else:
                        extension = ""
                        
                    """ * Preparar respuesta con código 200. Construir una respuesta que incluya: la línea de respuesta y
                    las cabeceras Date, Server, Connection, Set-Cookie (para la cookie cookie_counter),
                    Content-Length y Content-Type. """
                    if extension in filetypes: # Solo trata las extensiones válidas
                        fecha_actual = datetime.now()
                        fecha_formateada = fecha_actual.strftime('%Y-%m-%d %H:%M:%S') # El formato del loggin
                        tipo_extension = filetypes[extension] # Extensión según el diccionario filetypes
                        respuesta = "HTTP/1.1 200 OK\r\n"
                        respuesta += "Server: fontanerosvillanueva6493.org (Ubuntu)\r\n"
                        respuesta += "Content-Type: " + tipo_extension + "; charset=utf-8\r\n"
                        respuesta += "Content-Length: " + str(tamano) + "\r\n"
                        respuesta += "Date: " + fecha_formateada + "\r\n"
                        respuesta += "Connection: Keep-Alive\r\n"
                        respuesta += "Keep-Alive: timeout=" + str(TIMEOUT_CONNECTION) + ", max=100\r\n"
                        respuesta += "Set-Cookie: cookie_counter_6493=" + str(contador_cookies) + "; Max-Age=30 \r\n"
                        respuesta += "\r\n"
                        
                        # * Leer y enviar el contenido del fichero a retornar en el cuerpo de la respuesta.
                        enviar_mensaje(cs, respuesta)

                        # * Se abre el fichero en modo lectura y modo binario
                        f = open(ruta_absoluta, 'rb')
                        if tamano%BUFSIZE != 0:                       
                            bloques_leer = tamano//BUFSIZE + 1
                        else:
                            bloques_leer = tamano//BUFSIZE

                        for bloque in range(bloques_leer):
                            # * Se lee el fichero en bloques de BUFSIZE bytes (8KB)
                            datos = f.read(BUFSIZE)
                            cs.send(datos) # No usamos enviar_mensaje ya que no queremos codificar los datos
                            # * Cuando ya no hay más información para leer, se corta el bucle                        
                        f.close()
                    else:
                        # Error "Not Found" 
                        procesar_error(cs, 404)
                        continue
                else:
                    # Error "HTTP Version Not Supported"
                    procesar_error(cs, 505)
                    break
            else:
                # Error "Bad Request" se cierra la conexión
                procesar_error(cs, 400)
                break
        # * Si es por timeout, se cierra el socket tras el período de persistencia.
        # * NOTA: Si hay algún error, enviar una respuesta de error con una pequeña página HTML que informe del error.
    # Cerrar la conexión por timeout o errores 400/505
    cerrar_conexion(cs)


def main():
    """ Función principal del servidor
    """
    try:
        # Argument parser para obtener la ip y puerto de los parámetros de ejecución del programa. IP por defecto 0.0.0.0
        parser = argparse.ArgumentParser()
        parser.add_argument("-p", "--port", help="Puerto del servidor", type=int, required=True)
        parser.add_argument("-ip", "--host", help="Dirección IP del servidor o localhost", required=True)
        parser.add_argument("-wb", "--webroot", help="Directorio base desde donde se sirven los ficheros (p.ej. /home/user/mi_web)")
        parser.add_argument('--verbose', '-v', action='store_true', help='Incluir mensajes de depuración en la salida')
        args = parser.parse_args()

        if args.verbose:
            logger.setLevel(logging.DEBUG)

        logger.info('Enabling server in address {} and port {}.'.format(args.host, args.port))

        logger.info("Serving files from {}".format(args.webroot))

        # * Crea un socket TCP (SOCK_STREAM)
        server = socket.socket(family=socket.AF_INET, type=socket.SOCK_STREAM, proto=0)
        #* Permite reusar la misma dirección previamente vinculada a otro proceso. Debe ir antes de sock.bind
        server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        #* Vinculamos el socket a una IP y puerto elegidos
        server.bind((args.host, args.port))
        #* Escucha conexiones entrantes
        server.listen()
        #* Bucle infinito para mantener el servidor activo indefinidamente
        while True:
            # - Aceptamos la conexión
            conn, addr = server.accept()
            # - Creamos un proceso hijo
            pid = os.fork()
            # - Si es el proceso hijo se cierra el socket del padre y procesar la petición con process_web_request()
            if pid == 0:
                cerrar_conexion(server)
                process_web_request(conn, args.webroot) 
                sys.exit(0)
            # - Si es el proceso padre cerrar el socket que gestiona el hijo.
            else:
                cerrar_conexion(conn)
    except KeyboardInterrupt:
        True

if __name__== "__main__":
    main()
