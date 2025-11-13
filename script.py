import qrcode
import requests
import esptool
import serial
import time
import os
import json


firmware_path = "build-rcd-fw/rcd-firmware.bin"
bootloader_path = "build-rcd-fw/bootloader/bootloader.bin"
partition_table_path = "build-rcd-fw/partition_table/partition-table.bin"
ota_data_initial_path = "build-rcd-fw/ota_data_initial.bin"
site_bin_path = "build-rcd-fw/site.bin"

fvt_firmware_path = "build/rcd-firmware.bin"
fvt_bootloader_path = "build/bootloader/bootloader.bin"
fvt_partition_table_path = "build/partition_table/partition-table.bin"
fvt_ota_data_initial_path = "build/ota_data_initial.bin"
fvt_site_bin_path = "build/site.bin"


# Para trocar a imagem que é inserida no Auvo ao final do teste, basta trocar a imagem no S3 em: https://us-east-2.console.aws.amazon.com/s3/buckets/polus-assets?region=us-east-2&bucketType=general&tab=objects
# Colocar uma imagem com o nome exatamente igual ao que estava antes: "rcd.jpg"


""" Campos para inserir Sistema Polus"""
token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJpZCI6IjYyMTU3YTA5YWY5ODFiYTUyODc3ZjAzNiIsImlhdCI6MTY3ODgzODgxM30.F5Icoma-bOswkRmKpjYjmAQrXE32CM9kAQ0D2S0JgPY"
batch_number = "RCDCR103000724BR00002"


def clear_screen():
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")


# Função para detectar o ESP32 usando esptool
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


# Função para ler e imprimir os dados da porta serial
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


# Função para enviar dados para a API
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
        response.raise_for_status()  # Lança um erro para códigos de status HTTP 4xx/5xx
        print("Data saved successfully")
    except requests.exceptions.RequestException as e:
        print(f"Error sending data to API: {e}")
    return response.json()


# Função para gerar um qrcode e salvar em uma pasta especifica
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
                    fvt_firmware_path,  # Aplicação inicial (ota_0)
                    "0x325000",
                    fvt_site_bin_path,  # site.bin
                ]
            )

            # Resetando o ESP32
            print("Resetting ESP32...")
            esptool.main(["--port", esp32_port, "run"])

            print("ESP32 reset. Starting serial monitor...")

            # Estabelecer conexão serial com o ESP32 para monitoramento
            ser = serial.Serial(esp32_port, baudrate=115200, timeout=1)
            time.sleep(2)  # Esperar a reinicialização

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
                

                print("\n=========== PRONTO PARA COLAR NO RÓTULO ===========")
                print(f"MAC: {mac_address}")
                print(f"SSID: {SSID}")
                print(f"Password: {PASSWORD1}")
                print(f"Username: {USERNAME}")
                print(f"Password: {PASSWORD2}") 
                print("===================================================")

            except Exception as e:
                print(f"🚨 --> Error saving test on Polus System: {e}")

            if all_tests_passed:
                print("\n\nAll tests passed!")
                print("\n\nFlashing final firmware in ESP32...")

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
                        bootloader_path,  # bootloader
                        "0xf000",
                        partition_table_path,  # partition table
                        "0x24000",
                        ota_data_initial_path,  # OTA data initial
                        "0x30000",
                        firmware_path,  # Aplicação inicial (ota_0)
                        "0x335000",
                        site_bin_path,  # site.bin
                    ]
                )

                # Resetando o ESP32
                print("Resetting ESP32...")
                esptool.main(["--port", esp32_port, "run"])

            else:
                print("\n\nNot all tests passed.")

        except json.JSONDecodeError as e:
            print(f"Error decoding JSON: {e}")

        input(
            "\n\nTest finished, please insert new hardware and press Enter, or close the program to exit.\n\n"
        )
        clear_screen()
