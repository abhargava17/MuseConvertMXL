from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import subprocess
import tempfile
import shutil
import os
from music21 import converter, interval

app = FastAPI(title="MuseConvert Backend")

MUSESCORE_CLI = os.getenv("MUSESCORE_CLI", "/opt/musescore/bin/mscore4portable")

# ----------------------------------------
# Health + Root
# ----------------------------------------
@app.get("/")
def root():
    return {"service": "MuseConvert Backend", "status": "running"}

@app.get("/healthz")
def health():
    return {"status": "ok"}

# ----------------------------------------
# Debug — inspect live container
# ----------------------------------------
@app.get("/debug")
def debug():
    results = {}
    results["mscore_exists"] = Path(MUSESCORE_CLI).exists()
    r = subprocess.run(["java", "-version"], capture_output=True, text=True)
    results["java_version"] = r.stderr.strip()
    r = subprocess.run([MUSESCORE_CLI, "--version"], capture_output=True, text=True)
    results["mscore_version"] = r.stdout.strip() or r.stderr.strip()
    return results

# ----------------------------------------
# Transposition — interval-based (source -> concert -> target)
# ----------------------------------------
def get_transpose_intervals(original_inst, final_inst):
    intvl_1 = None
    intvl_2 = None

    match original_inst:
        case "Piccolo":                  intvl_1 = interval.Interval('-P8')
        case "Flute":                    intvl_1 = interval.Interval('-P5')
        case "Alto Flute":               intvl_1 = interval.Interval('-M6')
        case "Oboe":                     intvl_1 = interval.Interval('-P5')
        case "Oboe d'amore":             intvl_1 = interval.Interval('-m6')
        case "English Horn":             intvl_1 = interval.Interval('-P8')
        case "Heckelphone":              intvl_1 = interval.Interval('-P8')
        case "Bass Oboe":                intvl_1 = interval.Interval('-P8')
        case "Clarinet in Bb":           intvl_1 = interval.Interval('-M7')
        case "Clarinet in A":            intvl_1 = interval.Interval('-m7')
        case "Clarinet in Eb":           intvl_1 = interval.Interval('-m6')
        case "Basset Horn":              intvl_1 = interval.Interval('-P11')
        case "Bass Clarinet":            intvl_1 = interval.Interval('-P14')
        case "Bassoon":                  intvl_1 = interval.Interval('P12')
        case "Contrabassoon":            intvl_1 = interval.Interval('P24')
        case "Saxophone Bb Soprano":     intvl_1 = interval.Interval('-M7')
        case "Saxophone Eb Alto":        intvl_1 = interval.Interval('-M13')
        case "Saxophone Bb Tenor":       intvl_1 = interval.Interval('-P14')
        case "Saxophone Eb Baritone":    intvl_1 = interval.Interval('-P20')
        case "Saxophone Bb Bass":        intvl_1 = interval.Interval('-P21')
        case "Saxophone Eb Contrabass":  intvl_1 = interval.Interval('-P27')
        case "Horn in F":                intvl_1 = interval.Interval('-P24')
        case "Tuba Bb":                  intvl_1 = interval.Interval('P24')
        case "Tuba Eb":                  intvl_1 = interval.Interval('P30')
        case "Trumpet in C":             intvl_1 = interval.Interval('-P5')
        case "Trumpet in Bb":            intvl_1 = interval.Interval('-M7')
        case "Trumpet in A":             intvl_1 = interval.Interval('-m7')
        case "Piccolo Trumpet Bb":       intvl_1 = interval.Interval('-M7')
        case "Piccolo Trumpet A":        intvl_1 = interval.Interval('-m7')
        case "Cornet in Bb":             intvl_1 = interval.Interval('-M7')
        case "Flugelhorn":               intvl_1 = interval.Interval('-M7')
        case "Posthorn":                 intvl_1 = interval.Interval('-M7')
        case "Pocket Trumpet":           intvl_1 = interval.Interval('-M7')
        case "Alto Trombone":            intvl_1 = interval.Interval('-P5')
        case "Tenor Trombone":           intvl_1 = interval.Interval('-P14')
        case "Bass Trombone":            intvl_1 = interval.Interval('-P14')
        case "Contrabass Trombone":      intvl_1 = interval.Interval('P1')
        case "Euphonium":                intvl_1 = interval.Interval('P12')
        case "Tenor Tuba":               intvl_1 = interval.Interval('P12')
        case "Timpani":                  intvl_1 = interval.Interval('P1')
        case "Xylophone":                intvl_1 = interval.Interval('-P8')
        case "Marimba":                  intvl_1 = interval.Interval('P1')
        case "Orchestra Bells":          intvl_1 = interval.Interval('-P15')
        case "Glockenspiel":             intvl_1 = interval.Interval('-P15')
        case "Vibraphone":               intvl_1 = interval.Interval('P1')
        case "Chimes":                   intvl_1 = interval.Interval('P1')
        case "Guitar":                   intvl_1 = interval.Interval('P8')
        case "Violin":                   intvl_1 = interval.Interval('-P5')
        case "Viola":                    intvl_1 = interval.Interval('P1')
        case "Cello":                    intvl_1 = interval.Interval('P8')
        case "Double Bass":              intvl_1 = interval.Interval('P16')
        case _: raise ValueError(f"Unsupported source instrument '{original_inst}'")

    match final_inst:
        case "Piccolo":                  intvl_2 = interval.Interval('P8')
        case "Flute":                    intvl_2 = interval.Interval('P5')
        case "Alto Flute":               intvl_2 = interval.Interval('M6')
        case "Oboe":                     intvl_2 = interval.Interval('P5')
        case "Oboe d'amore":             intvl_2 = interval.Interval('m6')
        case "English Horn":             intvl_2 = interval.Interval('P8')
        case "Heckelphone":              intvl_2 = interval.Interval('P8')
        case "Bass Oboe":                intvl_2 = interval.Interval('P8')
        case "Clarinet in Bb":           intvl_2 = interval.Interval('M7')
        case "Clarinet in A":            intvl_2 = interval.Interval('m7')
        case "Clarinet in Eb":           intvl_2 = interval.Interval('m6')
        case "Basset Horn":              intvl_2 = interval.Interval('P11')
        case "Bass Clarinet":            intvl_2 = interval.Interval('P14')
        case "Bassoon":                  intvl_2 = interval.Interval('-P12')
        case "Contrabassoon":            intvl_2 = interval.Interval('-P24')
        case "Saxophone Bb Soprano":     intvl_2 = interval.Interval('M7')
        case "Saxophone Eb Alto":        intvl_2 = interval.Interval('M13')
        case "Saxophone Bb Tenor":       intvl_2 = interval.Interval('P14')
        case "Saxophone Eb Baritone":    intvl_2 = interval.Interval('P20')
        case "Saxophone Bb Bass":        intvl_2 = interval.Interval('P21')
        case "Saxophone Eb Contrabass":  intvl_2 = interval.Interval('P27')
        case "Horn in F":                intvl_2 = interval.Interval('P24')
        case "Tuba Bb":                  intvl_2 = interval.Interval('-P24')
        case "Tuba Eb":                  intvl_2 = interval.Interval('-P30')
        case "Trumpet in C":             intvl_2 = interval.Interval('P5')
        case "Trumpet in Bb":            intvl_2 = interval.Interval('M7')
        case "Trumpet in A":             intvl_2 = interval.Interval('m7')
        case "Piccolo Trumpet Bb":       intvl_2 = interval.Interval('M7')
        case "Piccolo Trumpet A":        intvl_2 = interval.Interval('m7')
        case "Cornet in Bb":             intvl_2 = interval.Interval('M7')
        case "Flugelhorn":               intvl_2 = interval.Interval('M7')
        case "Posthorn":                 intvl_2 = interval.Interval('M7')
        case "Pocket Trumpet":           intvl_2 = interval.Interval('M7')
        case "Alto Trombone":            intvl_2 = interval.Interval('P5')
        case "Tenor Trombone":           intvl_2 = interval.Interval('P14')
        case "Bass Trombone":            intvl_2 = interval.Interval('P14')
        case "Contrabass Trombone":      intvl_2 = interval.Interval('P1')
        case "Euphonium":                intvl_2 = interval.Interval('-P12')
        case "Tenor Tuba":               intvl_2 = interval.Interval('-P12')
        case "Timpani":                  intvl_2 = interval.Interval('P1')
        case "Xylophone":                intvl_2 = interval.Interval('P8')
        case "Marimba":                  intvl_2 = interval.Interval('P1')
        case "Orchestra Bells":          intvl_2 = interval.Interval('P15')
        case "Glockenspiel":             intvl_2 = interval.Interval('P15')
        case "Vibraphone":               intvl_2 = interval.Interval('P1')
        case "Chimes":                   intvl_2 = interval.Interval('P1')
        case "Guitar":                   intvl_2 = interval.Interval('-P8')
        case "Violin":                   intvl_2 = interval.Interval('P5')
        case "Viola":                    intvl_2 = interval.Interval('P1')
        case "Cello":                    intvl_2 = interval.Interval('-P8')
        case "Double Bass":              intvl_2 = interval.Interval('-P16')
        case _: raise ValueError(f"Unsupported target instrument '{final_inst}'")

    return intvl_1, intvl_2

# ----------------------------------------
# MuseScore: MusicXML -> PDF
# ----------------------------------------
def run_musescore_to_pdf(musicxml_path: Path, out_dir: Path) -> Path:
    out_pdf = out_dir / f"{musicxml_path.stem}.pdf"
    cmd = [
        "xvfb-run", "-a",
        MUSESCORE_CLI,
        str(musicxml_path),
        "-o", str(out_pdf),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    if result.returncode != 0:
        raise RuntimeError(
            f"MuseScore failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-1000:]}\nSTDERR:\n{result.stderr[-1000:]}"
        )
    if not out_pdf.exists():
        raise FileNotFoundError("MuseScore did not produce a PDF")
    return out_pdf

# ----------------------------------------
# Convert endpoint — accepts MusicXML or MXL
# ----------------------------------------
@app.post("/convert")
async def convert_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    original_instrument: str = Form(...),
    final_instrument: str = Form(...),
):
    # Validate file type
    filename = file.filename or ""
    if not filename.lower().endswith((".xml", ".mxl", ".musicxml")):
        return JSONResponse(
            status_code=422,
            content={"error": "Please upload a MusicXML file (.xml, .mxl, or .musicxml)"}
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="museconvert_"))

    try:
        input_path = temp_dir / filename
        input_path.write_bytes(await file.read())

        # Transpose with music21
        i1, i2 = get_transpose_intervals(original_instrument, final_instrument)
        score = converter.parse(str(input_path))
        score.transpose(i1, inPlace=True)
        score.transpose(i2, inPlace=True)

        transposed_xml = temp_dir / f"transposed_{input_path.stem}.musicxml"
        score.write("musicxml", fp=str(transposed_xml))

        # Convert to PDF via MuseScore
        pdf_out = run_musescore_to_pdf(transposed_xml, temp_dir)

        background_tasks.add_task(shutil.rmtree, str(temp_dir), True)

        return FileResponse(
            path=str(pdf_out),
            filename=f"converted_{input_path.stem}.pdf",
            media_type="application/pdf",
        )

    except ValueError as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(status_code=422, content={"error": str(e)})
    except (FileNotFoundError, RuntimeError) as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(status_code=500, content={"error": str(e)[:500]})
