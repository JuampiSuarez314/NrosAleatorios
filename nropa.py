from __future__ import annotations

import csv
import math
import zipfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from statistics import NormalDist
from xml.sax.saxutils import escape


ALPHA = 0.05
BASE_DIR = Path(__file__).resolve().parent
OUTPUT_DIR = BASE_DIR / "Resultado"
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
LINEA = "=" * 72


@dataclass
class TestResult:
    nombre: str
    estadistico: float
    critico: str
    decision: str
    detalle: str


def prompt_int(texto: str, minimo: int = 1) -> int:
    while True:
        try:
            valor = int(input(texto).strip())
            if valor < minimo:
                raise ValueError
            return valor
        except ValueError:
            print(f"Ingrese un entero valido mayor o igual a {minimo}.")


def prompt_path(texto: str) -> Path:
    while True:
        ruta = Path(input(texto).strip().strip('"'))
        if ruta.exists():
            return ruta
        print("No existe esa ruta. Intente otra vez.")


def limpiar_pantalla() -> None:
    print("\n" * 2)


def titulo(texto: str) -> None:
    print(LINEA)
    print(texto.center(len(LINEA)))
    print(LINEA)


def mostrar_menu() -> None:
    titulo("NroPA")
    print("1) Cargar CSV")
    print("2) Generar numeros")
    print("3) Salir")
    print(LINEA)


def mostrar_bloque_resultado(numero: int, res: TestResult) -> None:
    print(f"[{numero}] {res.nombre}")
    print(f"    {'Estadistico':<12}: {res.estadistico:.6f}")
    print(f"    {'Critico':<12}: {res.critico}")
    print(f"    {'Decision':<12}: {res.decision}")
    print(f"    {'Detalle':<12}: {res.detalle}")
    print(LINEA)


def resumen_entrada(origen: str, cantidad: int) -> None:
    print(f"Origen   : {origen}")
    print(f"Cantidad : {cantidad}")
    print(LINEA)


def generate_lcg(n: int, seed: int = 123456789) -> list[float]:
    a = 1664525
    c = 1013904223
    m = 2**32
    x = seed % m
    nums = []
    for _ in range(n):
        x = (a * x + c) % m
        nums.append(x / m)
    return nums


def load_numbers_from_csv(path: Path) -> list[float]:
    text = path.read_text(encoding="utf-8-sig", errors="ignore")
    if not text.strip():
        return []

    sample = text[:4096]
    delimiter = ","
    try:
        dialect = csv.Sniffer().sniff(sample, delimiters=",;\t|")
        delimiter = dialect.delimiter
    except csv.Error:
        if ";" in sample and "," not in sample:
            delimiter = ";"
        elif "\t" in sample:
            delimiter = "\t"

    nums: list[float] = []
    reader = csv.reader(text.splitlines(), delimiter=delimiter)
    for row in reader:
        for cell in row:
            cell = cell.strip().replace(" ", "")
            if not cell:
                continue
            if cell.count(",") == 1 and cell.count(".") == 0:
                cell = cell.replace(",", ".")
            try:
                nums.append(float(cell))
            except ValueError:
                continue
    return nums


def validate_unit_interval(nums: list[float]) -> None:
    if any(not (0.0 <= x < 1.0) for x in nums):
        print("Aviso: hay valores fuera de [0,1). Las pruebas asumen uniformes en ese rango.")


def z_critico(alpha: float = ALPHA) -> float:
    return NormalDist().inv_cdf(1 - alpha / 2)


def chi2_quantile(p: float, df: int) -> float:
    z = NormalDist().inv_cdf(p)
    return df * (1 - 2 / (9 * df) + z * math.sqrt(2 / (9 * df))) ** 3


def prueba_medias(nums: list[float], alpha: float = ALPHA) -> TestResult:
    n = len(nums)
    media = sum(nums) / n
    z = abs(media - 0.5) / math.sqrt(1 / (12 * n))
    crit = z_critico(alpha)
    decision = "Se acepta H0" if z < crit else "Se rechaza H0"
    return TestResult("Prueba de Medias", z, f"{crit:.4f}", decision, f"media={media:.6f}")


def prueba_chi_cuadrada(nums: list[float], alpha: float = ALPHA) -> TestResult:
    n = len(nums)
    k = 10 if n >= 50 else max(5, n // 5 or 1)
    frec = [0] * k
    for x in nums:
        idx = min(max(int(x * k), 0), k - 1)
        frec[idx] += 1
    esperada = n / k
    chi2 = sum((obs - esperada) ** 2 / esperada for obs in frec)
    crit = chi2_quantile(1 - alpha, k - 1)
    decision = "Se acepta H0" if chi2 < crit else "Se rechaza H0"
    return TestResult("Chi-Cuadrada", chi2, f"{crit:.4f}", decision, f"k={k}, esperada={esperada:.3f}")


def prueba_varianza(nums: list[float], alpha: float = ALPHA) -> TestResult:
    n = len(nums)
    media = sum(nums) / n
    s2 = sum((x - media) ** 2 for x in nums) / (n - 1)
    chi2 = (n - 1) * s2 / (1 / 12)
    df = n - 1
    crit_inf = chi2_quantile(alpha / 2, df)
    crit_sup = chi2_quantile(1 - alpha / 2, df)
    decision = "Se acepta H0" if crit_inf < chi2 < crit_sup else "Se rechaza H0"
    return TestResult("Varianza", chi2, f"[{crit_inf:.4f}, {crit_sup:.4f}]", decision, f"s2={s2:.6f}")


def prueba_corridas_arriba_abajo(nums: list[float], alpha: float = ALPHA) -> TestResult:
    etiquetas = ["A" if x > 0.5 else "B" for x in nums]
    n1 = sum(1 for e in etiquetas if e == "A")
    n2 = len(etiquetas) - n1
    if n1 == 0 or n2 == 0:
        return TestResult(
            "Corridas Arriba y Abajo",
            float("inf"),
            "N/A",
            "No evaluable",
            "Todos los numeros quedaron del mismo lado de 0.5",
        )
    corridas = 1 + sum(1 for i in range(1, len(etiquetas)) if etiquetas[i] != etiquetas[i - 1])
    n = n1 + n2
    media = (2 * n1 * n2 / n) + 1
    var = (2 * n1 * n2 * (2 * n1 * n2 - n)) / (n * n * (n - 1))
    z = abs(corridas - media) / math.sqrt(var)
    crit = z_critico(alpha)
    decision = "Se acepta H0" if z < crit else "Se rechaza H0"
    return TestResult("Corridas Arriba y Abajo", z, f"{crit:.4f}", decision, f"corridas={corridas}, n1={n1}, n2={n2}")


def write_xlsx(path: Path, sheets: dict[str, list[list[object]]]) -> None:
    def col_name(n: int) -> str:
        s = ""
        while n:
            n, r = divmod(n - 1, 26)
            s = chr(65 + r) + s
        return s

    def cell_xml(value: object, row: int, col: int) -> str:
        ref = f"{col_name(col)}{row}"
        if value is None:
            return f'<c r="{ref}"/>'
        if isinstance(value, bool):
            return f'<c r="{ref}" t="b"><v>{int(value)}</v></c>'
        if isinstance(value, (int, float)) and not isinstance(value, bool):
            if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
                txt = escape(str(value))
                return f'<c r="{ref}" t="inlineStr"><is><t>{txt}</t></is></c>'
            return f'<c r="{ref}"><v>{value}</v></c>'
        txt = escape(str(value))
        return f'<c r="{ref}" t="inlineStr"><is><t>{txt}</t></is></c>'

    sheet_entries = []
    ct_overrides = []
    rels_entries = []

    for i, (name, rows) in enumerate(sheets.items(), start=1):
        sheet_path = f"xl/worksheets/sheet{i}.xml"
        sheet_entries.append((sheet_path, name, rows))
        ct_overrides.append(
            f'<Override PartName="/xl/worksheets/sheet{i}.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/>'
        )
        rels_entries.append(
            f'<Relationship Id="rId{i}" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/worksheet" Target="worksheets/sheet{i}.xml"/>'
        )

    workbook_sheets = [
        f'<sheet name="{escape(name)}" sheetId="{i}" r:id="rId{i}"/>'
        for i, (_, name, _) in enumerate(sheet_entries, start=1)
    ]

    content_types = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
        '<Default Extension="xml" ContentType="application/xml"/>'
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>'
        + "".join(ct_overrides)
        + '<Override PartName="/docProps/core.xml" ContentType="application/vnd.openxmlformats-package.core-properties+xml"/>'
        + '<Override PartName="/docProps/app.xml" ContentType="application/vnd.openxmlformats-officedocument.extended-properties+xml"/>'
        + "</Types>"
    )

    root_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        '<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="xl/workbook.xml"/>'
        '<Relationship Id="rId2" Type="http://schemas.openxmlformats.org/package/2006/relationships/metadata/core-properties" Target="docProps/core.xml"/>'
        '<Relationship Id="rId3" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/extended-properties" Target="docProps/app.xml"/>'
        "</Relationships>"
    )

    workbook_rels = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
        + "".join(rels_entries)
        + "</Relationships>"
    )

    workbook = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" '
        'xmlns:r="http://schemas.openxmlformats.org/officeDocument/2006/relationships">'
        "<sheets>"
        + "".join(workbook_sheets)
        + "</sheets></workbook>"
    )

    now = datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")
    core = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<cp:coreProperties xmlns:cp="http://schemas.openxmlformats.org/package/2006/metadata/core-properties" '
        'xmlns:dc="http://purl.org/dc/elements/1.1/" '
        'xmlns:dcterms="http://purl.org/dc/terms/" '
        'xmlns:dcmitype="http://purl.org/dc/dcmitype/" '
        'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance">'
        "<dc:creator>Codex</dc:creator>"
        "<cp:lastModifiedBy>Codex</cp:lastModifiedBy>"
        f'<dcterms:created xsi:type="dcterms:W3CDTF">{now}</dcterms:created>'
        f'<dcterms:modified xsi:type="dcterms:W3CDTF">{now}</dcterms:modified>'
        "</cp:coreProperties>"
    )

    app = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<Properties xmlns="http://schemas.openxmlformats.org/officeDocument/2006/extended-properties" '
        'xmlns:vt="http://schemas.openxmlformats.org/officeDocument/2006/docPropsVTypes">'
        "<Application>Codex</Application><DocSecurity>0</DocSecurity><ScaleCrop>false</ScaleCrop>"
        f'<HeadingPairs><vt:vector size="2" baseType="variant"><vt:variant><vt:lpstr>Worksheets</vt:lpstr></vt:variant><vt:variant><vt:i4>{len(sheets)}</vt:i4></vt:variant></vt:vector></HeadingPairs>'
        f'<TitlesOfParts><vt:vector size="{len(sheets)}" baseType="lpstr">'
        + "".join(f"<vt:lpstr>{escape(name)}</vt:lpstr>" for name in sheets)
        + "</vt:vector></TitlesOfParts></Properties>"
    )

    with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED) as zf:
        zf.writestr("[Content_Types].xml", content_types)
        zf.writestr("_rels/.rels", root_rels)
        zf.writestr("docProps/core.xml", core)
        zf.writestr("docProps/app.xml", app)
        zf.writestr("xl/workbook.xml", workbook)
        zf.writestr("xl/_rels/workbook.xml.rels", workbook_rels)

        for sheet_path, _, rows in sheet_entries:
            row_xml = []
            for r_idx, row in enumerate(rows, start=1):
                cells = "".join(cell_xml(v, r_idx, c_idx) for c_idx, v in enumerate(row, start=1))
                row_xml.append(f'<row r="{r_idx}">{cells}</row>')
            sheet_xml = (
                '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
                '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main">'
                "<sheetData>"
                + "".join(row_xml)
                + "</sheetData></worksheet>"
            )
            zf.writestr(sheet_path, sheet_xml)


def mostrar_resultado(res: TestResult) -> None:
    mostrar_bloque_resultado(0, res)


def main() -> int:
    while True:
        limpiar_pantalla()
        mostrar_menu()
        opcion = input("Elija una opcion: ").strip()

        if opcion == "3":
            print("Fin.")
            return 0

        if opcion == "1":
            ruta = prompt_path("Ruta del CSV: ")
            nums = load_numbers_from_csv(ruta)
            origen = f"CSV: {ruta}"
        elif opcion == "2":
            n = prompt_int("Cuantos numeros quiere generar: ")
            nums = generate_lcg(n)
            origen = f"Generados LCG ({n})"
        else:
            print("Opcion invalida.")
            input("Enter para continuar...")
            continue

        if len(nums) < 2:
            print("No hay suficientes numeros para evaluar.")
            input("Enter para continuar...")
            continue

        titulo("Pruebas")
        resumen_entrada(origen, len(nums))
        validate_unit_interval(nums)

        pruebas = [prueba_medias, prueba_chi_cuadrada, prueba_varianza, prueba_corridas_arriba_abajo]
        resultados = []
        for idx, prueba in enumerate(pruebas, start=1):
            print(f"Ejecutando {prueba.__name__}...")
            res = prueba(nums)
            mostrar_bloque_resultado(idx, res)
            resultados.append(res)

        salida = OUTPUT_DIR / f"resultado_{datetime.now().strftime('%Y%m%d_%H%M%S')}.xlsx"
        filas_numeros = [["Indice", "Numero"]] + [[i + 1, x] for i, x in enumerate(nums)]
        filas_resultados = [["Prueba", "Estadistico", "Critico", "Decision", "Detalle"]]
        filas_resultados += [[r.nombre, r.estadistico, r.critico, r.decision, r.detalle] for r in resultados]
        filas_resumen = [["Origen", origen], ["Cantidad", len(nums)], ["Fecha", datetime.now().isoformat(timespec="seconds")]]

        write_xlsx(
            salida,
            {
                "Numeros": filas_numeros,
                "Resultados": filas_resultados,
                "Resumen": filas_resumen,
            },
        )

        print(f"Excel generado en: {salida}")
        input("Enter para volver al menu...")


if __name__ == "__main__":
    raise SystemExit(main())
