from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import subprocess
import tempfile
import shutil
import os
import time

from music21 import converter, stream, clef, metadata, chord, key, interval, meter, tempo

# Simple in-memory log buffer for live debugging
LIVE_LOGS = []

def live_log(msg: str):
    LIVE_LOGS.append(msg)
    print(msg)

app = FastAPI(title="MuseConvert PDF Instrument Converter")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MUSESCORE_CLI = os.getenv("MUSESCORE_CLI", "/opt/musescore/bin/mscore4portable")
AUDIVERIS_CLI = os.getenv("AUDIVERIS_CLI", "/opt/audiveris/bin/audiveris.sh")

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_STYLE_PATH = BASE_DIR / "styles" / "default.mss"
STYLE_FILE = Path(os.getenv("MUSESCORE_STYLE", str(DEFAULT_STYLE_PATH)))


# ----------------------------------------
# Health
# ----------------------------------------
@app.get("/")
def root():
    return {"service": "MuseConvert PDF Instrument Converter", "status": "running"}


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
    results["audiveris_exists"] = Path(AUDIVERIS_CLI).exists()

    # MuseScore version
    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    r = subprocess.run(
        [MUSESCORE_CLI, "--version"],
        capture_output=True,
        text=True,
        env=env
    )
    results["mscore_version"] = r.stdout.strip() or r.stderr.strip()

    # Audiveris version
    r2 = subprocess.run(
        [AUDIVERIS_CLI, "-version"],
        capture_output=True,
        text=True
    )
    results["audiveris_version"] = r2.stdout.strip() or r2.stderr.strip()

    return results


@app.post("/debug-process")
async def debug_process(file: UploadFile = File(...), original_instrument: str = Form(...), final_instrument: str = Form(...)):
    LIVE_LOGS.clear()
    live_log("🚀 Starting debug pipeline")

    temp_dir = Path(tempfile.mkdtemp(prefix="museconvert_debug_"))

    try:
        filename = file.filename or "upload.pdf"
        pdf_path = temp_dir / filename
        pdf_path.write_bytes(await file.read())

        # STEP 1 — PDF → MusicXML (Audiveris)
        try:
            musicxml_path = run_audiveris_on_pdf(pdf_path, temp_dir)
        except Exception as e:
            return {
                "stage": "audiveris",
                "status": "error",
                "error": str(e)[:1000]
            }

        # STEP 2 — MusicXML → transposed MusicXML (Music21)
        try:
            new_score = process_score(
                musicxml_path,
                original_instrument,
                final_instrument,
                musicxml_path.stem
            )
            transposed_xml = temp_dir / f"transposed_{musicxml_path.stem}.musicxml"
            new_score.write("musicxml", fp=str(transposed_xml))
        except Exception as e:
            import traceback
            return {
                "stage": "music21",
                "status": "error",
                "error": str(e)[:1000],
                "traceback": traceback.format_exc()[-2000:]
            }

        # STEP 3 — Transposed MusicXML → PDF (MuseScore)
        try:
            pdf_out = run_musescore_to_pdf(transposed_xml, temp_dir)
        except Exception as e:
            import traceback
            return {
                "stage": "musescore",
                "status": "error",
                "error": str(e)[:1000],
                "traceback": traceback.format_exc()[-2000:]
            }

        # SUCCESS — return metadata
        return {
            "stage": "complete",
            "status": "ok",
            "input_pdf": filename,
            "musicxml_generated": musicxml_path.name,
            "musicxml_size": musicxml_path.stat().st_size,
            "transposed_xml": transposed_xml.name,
            "transposed_xml_size": transposed_xml.stat().st_size,
            "pdf_generated": pdf_out.name,
            "pdf_size": pdf_out.stat().st_size,
        }

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

# ----------------------------------------
# Transposition intervals (your existing logic)
# ----------------------------------------
def get_transpose_intervals(original_inst, final_inst):
    intvl_1 = None
    intvl_2 = None

    match original_inst:
        case "Piccolo": intvl_1 = interval.Interval('-P8')
        case "Flute": intvl_1 = interval.Interval('-P5')
        case "Alto Flute": intvl_1 = interval.Interval('-M6')
        case "Oboe": intvl_1 = interval.Interval('-P5')
        case "Oboe d'amore": intvl_1 = interval.Interval('-m6')
        case "English Horn": intvl_1 = interval.Interval('-P8')
        case "Heckelphone": intvl_1 = interval.Interval('-P8')
        case "Bass Oboe": intvl_1 = interval.Interval('-P8')
        case "Clarinet in Bb": intvl_1 = interval.Interval('-M7')
        case "Clarinet in A": intvl_1 = interval.Interval('-m7')
        case "Clarinet in Eb": intvl_1 = interval.Interval('-m6')
        case "Basset Horn": intvl_1 = interval.Interval('-P11')
        case "Bass Clarinet": intvl_1 = interval.Interval('-P14')
        case "Bassoon": intvl_1 = interval.Interval('P12')
        case "Contrabassoon": intvl_1 = interval.Interval('P24')
        case "Saxophone Bb Soprano": intvl_1 = interval.Interval('-M7')
        case "Saxophone Eb Alto": intvl_1 = interval.Interval('-M13')
        case "Saxophone Bb Tenor": intvl_1 = interval.Interval('-P14')
        case "Saxophone Eb Baritone": intvl_1 = interval.Interval('-P20')
        case "Saxophone Bb Bass": intvl_1 = interval.Interval('-P21')
        case "Saxophone Eb Contrabass": intvl_1 = interval.Interval('-P27')
        case "Horn in F": intvl_1 = interval.Interval('-P24')
        case "Tuba Bb": intvl_1 = interval.Interval('P24')
        case "Tuba Eb": intvl_1 = interval.Interval('P30')
        case "Trumpet in C": intvl_1 = interval.Interval('-P5')
        case "Trumpet in Bb": intvl_1 = interval.Interval('-M7')
        case "Trumpet in A": intvl_1 = interval.Interval('-m7')
        case "Piccolo Trumpet Bb": intvl_1 = interval.Interval('-M7')
        case "Piccolo Trumpet A": intvl_1 = interval.Interval('-m7')
        case "Cornet in Bb": intvl_1 = interval.Interval('-M7')
        case "Flugelhorn": intvl_1 = interval.Interval('-M7')
        case "Posthorn": intvl_1 = interval.Interval('-M7')
        case "Pocket Trumpet": intvl_1 = interval.Interval('-M7')
        case "Alto Trombone": intvl_1 = interval.Interval('-P5')
        case "Tenor Trombone": intvl_1 = interval.Interval('-P14')
        case "Bass Trombone": intvl_1 = interval.Interval('-P14')
        case "Contrabass Trombone": intvl_1 = interval.Interval('P1')
        case "Euphonium": intvl_1 = interval.Interval('P12')
        case "Tenor Tuba": intvl_1 = interval.Interval('P12')
        case "Timpani": intvl_1 = interval.Interval('P1')
        case "Xylophone": intvl_1 = interval.Interval('-P8')
        case "Marimba": intvl_1 = interval.Interval('P1')
        case "Orchestra Bells": intvl_1 = interval.Interval('-P15')
        case "Glockenspiel": intvl_1 = interval.Interval('-P15')
        case "Vibraphone": intvl_1 = interval.Interval('P1')
        case "Chimes": intvl_1 = interval.Interval('P1')
        case "Guitar": intvl_1 = interval.Interval('P8')
        case "Violin": intvl_1 = interval.Interval('-P5')
        case "Viola": intvl_1 = interval.Interval('P1')
        case "Cello": intvl_1 = interval.Interval('P8')
        case "Double Bass": intvl_1 = interval.Interval('P16')
        case _: raise ValueError(f"Unsupported source instrument '{original_inst}'")

    match final_inst:
        case "Piccolo": intvl_2 = interval.Interval('P8')
        case "Flute": intvl_2 = interval.Interval('P5')
        case "Alto Flute": intvl_2 = interval.Interval('M6')
        case "Oboe": intvl_2 = interval.Interval('P5')
        case "Oboe d'amore": intvl_2 = interval.Interval('m6')
        case "English Horn": intvl_2 = interval.Interval('P8')
        case "Heckelphone": intvl_2 = interval.Interval('P8')
        case "Bass Oboe": intvl_2 = interval.Interval('P8')
        case "Clarinet in Bb": intvl_2 = interval.Interval('M7')
        case "Clarinet in A": intvl_2 = interval.Interval('m7')
        case "Clarinet in Eb": intvl_2 = interval.Interval('m6')
        case "Basset Horn": intvl_2 = interval.Interval('P11')
        case "Bass Clarinet": intvl_2 = interval.Interval('P14')
        case "Bassoon": intvl_2 = interval.Interval('-P12')
        case "Contrabassoon": intvl_2 = interval.Interval('-P24')
        case "Saxophone Bb Soprano": intvl_2 = interval.Interval('M7')
        case "Saxophone Eb Alto": intvl_2 = interval.Interval('M13')
        case "Saxophone Bb Tenor": intvl_2 = interval.Interval('P14')
        case "Saxophone Eb Baritone": intvl_2 = interval.Interval('P20')
        case "Saxophone Bb Bass": intvl_2 = interval.Interval('P21')
        case "Saxophone Eb Contrabass": intvl_2 = interval.Interval('P27')
        case "Horn in F": intvl_2 = interval.Interval('P24')
        case "Tuba Bb": intvl_2 = interval.Interval('-P24')
        case "Tuba Eb": intvl_2 = interval.Interval('-P30')
        case "Trumpet in C": intvl_2 = interval.Interval('P5')
        case "Trumpet in Bb": intvl_2 = interval.Interval('M7')
        case "Trumpet in A": intvl_2 = interval.Interval('m7')
        case "Piccolo Trumpet Bb": intvl_2 = interval.Interval('M7')
        case "Piccolo Trumpet A": intvl_2 = interval.Interval('m7')
        case "Cornet in Bb": intvl_2 = interval.Interval('M7')
        case "Flugelhorn": intvl_2 = interval.Interval('M7')
        case "Posthorn": intvl_2 = interval.Interval('M7')
        case "Pocket Trumpet": intvl_2 = interval.Interval('M7')
        case "Alto Trombone": intvl_2 = interval.Interval('P5')
        case "Tenor Trombone": intvl_2 = interval.Interval('P14')
        case "Bass Trombone": intvl_2 = interval.Interval('P14')
        case "Contrabass Trombone": intvl_2 = interval.Interval('P1')
        case "Euphonium": intvl_2 = interval.Interval('-P12')
        case "Tenor Tuba": intvl_2 = interval.Interval('-P12')
        case "Timpani": intvl_2 = interval.Interval('P1')
        case "Xylophone": intvl_2 = interval.Interval('P8')
        case "Marimba": intvl_2 = interval.Interval('P1')
        case "Orchestra Bells": intvl_2 = interval.Interval('P15')
        case "Glockenspiel": intvl_2 = interval.Interval('P15')
        case "Vibraphone": intvl_2 = interval.Interval('P1')
        case "Chimes": intvl_2 = interval.Interval('P1')
        case "Guitar": intvl_2 = interval.Interval('-P8')
        case "Violin": intvl_2 = interval.Interval('P5')
        case "Viola": intvl_2 = interval.Interval('P1')
        case "Cello": intvl_2 = interval.Interval('-P8')
        case "Double Bass": intvl_2 = interval.Interval('-P16')
        case _: raise ValueError(f"Unsupported target instrument '{final_inst}'")

    return intvl_1, intvl_2


# ----------------------------------------
# Clef map (your existing logic)
# ----------------------------------------
TREBLE_INSTRUMENTS = {
    "Piccolo", "Flute", "Alto Flute", "Oboe", "Oboe d'amore",
    "English Horn", "Heckelphone", "Bass Oboe",
    "Clarinet in Bb", "Clarinet in A", "Clarinet in Eb",
    "Basset Horn", "Bass Clarinet",
    "Saxophone Bb Soprano", "Saxophone Eb Alto",
    "Saxophone Bb Tenor", "Saxophone Eb Baritone",
    "Saxophone Bb Bass", "Saxophone Eb Contrabass",
    "Horn in F", "Trumpet in C", "Trumpet in Bb", "Trumpet in A",
    "Piccolo Trumpet Bb", "Piccolo Trumpet A",
    "Cornet in Bb", "Flugelhorn", "Posthorn", "Pocket Trumpet",
    "Alto Trombone",
    "Xylophone", "Marimba", "Orchestra Bells",
    "Glockenspiel", "Vibraphone", "Chimes",
    "Guitar", "Violin",
}

ALTO_INSTRUMENTS = {"Viola"}

BASS_INSTRUMENTS = {
    "Cello", "Double Bass", "Bassoon", "Contrabassoon",
    "Tenor Trombone", "Bass Trombone", "Contrabass Trombone",
    "Euphonium", "Tenor Tuba", "Tuba Bb", "Tuba Eb",
    "Timpani",
}

def get_clef(instrument_name: str):
    if instrument_name in ALTO_INSTRUMENTS:
        return clef.AltoClef()
    elif instrument_name in BASS_INSTRUMENTS:
        return clef.BassClef()
    else:
        return clef.TrebleClef()


def process_score(input_path: Path, original_inst: str, final_inst: str, stem: str) -> stream.Score:
    # ----------------------------------------
    # 1. Compute transposition interval
    # ----------------------------------------
    i1, i2 = get_transpose_intervals(original_inst, final_inst)
    semitones_total = i1.semitones + i2.semitones
    transp_intvl = interval.Interval(semitones_total)

    # ----------------------------------------
    # 2. Parse original score
    # ----------------------------------------
    score = converter.parse(str(input_path))
    original_part = score.parts[0]

    # ----------------------------------------
    # 3. Transpose the part
    # ----------------------------------------
    transposed = original_part.transpose(transp_intvl)

    # ----------------------------------------
    # 4. Build new part
    # ----------------------------------------
    new_part = stream.Part()
    new_part.partName = final_inst

    # ----------------------------------------
    # 5. Extract original written key signature
    # ----------------------------------------
    orig_key_sig = original_part.recurse().getElementsByClass(key.KeySignature).first()

    if orig_key_sig:
        # Transpose sharps count by circle-of-fifths logic
        new_sharps = orig_key_sig.sharps + (transp_intvl.semitones // 2)
    
        # RULE 1: Preserve accidental family
        orig_was_flat = orig_key_sig.sharps < 0
        orig_was_sharp = orig_key_sig.sharps > 0
    
        # RULE 2: If original was flat-based, force flat-based spelling
        if orig_was_flat and new_sharps > 0:
            new_sharps -= 12  # convert C# major → Db major, etc.
    
        # RULE 3: If original was sharp-based, allow sharp keys (including C# major)
        # No change needed
    
        # RULE 4: Avoid extreme keys (more than 6 sharps or flats)
        if new_sharps > 6:
            new_sharps -= 12
        if new_sharps < -6:
            new_sharps += 12
    
        new_part.insert(0.1, key.KeySignature(new_sharps))


    # ----------------------------------------
    # 6. Clef, time signature, tempo
    # ----------------------------------------
    target_clef = get_clef(final_inst)
    time_sig = transposed.recurse().getElementsByClass(meter.TimeSignature).first()
    tempo_mark = transposed.recurse().getElementsByClass(tempo.MetronomeMark).first()

    # ----------------------------------------
    # 7. Insert measures and clean mid‑measure clefs
    # ----------------------------------------
    for i, measure in enumerate(transposed.getElementsByClass(stream.Measure)):
        for c in measure.recurse().getElementsByClass(clef.Clef):
            measure.remove(c)

        if i == 0:
            if target_clef: measure.insert(0, target_clef)
            if time_sig:    measure.insert(0, time_sig)
            if tempo_mark:  measure.insert(0, tempo_mark)

        new_part.append(measure)

    # ----------------------------------------
    # 8. Remove trailing empty measures
    # ----------------------------------------
    measures = list(new_part.getElementsByClass(stream.Measure))
    for m in reversed(measures):
        if len(m.notesAndRests) == 0 or all(n.isRest for n in m.notesAndRests):
            new_part.remove(m)
        else:
            break

    # ----------------------------------------
    # 9. Build final score
    # ----------------------------------------
    new_score = stream.Score()
    new_score.metadata = metadata.Metadata()
    new_score.metadata.title = f"{stem} ({final_inst} Transcription)"
    new_score.metadata.composer = "Arranged by MuseConvert"
    new_score.insert(0, new_part)

    # ----------------------------------------
    # 10. Clean accidental spelling (based on key)
    # ----------------------------------------
    new_score.rewriteAccidentals(inPlace=True)

    return new_score
    
# ----------------------------------------
# MuseScore: MusicXML → PDF (your existing logic)
# ----------------------------------------
def get_musescore_style_args(style_path: Path | None) -> list[str]:
    if not style_path or not style_path.exists():
        return []

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"
    help_result = subprocess.run(
        [MUSESCORE_CLI, "--help"],
        capture_output=True,
        text=True,
        timeout=30,
        env=env,
    )
    help_text = f"{help_result.stdout}\n{help_result.stderr}".lower()

    if "--style" in help_text:
        return ["--style", str(style_path)]
    if "-s" in help_text:
        return ["-s", str(style_path)]
    return []


def run_musescore_to_pdf(musicxml_path: Path, out_dir: Path) -> Path:
    out_pdf = out_dir / f"{musicxml_path.stem}.pdf"

    env = os.environ.copy()
    env["QT_QPA_PLATFORM"] = "offscreen"

    # Start virtual display
    xvfb = subprocess.Popen(
        ["Xvfb", ":99", "-screen", "0", "1280x1024x24"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL
    )
    env["DISPLAY"] = ":99"

    try:
        time.sleep(1)  # allow Xvfb to initialize

        style_args = get_musescore_style_args(STYLE_FILE)
        cmd = [MUSESCORE_CLI, *style_args, str(musicxml_path), "-o", str(out_pdf)]

        live_log("▶ MuseScore engraving (MusicXML → PDF)")
        live_log(f"$ {' '.join(cmd)}")

        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            env=env
        )

        start_time = time.time()
        TIMEOUT = 120  # 2 minutes (adjust if needed)

        # Stream logs line-by-line
        for line in process.stdout:
            live_log(line.rstrip())

            # Manual timeout check
            if time.time() - start_time > TIMEOUT:
                process.kill()
                live_log("❌ MuseScore timed out after 120 seconds")
                raise TimeoutError("MuseScore timed out after 120 seconds")

        process.wait()

        if process.returncode != 0:
            live_log(f"❌ MuseScore failed with code {process.returncode}")
            raise RuntimeError(f"MuseScore failed (exit {process.returncode})")

        live_log("✔ MuseScore engraving completed")

        if not out_pdf.exists():
            raise FileNotFoundError("MuseScore did not produce a PDF")

        return out_pdf

    finally:
        xvfb.terminate()


# ----------------------------------------
# Audiveris: PDF → MusicXML (new)
# ----------------------------------------
def run_audiveris_on_pdf(pdf_path: Path, out_dir: Path) -> Path:
    cmd = [
        AUDIVERIS_CLI,
        "-batch",
        "-export",
        "-output", str(out_dir),
        str(pdf_path),
    ]

    # Use Popen for streaming logs
    live_log("▶ Audiveris OMR (PDF → MusicXML)")
    live_log(f"$ {' '.join(cmd)}")

    process = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True
    )

    start_time = time.time()
    TIMEOUT = 900  # 15 minutes

    # Stream logs line-by-line
    for line in process.stdout:
        live_log(line.rstrip())

        # Manual timeout check
        if time.time() - start_time > TIMEOUT:
            process.kill()
            live_log("❌ Audiveris timed out after 900 seconds")
            raise TimeoutError("Audiveris timed out after 900 seconds")

    process.wait()

    if process.returncode != 0:
        live_log(f"❌ Audiveris failed with code {process.returncode}")
        raise RuntimeError(f"Audiveris failed (exit {process.returncode})")

    live_log("✔ Audiveris OMR completed")

    # Find MusicXML output
    candidates = list(out_dir.glob("*.xml")) + list(out_dir.glob("*.mxl"))
    if not candidates:
        raise FileNotFoundError("Audiveris did not produce any MusicXML file")

    return candidates[0]

@app.get("/debug-logs")
def debug_logs():
    return {"logs": LIVE_LOGS[-200:]}  # last 200 lines

@app.post("/convert-pdf")
async def convert_pdf(
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    original_instrument: str = Form(...),
    final_instrument: str = Form(...),
):
    filename = file.filename or ""
    if not filename.lower().endswith(".pdf"):
        return JSONResponse(
            status_code=422,
            content={"error": "Please upload a PDF file (.pdf)"}
        )

    temp_dir = Path(tempfile.mkdtemp(prefix="museconvert_pdf_"))

    try:
        # Save uploaded PDF
        pdf_path = temp_dir / filename
        pdf_path.write_bytes(await file.read())

        # STEP 1 — PDF → MusicXML (Audiveris)
        musicxml_path = run_audiveris_on_pdf(pdf_path, temp_dir)

        # STEP 2 — MusicXML → transposed MusicXML (your existing pipeline)
        new_score = process_score(
            musicxml_path,
            original_instrument,
            final_instrument,
            musicxml_path.stem
        )

        transposed_xml = temp_dir / f"transposed_{musicxml_path.stem}.musicxml"
        new_score.write("musicxml", fp=str(transposed_xml))

        # STEP 3 — MusicXML → PDF (MuseScore)
        pdf_out = run_musescore_to_pdf(transposed_xml, temp_dir)

        # Cleanup
        background_tasks.add_task(shutil.rmtree, str(temp_dir), True)

        return FileResponse(
            path=str(pdf_out),
            filename=f"converted_{pdf_path.stem}.pdf",
            media_type="application/pdf",
        )

    except Exception as e:
        shutil.rmtree(temp_dir, ignore_errors=True)
        return JSONResponse(
            status_code=500,
            content={"error": str(e)[:500]}
        )
