"""
Kokoro TTS Web 服务
- 前端：静态页面 (index.html + TailwindCSS CDN)
- 后端：Flask API，调用 Kokoro KPipeline 生成语音
- 生成成功后返回可点击下载的音频链接

语速处理流程（两段式）：
1. Kokoro 始终以 speed=1 生成临时 WAV（模型原生语速，韵律最自然）
2. 若目标语速 != 1.0，用 ffmpeg atempo 滤镜对临时 WAV 变速，输出最终文件
3. 临时文件用完即删
"""
import os
import re
import subprocess
import time
import uuid

import numpy as np
import soundfile as sf
from flask import Flask, jsonify, request, send_from_directory

from kokoro import KPipeline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

SAMPLE_RATE = 24000

app = Flask(__name__, static_folder="static", static_url_path="/static")

# 全局只加载一次模型（首次调用时懒加载）
_pipeline = None


def get_pipeline():
    global _pipeline
    if _pipeline is None:
        print("⏳ 正在加载 Kokoro 模型（首次调用需要一些时间）...")
        _pipeline = KPipeline(lang_code="a")  # 'a' = American English
        print("✅ 模型加载完成")
    return _pipeline


def safe_filename(text: str) -> str:
    """从文本中提取安全文件名"""
    text = re.sub(r"\s+", " ", text.strip())
    text = re.sub(r"[^\w\s-]", "", text)
    text = text[:40].strip().replace(" ", "_")
    return text or "speech"


def build_atempo_filter(speed: float) -> str:
    """
    ffmpeg 的 atempo 单个滤镜只支持 0.5 ~ 2.0，
    超出范围时串联多个 atempo 实现任意语速。
    例：speed=4.0   -> "atempo=2.0,atempo=2.0"
        speed=0.25  -> "atempo=0.5,atempo=0.5"
    """
    if speed <= 0:
        raise ValueError("speed 必须大于 0")
    filters = []
    remaining = speed
    while remaining > 2.0:
        filters.append("atempo=2.0")
        remaining /= 2.0
    while remaining < 0.5:
        filters.append("atempo=0.5")
        remaining *= 2.0
    filters.append(f"atempo={remaining:.4f}")
    return ",".join(filters)


def ffmpeg_change_speed(input_path: str, output_path: str, speed: float) -> None:
    """用 ffmpeg atempo 滤镜把 input_path 变速为 speed 倍，写入 output_path"""
    filter_str = build_atempo_filter(speed)
    cmd = [
        "ffmpeg", "-y", "-loglevel", "error",
        "-i", input_path,
        "-filter:a", filter_str,
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 变速失败: {result.stderr.strip()[:300]}")


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    voice = data.get("voice", "af_heart")
    try:
        speed = float(data.get("speed", 1.0))
    except (TypeError, ValueError):
        return jsonify({"success": False, "error": "speed 参数无效"}), 400

    if not text:
        return jsonify({"success": False, "error": "文本不能为空"}), 400
    if len(text) > 5000:
        return jsonify({"success": False, "error": "文本过长（最多 5000 字符）"}), 400
    if not (0.1 <= speed <= 4.0):
        return jsonify({"success": False, "error": "speed 需在 0.1 ~ 4.0 之间"}), 400

    temp_path = None
    try:
        start = time.time()
        pipeline = get_pipeline()

        # 1️⃣ Kokoro 始终用 speed=1 生成（不管前端传什么）
        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=1.0):
            audio_chunks.append(audio)

        if not audio_chunks:
            return jsonify({"success": False, "error": "未生成任何音频"}), 500

        audio = np.concatenate(audio_chunks)

        # 2️⃣ 先写临时 WAV
        temp_path = os.path.join(OUTPUT_DIR, f"temp_{uuid.uuid4().hex}.wav")
        sf.write(temp_path, audio, SAMPLE_RATE)

        # 3️⃣ 语速处理：1.0 直接改名复用；否则 ffmpeg atempo 变速
        filename = f"{int(time.time())}_{safe_filename(text)}.wav"
        final_path = os.path.join(OUTPUT_DIR, filename)

        if abs(speed - 1.0) < 1e-6:
            os.replace(temp_path, final_path)
            temp_path = None  # 已被移动，无需再清理
        else:
            ffmpeg_change_speed(temp_path, final_path, speed)

        # 4️⃣ 读取最终文件的真实时长
        duration = round(sf.info(final_path).duration, 1)

        elapsed = round(time.time() - start, 2)
        print(f"✅ 生成完成: {filename} (语速 {speed}x, 时长 {duration}s, 耗时 {elapsed}s)")

        return jsonify({
            "success": True,
            "url": f"/output/{filename}",
            "filename": filename,
            "duration": duration,
            "elapsed": elapsed,
            "speed": speed,
            "download_url": f"/output/{filename}?download=1",
        })
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        # 5️⃣ 清理临时文件
        if temp_path and os.path.exists(temp_path):
            try:
                os.remove(temp_path)
            except OSError:
                pass


@app.route("/output/<path:filename>")
def serve_output(filename):
    as_attachment = request.args.get("download") == "1"
    return send_from_directory(
        OUTPUT_DIR, filename,
        as_attachment=as_attachment,
        mimetype="audio/wav",
    )


@app.route("/api/health")
def health():
    return jsonify({"status": "ok", "model_loaded": _pipeline is not None})


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 7860))
    app.run(host="0.0.0.0", port=port, debug=False, threaded=True)
