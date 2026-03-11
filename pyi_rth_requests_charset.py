"""Runtime hook to stabilize Requests charset detection in frozen builds."""

import sys
import types
import warnings


def _install_chardet_shim_from_charset_normalizer():
    """Provide a minimal chardet-compatible shim backed by charset_normalizer."""
    if 'chardet' in sys.modules:
        return

    shim = types.ModuleType('chardet')

    def detect(data):
        payload = data or b''
        try:
            from charset_normalizer import from_bytes

            matches = from_bytes(payload)
            best = matches.best() if matches else None
            if best is not None:
                return {
                    'encoding': getattr(best, 'encoding', None),
                    'confidence': 0.99,
                    'language': getattr(best, 'language', '') or '',
                }
        except Exception:
            pass

        # Last-resort fallback keeps Requests operational in frozen builds.
        return {'encoding': 'utf-8', 'confidence': 0.5, 'language': ''}

    shim.detect = detect
    sys.modules['chardet'] = shim


_install_chardet_shim_from_charset_normalizer()

# Avoid importing requests here; only filter by warning text pattern.
warnings.filterwarnings(
    'ignore',
    message=r'.*Unable to find acceptable character detection dependency.*',
)
