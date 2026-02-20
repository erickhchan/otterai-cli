import warnings

# Suppress urllib3 NotOpenSSLWarning on macOS systems using LibreSSL
warnings.filterwarnings("ignore", message=".*urllib3.*OpenSSL.*")
