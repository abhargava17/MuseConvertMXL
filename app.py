from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from pathlib import Path
import subprocess
import tempfile
import shutil
import os
import time
from music21 import converter, stream, clef, metadata, chord, key, interval, meter, tempo

app = FastAPI(title="MuseConvert Backend")

from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://project-rilup.vercel.app",
        "http://localhost:3000"
    ],
    allow_methods=["*"],
    allow_headers=["*"],
)

# IMPORTANT: Using full MuseScore AppImage (AppRun)
MUSESCORE_CLI = os.getenv("MUSESCORE_CLI", "/opt/musescore/AppRun")

# Style file for engraving fixes
STYLE_FILE = "/app/styles/default.mss"

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
# Debug
# ----------------------------------------
@app.get("/debug")
def debug():
    results = {}
    results["mscore_exists"] = Path(MUSESCORE_CLI).exists()
    r = subprocess.run([MUSESCORE_CLI, "--version"], capture_output=True, text=True)
    results["mscore_version"] = r.stdout.strip() or r.stderr.strip()
    return results

@app.post("/debug-process")
async def debug_process(
    file: UploadFile = File(...),
    original_instrument: str = Form(...),
    final_instrument: str = Form(...),
):
    temp_dir = Path(tempfile.mkdtemp(prefix="museconvert_debug_"))
    try:
        filename = file.filename or "upload.mxl"
        input_path = temp_dir / filename
        input_path.write_bytes(await file.read())

        try:
            new_score = process_score(
                input_path, original_instrument, final_instrument, input_path.stem
            )
            transposed_xml = temp_dir / f"transposed_{input_path.stem}.musicxml"
            new_score.write("musicxml", fp=str(transposed_xml))
            return {
                "status": "music21_ok",
                "xml_exists": transposed_xml.exists(),
                "xml_size": transposed_xml.stat().st_size if transposed_xml.exists() else 0,
            }
        except Exception as e:
            import traceback
            return {
                "status": "error",
                "error": str(e)[:1000],
                "traceback": traceback.format_exc()[-2000:]
            }
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ----------------------------------------
# Transposition intervals
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
# Clef map
# ----------------------------------------
def get_clef(instrument_name: str):
    if instrument_name in ["Violin", "Piccolo", "Flute", "Oboe", "Clarinet in Bb", "Trumpet in C", "Trumpet in Bb", "Saxophone Bb Soprano", "Saxophone Eb Alto", "Saxophone Bb Tenor", "Saxophone Eb Baritone"]:
        return clef.TrebleClef()
    elif instrument_name in ["Viola"]:
        return clef.AltoClef()
    elif instrument_name in ["Cello", "Double Bass", "Bassoon", "Contrabassoon", "Tuba Bb", "Tuba Eb", "Tenor Tuba", "Euphonium", "Bass Trombone", "Contrabass Trombone"]:
        return clef.BassClef()

# ----------------------------------------
# Core processing
# ----------------------------------------
def process_score(input_path: Path, original_inst: str, final_inst: str, stem: str) -> stream.Score:
    i1, i2 = get_transpose_intervals(original_inst, final_inst)
    semitones_total = i1.semitones + i2.semitones
    transp_intvl = interval.Interval(semitones_total)

    score = converter.parse(str(input_path))
    original_part = score.parts[0]
    transposed = original_part.transpose(transp_intvl)

    new_part = stream.Part()
    new_part.partName = final_inst

    new_part.insert(0, get_clef(final_inst))

    orig_key = score.analyze('key')
    new_key_obj = orig_key.transpose(transp_intvl)
    new_key_sig = key.KeySignature(new_key_obj.sharps)
    new_part.insert(0.1, new_key_sig)

    time_sig = transposed.recurse().getElementsByClass(meter.TimeSignature).first()
    if time_sig:
        new_part.insert(0.2, time_sig)

    tempo_mark = transposed.recurse().getElementsByClass(tempo.MetronomeMark).first()
    if tempo_mark:
        new_part.insert(0.3, tempo_mark)

    for measure in transposed.getElementsByClass(stream.Measure):
        for c in measure.recurse().getElementsByClass(clef.Clef):
            measure.remove(c)
        new_part.append(measure)

    for n in new_part.recurse().getElementsByClass('Note'):
        n.pitch = n.pitch.simplifyEnharmonic()
    for ch in new_part.recurse().getElementsByClass('Chord'):
        ch.pitches = [p.simplifyEnharmonic() for p in ch.pitches]

    measures = list(new_part.getElementsByClass(stream.Measure))
    for m in reversed(measures):
        if len(m.notesAndRests) == 0 or all(n.isRest for n in m.notesAndRests):
            new_part.remove(m)
        else:
            break

    new_score = stream.Score()
    new_score.metadata = metadata.Metadata()
    new_score.metadata.title = f"{stem} ({final_inst} Transcription)"
    new_score.metadata.composer = "Arranged by MuseConvert"
    new_score.insert(0, new_part)

    return new_score

# ----------------------------------------
# MuseScore: MusicXML -> PDF (FINAL FIXED VERSION)
# ----------------------------------------
def run_musescore_to_pdf(musicxml_path: Path, out_dir: Path) -> Path:
    out_pdf = out_dir / f"{musicxml_path.stem}.pdf"

    result = subprocess.run(
        [
            MUSESCORE_CLI,
            str(musicxml_path),
            "--style", STYLE_FILE,
            "-o", str(out_pdf)
        ],
        capture_output=True, text=True, timeout=120
    )

    if result.returncode != 0:
        raise RuntimeError(
            f"MuseScore failed (exit {result.returncode}):\n"
            f"STDOUT:\n{result.stdout[-1000:]}\n"
            f"STDERR:\n{result.stderr[-1000:]}"
        )

    if not out_pdf.exists():
        raise FileNotFoundError("MuseScore did not produce a PDF")

    return out_pdf

# ----------------------------------------
# Convert endpoint
# ----------------------------------------
@app.post("/convert")
async def convert_file(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    original_instrument: str = Form(...),
    final_instrument: str = Form(...),
):
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

        new_score = process_score(
            input_path, original_instrument, final_instrument, input_path.stem
        )

        transposed_xml = temp_dir / f"transposed_{input_path.stem}.musicxml"
        new_score.write("musicxml", fp=str(transposed_xml))

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

if __name__ == "__main__":
    import uvicorn, os
    uvicorn.run(app, host="0.0.0.0", port=int(os.getenv("PORT", 8000)))
