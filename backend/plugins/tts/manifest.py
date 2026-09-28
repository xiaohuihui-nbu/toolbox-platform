from app.toolbox.schemas.tools import NaturalSpeechInput, SpeechInput

TOOLS = [
    {
        "id": "tts.natural",
        "name": "AI 自然配音",
        "category": "音频工具",
        "icon": "AudioLines",
        "color": "coral",
        "description": "GPT-SoVITS 中文自然音色，合成后直接试听。",
        "tags": ["16 种音色", "CPU"],
        "mode": "job",
        "handler": "gptsovits",
        "schema": NaturalSpeechInput,
        "note": "使用本机 GPT-SoVITS v2ProPlus，CPU 合成需要等待；参考音为合成预置样例，最终语气可能不同。最多 1000 字，建议先试一句短文。",
    },
    {
        "id": "tts.basic",
        "name": "文字转语音",
        "category": "音频工具",
        "icon": "AudioLines",
        "color": "coral",
        "description": "把文字变成声音，离线 CPU 即可运行。",
        "tags": ["离线", "TTS"],
        "mode": "job",
        "handler": "speech",
        "schema": SpeechInput,
        "note": "内置 eSpeak NG 基础音色，适合流程验证；自然中文音色请使用 AI 自然配音。",
    },
]
