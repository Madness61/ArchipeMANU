"""Blueprint identity is independent of service imports."""
from flask import Blueprint
rounds = Blueprint("mvp", __name__)
