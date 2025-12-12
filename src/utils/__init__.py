# Utils package
from .constants import STICKER_SIZE, STICKER_MAX_SIZE, WEBP_QUALITY
from .links import create_miniapp_deeplink, decode_miniapp_start_param, create_miniapp_deeplink_simple

__all__ = [
    'STICKER_SIZE',
    'STICKER_MAX_SIZE',
    'WEBP_QUALITY',
    'create_miniapp_deeplink',
    'decode_miniapp_start_param',
    'create_miniapp_deeplink_simple',
]
