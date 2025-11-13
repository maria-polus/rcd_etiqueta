# imprimir.py
# Uso:
#   LBX + QR (b-PAC):
#       python imprimir.py --lbx ".\etiqueta.lbx" --qr "https://exemplo.com/ABC" [--printer "QL-800"] [--qr-field qr] [--copies 1]
#   PNG (spooler):
#       python imprimir.py --png ".\etiqueta.png" [--printer "QL-800"] [--copies 1]

from __future__ import annotations

import argparse
import os
import sys

PRINTER_DEFAULT_MATCH = "QL-800"  # parte do nome da fila da Brother (caso --printer não seja usado)

def ensure_file(path: str) -> str:
    ap = os.path.abspath(path)
    if not os.path.exists(ap):
        raise FileNotFoundError(f"Arquivo não encontrado: {ap}\n"
                                f"Dica: se o caminho tem espaço, use aspas. Ex.: \"{path}\"")
    return ap

def pick_printer_win32(preferred: str | None = None) -> str:
    import win32print
    printers = [p[2] for p in win32print.EnumPrinters(win32print.PRINTER_ENUM_LOCAL)]
    if preferred:
        # match exato ou parcial
        for name in printers:
            if preferred.lower() in name.lower():
                return name
    else:
        for name in printers:
            if PRINTER_DEFAULT_MATCH.lower() in name.lower():
                return name
    # fallback: padrão do sistema
    default_p = win32print.GetDefaultPrinter()
    if not default_p:
        # ajuda o usuário mostrando as filas existentes
        raise RuntimeError("Nenhuma impressora encontrada como padrão. "
                           f"Filas disponíveis: {', '.join(printers) if printers else '(nenhuma)'}")
    return default_p

def print_png(path_png: str, printer_name: str | None, copies: int):
    try:
        import win32print, win32ui
        from PIL import Image, ImageWin
    except ImportError as e:
        raise RuntimeError("Dependências faltando para impressão de PNG. Instale no Windows:\n"
                           "  pip install pywin32 pillow") from e

    printer = pick_printer_win32(printer_name)
    hprinter = win32print.OpenPrinter(printer)
    try:
        hdc = win32ui.CreateDC()
        hdc.CreatePrinterDC(printer)
        for _ in range(max(1, copies)):
            hdc.StartDoc(path_png)
            hdc.StartPage()

            img = Image.open(path_png).convert("RGB")

            # Constantes do GDI
            PHYSICALWIDTH  = 110
            PHYSICALHEIGHT = 111
            HORZRES = 8
            VERTRES = 10
            PHYSICALOFFSETX = 112
            PHYSICALOFFSETY = 113

            phys_width  = hdc.GetDeviceCaps(PHYSICALWIDTH)
            phys_height = hdc.GetDeviceCaps(PHYSICALHEIGHT)
            horz_res    = hdc.GetDeviceCaps(HORZRES)
            vert_res    = hdc.GetDeviceCaps(VERTRES)
            offx        = hdc.GetDeviceCaps(PHYSICALOFFSETX)
            offy        = hdc.GetDeviceCaps(PHYSICALOFFSETY)

            # área imprimível
            box_w = horz_res
            box_h = vert_res

            # Redimensiona preservando aspecto para caber na área imprimível
            img_ratio = img.width / img.height
            box_ratio = box_w / box_h
            if img_ratio > box_ratio:
                new_w = box_w
                new_h = int(new_w / img_ratio)
            else:
                new_h = box_h
                new_w = int(new_h * img_ratio)
            if new_w <= 0 or new_h <= 0:
                raise RuntimeError("Dimensões de destino inválidas retornadas pelo driver.")

            img = img.resize((new_w, new_h), Image.LANCZOS)

            # Centraliza
            x = offx + (box_w - new_w)//2
            y = offy + (box_h - new_h)//2

            dib = ImageWin.Dib(img)
            dib.draw(hdc.GetHandleOutput(), (x, y, x + new_w, y + new_h))

            hdc.EndPage()
            hdc.EndDoc()
        hdc.DeleteDC()
        print(f"✅ PNG impresso em '{printer}' ({copies} cópia(s)).")
    finally:
        win32print.ClosePrinter(hprinter)

def print_lbx_qr(
    path_lbx: str,
    qr_text: str,
    printer_name: str | None,
    qr_field: str,
    copies: int,
    text_field: str | None = None,
    text_value: str | None = None,
):
    try:
        import win32com.client as win32
    except ImportError as e:
        raise RuntimeError("Dependências faltando para b-PAC. Instale no Windows:\n"
                           "  (instalador oficial do b-PAC SDK) e, se usar Python, pywin32") from e

    bpac = win32.Dispatch("bpac.Document")
    ok = bpac.Open(path_lbx)
    if not ok:
        raise RuntimeError(f"Não abriu o LBX: {path_lbx}. Verifique o caminho e se o b-PAC está instalado.")

    # Seleciona a fila
    try:
        if printer_name:
            bpac.Printer.SetPrinter(printer_name, True)
        else:
            # tenta achar QL-800
            for i in range(bpac.Printer.PrinterCount):
                name = bpac.Printer.GetPrinterByIndex(i).Name
                if PRINTER_DEFAULT_MATCH.lower() in name.lower():
                    bpac.Printer.SetPrinter(name, True)
                    break
        # segue com a atual se não achou
    except Exception:
        pass

    # Objeto de QR pelo nome (default: "qr")
    qr = bpac.GetObject(qr_field)
    if qr is None:
        # ajuda: liste objetos do layout
        try:
            names = []
            for i in range(bpac.ObjectCount):
                names.append(bpac.GetObjectByIndex(i).Name)
        except Exception:
            names = []
        raise RuntimeError(f"Objeto de QR '{qr_field}' não encontrado no template.\n"
                           f"Objetos disponíveis: {', '.join(names) if names else '(não foi possível listar)'}\n"
                           f"Dica: no P-touch Editor renomeie o QR para '{qr_field}'.")

    qr.Text = qr_text

    if text_value is not None:
        if not text_field:
            raise ValueError("Informe --text-field quando quiser preencher texto dinâmico.")
        text_obj = bpac.GetObject(text_field)
        if text_obj is None:
            try:
                names = []
                for i in range(bpac.ObjectCount):
                    names.append(bpac.GetObjectByIndex(i).Name)
            except Exception:
                names = []
            raise RuntimeError(
                f"Objeto de texto '{text_field}' não encontrado no template.\n"
                f"Objetos disponíveis: {', '.join(names) if names else '(não foi possível listar)'}\n"
                f"Dica: no P-touch Editor renomeie o texto para '{text_field}'."
            )
        text_obj.Text = text_value

    bpac.StartPrint("", 0)
    bpac.PrintOut(max(1, copies), 0)
    bpac.EndPrint()

    # Evita chamar Close() se for propriedade booleana
    close_attr = getattr(bpac, "Close", None)
    if callable(close_attr):
        close_attr()
    bpac = None
    print(f"✅ LBX impresso ({copies} cópia(s)).")

def main():
    parser = argparse.ArgumentParser(description="Impressão Brother QL (b-PAC ou spooler).")
    parser.add_argument("--lbx", help="caminho para o template .lbx (b-PAC)")
    parser.add_argument("--qr", help="texto/URL a codificar no QR (quando usar --lbx)")
    parser.add_argument("--qr-field", default="qr", help="nome do objeto QR no .lbx (padrão: qr)")
    parser.add_argument("--text", help="texto dinâmico para preencher no template .lbx")
    parser.add_argument("--text-field", help="nome do objeto de texto no .lbx (use com --text)")
    parser.add_argument("--png", help="caminho para a imagem .png a imprimir (spooler)")
    parser.add_argument("--printer", help="nome (ou parte) da fila da impressora. Ex.: \"QL-800-62mm\"")
    parser.add_argument("--copies", type=int, default=1, help="número de cópias (padrão: 1)")
    args = parser.parse_args()

    try:
        if args.lbx:
            if not args.qr:
                print("Erro: use --qr junto com --lbx.")
                sys.exit(1)
            if args.text and not args.text_field:
                print("Erro: use --text-field junto com --text.")
                sys.exit(1)
            path = ensure_file(args.lbx)
            print_lbx_qr(path, args.qr, args.printer, args.qr_field, args.copies, args.text_field, args.text)
        elif args.png:
            path = ensure_file(args.png)
            print_png(path, args.printer, args.copies)
        else:
            print("Use --lbx <arquivo.lbx> --qr <texto>  OU  --png <arquivo.png>.")
            sys.exit(2)
    except Exception as e:
        # mensagens claras e amigáveis
        print(f"❌ Erro: {e}")
        # dica extra sobre caminhos com espaços
        print("Dica: se o caminho tem espaço, rode com aspas. Ex.:")
        print('  python "C:\\caminho\\com espaço\\imprimir.py" --png ".\\etiqueta.png"')
        sys.exit(3)

if __name__ == "__main__":
    main()
