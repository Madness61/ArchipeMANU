"""python -m hub [--host 0.0.0.0] [--port 8080]"""
import argparse

from .app import create_app
from .config import APP_NAME


def main() -> None:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--host", default="127.0.0.1", help="0.0.0.0 to make it reachable from other machines")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()

    app = create_app()
    if args.debug:
        app.run(host=args.host, port=args.port, debug=True)
        return
    try:
        from waitress import serve
    except ImportError:
        app.run(host=args.host, port=args.port)
        return
    print(f"{APP_NAME} läuft auf http://{args.host}:{args.port}")
    serve(app, host=args.host, port=args.port, threads=8)


if __name__ == "__main__":
    main()
