"""Allow service-local and installed cost providers to share this package."""

from pkgutil import extend_path

__path__ = extend_path(__path__, __name__)
