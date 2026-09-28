"""Compatibility import; FastapiAdmin owns the application factory."""
from app import create_app

app = create_app()
