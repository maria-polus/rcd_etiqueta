import json
import os
import subprocess
import sys
import time

import esptool
import qrcode
import requests
import serial

from imprimir import print_lbx_qr



fvt_firmware_path = "build/rcd-firmware.bin"
fvt_bootloader_path = "build/bootloader/bootloader.bin"
fvt_partition_table_path = "build/partition_table/partition-table.bin"
fvt_ota_data_initial_path = "build/ota_data_initial.bin"
fvt_site_bin_path = "build/site.bin"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DEVICE_BURN_ROOT = os.path.join(BASE_DIR, "device-burn", "device-burn")
FLASHER_SCRIPT_PATH = os.path.join(DEVICE_BURN_ROOT, "flash_encrypted_combined.py")
ENCRYPTED_FW_PATH = os.path.join(DEVICE_BURN_ROOT, "rcd_firmware_v1_2_5-combined.bin.enc")
DECRYPTED_FW_FILENAME = "rcd-firmware-combined-decrypted.bin"
DECRYPTED_FW_PATH = os.path.join(DEVICE_BURN_ROOT, DECRYPTED_FW_FILENAME)
FINAL_FIRMWARE_BAUDRATE = 460800



""" Campos para inserir Sistema Polus"""
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjYyMTU3YTA5YWY5ODFiYTUyODc3ZjAzNiIsImlhdCI6MTY3ODgzODgxM30.F5Icoma-bOswkRmKpjYjmAQrXE32CM9kAQ0D2S0JgPY"
batch_number = "RCDCR103000724BR00002"


def clear_screen():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


# FunÃ§Ã£o para detectar o ESP32 usando esptool
def find_esp32_port():
    try:
        ports = esptool.get_port_list()
        print(ports)
        for port in ports:
            print(f"Trying port: {port}")
            try:
                esptool.detect_chip(port)
                print(f"ESP32 found on port: {port}")
                return port
            except esptool.FatalError:
                pass
    except Exception as e:
        print(f"Error while trying to communicate with serial ports: {e}")
    return None


# FunÃ§Ã£o para ler e imprimir os dados da porta serial
def read_serial(ser):
    json_data = ""
    json_started = False
    while True:
        if ser.in_waiting > 0:
            data = ser.read(ser.in_waiting)
            for byte in data:
                char = chr(byte)
                if char == "{":
                    json_started = True
                    json_data = char
                elif char == "}" and json_started:
                    json_data += char
                    json_started = False
                    return json_data  # Retorna o JSON capturado e encerra o loop
                elif json_started:
                    json_data += char
                else:
                    print(char, end="")


# FunÃ§Ã£o para enviar dados para a API
def send_data_to_api(json_data, token):
    api_url = "https://services.polusbrasil.com.br/api/meter/save-tests/rcd-cr"
    headers = {
        "x-access-token": token,
        "Content-Type": "application/json",
    }
    try:
        response = requests.post(
            api_url,
            json={"test": json_data, "batch_number": batch_number},
            headers=headers,
        )
        response.raise_for_status()  # LanÃ§a um erro para cÃ³digos de status HTTP 4xx/5xx
        print("Data saved successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to API: {e}")
    return response.json()


# FunÃ§Ã£o para gerar um qrcode e salvar em uma pasta especifica
def create_auvo_qr_code(folder_name, link):
    qr = qrcode.QRCode(version=1)
    qr.add_data(link)
    qr.make(fit=True)

    img = qr.make_image(fill_color="black", back_color="white")
    # Caso nao exista pasta, o programa cria
    if os.path.exists(f"./{folder_name}") == False:
        os.mkdir(f"./{folder_name}")

    img.save(f"./{folder_name}/{folder_name}_qr.png")
    return os.path.abspath(f"./{folder_name}/{folder_name}_qr.png")


def ensure_encrypted_firmware_path():
    encrypted_path = os.path.abspath(ENCRYPTED_FW_PATH)
    if not os.path.isfile(encrypted_path):
        raise FileNotFoundError(
            "Firmware definitivo não encontrado para gravação. "
            f"Verifique o arquivo encriptado em: {encrypted_path}"
        )
    return encrypted_path


def ensure_flasher_script_path():
    flasher_path = os.path.abspath(FLASHER_SCRIPT_PATH)
    if not os.path.isfile(flasher_path):
        raise FileNotFoundError(
            "Script oficial de gravação não encontrado. "
            f"Esperado em: {flasher_path}"
        )
    return flasher_path


def flash_definitive_firmware(esp32_port):
    encrypted_path = ensure_encrypted_firmware_path()
    flasher_path = ensure_flasher_script_path()
    decrypted_path = os.path.abspath(DECRYPTED_FW_PATH)

    cmd = [
        sys.executable,
        flasher_path,
        "--enc",
        encrypted_path,
        "--out",
        decrypted_path,
        "--port",
        esp32_port,
        "--baud",
        str(FINAL_FIRMWARE_BAUDRATE),
        "--no-monitor",
        "--keep-decrypted",
    ]

    print("Invocando flash_encrypted_combined.py para gravar firmware definitivo...", flush=True)
    proc = subprocess.run(cmd, cwd=DEVICE_BURN_ROOT)
    if proc.returncode != 0:
        raise RuntimeError(
            "Falha ao executar flash_encrypted_combined.py para gravar o firmware definitivo."
        )
    print(f"Firmware definitivo gravado com sucesso. Arquivo decriptado disponível em: {decrypted_path}", flush=True)


while True:
    clear_screen()
    # esp32_port = find_esp32_port()
    esp32_port = "COM4"

    if esp32_port is None:
        input(
            "No ESP device found. Please make sure an ESP device is connected to the PC and press Enter to retry."
        )
        clear_screen()
    else:
        try:
            print("Erasing flash memory ")
            # Apagando a memÃ³ria
            esptool.main(
                [
                    "--chip",
                    "esp32",
                    "--port",
                    esp32_port,
                    "erase_flash", 
                ]
            )
            print("Flash erase complete. ")
            # Gravando o firmware usando esptool
            print("Flashing ESP32...")
            esptool.main(
                [
                    "--chip",
                    "esp32",
                    "--port",
                    esp32_port,
                    "--baud",
                    "460800", #"115200", 460800
                    "write_flash",
                    "-z",
                    "0x1000",
                    fvt_bootloader_path,  # bootloader
                    "0xf000",
                    fvt_partition_table_path,  # partition table
                    "0x14000",
                    fvt_ota_data_initial_path,  # OTA data initial
                    "0x20000",
                    fvt_firmware_path,  # Aplicacao inicial (ota_0)
                    "0x325000",
                    fvt_site_bin_path,  # site.bin
                ]
            )

            # Resetando o ESP32
            print("Resetting ESP32...")
            esptool.main(["--port", esp32_port, "run"])

            print("ESP32 reset. Starting serial monitor...")

            # Estabelecer conexÃ£o serial com o ESP32 para monitoramento
            ser = serial.Serial(esp32_port, baudrate=115200, timeout=1)
            time.sleep(2)  # Esperar a reinicializaÃ§Ã£o

            print("Terminal started:")
            json_data = read_serial(ser)

        except Exception as e:
            print(f"Error communicating with ESP32: {e}")
        finally:
            try:
                if ser.is_open:
                    ser.close()
            except NameError:
                pass

        print("\nJSON Captured:")
        print(json_data)

        try:
            data = json.loads(json_data)

            # Define the required keys for successful test
            required_keys = [
                "mac_address",
                "nvs_passed",
                "buzzer_passed",
                "red_led_passed",
                "green_led_passed",
                "blue_led_passed",
                "button_passed",
                "rtc_passed",
                "coel_comm_passed",
                "wifi_passed",
                "spiffs_passed",
                "dht22_passed",
                "ds18b20_passed",
            ]

            # Check if all required keys exist and have the value `true`
            all_tests_passed = True
            for key in required_keys:
                if key not in data or not data[key]:
                    all_tests_passed = False
                    print(f"Test {key} failed or missing.")

            print("\n\nSending test suite to Polus...")

            try:
                resPolus = send_data_to_api(json_data=data, token=token)

                if resPolus["auvoLink"] == None:
                    print(f"Warning: link from Auvo was not sent ")

                qrcode_path = create_auvo_qr_code(
                    data["mac_address"].replace(":", "_"), resPolus["auvoLink"]
                )

                print("\n\n QRCODE Generated!!")
                print("++++++++++++++++++++++++++++++++++++++++++++")
                print(f'+ MAC_ADDRESS: {data["mac_address"]}  ')
                print(f"+ QRCode was saved on:                     ")
                print(f"+  {qrcode_path}                           ")
                print("++++++++++++++++++++++++++++++++++++++++++++")

                mac_address = data["mac_address"]
                mac_parts = mac_address.split(':')
                ssid_suffix = ':'.join(mac_parts[-3:])
                SSID = f"RCD-{ssid_suffix}"
                MAC_ADDRESS_INPUT = "00:4B:12:18:8C:38"
                PASSWORD1 = "admin000"
                PASSWORD2 = "admin"
                USERNAME = "admin"

                text_for_label = (
                    f"MAC:{mac_address}\n"
                    f"SSID: {SSID}\n"
                    f"Password: {PASSWORD1}\n"
                    f"Username: {USERNAME}\n"
                    f"Password: {PASSWORD2}"
                )

                #impressÃ£o da etiqueta
                try:
                    lbx_template = os.path.abspath("RCD_v1.3_template.lbx")
                    print("\\nPrinting label via LBX template...")
                    print_lbx_qr(
                        path_lbx=lbx_template,
                        qr_text=(resPolus.get("auvoLink") if isinstance(resPolus, dict) else ""),
                        printer_name=None,
                        qr_field="qr",
                        copies=1,
                        text_field="Texto3",
                        text_value=text_for_label,
                    )
                    print("Label printed successfully.")
                except Exception as e:
                    print(f"LBX print failed: {e}")

            except Exception as e:
                print(f"ðŸš¨ --> Error saving test on Polus System: {e}")

            if all_tests_passed:
                print("\n\nAll tests passed!")
                print("\n\nFlashing final firmware in ESP32...")

                try:
                    flash_definitive_firmware(esp32_port)
                except Exception as e:
                    print(f"Erro ao gravar firmware definitivo: {e}")

            else:
                print("\n\nNot all tests passed.")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        input(
            "\n\nTest finished, please insert new hardware and press Enter, or close the program to exit.\n\n"
        )
        clear_screen()
