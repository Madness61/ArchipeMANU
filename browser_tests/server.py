"""Ephemeral HTTP server with real Flask routes and mock AP extraction/generation.

This entry point refuses all roots except a marked OS temporary directory. It
never attaches to an existing server, imports an APWorld, or runs ap_runner.py.
"""
import argparse
import hashlib
import json
import logging
import os
from pathlib import Path
import tempfile
import time
import zipfile

from .fixtures import GAME, SLUG, PASSWORD, ROOT_MARKER, schema, world_bytes


def checked_root(path):
    root = Path(path)
    resolved = root.resolve()
    if (not root.is_absolute() or root.is_symlink() or resolved.parent != Path(tempfile.gettempdir()).resolve()
            or not resolved.name.startswith("archipemanu-browser-")
            or not (resolved/".browser-test-root").is_file()
            or (resolved/".browser-test-root").read_text(encoding="utf-8") != ROOT_MARKER):
        raise ValueError("Browser server requires a marked, disposable OS temporary directory.")
    return resolved


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--root",required=True)
    args = parser.parse_args()
    root = checked_root(args.root)
    # Set every runtime path BEFORE importing the application or config module.
    os.environ.update(HUB_DATA=str(root), AP_HOME=str(root/"ap"), AP_SOURCE=str(root/"ap"/"source"),
                      AP_PYTHON=str(root/"ap"/"not-an-executable"), HUB_PASSWORD="",
                      HUB_COOKIE_SECURE="0",HUB_TRUSTED_APWORLDS="1")
    from werkzeug.serving import make_server
    from werkzeug.security import generate_password_hash
    import yaml
    from hub import ap_bridge, config, db, stats, yamlgen
    from hub.app import create_app

    for path in (config.DATA,config.DB_PATH.parent,config.APWORLDS,config.SCHEMAS,config.SESSIONS,config.AP_SOURCE):
        if not path.resolve().is_relative_to(root):
            raise RuntimeError("Test isolation violation")
    config.ensure_dirs()
    config.AP_SOURCE.mkdir(parents=True)
    (config.SCHEMAS/"index.json").write_text(json.dumps({"games":{},"failed":{},"ap_version":"0.6.8"}),encoding="utf-8")
    allowed = {hashlib.sha256(world_bytes(v)).hexdigest():v for v in ("1.0.0","1.1.0")}

    def mock_extract(args,timeout):
        if args[0] != "extract":
            raise RuntimeError("No real Archipelago subprocess is allowed in browser tests")
        out = Path(args[args.index("--out")+1])
        if not out.resolve().is_relative_to(root):
            raise RuntimeError("Extraction path escaped test root")
        out.mkdir(parents=True)
        index = {"games":{},"failed":{},"ap_version":"0.6.8"}
        for file in config.APWORLDS.glob("*.apworld"):
            digest = hashlib.sha256(file.read_bytes()).hexdigest()
            if digest not in allowed:
                return False,"Only the known inert browser-test APWorld is accepted"
            version = allowed[digest]
            (out/f"{SLUG}.json").write_text(json.dumps(schema(version)),encoding="utf-8")
            index["games"][SLUG] = {"game":GAME,"version":version,"custom":True}
        # Exercise the real queued/running status and browser refresh behavior.
        time.sleep(0.25)
        (out/"index.json").write_text(json.dumps(index),encoding="utf-8")
        logging.info("MOCK schema extraction: %s games",len(index["games"]))
        return True,"Mock extraction of known inert APWorld; no Python world code executed."

    def mock_generate(players,out,spoiler,race,expected_worlds=None):
        if not players.resolve().is_relative_to(root) or not out.resolve().is_relative_to(root):
            raise RuntimeError("Generator path escaped test root")
        for module,digest in (expected_worlds or {}).items():
            assert module == SLUG and digest in allowed
            assert hashlib.sha256((config.APWORLDS/f"{module}.apworld").read_bytes()).hexdigest() == digest
        documents = []
        payloads = {}
        for file in sorted(players.glob("*.yaml")):
            payloads[file.name] = file.read_text(encoding="utf-8")
            document = yaml.safe_load(payloads[file.name])
            assert document["game"] == GAME
            assert not yamlgen.validate_values(schema("1.0.0"),document[GAME])
            documents.append(document)
        assert documents
        with (root/"generation_calls.jsonl").open("a",encoding="utf-8") as log:
            log.write(json.dumps({"yamls":payloads,"spoiler":spoiler,"race":race})+"\n")
        slots = [{"id":i,"name":doc["name"],"game":GAME} for i,doc in enumerate(documents,1)]
        placements,details = [],[]
        for slot in slots:
            for offset,(item,kind,recipient) in enumerate([
                ("Key","progression",slot["id"]%len(slots)+1),
                ("Potion","useful",slot["id"]%len(slots)+1),
            ]):
                placements.append((slot["id"],recipient,kind))
                details.append({"finder":slot["id"],"recipient":recipient,"category":kind,
                                "item_id":offset+1,"location_id":slot["id"]*10+offset,
                                "item":item,"location":"Chest" if offset==0 else "Boss"})
        if not race:
            distribution = stats.aggregate_placements(slots,placements)
            (out/"item_distribution.json").write_text(json.dumps(distribution),encoding="utf-8")
            (out/"item_placements.json").write_text(json.dumps({"source":distribution["source"],"placements":details}),encoding="utf-8")
        archive = out/"AP_BROWSER_TEST.zip"
        with zipfile.ZipFile(archive,"w") as z:
            z.writestr("AP_BROWSER_TEST.archipelago",b"Mock seed; not a playable multiworld")
            for name,text in payloads.items():
                z.writestr("configs/"+name,text.encode("utf-8"))
        logging.info("MOCK generated %s with %s slots",archive.name,len(slots))
        return True,"Simulated browser-test generation, no Archipelago worker used.",archive

    ap_bridge._run = mock_extract
    ap_bridge.generate = mock_generate
    # Empty schema cache already exists, so startup cannot launch extraction.
    ap_bridge.ap_ready = lambda: True
    app = create_app()
    with app.app_context():
        db.execute("INSERT INTO users(username,slot_name,is_admin,password_hash) VALUES ('TestAdmin','TestAdmin',1,?)",
                   (generate_password_hash(PASSWORD,method="scrypt"),))
    logging.basicConfig(level=logging.INFO,format="%(asctime)s %(levelname)s %(message)s",force=True)
    server = make_server("127.0.0.1",0,app,threaded=True)
    (root/"ready.json").write_text(json.dumps({"url":f"http://127.0.0.1:{server.server_port}"}),encoding="utf-8")
    logging.info("Isolated browser test server started; all state is disposable")
    try:
        server.serve_forever()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
