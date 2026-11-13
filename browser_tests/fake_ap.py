"""Local protocol fixture: never connects to an external Archipelago service."""
import json
import threading


class FakeAP:
    def __init__(self, game="Test World", names=("Host", "Friend"), seed="CONSOLE_TEST", password=""):
        self.game, self.names, self.seed, self.password = game, names, seed, password
        self.packets, self.clients = [], []
        self.lock = threading.RLock()

    def __enter__(self):
        from websockets.sync.server import serve
        self.server = serve(self.handle, "127.0.0.1", 0)
        self.port = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        with self.lock:
            clients = list(self.clients)
        for wire in clients:
            wire.close()
        self.server.shutdown()
        self.thread.join(5)

    def send(self, wire, packets):
        wire.send(json.dumps(packets))

    def broadcast_item(self):
        payload = [{"cmd":"PrintJSON","type":"ItemSend","receiving":1,
                    "item":{"item":501,"location":1001,"player":2,"flags":1,"class":"NetworkItem"},
                    "data":[]}]
        with self.lock:
            clients = list(self.clients)
        for wire in clients:
            try:
                self.send(wire,payload)
            except Exception:
                pass

    def interrupt(self):
        with self.lock:
            clients = list(self.clients)
        for wire in clients:
            wire.close(code=1012, reason="isolated test restart")

    def handle(self, wire):
        self.send(wire,[{"cmd":"RoomInfo","seed_name":self.seed,"password":bool(self.password),
                         "version":{"major":0,"minor":6,"build":8,"class":"Version"},"games":[self.game]}])
        name = None
        try:
            for frame in wire:
                for packet in json.loads(frame):
                    self.packets.append(packet)
                    cmd = packet["cmd"]
                    if cmd == "Connect":
                        if (packet["password"] or "") != self.password:
                            self.send(wire,[{"cmd":"ConnectionRefused","errors":["InvalidPassword"]}])
                            continue
                        if packet["name"] not in self.names:
                            self.send(wire,[{"cmd":"ConnectionRefused","errors":["InvalidSlot"]}])
                            continue
                        name = packet["name"]
                        slot = self.names.index(name)+1
                        players = [{"team":0,"slot":i,"alias":n,"name":n,"class":"NetworkPlayer"}
                                   for i,n in enumerate(self.names,1)]
                        self.send(wire,[{"cmd":"Connected","team":0,"slot":slot,"players":players,
                            "slot_info":{str(i):{"name":n,"game":self.game,"type":1,"class":"NetworkSlot"}
                                         for i,n in enumerate(self.names,1)},"missing_locations":[1001,1002],"checked_locations":[1000]},
                            {"cmd":"ReceivedItems","index":0,"items":[[501,1001,2,1]]}])
                        with self.lock:
                            self.clients.append(wire)
                        self.broadcast_item()
                    elif cmd == "GetDataPackage":
                        self.send(wire,[{"cmd":"DataPackage","data":{"games":{self.game:{
                            "item_name_to_id":{"Progression Key":501,"Potion":502},
                            "location_name_to_id":{"Town":1000,"Old Fortress - Chest":1001,"Deep Cave - Boss":1002}}}}}])
                    elif cmd == "Say":
                        text = packet["text"]
                        if text.startswith("!hint"):
                            self.send(wire,[{"cmd":"PrintJSON","type":"Hint","data":[{"text":f"Privater Hinweis für {name}: Deep Cave - Boss <script>never_execute()</script>"}]}])
                        else:
                            self.send(wire,[{"cmd":"PrintJSON","type":"Chat","data":[{"text":f"{name}: {text}"}]}])
                    elif cmd == "Sync":
                        self.send(wire,[{"cmd":"ReceivedItems","index":0,"items":[[501,1001,2,1]]}])
        except Exception:
            pass
        finally:
            with self.lock:
                if wire in self.clients:
                    self.clients.remove(wire)
