# Teste Script RCD v1.3.0

Ferramenta de produção que testa cada RCD baseado em ESP32, registra o resultado na API da **Polus/AUVO**, imprime a etiqueta e grava o firmware final criptografado. Este repositório contém todo o fluxo usado na linha de produção do DUT.

## Visão geral do fluxo

1. `execute.bat`
   - Garante Python 3 (`py -3` ou `python`) e cria um `venv` interno (`.venv`).
   - Atualiza `pip` apenas uma vez (usa `.pip-updated.flag`).
   - Confere/instala dependências: `esptool`, `requests`, `qrcode`, `pyserial`, `pywin32`, `pillow`, `cryptography`.
   - Verifica a presença do b-PAC (`HKCR\bpac.Document`) e instala `bpac\bsdkw34015_64us.exe` se necessário (requer privilégios).
   - Executa `teste.py` dentro do ambiente virtual.

2. `teste.py`
   - Apaga e grava o **firmware FVT** (arquivos em `build/`) para rodar a suíte de testes no DUT conectado (porta fixa `COM4` por padrão).
   - Abre o terminal serial, captura o JSON com os resultados e avalia se todos os testes obrigatórios passaram.
   - Envia o JSON + `batch_number` para `https://services.polusbrasil.com.br/api/meter/save-tests/rcd-cr` usando o token JWT definido no topo do arquivo.
   - Usa o `auvoLink` retornado para gerar/guardar o QR code, preencher a etiqueta (`RCD_v1.3_template.lbx`) e imprimir via `imprimir.print_lbx_qr` (b-PAC/Windows).
   - Caso todos os testes passem, descriptografa o firmware final `final-firmware/rcd_firmware_v1_2_5-combined.bin.enc` com AES‑256‑CBC (chave/IV embutidos), valida o byte mágico e grava a imagem combinada única pelo `esptool` (0x0, flash de 8 MB).
   - Remove o `.build/rcd-firmware-combined-decrypted.bin` depois do uso e aguarda o próximo DUT.

## Pré-requisitos

- Windows com Python 3 disponível no PATH (`py -3` recomendado).
- Porta serial dedicada (atualmente `COM4`) conectada ao ESP32 usado nos testes.
- Dependências instaladas automaticamente pelo `execute.bat`; caso rode scripts manualmente, garanta que o `venv` esteja ativo (`.venv\Scripts\activate`).
- b-PAC instalado (irmado via `execute.bat`, necessário para impressão com `print_lbx_qr`).
- Arquivos de firmware:
  - **FVT build**: `build/bootloader/bootloader.bin`, `build/partition_table/partition-table.bin`, `build/ota_data_initial.bin`, `build/rcd-firmware.bin`, `build/site.bin`.
  - **Firmware final criptografado**: coloque `rcd_firmware_v1_2_5-combined.bin.enc` em `final-firmware/`.

## Executando

2. abra a pasta `Teste Script RCD v1.3.0`.
3. Rode `execute.bat`.
4. Siga as instruções no terminal 
5. Quando terminar, o script exibirá o código de saída do firmware final;

## API, QR code e etiqueta

- A função `send_data_to_api` envia o JSON da linha serial + `batch_number`. Se a API estiver fora ou retornar erro/JSON inválido, o script apenas loga o problema e continua (o QR fica vazio).
- O `auvoLink` retornado é usado em dois pontos:
  - `create_auvo_qr_code`: salva um PNG em `./<MAC>/`.
  - `print_lbx_qr`: imprime a etiqueta com o link no campo `qr` do template LBX e adiciona o texto (MAC, SSID, senhas) em `Texto3`.
- O módulo `imprimir.py` encapsula a chamada ao b-PAC; caso a impressora falhe será mostrado um `LBX print failed: ...`.

## Firmware final criptografado

- Guardado em `final-firmware/rcd_firmware_v1_2_5-combined.bin.enc`.
- Decriptado on‑the‑fly com AES‑256‑CBC (chave/IV fixos). O arquivo resultante é validado (byte 0xE9 em `0x1000`) antes da gravação.
- Flash único (imagem combinada) com `--flash-mode dio`, `--flash-freq 40m`, `--flash-size 8MB`. Há fallback automático de baud para 115200 se 460800 falhar.

## Personalizações comuns

- **Porta serial**: altere `esp32_port = "COM4"` em `teste.py`.
- **Token/batch**: edite as constantes logo abaixo do cabeçalho do arquivo.
- **Template da etiqueta**: substitua `RCD_v1.3_template.lbx` ou ajuste campos em `print_lbx_qr`.
- **Timeouts e prompts de teste**: ficam no firmware FVT; o script apenas analisa o JSON enviado pela UART.

## Solução de problemas

- **Faltam arquivos `build/...`**: o `esptool` falha antes da coleta dos testes. Gere/copiei o build completo.
- **API AUVO 500/JSON inválido**: o script mostra “Warning: link from Auvo was not sent; QR code will be empty.” e continua.
- **Erro na impressão**: verifique se o b-PAC está instalado e se a impressora está selecionada corretamente em `print_lbx_qr`.
- **Firmware final não encontrado**: confira se o `.enc` está em `final-firmware/`. O script aborta antes da gravação se o arquivo estiver ausente.
- **Chave/IV diferentes**: ajuste as constantes `ENCRYPTION_KEY` e `ENCRYPTION_IV` antes de gerar uma nova imagem.

## Estrutura relevante

```
execute.bat                 # Bootstrap no Windows
teste.py                    # Fluxo completo (FVT + API + impressão + gravação final)
imprimir.py                 # Utilitário para impressão do template LBX via b-PAC
final-firmware/             # Armazena o .bin.enc final usado na produção
build/, build-rcd-fw/       # Artifacts do firmware de teste e (opcional) firmwares individuais
.build/                     # Saída temporária com o binário decriptado
bpac/                       # Instalador offline do b-PAC
```

## Observações

- A execução roda continuamente (`while True`), por isso o terminal deve permanecer aberto.
- Use sempre o `execute.bat`; rodar `teste.py` direto pode falhar se o `venv` não estiver ativado.


