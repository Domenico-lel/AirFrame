"""Device identity is authoritative only when advertised; resolution is not identity."""
from dataclasses import dataclass


@dataclass(frozen=True)
class Profile:
    key: str
    label: str
    width: int
    height: int
    cutout: str = 'none'
    radius: float = .115


PROFILES = {
    'generic': Profile('generic', 'Automatico / dispositivo generico', 393, 852, 'none'),
    '14pro': Profile('14pro', 'iPhone 14 Pro', 393, 852, 'island'),
    '14promax': Profile('14promax', 'iPhone 14 Pro Max', 430, 932, 'island'),
    '14': Profile('14', 'iPhone 14', 390, 844, 'notch'),
    '14plus': Profile('14plus', 'iPhone 14 Plus', 428, 926, 'notch'),
    '13mini': Profile('13mini', 'iPhone 13 mini', 375, 812, 'notch'),
    '13': Profile('13', 'iPhone 13 / 13 Pro', 390, 844, 'notch'),
    '13promax': Profile('13promax', 'iPhone 13 Pro Max', 428, 926, 'notch'),
    '15': Profile('15', 'iPhone 15', 393, 852, 'island'),
    '15plus': Profile('15plus', 'iPhone 15 Plus', 430, 932, 'island'),
    '15pro': Profile('15pro', 'iPhone 15 Pro', 393, 852, 'island'),
    '15promax': Profile('15promax', 'iPhone 15 Pro Max', 430, 932, 'island'),
    '16': Profile('16', 'iPhone 16', 393, 852, 'island'),
    '16plus': Profile('16plus', 'iPhone 16 Plus', 430, 932, 'island'),
    '16pro': Profile('16pro', 'iPhone 16 Pro', 402, 874, 'island'),
    '16promax': Profile('16promax', 'iPhone 16 Pro Max', 440, 956, 'island'),
    'se': Profile('se', 'iPhone SE / 8', 375, 667, 'home', .035),
    'ipad': Profile('ipad', 'iPad generico', 768, 1024, 'none', .05),
}

# Model identifiers: DeviceKit's device table (see THIRD_PARTY.md).
MODELS = {
    'iPhone15,2': '14pro', 'iPhone15,3': '14promax',
    'iPhone14,7': '14', 'iPhone14,8': '14plus',
    'iPhone14,4': '13mini', 'iPhone14,5': '13',
    'iPhone14,2': '13', 'iPhone14,3': '13promax',
    'iPhone15,4': '15', 'iPhone15,5': '15plus',
    'iPhone16,1': '15pro', 'iPhone16,2': '15promax',
    'iPhone17,3': '16', 'iPhone17,4': '16plus',
    'iPhone17,1': '16pro', 'iPhone17,2': '16promax',
    'iPhone14,6': 'se', 'iPhone12,8': 'se',
    'iPhone10,1': 'se', 'iPhone10,4': 'se',
}


def identify(model: str) -> Profile:
    if model in MODELS:
        return PROFILES[MODELS[model]]
    if model.startswith('iPad'):
        return PROFILES['ipad']
    return PROFILES['generic']


def fit_rect(area_width: int, area_height: int, ratio: float):
    width = min(area_width, int(area_height * ratio))
    height = min(area_height, int(width / ratio))
    return (area_width - width) // 2, (area_height - height) // 2, width, height
