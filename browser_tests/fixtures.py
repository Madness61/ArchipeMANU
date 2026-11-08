"""Deterministic, inert archive and schema used only by the isolated test server."""
import io
import json
import zipfile

GAME = "Browser Test World"
SLUG = "browser_test_world"
PASSWORD = "Browser test password 2026!"
ROOT_MARKER = "ArchipeMANU disposable browser test root v1"


def world_bytes(version="1.0.0"):
    stream = io.BytesIO()
    with zipfile.ZipFile(stream,"w",compression=zipfile.ZIP_STORED) as archive:
        for name,text in {
            f"{SLUG}/__init__.py":"# Inert acceptance-test fixture; never imported.\n",
            f"{SLUG}/archipelago.json":json.dumps({"game":GAME,"world_version":version}),
        }.items():
            entry = zipfile.ZipInfo(name,date_time=(2026,1,1,0,0,0))
            archive.writestr(entry,text)
    return stream.getvalue()


def schema(version):
    return {"game":GAME,"slug":SLUG,"version":version,"custom":True,
            "presets":{},"items":["Key","Potion"],"locations":["Chest","Boss"],
            "options":[
                {"key":"goal","name":"Goal","kind":"choice","default":"finish",
                 "choices":[["finish","Finish"],["collect","Collect"]],"simple":True,"group":"Game Options","doc":"Choose a goal."},
                {"key":"difficulty","name":"Difficulty","kind":"range","default":3,"min":1,"max":10,
                 "special":{},"simple":True,"group":"Game Options","doc":"Difficulty from 1 to 10."},
                {"key":"death_link","name":"Death Link","kind":"toggle","default":False,
                 "simple":True,"group":"Game Options","doc":"Share deaths."},
            ]}
