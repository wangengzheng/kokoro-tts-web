# Kokoro TTS Web

英文文本 → 语音合成（Kokoro-82M 本地推理）→ 返回可点击下载的 WAV 链接。

## 结构

```
web/
├── app.py              # Flask 后端（API + 静态托管）
├── static/
│   └── index.html      # 静态前端（TailwindCSS CDN）
├── output/             # 生成的音频文件
└── README.md
```

## 启动

```bash
conda activate kokoro
cd /Users/james/kokoro/web
python app.py
```

打开 http://localhost:7860

## API

| 方法 | 路径 | 说明 |
|------|------|------|
| GET  | `/` | 前端页面 |
| POST | `/api/tts` | `{ "text": "...", "voice": "af_heart", "speed": 1.0 }` → `{ success, url, download_url, duration, elapsed }` |
| GET  | `/output/<file>` | 播放音频；加 `?download=1` 触发下载 |
| GET  | `/api/health` | 健康检查 |

## 特性

- ✅ 静态页面 + TailwindCSS（CDN，零构建）
- ✅ 音色 / 语速可选
- ✅ 生成后内嵌播放器 + 下载链接
- ✅ 会话内历史记录
- ✅ ⌘/Ctrl + Enter 快捷生成
- ✅ 响应式 + 无障碍（aria-live、role、键盘可达）
