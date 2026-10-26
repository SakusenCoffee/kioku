# Benchmark run inside Kioku, the same code on the web build (selftest.py
# with ONLY=bench) and in the native apps (ios/tools/devcmd.sh, see
# bench.py): Anki's core and Python on a throwaway collection in a temporary
# folder, never the profile's. Results (ms) go to <tmp>/kioku-bench.json and
# are printed as "BENCH {...}".
import json
import os
import shutil
import sys
import tempfile
import time

from anki.collection import Collection, ExportAnkiPackageOptions

results: dict = {"platform": sys.platform}


def timed(name, fn):
    start = time.perf_counter()
    value = fn()
    results[name] = round((time.perf_counter() - start) * 1000, 1)
    return value


folder = tempfile.mkdtemp(prefix="kioku-bench-")
timed("python: loop, 3M multiply-adds", lambda: sum(i * i for i in range(3_000_000)))
data = {"cards": [{"id": i, "q": "question " * 10, "tags": ["a", "b"], "ivl": i % 365} for i in range(20_000)]}
timed("python: json dumps+loads, 20k records", lambda: json.loads(json.dumps(data)))
col = timed("core: create collection", lambda: Collection(os.path.join(folder, "bench.anki2")))
basic = col.models.by_name("Basic")


def add_notes():
    for i in range(1000):
        note = col.new_note(basic)
        note["Front"] = f"front {i} " + "word " * 20
        note["Back"] = f"back {i} <b>bold</b>"
        col.add_note(note, 1)


timed("core: add 1000 notes", add_notes)
timed("core: search all cards x20", lambda: [col.find_cards("") for _ in range(20)])
timed("core: search text x20", lambda: [col.find_cards("front 1*") for _ in range(20)])
cids = col.find_cards("")
timed("core: render 300 cards (q+a)", lambda: [(c := col.get_card(cid)).question() + c.answer() for cid in cids[:300]])
timed("core: deck tree x20", lambda: [col.sched.deck_due_tree() for _ in range(20)])


conf = col.decks.config_dict_for_deck_id(1)
conf["new"]["perDay"] = 9999
col.decks.update_config(conf)


def answer():
    for _ in range(200):
        card = col.sched.getCard()
        if card is None:
            break
        col.sched.answerCard(card, 3)


timed("core: answer 200 cards", answer)
timed("core: stats graphs x3", lambda: [col._backend.graphs(search="", days=365) for _ in range(3)])
timed("core: check database", lambda: col.fix_integrity())
timed("core: export .apkg (1000 notes)", lambda: col.export_anki_package(
    out_path=os.path.join(folder, "bench.apkg"),
    options=ExportAnkiPackageOptions(with_scheduling=True, with_deck_configs=True, with_media=False, legacy=False),
    limit=None))
timed("core: close collection", lambda: col.close())
shutil.rmtree(folder, ignore_errors=True)
with open(os.path.join(tempfile.gettempdir(), "kioku-bench.json"), "w") as f:
    json.dump(results, f)
print("BENCH", json.dumps(results))
