from fastapi import FastAPI, File, UploadFile, Form, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pathlib import Path
import subprocess
import tempfile
import shutil
import os
import time

from music21 import converter, stream, clef, metadata, chord, key, interval, meter, tempo, pitch

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
def instrument_to_viola_interval(inst: str):
    """
    Returns (diatonic_interval, octave_shift)
    where octave_shift is an integer number of 8ves.
    """

    mapping = {
        # -------------------------
        # STRINGS (your logic)
        # -------------------------
        "Violin":      ("-P5", 0),
        "Viola":       ("P1",  0),
        "Cello":       ("P1",  1),   # P8
        "Double Bass": ("P1",  2),   # P16

        # -------------------------
        # SAXOPHONES (your logic)
        # -------------------------
        "Saxophone Bb Soprano": ("-M7", 0),
        "Saxophone Eb Alto":    ("-M6", -1),  # -M13 = -M6 - P8
        "Saxophone Bb Tenor":   ("-P6", -1),  # -P14 = -P6 - P8
        "Saxophone Eb Baritone":("-P4", -2),  # -P20 = -P4 - 2×P8
        "Saxophone Bb Bass":    ("-P5", -2),  # -P21 = -P5 - 2×P8
        "Saxophone Eb Contrabass": ("-P3", -3), # -P27 = -P3 - 3×P8

        # -------------------------
        # CLARINETS (your logic)
        # -------------------------
        "Clarinet in Bb": ("-M7", 0),
        "Clarinet in A":  ("-m7", 0),
        "Clarinet in Eb": ("-m6", 0),
        "Bass Clarinet":  ("-P6", -1),  # -P14 = -P6 - P8
        "Basset Horn":    ("-P11", 0),  # stays as is

        # -------------------------
        # FLUTES / OBOES (your logic)
        # -------------------------
        "Piccolo":        ("-P8", 0),
        "Flute":          ("-P5", 0),
        "Alto Flute":     ("-M6", 0),
        "Oboe":           ("-P5", 0),
        "Oboe d'amore":   ("-m6", 0),
        "English Horn":   ("-P8", 0),
        "Heckelphone":    ("-P8", 0),
        "Bass Oboe":      ("-P8", 0),

        # -------------------------
        # BRASS (your logic)
        # -------------------------
        "Horn in F":      ("-P8", -1),  # -P24 = -P8 - 2×P8
        "Trumpet in C":   ("-P5", 0),
        "Trumpet in Bb":  ("-M7", 0),
        "Trumpet in A":   ("-m7", 0),
        "Cornet in Bb":   ("-M7", 0),
        "Flugelhorn":     ("-M7", 0),
        "Posthorn":       ("-M7", 0),
        "Pocket Trumpet": ("-M7", 0),

        # -------------------------
        # LOW BRASS (your logic)
        # -------------------------
        "Tenor Trombone": ("-P6", -1),  # -P14 = -P6 - P8
        "Bass Trombone":  ("-P6", -1),
        "Contrabass Trombone": ("P1", 0),

        "Euphonium":      ("P1", 1),  # P12 = P1 + P8
        "Tenor Tuba":     ("P1", 1),

        "Tuba Bb":        ("P1", 1),  # P24 = P1 + 2×P8
        "Tuba Eb":        ("P1", 2),  # P30 = P1 + 3×P8

        # -------------------------
        # PERCUSSION (your logic)
        # -------------------------
        "Xylophone":      ("-P8", 0),
        "Marimba":        ("P1", 0),
        "Orchestra Bells":("-P7", -1),  # -P15 = -P7 - P8
        "Glockenspiel":   ("-P7", -1),
        "Vibraphone":     ("P1", 0),
        "Chimes":         ("P1", 0),

        # -------------------------
        # GUITAR
        # -------------------------
        "Guitar":         ("P1", 1),  # P8
    }

    if inst not in mapping:
        raise ValueError(f"Unsupported instrument '{inst}'")

    return mapping[inst]

def viola_to_instrument_interval(inst):
    d, o = instrument_to_viola_interval(inst)

    # invert diatonic
    inv_diatonic = interval.Interval(d).reverse().directedName

    # invert octave shift
    inv_octaves = -o

    return (inv_diatonic, inv_octaves)

def build_interval(diatonic: str, octaves: int):
    # Start from a reference pitch
    ref = pitch.Pitch('C4')

    # Apply diatonic interval
    p = ref.transpose(interval.Interval(diatonic))

    # Apply octave shifts
    for _ in range(abs(octaves)):
        if octaves > 0:
            p = p.transpose(interval.Interval('P8'))
        else:
            p = p.transpose(interval.Interval('-P8'))

    # Build final interval from ref → p
    return interval.Interval(ref, p)

def get_transpose_interval(original_inst: str, final_inst: str):
    # original → viola
    d1, o1 = instrument_to_viola_interval(original_inst)
    i1 = build_interval(d1, o1)

    # viola → final
    d2, o2 = viola_to_instrument_interval(final_inst)
    i2 = build_interval(d2, o2)

    # combine
    ref = pitch.Pitch('C4')
    target = ref.transpose(i1).transpose(i2)
    return interval.Interval(ref, target)

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
    # ---------------------------------------------------------
    # 1. Compute transposition interval (new logic)
    # ---------------------------------------------------------
    transp_intvl = get_transpose_interval(original_inst, final_inst)

    # 2. Parse original score
    score = converter.parse(str(input_path))
    original_part = score.parts[0]

    # 3. Transpose the part
    transposed = original_part.transpose(transp_intvl)

    # 4. Build new part
    new_part = stream.Part()
    new_part.partName = final_inst

    # ---------------------------------------------------------
    # 5. Key Signature Handling
    # ---------------------------------------------------------
    orig_key_sig = original_part.recurse().getElementsByClass(key.KeySignature).first()
    
    if orig_key_sig:
        target_key_sig = orig_key_sig.transpose(transp_intvl)
    else:
        target_key_sig = key.KeySignature(0)

    if target_key_sig.sharps > 7 or target_key_sig.sharps < -7:
        target_key_sig = target_key_sig.getEnharmonic()

    # 6. Clef, time signature, tempo
    target_clef = get_clef(final_inst)
    tempo_mark = transposed.recurse().getElementsByClass(tempo.MetronomeMark).first()

    # 7. Insert measures and clean mid‑measure clefs
    for i, measure in enumerate(transposed.getElementsByClass(stream.Measure)):
        for c in measure.recurse().getElementsByClass(clef.Clef):
            measure.remove(c)

        if i == 0:
            if target_clef:
                measure.insert(0, target_clef)
            if tempo_mark:
                measure.insert(0, tempo_mark)
            measure.insert(0, target_key_sig)

        new_part.append(measure)

    # 8. Remove trailing empty measures
    measures = list(new_part.getElementsByClass(stream.Measure))
    for m in reversed(measures):
        if len(m.notesAndRests) == 0 or all(n.isRest for n in m.notesAndRests):
            new_part.remove(m)
        else:
            break

    # 9. Build final score
    new_score = stream.Score()
    new_score.metadata = metadata.Metadata()
    new_score.metadata.title = f"{stem} ({final_inst} Transcription)"
    new_score.metadata.composer = "Arranged by MuseConvert"
    new_score.insert(0, new_part)

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

        # STEP 2 — MusicXML → transposed MusicXML 
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
