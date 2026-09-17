"""
Kokoro TTS Web 服务
- 前端：静态页面 (index.html + TailwindCSS CDN)
- 后端：Flask API，调用 Kokoro KPipeline 生成语音
- 生成成功后返回可点击下载的音频链接
"""
import os
import re
import time
import uuid
import numpy as np
from flask import Flask, request, jsonify, send_from_directory, send_file

from kokoro import KPipeline

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
OUTPUT_DIR = os.path.join(BASE_DIR, "output")
os.makedirs(OUTPUT_DIR, exist_ok=True)

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


@app.route("/")
def index():
    return send_from_directory("static", "index.html")


@app.route("/api/tts", methods=["POST"])
def tts():
    data = request.get_json(silent=True) or {}
    text = (data.get("text") or "").strip()
    voice = data.get("voice", "af_heart")
    speed = float(data.get("speed", 1.0))

    if not text:
        return jsonify({"success": False, "error": "文本不能为空"}), 400

    if len(text) > 5000:
        return jsonify({"success": WAV_HEADER_PLACEHOLDER, "error": "文本过长（最多 5000 字符）"}), 400

    try:
        start = time.time()
        pipeline = get_pipeline()

        audio_chunks = []
        for _, _, audio in pipeline(text, voice=voice, speed=speed):
            audio_chunks.append(audio)

        if not audio_chunks:
            return jsonify({"success": False, "error": "未生成任何音频"}), 500

        audio = np.concatenate(audio_chunks)

        filename = f"{int(time.time())}_{safe_filename(text)}.wav"
        filepath = os.path.join(OUTPUT_DIR, filename)
        sf_write(filepath, audio, 24000)

        elapsed = round(time.time() - start, 2)
        duration = round(len(audio) / 24000, 1)

        print(f"✅ 生成完成: {filename} ({duration}s, 耗时 {elapsed}s)")

        return jsonify({
            "success": True,
            "url": f"/output/{filename}",
            "filename": filename,
            "duration": duration,
            "elapsed": elapsed,
            "download_url": f"/output/{filename}?download=1",
        })
    except Exception as e:
        print(f"❌ 生成失败: {e}")
        return jsonify({"success": False, "error": str(e)}), 500


def sf_write(filepath, audio, sample_rate):
    import soundfile as sf
    sf.write(filepath, audio, sample_rate)


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
    app.run(host="0.0.0.0", port=7860, debug=False, threaded=True)
