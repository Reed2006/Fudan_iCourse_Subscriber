import os

STUDENT_ID = os.environ.get("StuId", "").strip()
PASSWORD = os.environ.get("UISPsw", "").strip()

WEBVPN_BASE = "https://webvpn.fudan.edu.cn"
IDP_BASE = "https://id.fudan.edu.cn"
ICOURSE_BASE = "https://icourse.fudan.edu.cn"

ICOURSE_ACCESS_MODE = os.environ.get("ICOURSE_ACCESS_MODE", "webvpn").strip().lower()

WEBVPN_AES_KEY = b"wrdvpnisthebest!"
WEBVPN_AES_IV = b"wrdvpnisthebest!"

TENANT_CODE = "222"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/120.0.0.0 Safari/537.36"
)

OUTPUT_DIR = os.environ.get("OUTPUT_DIR", "output").strip() or "output"

ASR_MODEL_DIR = os.environ.get(
    "ASR_MODEL_DIR",
    os.environ.get(
        "SENSEVOICE_MODEL_DIR",
        "sherpa-onnx-sense-voice-zh-en-ja-ko-yue-2024-07-17",
    ),
)
SILERO_VAD_PATH = os.environ.get("SILERO_VAD_PATH", "silero_vad.onnx").strip()
ASR_BACKEND = os.environ.get("ASR_BACKEND", "sensevoice").strip().lower()
ASR_NUM_THREADS = int(os.environ.get("ASR_NUM_THREADS", "4"))
