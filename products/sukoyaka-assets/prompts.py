# prompts.py — Flux Pro画像生成プロンプト定義

WOMAN_A = """
Portrait photo of an elegant Japanese woman in her 40s,
naturally feminine figure, soft curves,
warm genuine smile, casual-elegant clothing in cream and orange tones,
soft warm bokeh background, vintage warm film filter,
vignette effect, photorealistic, upper body shot,
high quality, no text
""".strip()

WOMAN_B = """
Portrait photo of an elegant Japanese woman in her 40s,
naturally feminine figure, soft curves,
slightly different angle from previous, cheerful expression,
casual-elegant clothing in warm earth tones,
soft warm bokeh background, vintage warm film filter,
vignette effect, photorealistic, upper body shot,
high quality, no text
""".strip()

COUPLE = """
Two Japanese people, man in his 50s and woman in her 40s,
natural warm expressions, casual-elegant clothing,
soft warm lighting, vintage film filter,
photorealistic, upper body shot, friendly atmosphere,
standing side by side, both smiling naturally,
no text, high quality
""".strip()

# モデル指定（Flux Pro）
FLUX_MODEL = "fal-ai/flux-pro"

# 生成パラメータ
GENERATION_PARAMS = {
    "width": 1024,
    "height": 1024,
    "num_inference_steps": 28,
    "guidance_scale": 3.5,
    "num_images": 1,
    "output_format": "png",
}
