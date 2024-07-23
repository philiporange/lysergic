try:
    from lysergic import LSD
except ImportError:
    from .lysergic import LSD

__program__ = "lysergic"
__version__ = "0.1.3"

__all__ = ["LSD"]
