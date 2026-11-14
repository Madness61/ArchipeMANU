"""Editorial game information, separate from APWorld installation state.

Setup summaries refer to the linked upstream documentation for AP 0.6.8.
They never assert that a player's computer or a generator has been configured.
Unknown uploads deliberately receive no guessed genres or requirements.
"""
import json
from pathlib import Path
from urllib.parse import urlsplit
from . import i18n

_EN = json.loads(Path(__file__).with_name('locales').joinpath('games_en.json').read_text(encoding='utf-8'))

SETUP_TYPES = {
    "rom": "Original-ROM / Disc + Emulator oder Port",
    "mod": "PC-Spiel + Mod / Randomizer",
    "client": "Eigenständiger Spielclient",
    "browser": "Im Browser spielbar",
    "unknown": "Einrichtung noch undokumentiert",
}
SUPPORT_STATES = {
    "loaded": "Für Lobby auswählbar",
    "loading": "Aktiv, Optionen fehlen",
    "inactive": "APWorld inaktiv",
}

# Verified generator-side ROM reads in the bundled AP 0.6.8 integrations.
# Other ROM games may create procedure patches without reading the original.
HOST_ROM_REQUIRED = {
    "alttp": "A Link to the Past: japanische Original-ROM, Version 1.0",
    "smw": "Super Mario World: US-Original-ROM (Super Mario World (USA).sfc)",
    "lufia2ac": "Lufia II: Rise of the Sinistrals: US-Original-ROM",
    "mmbn3": "MegaMan Battle Network 3 Blue: US-Original-ROM",
    "yoshisisland": "Yoshi's Island: englische Original-ROM, Version 1.0",
    "oot": "Ocarina of Time: US-Original-ROM, Version 1.0",
    "tloz": "The Legend of Zelda: US-Original-ROM, Version 1.0 PRG0",
    "soe": "Secret of Evermore: US-Original-ROM",
}

# slug | genres | setup | description | required game/version/tools | specific setup
_DATA = """
ahit|Jump ’n’ Run,Adventure|mod|Erkunde bunte 3D-Welten und sammle Zeitstücke mit wechselnden Hut-Fähigkeiten.|Steam-Version von A Hat in Time und Archipelago-Workshop-Mod.|Spielstände sichern, den tcplink-Zweig in Steam wählen und den Workshop-Mod abonnieren. Entwicklerkonsole aktivieren. AHIT-Client aus dem Archipelago Launcher verbinden, danach einen neuen Spielstand starten.
alttp|Action-Adventure|rom|Erkunde Hyrule, löse Dungeons und finde Ausrüstung für Links Abenteuer.|Japanische Version 1.0 von A Link to the Past, Archipelago und ein SNI-kompatibler SNES-Emulator.|Original-ROM am Generator und beim Patchen bereitstellen. Den Slot-Patch mit Archipelago öffnen, die erzeugte ROM starten und Emulator sowie SNI mit dem SNES-Client verbinden.
shorthike|Adventure,Jump ’n’ Run|mod|Wandere, klettere und gleite über eine Insel auf der Suche nach goldenen Federn.|PC-Version von A Short Hike und AShortHike.Randomizer samt Abhängigkeiten.|Den verlinkten Mod Installer gemäß README einrichten und den Randomizer installieren. Bei einem neuen oder fortgesetzten Spiel im Verbindungsfenster Server, Slotname und gegebenenfalls Passwort eintragen.
apquest|Adventure|client|Ein kleines Abenteuer mit Bewegung auf einem Raster und wenigen Checks.|Archipelago mit APQuest-Client; bei älteren Installationen zusätzlich die passende APQuest-APWorld.|APQuest-Client im Archipelago Launcher öffnen. Serveradresse eingeben, verbinden und den Slotnamen der Runde verwenden. Ein separat gekauftes Grundspiel ist nicht nötig.
adventure|Action-Adventure|rom|Finde den verzauberten Kelch und bringe ihn durch Burgen und Drachen zurück.|Adventure als NTSC-ROM, BizHawk und Archipelagos Adventure-Client; Windows oder Linux.|Den erzeugten Slot-Patch öffnen und die Original-ROM auswählen. In BizHawk Hintergrundausführung aktivieren und connector_adventure.lua laden. Emulator und Adventure-Client gemäß Anleitung verbinden.
aquaria|Metroidvania,Action-Adventure|mod|Erkunde als Naija eine Unterwasserwelt mit Gesang, Kämpfen und neuen Formen.|Installiertes Aquaria und Aquaria Randomizer für das eigene Betriebssystem.|Eine Kopie des Aquaria-Spielordners anlegen. Die Randomizer-Dateien dort entpacken und aquaria_randomizer starten. Im Launcher Serveradresse und Slotnamen eintragen; pro Runde eine eigene Kopie verwenden.
blasphemous|Metroidvania,Action|mod|Durchquere Cvstodia mit anspruchsvollen Kämpfen und verschachtelten Gebieten.|PC-Version von Blasphemous, Mod Installer und Multiworld-Mod.|Über den verlinkten Mod Installer den Multiworld-Mod und seine Abhängigkeiten installieren. Je nach YAML zusätzlich Double Jump oder Boots of Pleading installieren. Spielstand auswählen und im Mod-Menü verbinden.
bomb_rush_cyberfunk|Action,Jump ’n’ Run|mod|Fahre, grinde und sprühe Graffiti, um die Stadtviertel zu erobern.|Bomb Rush Cyberfunk und BRC Archipelago mit BepInEx 5 und ModLocalizer.|Den Archipelago-Mod mit r2modman installieren oder die in der Anleitung beschriebenen Abhängigkeiten manuell einrichten. Das Spiel mit aktiviertem Mod starten und die Verbindungsdaten im Mod konfigurieren.
borderlands2|Shooter,Rollenspiel|mod|Ein Loot-Shooter mit Quests, Charakterfähigkeiten und zufällig verteilter Ausrüstung.|Borderlands 2 für PC, BL2 Python SDK Mod Manager, coroutines, BouncyLootGod und dieselbe APWorld-Version wie beim Host.|Charaktere sichern. SDK und coroutines installieren, BouncyLootGod.sdkmod in sdk_mods ablegen und die passende APWorld lokal installieren. Zuerst den Borderlands-2-Client verbinden, dann das Spiel mit Mod starten. Nicht vorhandene DLCs in der YAML ausschließen.
bumpstik|Puzzle,Arcade|client|Schieße farbige Spielsteine auf ein Raster und bilde Dreierreihen und Ketten.|Die Archipelago-Ausgabe von Bumper Stickers; als Download oder im Browser verfügbar.|Spiel herunterladen und entpacken oder die verlinkte Browserfassung öffnen. Archipelago Mode auswählen, die Serverdaten eintragen und Start drücken.
cvcotm|Metroidvania,Action|rom|Erkunde Draculas Schloss mit Peitsche und kombinierbaren magischen Karten.|US-ROM von Castlevania: Circle of the Moon, BizHawk ab 2.7 und Archipelago.|Den .apcvcotm-Slot-Patch mit Archipelago auf die US-ROM anwenden. Die erzeugte GBA-ROM in BizHawk starten und den BizHawk-Client samt Lua-Verbindung einrichten. Die Wii-U-VC-ROM ist inkompatibel; die Advance-Collection-ROM hat laut Anleitung kein Audio.
cv64|Action-Adventure,Jump ’n’ Run|rom|Ein dreidimensionales Castlevania mit Kämpfen, Fallen und Erkundung.|US-Version 1.0 von Castlevania 64, BizHawk ab 2.7 und Archipelago.|Den Slot-Patch auf die Original-ROM anwenden und in BizHawk laden. Für Spielstände Controller 1 auf Memory Card stellen und den Emulator neu starten. Den BizHawk-Client mit dem Emulator und der Runde verbinden.
celeste_open_world|Jump ’n’ Run|mod|Erklimme den Berg in einer offenen Variante, in der Bewegungsmechaniken freigeschaltet werden.|PC-Version von Celeste, Olympus/Everest und der Celeste Open World Archipelago-Mod.|Olympus installieren und damit Everest für Celeste einrichten. Den Open-World-Mod samt Abhängigkeiten installieren. Das Spiel über Everest starten und die Verbindung nach der Mod-Anleitung konfigurieren.
celeste64|Jump ’n’ Run|client|Sammle Erdbeeren und erkunde einen kompakten dreidimensionalen Berg.|Die spezielle Archipelago-Ausgabe von Celeste 64.|Archipelago-Build herunterladen und entpacken. In AP.json Url, SlotName und gegebenenfalls Password eintragen. Anschließend Celeste64 starten; unter Linux/Steam Deck den in der Anleitung beschriebenen Proton-Weg verwenden.
checksfinder|Puzzle|browser|Löse Minenfelder, sammle Checks und erweitere deine Möglichkeiten.|ChecksFinder als Browserfassung oder heruntergeladener Spielclient.|Browserfassung öffnen oder Download entpacken. Play Online wählen, im Konsolenfenster Server, Port und Slotnamen eintragen und Connect drücken; danach zum Spielfenster wechseln.
cccharles|Horror,Action-Adventure|mod|Erkunde mit einem aufrüstbaren Zug eine Insel und entkomme einem Monster.|Choo-Choo Charles für Windows, Archipelago und CCCharles Random Mod.|CCCharles_Random herunterladen und den Obscure-Ordner gemäß Setup-Anleitung in die Spielinstallation kopieren. Den passenden Client installieren und die dort beschriebenen Schritte zum Verbinden ausführen.
civ_6|Strategie,Rundenstrategie|mod|Entwickle eine Zivilisation durch Forschung, Kultur und Eroberung.|Civilization VI unter Windows mit Rise & Fall und Gathering Storm, Archipelago und Civ VI AP Mod.|Den Mod in den Civ-VI-Mods-Ordner kopieren und beide Erweiterungen sowie den Mod aktivieren. Den Civ-VI-Client einrichten und nach Anleitung mit einer neuen Partie verbinden. Ohne beide Erweiterungen funktioniert diese Integration nicht.
dlcquest|Jump ’n’ Run,Adventure|mod|Eine satirische Plattformwelt, in der selbst grundlegende Fähigkeiten freigeschaltet werden.|DLCQuest für PC und DLCQuestipelago mit BepInEx; der vollständige Installer enthält den Modloader.|DLCQuestipelagoInstaller aus dem Mod-Release ausführen und den Spielpfad auswählen. In der modifizierten Installation ArchipelagoConnectionInfo.json mit Server, Port und Slotnamen befüllen. Danach über BepInEx.NET.Framework.Launcher oder die erzeugte Verknüpfung starten.
doom_1993|Shooter|mod|Kämpfe dich durch die klassischen DOOM-Episoden und finde Schlüssel und Waffen.|DOOM mit eigener DOOM.WAD und Archipelago Crispy DOOM (APDOOM).|APDOOM herunterladen, entpacken und DOOM.WAD aus der Spielinstallation hineinkopieren. apdoom-launcher starten, DOOM auswählen und mit Serveradresse, Slotname und optionalem Passwort verbinden.
doom_ii|Shooter|mod|Klassischer Ego-Shooter mit Dämonen, Schlüsselrätseln und großen Levels.|DOOM II mit eigener DOOM2.WAD und Archipelago Crispy DOOM (APDOOM).|APDOOM herunterladen, entpacken und DOOM2.WAD aus der Spielinstallation hineinkopieren. apdoom-launcher starten, DOOM II auswählen und mit den Daten der Runde verbinden.
dark_souls_3|Action,Rollenspiel|mod|Kämpfe dich durch Lothric und entwickle einen Charakter mit wechselnder Ausrüstung.|Dark Souls III für PC und der DS3 Archipelago Client in einer zur Integration passenden Version.|Client separat entpacken. Einmal pro Multiworld im enthaltenen DS3Randomizer die Server- und Slotdaten laden und die lokalen Randomizer-Daten erstellen. Danach das Spiel über den in der Client-Anleitung genannten Weg starten; Spiel- und Clientversion abgleichen.
earthbound|Rollenspiel|rom|Begleite Ness und seine Freunde durch eine skurrile Welt mit rundenbasierten Kämpfen.|Englische EarthBound-ROM, Archipelago und ein SNI-kompatibler SNES-Emulator.|ROM am Generator beziehungsweise beim Patchen bereitstellen. Den Slot-Patch mit Archipelago öffnen, die erzeugte ROM starten und SNES-Client sowie SNI verbinden. Emulator-Konfiguration der Anleitung beachten.
factorio|Automation,Aufbau,Strategie|mod|Baue Fabriken, automatisiere Forschung und erweitere deine Produktionsketten.|Factorio auf Spieler- und Factorio-Host-Rechner sowie Archipelago für den Host; eine zusätzliche Spielinstallation wird empfohlen.|Den Factorio-Pfad für Archipelago konfigurieren. Die generierten Mod-/Spieldaten der Runde mit dem Factorio-Client laden und einen Factorio-Server starten oder einem solchen beitreten. Der Factorio-Server ist zusätzlich zum Multiworld-Server erforderlich.
faxanadu|Action-Rollenspiel,Jump ’n’ Run|rom|Erkunde den Weltenbaum, bekämpfe Monster und finde neue Ausrüstung.|Englische Faxanadu-ROM und der Daxanadu-Spielclient.|Daxanadu herunterladen und Faxanadu (U).nes in den entpackten Ordner legen. Daxanadu starten, ARCHIPELAGO öffnen, Server und Slotnamen eingeben und PLAY wählen.
ff1|Rollenspiel|rom|Ein klassisches Gruppen-Rollenspiel mit rundenbasierten Kämpfen und Kristallquest.|Final Fantasy als US-NES-ROM, BizHawk, Archipelago und der externe Final Fantasy Randomizer.|Die Archipelago-YAML und randomisierte ROM über den Final Fantasy Randomizer gemäß Anleitung erzeugen. Diese spezielle YAML für die Runde verwenden. ROM in BizHawk laden und den BizHawk-Client verbinden; ein gewöhnliches leeres Standardprofil ersetzt diesen Export nicht.
ffmq|Rollenspiel|rom|Ein zugängliches Rollenspiel mit Erkundung und rundenbasierten Kämpfen.|Final Fantasy Mystic Quest als nordamerikanische ROM 1.0 oder 1.1, Archipelago und SNI-kompatibler SNES-Emulator.|Den erzeugten Slot-Patch mit Archipelago auf die passende Original-ROM anwenden. Randomisierte ROM laden, den SNES-Client starten und SNI nach Anleitung verbinden.
gl|Action-Rollenspiel|rom|Ein Dungeon-Abenteuer mit Kämpfen, Beute und freischaltbaren Gebieten.|Gauntlet Legends als US-N64-ROM, RetroArch mit Mupen64Plus-Next und Archipelagos Gauntlet-Legends-Client.|Die .apgl-Datei mit Archipelago öffnen und patchen. In RetroArch Network Commands aktivieren, die ROM mit Mupen64Plus-Next laden und den Gauntlet-Legends-Client verbinden. Der Generator benötigt laut Anleitung keine ROM.
heretic|Shooter|mod|Ein Fantasy-Ego-Shooter mit magischen Waffen, Schlüsseln und Monstern.|Heretic mit eigener HERETIC.WAD und Archipelago Crispy DOOM (APDOOM).|APDOOM entpacken, HERETIC.WAD aus dem eigenen Spielordner hineinkopieren und apdoom-launcher starten. Heretic auswählen und mit Serveradresse sowie Slotnamen verbinden.
hk|Metroidvania,Action-Adventure|mod|Erkunde Hallownest mit präzisen Kämpfen und neuen Bewegungsfähigkeiten.|PC-Version von Hollow Knight und der Lumafly Mod Manager.|Lumafly installieren, die Spielinstallation auswählen und Archipelago samt Abhängigkeiten installieren. Das Spiel mit Mod starten und die Runde im Archipelago-Menü verbinden. Diese Integration verwendet Lumafly statt BepInEx.
hylics2|Rollenspiel|mod|Ein surreal gestaltetes Rollenspiel mit Erkundung und rundenbasierten Kämpfen.|Hylics 2, BepInEx 5 in 32 Bit und ArchipelagoHylics2.|BepInEx einrichten, Spiel einmal starten und den Mod in BepInEx/plugins entpacken. Im Spiel über die Konsole /connect mit Server und Slotnamen verbinden, bevor du Checks sammelst.
inscryption|Kartenspiel,Roguelike,Horror|mod|Verbinde Kartenkämpfe mit Rätseln und wechselnden Spielwelten.|Inscryption und ArchipelagoMod mit den passenden BepInEx-Abhängigkeiten.|Spielstand sichern. Über r2modman/Thunderstore ein Profil mit ArchipelagoMod und Abhängigkeiten anlegen. Das Spiel modifiziert starten und im Archipelago-Menü verbinden; nicht getestete Zusatzmods vermeiden.
jakanddaxter|Jump ’n’ Run,Adventure|rom|Sammle Energiezellen und erkunde die offene Welt mit Jak und Daxter.|Eigene Kopie von Jak and Daxter: The Precursor Legacy, OpenGOAL Launcher und ArchipelaGOAL.|Zunächst das Originalspiel in OpenGOAL einrichten. Danach ArchipelaGOAL über die Mod-Funktion installieren. Die Archipelago-Partie über den Jak-and-Daxter-Client starten, wie in der Anleitung beschrieben.
kh1|Action-Rollenspiel|mod|Erkunde Disney-Welten mit Sora und finde Schlüsselschwerter und Fähigkeiten.|Kingdom Hearts HD 1.5+2.5 ReMIX für Steam/Epic, OpenKH, KH1FM Randomizer und Archipelago.|Spiel einmal starten und Originaldateien prüfen. OpenKH mit Panacea und Lua-Backend einrichten. Die erzeugte KH1-ZIP mit mod_generator aus dem KH1FM Randomizer verarbeiten und den Mod im Spiel laden. Den KH1-Client verbinden.
kh2|Action-Rollenspiel|mod|Reise durch Disney-Welten und erweitere Soras Kampf- und Bewegungsmöglichkeiten.|Kingdom Hearts II Final Mix für Steam/Epic, OpenKH mit Panacea und Lua-Backend, Archipelago.|Die verlinkte OpenKH-Anleitung befolgen und GoA-ROM-Edition, APCompanion sowie KH2-ArchipelagoEnablers installieren. Den Slot-Patch nach der Setup-Anleitung laden und den KH2-Client verbinden. Kompatible Mod- und Spielversionen beachten.
kdl3|Jump ’n’ Run|rom|Erkunde mit Kirby und seinen Tierfreunden fantasievolle zweidimensionale Levels.|Kirby's Dream Land 3 als US- oder japanische ROM, Archipelago und SNI-kompatibler Emulator mit ROM-Zugriff.|Slot-Patch mit Archipelago anwenden und die ROM im kompatiblen Emulator starten. SNI und SNES-Client verbinden. RetroArch wird für diese Integration laut Anleitung nicht unterstützt.
landstalker|Action-Rollenspiel,Adventure|rom|Ein isometrisches Schatzsucher-Abenteuer mit Kämpfen und Sprungrätseln.|Landstalker als US-ROM, Landstalker Archipelago Client für Windows und Genesis-Plus-GX-Emulator.|ROM in den Ordner des entpackten Clients legen und randstalker_archipelago starten. RetroArch oder BizHawk mit dem Genesis-Plus-GX-Core nach Anleitung konfigurieren und Client sowie Runde verbinden.
lingo|Puzzle|mod|Löse sprachbasierte Rätsel in einer vernetzten dreidimensionalen Welt.|Lingo für PC und der Lingo Archipelago Randomizer.|Workshop-Mod abonnieren oder den Randomizer manuell installieren. Im Spiel Settings → Level → Archipelago wählen, ein neues Spiel beginnen und im Verbindungsformular Server- und Slotdaten eingeben.
ladx|Action-Adventure|rom|Erkunde Koholint, löse Dungeons und sammle Instrumente.|Link's Awakening DX als amerikanische ROM 1.0, Archipelago sowie BizHawk oder RetroArch gemäß Anleitung.|Den Slot-Patch mit Archipelago öffnen und die Original-ROM auswählen. Die erzeugte GBC-ROM im Emulator laden und den spielbezogenen Client samt Emulator-Verbindung nach Anleitung starten.
lufia2ac|Rollenspiel,Roguelike|rom|Durchquere die zufällig aufgebaute Ahnenhöhle mit einer Rollenspielgruppe.|US-ROM von Lufia II: Rise of the Sinistrals, Archipelago und SNI-kompatibler SNES-Emulator.|Original-ROM für Generierung/Patchen bereitstellen, den erzeugten Slot-Patch öffnen und die ROM starten. Den SNES-Client und SNI verbinden; nicht unterstützte SNES-Mini-Konfigurationen vermeiden.
mlss|Rollenspiel|rom|Ein humorvolles Mario-Rollenspiel mit rundenbasierten Kämpfen und Timing-Aktionen.|US-ROM von Mario & Luigi: Superstar Saga, BizHawk und Archipelagos BizHawk-Client.|Den erzeugten Slot-Patch öffnen, auf die eigene ROM anwenden und die GBA-ROM in BizHawk laden. Den BizHawk-Client mit dem Lua-Connector und den Daten der Runde verbinden.
mm2|Action,Jump ’n’ Run|rom|Besiege Robot Master und nutze ihre Waffen in klassischen Plattformlevels.|Englische Mega-Man-2-ROM oder Mega Man Legacy Collection, BizHawk und Archipelago.|Slot-Patch mit Archipelago öffnen und die ROM beziehungsweise unterstützte Collection-Dateien bereitstellen. Die erzeugte NES-ROM in BizHawk starten und den BizHawk-Client verbinden.
mm3|Action,Jump ’n’ Run|rom|Durchquere Plattformlevels und schalte neue Waffen und Bewegungsmöglichkeiten frei.|Englische Mega-Man-3-ROM oder Mega Man Legacy Collection, BizHawk und Archipelago.|Slot-Patch mit Archipelago öffnen und die Originaldaten auswählen. Die erzeugte NES-ROM in BizHawk starten und den BizHawk-Client samt Lua-Verbindung einrichten.
mmbn3|Rollenspiel,Action|rom|Sammle Battle Chips und kämpfe auf taktischen Echtzeit-Rastern.|US-ROM von MegaMan Battle Network 3 Blue, BizHawk und Archipelago.|Die Blue-ROM bereitstellen; die Anleitung beschreibt auch den Export aus der Legacy Collection Vol. 1. Den Slot-Patch anwenden, die erzeugte GBA-ROM in BizHawk laden und den spielbezogenen Client verbinden.
meritous|Action,Adventure|client|Erkunde einen großen Dungeon und bekämpfe Gegner mit aufgeladenen PSI-Angriffen.|Die eigenständige Archipelago-Ausgabe Meritous Gaiden.|Spiel herunterladen und in einen beschreibbaren Ordner entpacken. In meritous-ap.json ap-enable aktivieren sowie server, port und slotname setzen. meritous starten und eine neue Partie beginnen.
musedash|Rhythmus,Action|mod|Laufe und kämpfe im Takt der Musik auf wechselnden Songs.|Muse Dash für Windows, MelonLoader, passende .NET-Laufzeiten und der Muse-Dash-Archipelago-Mod.|MelonLoader für MuseDash.exe installieren und die Mod-Dateien entsprechend der Anleitung ablegen. Das Spiel mit Mod starten und den Slot verbinden. Muse Plus ist optional; die YAML auf die verfügbaren Songs abstimmen.
noita|Roguelike,Action|mod|Erkunde eine physikalisch simulierte Welt voller Zauber, Gefahren und Geheimnisse.|Noita für PC und NoitaArchipelago.|Mod nach mods/archipelago entpacken. Im Mod-Menü Unsafe mods erlauben und Archipelago aktivieren. Server und Slot im Mod einrichten und für die Runde eine neue Partie starten.
oot|Action-Adventure|rom|Erkunde Hyrule als junger und erwachsener Link und löse verzweigte Dungeons.|US-ROM 1.0 von Ocarina of Time, BizHawk ab 2.10 und Archipelago.|Die .apz5-Datei mit Archipelago auf die Original-ROM anwenden. Die erzeugte ROM in BizHawk laden, Hintergrundausführung aktivieren und den OoT-Client mit dem Lua-Connector verbinden.
osrs|Rollenspiel,MMORPG|mod|Erledige Aufgaben und trainiere Fähigkeiten in einer regionsgebundenen RuneScape-Welt.|RuneLite, ein Old-School-RuneScape-Konto und gegebenenfalls der Jagex Launcher.|Im RuneLite Plugin Hub Archipelago und Region Locker installieren. Die benötigten Region-Locker-Einstellungen laut Anleitung setzen, dann das Archipelago-Plugin mit Server und Slot verbinden. Konto und verfügbare Inhalte auf die YAML abstimmen.
overcooked2|Simulation,Koop,Action|mod|Koche unter Zeitdruck in wechselnden Küchen und schalte neue Levels frei.|Overcooked! 2 für Windows und OC2-Modding; Steam empfohlen, Epic unterstützt.|OC2-Modding gemäß Anleitung installieren und das Spiel modifiziert starten. Im Login-Menü die Runde verbinden; die Spieldaten werden vom Mod geladen. Konsolen- und Windows-Store-Versionen sind laut Anleitung nicht kompatibel.
paint|Puzzle,Kreativ|browser|Schalte Malwerkzeuge und Bildfläche frei und zeichne ein vorgegebenes Zielbild.|Ein Browser und die Archipelago-Paint-Webseite.|Die verlinkte Paint-Webseite öffnen und Server, Slotname und optionales Passwort eingeben. Mit Connect verbinden. Für spätere Fortsetzung die vollständige URL einschließlich Hash speichern.
pokemon_emerald|Rollenspiel|rom|Fange Pokémon und erkunde Hoenn mit rundenbasierten Kämpfen.|Englische Pokémon-Emerald-ROM, BizHawk ab 2.7 und Archipelago.|Slot-Patch mit Archipelago auf die eigene englische ROM anwenden. Die erzeugte GBA-ROM in BizHawk laden und den BizHawk-Client samt Lua-Verbindung einrichten.
pokemon_rb|Rollenspiel|rom|Erkunde Kanto, fange Pokémon und besiege die Pokémon-Liga.|Passende Pokémon-Red- beziehungsweise Blue-ROM, BizHawk und Archipelago.|Die in der YAML gewählte Edition als Original-ROM bereitstellen. Den Slot-Patch öffnen, die erzeugte ROM in BizHawk starten und den Pokémon-Client mit Lua-Connector und Server verbinden.
raft|Survival,Aufbau,Adventure|mod|Baue ein Floß aus und erkunde Inseln in einer überschwemmten Welt.|Raft, Raft Mod Loader, Raftipelago und ModUtils in zueinander passenden Versionen.|Die dokumentierte Raft-Version verwenden; die vorliegende Anleitung nennt den Steam-Zweig 1.09_precrossplayupdate. RML installieren, Raftipelago und ModUtils aktivieren und das Spiel über RML starten. Im Mod die Runde verbinden.
ror2|Shooter,Roguelike,Action|mod|Überstehe Gegnerwellen und kombiniere immer stärkere Gegenstände.|Risk of Rain 2 und der Archipelago-Mod samt Abhängigkeiten.|Mit r2modman ein Spielprofil erstellen und den Archipelago-Mod installieren. Über Start modded starten und die Verbindung nach der Mod-Anleitung konfigurieren. Mitspieler im selben Spiel benötigen kompatible Mods.
smz3|Metroidvania,Action-Adventure|rom|Ein Crossover aus Super Metroid und A Link to the Past mit Übergängen zwischen beiden Welten.|Super-Metroid-ROM und japanische Zelda-3-ROM 1.0, Archipelago und SNI-kompatibler SNES-Emulator.|Beide Original-ROMs bereitstellen und den erzeugten SMZ3-Slot-Patch mit Archipelago öffnen. Die kombinierte ROM starten und SNES-Client sowie SNI mit der Runde verbinden.
satisfactory|Automation,Aufbau|mod|Baue weitläufige Fabriken und optimiere Förderbänder und Produktionsketten.|Satisfactory für Steam/Epic und Satisfactory Mod Manager.|Im Mod Manager den Archipelago-Mod in einer zur APWorld passenden Version installieren. Das Spiel mit aktiviertem Mod starten und die Serverdaten im Mod eintragen. Der Mod verbindet direkt; ein separater Archipelago-Spielclient ist nicht nötig.
saving_princess|Metroidvania,Action|mod|Erkunde eine Raumstation mit Schusswaffen und neuen Bewegungsfähigkeiten.|Saving Princess von itch.io und Archipelago mit Saving Princess Client.|Spiel herunterladen, dann Saving Princess Client im Archipelago Launcher starten und den Installationsdialogen folgen. Auch spätere Starts über diesen Client ausführen. Unter Linux die in der Anleitung genannten Wine-/7z-Voraussetzungen beachten.
soe|Action-Rollenspiel|rom|Reise mit einem Jungen und seinem Hund durch verschiedene Zeitalter.|US-ROM von Secret of Evermore, SNI-kompatibler SNES-Emulator und der in der Anleitung verlinkte Client.|Den erzeugten Slot-Patch auf die eigene ROM anwenden. Die ROM im Emulator starten, SNI einrichten und den Web- oder SNES-Client gemäß Anleitung mit der Runde verbinden.
shivers|Puzzle,Adventure,Horror|mod|Erkunde ein verlassenes Museum und löse Rätsel, um Geister einzufangen.|Shivers als GOG- oder Disc-Version, ScummVM ab 2.7 und Shivers Randomizer Client.|Die Spieldateien in ScummVM als Spiel hinzufügen. Den Randomizer-Client installieren und anhand der Setup-Anleitung mit ScummVM und dem Slot verbinden; keine SNES-ROM oder Emulator-Patchdatei verwenden.
sa2b|Jump ’n’ Run,Action|mod|Spiele rasante Levels und schalte Embleme, Fähigkeiten und Chao-Inhalte frei.|Sonic Adventure 2 für Steam, SA Mod Manager, .NET Desktop Runtime und SA2B Archipelago Mod.|Den Mod im SA Mod Manager installieren und aktivieren. Configure Mod öffnen und die Server- und Slotdaten setzen; über den Mod Manager starten. Für Chao-Karate-Checks wird das Battle-DLC benötigt.
sc2|Strategie,Echtzeitstrategie|mod|Spiele Kampagnenmissionen und schalte Einheiten und Verbesserungen frei.|StarCraft II, Archipelago mit Starcraft2-Client und passende Kampagneninhalte.|Starcraft2-Client starten und mit /download_data die benötigten Maps und Daten installieren. Danach die Runde verbinden und Missionen aus dem Client starten. Nicht vorhandene Kampagnen in der YAML ausschließen.
stardew_valley|Simulation,Aufbau,Rollenspiel|mod|Entwickle eine Farm, erkunde Minen und baue Beziehungen im Dorf auf.|Stardew Valley 1.6 für PC, SMAPI und eine zur APWorld passende StardewArchipelago-Version.|SMAPI installieren und StardewArchipelago in den Mods-Ordner entpacken. Über SMAPI starten und einen Archipelago-Spielstand mit den Verbindungsdaten der Runde anlegen. Die Mod-Hauptversion muss zum Generator passen; nicht mitten in einer Runde aktualisieren.
subnautica|Survival,Adventure|mod|Erkunde einen außerirdischen Ozean, baue Basen und entdecke neue Tiefen.|Subnautica für PC und der Subnautica-Archipelago-Mod.|Das Mod-Archiv in den Spielordner entpacken, sodass Subnautica/BepInEx existiert. Spiel starten und im Verbindungsformular des Hauptmenüs Server, PlayerName und gegebenenfalls Passwort eintragen. Linux-Startparameter stehen in der Anleitung.
sm64ex|Jump ’n’ Run|rom|Erkunde Peachs Schloss und sammle Sterne in dreidimensionalen Welten.|Eigene Super-Mario-64-ROM und der spezielle SM64AP-Launcher beziehungsweise Archipelago-sm64ex-Port.|SM64AP-Launcher samt plattformspezifischen Build-Werkzeugen einrichten und die passende Original-ROM bereitstellen. Den Archipelago-Port erstellen/starten und gemäß Anleitung verbinden. Ein beliebiger anderer SM64-Port ersetzt diese Integration nicht.
marioland2|Jump ’n’ Run|rom|Sammle sechs goldene Münzen und durchquere Marios zweidimensionale Welt.|Super Mario Land 2: 6 Golden Coins als ROM 1.0, BizHawk und Archipelago.|Slot-Patch mit Archipelago auf die eigene ROM anwenden und im Emulator laden. AutoSaveRAM und Hintergrundausführung in BizHawk aktivieren und den spielbezogenen Client samt Lua-Connector verbinden.
smw|Jump ’n’ Run|rom|Erkunde Dinosaur Land mit Mario und Yoshi und finde Ausgänge und Fähigkeiten.|Super Mario World (USA).sfc als eigene Original-ROM, Archipelago und ein SNI-kompatibler SNES-Emulator.|Der Host muss die US-ROM vor der Generierung auf dem Generator-Rechner einrichten. Spieler öffnen anschließend ihre .apsmw-Datei mit Archipelago und wählen ihre eigene ROM. Die erzeugte .sfc im Emulator starten, SNI/Lua-Connector einrichten und den SNES-Client verbinden.
sm|Metroidvania,Action|rom|Erkunde Zebes und erschließe mit Samus neue Wege durch Ausrüstung und Fähigkeiten.|Super Metroid als Japan/USA-ROM, Archipelago und SNI-kompatibler SNES-Emulator.|Original-ROM für Generierung/Patchen bereitstellen. Slot-Patch mit Archipelago anwenden, die erzeugte ROM starten und SNI sowie SNES-Client mit der Runde verbinden.
tunic|Action-Adventure,Puzzle|mod|Erkunde als kleiner Fuchs eine rätselhafte Welt und entdecke ihre Regeln.|TUNIC für PC und TUNIC Randomizer mit der ausdrücklich geforderten BepInEx-IL2CPP-Version.|Die in der Anleitung genannte BepInEx-Version installieren und den Randomizer in den Spielordner entpacken. Das Spiel mit Mod starten und im Randomizer die Archipelago-Verbindung konfigurieren. Versionen von Mod, Loader und APWorld abgleichen.
terraria|Sandbox,Survival,Action|mod|Baue, erkunde und bekämpfe Bosse in einer zweidimensionalen Sandbox.|Terraria für Steam, tModLoader und der Archipelago-Workshop-Mod.|Den Mod abonnieren, tModLoader starten und unter Workshop → Manage Mods aktivieren. Nach dem Neuladen eine passende Partie einrichten und gemäß Mod-Anleitung verbinden. Andere Mods dürfen die benötigte Progression nicht verändern.
tloz|Action-Adventure|rom|Erkunde das ursprüngliche Hyrule und sammle die Triforce-Fragmente.|The Legend of Zelda als US-ROM 1.0 PRG0, BizHawk und Archipelagos Zelda1Client.|Den erzeugten Slot-Patch mit Archipelago auf die Original-ROM anwenden und in BizHawk starten. Den in der Anleitung angegebenen Lua-Connector laden und Zelda1Client mit der Runde verbinden.
messenger|Metroidvania,Jump ’n’ Run,Action|mod|Ein Ninja-Abenteuer zwischen zwei Zeitaltern mit präzisen Plattformpassagen.|The Messenger für PC und Archipelago mit The-Messenger-Integration.|Im Archipelago Launcher The Messenger wählen und die Installation von Courier und Randomizer durchführen lassen. Auch später darüber starten, um kompatible Mod-Dateien zu laden, und die Verbindung im Randomizer einrichten.
tww|Action-Adventure|rom|Segle mit Link über das Meer und löse Dungeons auf zahlreichen Inseln.|Eigene nordamerikanische GameCube-ISO von The Wind Waker, Dolphin und der spezielle TWW AP Randomizer.|Den Archipelago-Build des Randomizers installieren, die eigene ISO wählen und die erzeugten Slotdaten nach Anleitung verarbeiten. Das randomisierte Spiel in Dolphin starten und mit dem TWW-Client verbinden. Der normale Standalone-Randomizer ist ein anderer Build.
witness|Puzzle|mod|Erkunde eine Insel mit Linienrätseln und entdecke gemeinsame Regeln.|The Witness für 64-Bit-Windows und The Witness Archipelago Randomizer.|Das Spiel mit einem frischen Spielstand starten. Danach den Randomizer öffnen, Server und Slot eingeben und Connect wählen. Zum Fortsetzen denselben Spielstand verwenden.
timespinner|Metroidvania,Action-Rollenspiel|mod|Reise durch die Zeit und erschließe eine zweidimensionale Welt mit neuen Fähigkeiten.|Timespinner für Steam, GOG oder Humble und TsRandomizer für das eigene Betriebssystem.|TsRandomizer in den Spielordner entpacken und anstelle des normalen Spiels starten. Die Archipelago-Verbindung im Randomizer einrichten; nicht unterstützte Konsolenfassungen funktionieren dafür nicht.
undertale|Rollenspiel|mod|Ein Rollenspiel mit dialogbasierten Entscheidungen und ausweichbasierten Kämpfen.|Undertale für Steam und Archipelago mit Undertale-Client.|Im Undertale-Client /auto_patch mit dem Pfad der Spielinstallation ausführen. Dadurch entsteht eine separate Archipelago-Spielkopie. Diese für die Runde starten und den Client verbinden; nach Archipelago-Updates kann erneutes Patchen nötig sein.
v6|Jump ’n’ Run,Puzzle|mod|Wechsle die Schwerkraftrichtung, um gefährliche Plattformräume zu durchqueren.|VVVVVV für Steam/GOG und der spezielle V6AP-Build.|V6AP in den Spielordner entpacken. Die Startparameter -v6ap_name für den Slotnamen und -v6ap_ip für Server:Port setzen; falls nötig -v6ap_passwd ergänzen. Das Spiel über diese Konfiguration starten.
wargroove|Strategie,Rundenstrategie|mod|Führe Einheiten über taktische Schlachtfelder und erobere gegnerische Festungen.|Wargroove für Steam unter Windows/Linux mit Double Trouble DLC und Archipelago mit Wargroove-Client.|Spielstände sichern und den Wargroove-Spielpfad unter wargroove_options/root_directory in der Archipelago-Konfiguration hinterlegen. Den Wargroove-Client starten und dessen Installations- und Verbindungsanweisungen folgen; unter Linux den AppData-Pfad nach Anleitung wählen.
yachtdice|Würfelspiel,Strategie|browser|Kombiniere Würfelergebnisse zu Wertungen und schalte neue Möglichkeiten frei.|Ein Browser und die Yacht-Dice-Archipelago-Webseite.|Yacht Dice öffnen, Archipelago auswählen und Server sowie Slotnamen eingeben. Alternativ Website.zip aus den Releases lokal entpacken und index.html öffnen. Solo play erlaubt einen Versuch ohne Multiworld.
yoshisisland|Jump ’n’ Run|rom|Trage Baby Mario mit Yoshi durch Levels voller Eierwürfe und Sammelobjekte.|Englische Yoshi's-Island-ROM 1.0, Archipelago und ein laut Anleitung kompatibler SNI-Emulator.|Original-ROM für Generierung/Patchen bereitstellen und den Slot-Patch anwenden. Die ROM im unterstützten Emulator starten und SNI sowie SNES-Client verbinden. RetroArch und FXPak Pro sind laut vorliegender Anleitung nicht unterstützt.
yugioh06|Kartenspiel,Strategie|rom|Baue Decks und bestreite Duelle mit den Regeln des Kartenspiels.|US- oder europäische ROM von Yu-Gi-Oh! Ultimate Masters 2006, BizHawk und Archipelago.|Den Slot-Patch mit Archipelago auf die passende Original-ROM anwenden. Die GBA-ROM in BizHawk starten und den spielbezogenen Client mit Lua-Connector und Server verbinden.
zillion|Metroidvania,Action|rom|Infiltriere eine Basis, sammle Ausrüstung und befreie Teammitglieder.|Zillion als UE-ROM für Master System, RetroArch und Archipelago.|Slot-Patch auf die eigene ROM anwenden. RetroArch mit SMS Plus GX oder Genesis Plus GX einrichten und Network Commands aktivieren. Die ROM starten und den Zillion-Client verbinden.
shapez|Automation,Aufbau,Puzzle|mod|Automatisiere das Schneiden, Färben und Kombinieren geometrischer Formen.|Installierbare PC-Version von shapez und der shapezipelago-Mod.|Die Mod-Datei aus mod.io herunterladen. Im Spiel MODS → OPEN MODS FOLDER öffnen und die JavaScript-Moddatei dort ablegen. Mod aktivieren und die Runde über den Mod verbinden. Die reine Browser-Demo ist dafür kein Ersatz.
"""

CATALOG = {}
for _line in _DATA.strip().splitlines():
    _slug, _genres, _mode, _description, _required, _steps = _line.split("|")
    CATALOG[_slug] = dict(genres=_genres.split(","), setup_type=_mode,
                          description=_description, requirements=[_required], steps=[_steps])

CATALOG.update({
    "bloodstained_rotn": dict(
        genres=["Metroidvania", "Action-Rollenspiel"], tags=["2D", "Erkundung", "Ausrüstung", "Bosskämpfe"], setup_type="mod",
        description="Erkunde als Miriam ein dämonisches Schloss, sammle Splitterfähigkeiten und entdecke neue Wege mit wechselnder Ausrüstung.",
        requirements=["Bloodstained: Ritual of the Night für Windows und ein zur APWorld passendes Bloodstained-AP-Releasepaket."],
        steps=["Spielstände sichern. Spielclient und APWorld aus derselben kompatiblen Veröffentlichung verwenden; Anleitungen für ältere Integrationen nicht miteinander mischen.",
               "Die Game-Dateien des Releasepakets nach Entwickler-Anleitung in den Spielordner kopieren. Alte Randomizer-Dateien vorab gemäß Anleitung entfernen.",
               "Einen neuen Story-Spielstand mit der zur YAML passenden Schwierigkeit anlegen. Nach dem Laden mit F5 das Verbindungsfenster öffnen und Server, Slotname sowie gegebenenfalls Passwort eintragen."]),
    "tmc": dict(
        genres=["Action-Adventure", "Puzzle"], tags=["2D", "Dungeons", "Erkundung", "GBA"], setup_type="rom",
        description="Reise mit Link und Ezelo durch Hyrule, schrumpfe auf Minish-Größe und löse Dungeons mit neu gefundener Ausrüstung.",
        requirements=["Eigene europäische GBA-ROM von The Legend of Zelda: The Minish Cap, Archipelago mit passender TMC-APWorld und BizHawk ab 2.7."],
        steps=["Den eigenen .aptmc-Slot-Patch aus der Runde mit Archipelago öffnen und die europäische Original-ROM zum Patchen auswählen.",
               "Die erzeugte GBA-ROM in BizHawk starten und Run in background aktivieren. Den BizHawk-Client öffnen und connector_bizhawk_generic.lua in der Lua-Konsole laden.",
               "Die Lua-Konsole offen lassen und den BizHawk-Client mit Server:Port der Runde verbinden. Der Client muss das Spiel erkannt haben, bevor Checks und Items übertragen werden."]),
    "tboir": dict(
        genres=["Roguelike", "Action", "Shooter"], tags=["2D", "Dungeon-Crawler", "Zufallsgeneriert", "Item-Synergien"], setup_type="mod",
        description="Kämpfe dich durch zufällig erzeugte Kellerräume und kombiniere Gegenstände zu immer neuen Fähigkeiten und Angriffen.",
        requirements=["The Binding of Isaac: Rebirth mit allen DLCs bis Repentance oder Repentance+, The Archipelago of Isaac aus dem Steam Workshop und die passende tboir.apworld.",
                      "Ein gesicherter Spielstand mit freigeschalteten Wegen zu den Endbossen; Archipelago mit Isaac Client."],
        steps=["Spielstand sichern, den Workshop-Mod abonnieren und die passende APWorld im Archipelago Launcher installieren. Den Launcher anschließend neu starten.",
               "Im Spiel einen ausreichend fortgeschrittenen Spielstand wählen, The Archipelago of Isaac aktivieren und einen Run starten.",
               "Den Isaac Client öffnen, Server:Port eintragen und verbinden. Slotname und verwendeten Spielstand angeben. Erst losspielen, wenn die Verbindung im Spiel grün angezeigt wird."]),
    "ss": dict(
        genres=["Action-Adventure", "Puzzle"], tags=["3D", "Dungeons", "Erkundung", "Wii"], setup_type="rom",
        description="Erkunde mit Link das Wolkenmeer und die Gebiete unter den Wolken, löse Dungeons und erschließe neue Wege mit Werkzeugen.",
        requirements=["Eigenes US-Disc-Abbild von Skyward Sword, Revision 1.00; die Wii-Fassung, nicht Skyward Sword HD.",
                      "Dolphin oder eine nach Entwickler-Anleitung eingerichtete Wii sowie SS AP Patcher und ss.apworld aus passenden Releases."],
        steps=["Die APWorld lokal installieren. Nach der Generierung den eigenen .apssr-Slot-Patch mit dem dazu passenden SS AP Patcher auf die Original-ISO anwenden.",
               "Das erzeugte Disc-Abbild in Dolphin starten und den Skyward Sword Client im Archipelago Launcher öffnen. Für echte Wii-Hardware die gesonderte Konsolen-Anleitung befolgen.",
               "Im Spiel ausschließlich Datei 1 für die Multiworld verwenden. Den Client mit /connect Server:Port verbinden und Spiel-Hash sowie Slot-Zuordnung prüfen, bevor du losspielst."]),
    "borderlands_tps": dict(
        genres=["Shooter", "Action-Rollenspiel", "Koop"], setup_type="mod",
        description="Erkunde den Mond Elpis mit Schwerelosigkeits-Sprüngen, Charakterfähigkeiten und zufälliger Beute.",
        requirements=["Borderlands: The Pre-Sequel für PC; DLC-Auswahl in der YAML auf die eigenen Inhalte abstimmen.",
                      "BL2/TPS Mod Manager (Python SDK), coroutines und BouncyLootGod.sdkmod; APWorld und Mod aus einer passenden Veröffentlichung."],
        steps=["Spielstände sichern. Den Python SDK Mod Manager gemäß seiner Anleitung für The Pre-Sequel installieren.",
               "coroutines zuerst in sdk_mods installieren, das Spiel starten und prüfen, dass die Abhängigkeit geladen ist. Danach das Spiel schließen.",
               "BouncyLootGod.sdkmod aus den Releases nach BorderlandsPreSequel/sdk_mods kopieren. Im Mod Manager aktivieren und das Spiel wieder schließen.",
               "Der Host benötigt borderlands_tps.apworld zur Generierung. Vor dem Spielen den zugehörigen Client im Archipelago Launcher starten und mit Server:Port und dem exakten Slotnamen verbinden. Erst danach das Spiel mit aktiviertem Mod starten; die falsche Startreihenfolge kann Probleme verursachen."]),
    "pseudoregalia": dict(
        genres=["Metroidvania", "Jump ’n’ Run", "Action-Adventure"], setup_type="mod",
        description="Erschließe eine dreidimensionale Traumwelt durch neue Bewegungsfähigkeiten und präzise Sprünge.",
        requirements=["Pseudoregalia für Steam und pseudoregalia-archipelago.zip aus einer zur APWorld passenden Veröffentlichung.",
                      "Für APWorld/Mod 0.11.0 die normale Spielversion verwenden: Full Gold wird nicht unterstützt. Steam Deck/Linux benötigt die zusätzlichen Schritte der Entwickler-Anleitung."],
        steps=["Den gesamten Steam-Spielordner Pseudoregalia als separate Kopie sichern, etwa Pseudoregalia_AP. Den Mod in dieser Kopie einrichten.",
               "pseudoregalia-archipelago.zip direkt in den kopierten Spielordner entpacken. Es darf kein zusätzlicher gleichnamiger Unterordner entstehen. Prüfe die Datei pseudoregalia/Content/Paks/AP_Randomizer_p.pak.",
               "Die modifizierte pseudoregalia.exe starten, im Hauptmenü eine neue Datei anlegen und Server:Port, Slotname sowie gegebenenfalls Passwort eingeben. Mit Start verbinden.",
               "Client-Einstellungen unter Optionen → Mods anpassen und mit Apply speichern. PseudoMenuMod ist inkompatibel; weitere Mods einzeln auf Verträglichkeit prüfen."]),
    "RE4R": dict(
        genres=["Horror", "Survival", "Shooter", "Action-Adventure"], setup_type="mod",
        description="Leons Rettungsmission als Multiworld mit geteilten Gegenständen; optional mit The Mercenaries.",
        requirements=["Resident Evil 4 Remake (2023) auf Steam inklusive Separate Ways und Treasure Map: Expansion laut Entwickler-Anleitung; RE4R AP Wizard passend zur APWorld.",
                      "Windows ist die unterstützte Zielplattform, Linux experimentell. Beta: Spielstände sichern und regelmäßig speichern.",
                      "Host: Die Entwickler-Anleitung nennt ausschließlich Archipelago 0.6.7 zur Generierung. Kompatibilität vor der Runde prüfen; der Hub stellt die Archipelago-Version nicht automatisch um."],
        steps=["Die Release-ZIP des RE4R AP Wizard in einen neuen leeren Ordner entpacken. RE4R.AP.Launcher.exe starten und fehlende Komponenten unter Setup Status installieren lassen.",
               "Unter Join a Multiworld die Einstellungen vorbereiten. Für diesen Hub muss der Host die passende RE4R.apworld installiert haben; dieselben YAML-Werte und denselben Slotnamen für die Runde verwenden.",
               "Nach Generierung und Serverstart die Raumadresse und den Slotnamen im Wizard eintragen und den Spiel-Patch erstellen lassen. Der Wizard richtet REFramework, Client und Welt-Patch ein.",
               "Danach das Spiel starten; mit Einfügen das Archipelago-Fenster öffnen und unter Server die Verbindung prüfen. Schwierigkeit und Included Content müssen zur YAML passen. Separate Ways ist als Spielinhalt noch nicht unterstützt; bei reinem Mercenaries entfällt der Kampagnen-Patch."]),
})

# Gameplay tags complement genres; they do not assert APWorld capabilities.
for _slug, _tags in {
    "borderlands2": ["Ego-Perspektive", "Loot", "Quests", "Science-Fiction"],
    "borderlands_tps": ["Ego-Perspektive", "Loot", "Quests", "Science-Fiction"],
    "pseudoregalia": ["3D", "Erkundung", "Bewegungsfähigkeiten", "Präzise Sprünge"],
    "RE4R": ["Third-Person", "Ressourcenmanagement", "Kampagne", "Horror"],
}.items():
    CATALOG[_slug]["tags"] = _tags

_SOURCES = json.loads(Path(__file__).with_name("game_catalog_sources.json").read_text(encoding="utf-8"))


def details(slug, name, metadata=None):
    """Return fresh presentation data; never match an unknown fork by title alone."""
    entry = CATALOG.get(slug)
    source = _SOURCES.get(slug, {})
    if entry is None:
        entry = dict(genres=["Noch nicht zugeordnet"], setup_type="unknown",
                     description=f"{name} ist eine zusätzliche Archipelago-Integration. Die Einrichtung hängt von dieser APWorld ab.",
                     requirements=["Eine zur APWorld passende Spielversion und der vom Entwickler angegebene Client oder Mod. Die Anforderungen sind hier noch nicht dokumentiert."],
                     steps=["Die Anleitung des APWorld-Entwicklers prüfen und Spiel, Client sowie Mod in passenden Versionen installieren. Den Host um die genaue Quelle bitten, falls sie beim Upload fehlt."])
    entry = {**entry, "tags": list(entry.get("tags", []))}
    english = i18n.language() == 'en'
    if english:
        translated = _EN.get(slug, _EN['_unknown'])
        entry = {**entry, **translated}
        if slug not in _EN:
            entry['description'] = translated['description'].replace('{name}',name)
    if metadata:
        if metadata.get("description"):
            entry["description"] = metadata["description"]
        if metadata.get("genres"):
            entry["genres"] = json.loads(metadata["genres"]) or entry["genres"]
        if "tags" in metadata:
            entry["tags"] = json.loads(metadata["tags"])
    return {**entry, "setup_label": i18n.t(SETUP_TYPES[entry["setup_type"]]),
            "host_rom": i18n.t(HOST_ROM_REQUIRED.get(slug)),
            "documented": slug in CATALOG, "guide_url": source.get("guide_url", ""),
            "source_url": source.get("source_url", ""), "links": source.get("links", []),
            "common_steps": _EN['_common'] if english else [
                "In der Lobby Spiel und YAML-Einstellungen wählen und bestätigen. Der Host generiert danach den gemeinsamen Seed; dafür können bereits Originaldateien oder weitere Programme auf seinem Rechner nötig sein.",
                "Nach erfolgreicher Generierung die eigenen Slotdateien aus der Runde herunterladen, soweit die Spielanleitung solche Dateien verlangt. Der Host richtet außerdem einen erreichbaren Multiworld-Server ein.",
                "Den Spielclient oder Mod mit Serveradresse einschließlich Port, dem exakten Slotnamen und gegebenenfalls dem Raumpasswort verbinden. Diese Daten stehen bei der generierten Runde. Erst mit eingerichteter Spielinstallation und Verbindung kannst du mitspielen.",
            ]}


def host_rom_requirements(entries):
    """One reminder per selected game, regardless of how many players chose it."""
    result = {}
    for entry in entries:
        slug = entry["game"]
        info = details(slug, entry["game_name"])
        if info["host_rom"] or info["setup_type"] == "rom":
            result[slug] = {"slug": slug, "name": entry["game_name"],
                            "required": info["host_rom"], "guide_url": info["guide_url"]}
    return list(result.values())


def enrich(rows):
    result = []
    for row in rows:
        info = details(row["slug"], row["name"], row.get("metadata"))
        if not info["documented"]:
            for version in row["versions"]:
                source = version.get("source_url", "")
                try:
                    parsed = urlsplit(source)
                    valid = parsed.scheme in ("https", "http") and parsed.hostname and not parsed.username
                except ValueError:
                    valid = False
                if valid:
                    info = {**info, "guide_url": source, "source_url": source}
                    break
        result.append({**row, "catalog": info,
                       "support_state": "loaded" if row["installed"] else "loading" if row["active"] else "inactive"})
    return result


def matches(row, q="", kind="all", state="all", genre="all", setup="all", tag="all"):
    info = row["catalog"]
    haystack = " ".join([row["name"], row["slug"], row["added_by"], info["description"], *info["genres"], *info["tags"]]).lower()
    return (q.lower().strip() in haystack
            and (kind == "all" or row["custom"] == (kind == "custom"))
            and (state == "all" or row["support_state"] == state)
            and (genre == "all" or genre in info["genres"])
            and (tag == "all" or tag in info["tags"])
            and (setup == "all" or info["setup_type"] == setup))
