"""Shared constants for the OpenClaw launcher -- Yonghao Tech theme."""

APP_NAME = "OpenClaw"
APP_PORT = 18790
HELP_URL = "https://heang.top/docs.html"
FEISHU_APP_URL = "https://open.feishu.cn/app"
LICENSE_SERVER_URL = "https://license.heang.top"

PROVIDERS = {
    "Heang AI": {"url": "https://api.heang.top/v1", "models": ["kimi-k2.5", "gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "OpenAI": {"url": "https://api.openai.com/v1", "models": ["gpt-4o", "gpt-4", "gpt-3.5-turbo"]},
    "Claude": {"url": "https://api.anthropic.com/v1", "models": ["claude-3-5-sonnet-20241022", "claude-3-opus-20240229"]},
    "DeepSeek": {"url": "https://api.deepseek.com/v1", "models": ["deepseek-chat", "deepseek-coder"]},
    "智谱AI": {"url": "https://open.bigmodel.cn/api/paas/v4", "models": ["glm-4", "glm-4-flash"]},
    "Moonshot": {"url": "https://api.moonshot.cn/v1", "models": ["moonshot-v1-8k", "moonshot-v1-32k"]},
    "自定义": {"url": "", "models": []},
}

IMAGE_MODEL = "gpt-image-2"
IMAGE_TRIPLE_TEMPLATES = [
    ("主图", "professional product photography, clean studio lighting, hero shot, commercial grade, photorealistic, high quality product image"),
    ("白底图", "pure white background, isolated product on white, e-commerce standard white background product shot, clean minimal product photo, white backdrop studio photography"),
    ("详情图", "detailed close-up macro product photography, showing product features and textures, fine details visible, premium quality product detail shot"),
]
VIDEO_MODEL_T2V = "happyhorse-1.0-t2v"
VIDEO_MODEL_I2V = "happyhorse-1.0-i2v"
DASHSCOPE_VIDEO_URL = "https://dashscope.aliyuncs.com/api/v1/services/aigc/video-generation/video-synthesis"
DASHSCOPE_TASK_URL = "https://dashscope.aliyuncs.com/api/v1/tasks/{task_id}"

# Yonghao Tech -- cool tech blue, clean surfaces, slate gray backgrounds.
COLORS = {
    "app_bg": "#F3F4F5",
    "sidebar_bg": "#F9F9FA",
    "surface": "#FFFFFF",
    "surface_alt": "#F6F7F8",
    "surface_deep": "#1C202A",
    "surface_deeper": "#14171E",
    "hover": "#EDEFF1",
    "input": "#F6F7F8",
    "border": "#DDDFE3",
    "border_strong": "#C1C4CC",
    "text": "#1E2A3A",
    "text_muted": "#64748B",
    "text_subtle": "#94A3B8",
    "accent": "#1A56DB",
    "accent_hover": "#1444AD",
    "accent_soft": "#E4E8F0",
    "accent_ink": "#0F327F",
    "success": "#059669",
    "warning": "#D97706",
    "danger": "#DC2626",
    "danger_hover": "#B91C1C",
    "terminal_bg": "#0F172A",
    "terminal_header": "#1E293B",
    "terminal_text": "#34D399",
    # - relocated from nav_button.py -
    "danger_muted": "#FEE2E2",
    "primary_muted": "#DBEAFE",
    "accent_hover_light": "#BFDBFE",
    # - relocated from app.py (terminal area) -
    "terminal_dot_red": "#EF4444",
    "terminal_dot_yellow": "#F59E0B",
    "terminal_dot_green": "#22C55E",
    "terminal_label": "#CBD5E1",
    "terminal_label_muted": "#64748B",
    "terminal_button_bg": "#334155",
    "terminal_button_hover": "#475569",
    "terminal_button_text": "#FFFFFF",
    "terminal_selection": "#1E3A2F",
    # - relocated from image_page.py -
    "viewer_bg": "#000000",
    "viewer_bar_bg": "#1E293B",
    # - relocated from license_page.py -
    "code_input_bg": "#FFFFFF",
}

FONTS = {
    "display": ("Microsoft YaHei UI", 21, "bold"),
    "title": ("Microsoft YaHei UI", 14, "bold"),
    "section": ("Microsoft YaHei UI", 10, "bold"),
    "body": ("Microsoft YaHei UI", 10),
    "small": ("Microsoft YaHei UI", 9),
    "mono": ("Consolas", 10),
    # - relocated from app.py -
    "sidebar_caption": ("Microsoft YaHei UI", 8, "bold"),
    # - relocated from license_page.py -
    "license_code": ("Consolas", 13),
}

BRAND = {
    "name": "永浩科技",
    "subtitle": "智能AI服务平台",
    "app_user_model_id": "YonghaoTech.Launcher",
    "terminal_header": "Service Console",
}
