"""Local protocol fixture: never connects to an external Archipelago service."""
import json
import threading


class FakeAP:
    def __init__(self, game="Test World", names=("Host", "Friend"), seed="CONSOLE_TEST", password=""):
        self.game, self.names, self.seed, self.password = game, names, seed, password
        self.packets, self.clients = [], []
        self.commands = []
        self.history = {1:[[501,1001,2,1]],2:[]}
        self.hints = {}
        self.emit_live = True
        self.suppress_empty_receipts = False
        self.announce_joins = False
        self.before_connected = []
        self.accept_connections = True
        self.lock = threading.RLock()
        self.package_requested = threading.Event()
        self.package_gate = threading.Event()
        self.package_gate.set()

    def __enter__(self):
        from websockets.sync.server import serve
        self.server = serve(self.handle, "127.0.0.1", 0)
        self.port = self.server.socket.getsockname()[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        return self

    def __exit__(self, *args):
        self.package_gate.set()
        with self.lock:
            clients = list(self.clients)
        for wire in clients:
            wire.close()
        self.server.shutdown()
        self.thread.join(5)

    def send(self, wire, packets):
        wire.send(json.dumps(packets))

    def broadcast_item(self):
        if not self.emit_live:
            return
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
        if not self.accept_connections:
            wire.close(code=1012, reason="isolated test outage")
            return
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
                        reply=[{"cmd":"Connected","team":0,"slot":slot,"players":players,
                            "slot_info":{str(i):{"name":n,"game":self.game,"type":1,"class":"NetworkSlot"}
                                         for i,n in enumerate(self.names,1)},"missing_locations":[1001,1002],"checked_locations":[1000]}]
                        if self.history.get(slot) or not self.suppress_empty_receipts:
                            reply.append({"cmd":"ReceivedItems","index":0,"items":self.history.get(slot,[])})
                        if self.announce_joins:
                            tags = packet['tags']
                            verb = 'tracking' if 'Tracker' in tags else 'viewing' if 'TextOnly' in tags else 'playing'
                            event = dict(cmd='PrintJSON', type='Join', team=0, slot=slot, tags=tags,
                                         data=[dict(text=f'{name} {verb} has joined.')])
                            with self.lock:
                                recipients = list(self.clients)
                            for recipient in recipients + [wire]:
                                self.send(recipient, [event])
                        if self.before_connected:
                            self.send(wire, self.before_connected)
                        self.send(wire,reply)
                        with self.lock:
                            self.clients.append(wire)
                        self.broadcast_item()
                    elif cmd == "GetDataPackage":
                        self.package_requested.set()
                        self.package_gate.wait(20)
                        self.send(wire,[{"cmd":"DataPackage","data":{"games":{self.game:{
                            "item_name_to_id":{"Progression Key":501,"Potion":502},
                            "location_name_to_id":{"Town":1000,"Old Fortress - Chest":1001,"Deep Cave - Boss":1002}}}}}])
                    elif cmd == "Get":
                        self.send(wire, [dict(cmd='Retrieved', keys={key:self.hints.get(key, []) for key in packet['keys']})])
                    elif cmd == "Say":
                        text = packet["text"]
                        self.commands.append((name,text))
                        if text.startswith("!hint"):
                            self.send(wire,[{"cmd":"PrintJSON","type":"Hint","data":[{"text":f"Privater Hinweis für {name}: Deep Cave - Boss <script>never_execute()</script>"}]}])
                        else:
                            chat=[{"cmd":"PrintJSON","type":"Chat","team":0,"slot":slot,"message":text,
                                   "data":[{"text":str(slot),"type":"player_id"},{"text":f": {text}"}]}]
                            with self.lock:
                                recipients=list(self.clients)
                            for recipient in recipients:
                                try:self.send(recipient,chat)
                                except Exception:pass
                    elif cmd == "Sync":
                        if self.history.get(slot) or not self.suppress_empty_receipts:
                            self.send(wire,[{"cmd":"ReceivedItems","index":0,"items":self.history.get(slot,[])}])
        except Exception:
            pass
        finally:
            with self.lock:
                if wire in self.clients:
                    self.clients.remove(wire)
