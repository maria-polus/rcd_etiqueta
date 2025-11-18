import json
import os
import qrcode
import requests
import serial
import subprocess
import time
from cryptography.hazmat.primitives.ciphers import Cipher, algorithms, modes

import esptool
from imprimir import print_lbx_qr



firmware_path = "build-rcd-fw/rcd-firmware.bin"
bootloader_path = "build-rcd-fw/bootloader/bootloader.bin"
partition_table_path = "build-rcd-fw/partition_table/partition-table.bin"
ota_data_initial_path = "build-rcd-fw/ota_data_initial.bin"
site_bin_path = "build-rcd-fw/site.bin"

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
FINAL_FIRMWARE_ENC_PATH = os.path.join(
    SCRIPT_DIR, "final-firmware", "rcd_firmware_v1_2_5-combined.bin.enc"
)
DECRYPTED_OUTPUT_DIR = os.path.join(SCRIPT_DIR, ".build")
DECRYPTED_OUTPUT_PATH = os.path.join(
    DECRYPTED_OUTPUT_DIR, "rcd-firmware-combined-decrypted.bin"
)
ENCRYPTION_KEY = b"+KbPeSgVkYp3s6v9y$B&E)H@McQfTjWm"
ENCRYPTION_IV = b"WnZr4u7w!z%C*F-J"
BOOTLOADER_OFFSET = 0x1000
DEFAULT_FLASH_BAUD = 460800
FALLBACK_FLASH_BAUD = 115200
FLASH_CHIP = "esp32"

fvt_firmware_path = "build/rcd-firmware.bin"
fvt_bootloader_path = "build/bootloader/bootloader.bin"
fvt_partition_table_path = "build/partition_table/partition-table.bin"
fvt_ota_data_initial_path = "build/ota_data_initial.bin"
fvt_site_bin_path = "build/site.bin"



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
    response_payload = {}
    try:
        response = requests.post(
            api_url,
            json={"test": json_data, "batch_number": batch_number},
            headers=headers,
        )
        response.raise_for_status()  # Lança um erro para códigos de status HTTP 4xx/5xx
        print("Data saved successfully")
        try:
            response_payload = response.json()
        except ValueError as json_error:
            print(f"Resposta da API nao retornou JSON valido: {json_error}")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to API: {e}")
    return response_payload


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


def ensure_ciphertext_block_size(file_path):
    size = os.path.getsize(file_path)
    if size == 0 or size % 16 != 0:
        raise ValueError(
            f"Tamanho invalido do arquivo cifrado ({size} bytes). "
            "O arquivo deve ser multiplo de 16 para AES-CBC sem padding."
        )


def decrypt_encrypted_firmware(enc_path, out_path=DECRYPTED_OUTPUT_PATH):
    ensure_ciphertext_block_size(enc_path)
    print(f"Decriptando firmware final de {enc_path} ...")
    cipher = Cipher(algorithms.AES(ENCRYPTION_KEY), modes.CBC(ENCRYPTION_IV))
    decryptor = cipher.decryptor()
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(enc_path, "rb") as fin, open(out_path, "wb") as fout:
        for chunk in iter(lambda: fin.read(64 * 1024), b""):
            if chunk:
                fout.write(decryptor.update(chunk))
        fout.write(decryptor.finalize())
    try:
        validate_decrypted_image(out_path)
    except Exception:
        try:
            os.remove(out_path)
        except OSError:
            pass
        raise
    print(f"Firmware final decriptado salvo em {out_path}.")
    return out_path


def validate_decrypted_image(bin_path):
    try:
        with open(bin_path, "rb") as f:
            f.seek(BOOTLOADER_OFFSET)
            boot_byte = f.read(1)
    except OSError as exc:
        raise RuntimeError(f"Falha ao validar firmware decriptado: {exc}")
    if not boot_byte or boot_byte[0] != 0xE9:
        raise ValueError(
            "Arquivo decriptado invalido: byte magico 0xE9 nao encontrado no offset do bootloader."
        )


def resolve_encrypted_firmware_path():
    enc_path = os.path.abspath(FINAL_FIRMWARE_ENC_PATH)
    if not os.path.isfile(enc_path):
        raise FileNotFoundError(
            f"Arquivo de firmware final nao encontrado em {enc_path}. "
            "Certifique-se de baixar/copiar o rcd_firmware_v1_2_5-combined.bin.enc para a pasta final-firmware."
        )
    print(f"Firmware encriptado selecionado: {enc_path}")
    return enc_path


def flash_decrypted_image(port, image_path, baud):
    print(f"Gravando imagem combinada em {port} @ {baud} baud ...")
    esptool.main(
        [
            "--chip",
            FLASH_CHIP,
            "--port",
            port,
            "--baud",
            str(baud),
            "--before",
            "default_reset",
            "--after",
            "hard_reset",
            "write_flash",
            "--flash_mode",
            "dio",
            "--flash_freq",
            "40m",
            "--flash_size",
            "8MB",
            "0x0",
            image_path,
        ]
    )


def flash_final_encrypted_firmware(port):
    enc_path = resolve_encrypted_firmware_path()
    decrypted_path = decrypt_encrypted_firmware(enc_path)
    try:
        try:
            flash_decrypted_image(port, decrypted_path, DEFAULT_FLASH_BAUD)
        except Exception as high_speed_error:
            if DEFAULT_FLASH_BAUD != FALLBACK_FLASH_BAUD:
                print(
                    f"Erro na gravacao em {DEFAULT_FLASH_BAUD} baud ({high_speed_error}). "
                    f"Tentando novamente em {FALLBACK_FLASH_BAUD} baud."
                )
                flash_decrypted_image(port, decrypted_path, FALLBACK_FLASH_BAUD)
            else:
                raise
        print("Gravacao do firmware final concluida com sucesso.")
    finally:
        try:
            os.remove(decrypted_path)
        except OSError:
            pass


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
                resPolus = send_data_to_api(json_data=data, token=token) or {}

                auvo_link = resPolus.get("auvoLink")
                if not auvo_link:
                    print("Warning: link from Auvo was not sent; QR code will be empty.")

                qrcode_path = create_auvo_qr_code(
                    data["mac_address"].replace(":", "_"), auvo_link or ""
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
                        qr_text=auvo_link or "",
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
                print("\n\nFlashing final encrypted firmware in ESP32...")
                flash_final_encrypted_firmware(esp32_port)

            else:
                print("\n\nNot all tests passed.")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        input(
            "\n\nTest finished, please insert new hardware and press Enter, or close the program to exit.\n\n"
        )
        clear_screen()
