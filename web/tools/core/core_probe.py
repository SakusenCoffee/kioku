import sys, time, threading
print("python", sys.version.split()[0], sys.platform)
t = time.time()
from anki.collection import Collection
col = Collection("/tmp/probe.anki2")
deck = col.decks.id("Web probe")
col.decks.select(deck)
for i in range(200):
    note = col.new_note(col.models.by_name("Basic"))
    note["Front"] = f"Q{i}: does Anki run in WebAssembly?"
    note["Back"] = "Its Rust core does."
    col.add_note(note, deck)
print(f"added 200 notes in {time.time()-t:.2f}s; cards: {col.card_count()}; due: {col.sched.counts()}")
card = col.sched.getCard()
card.start_timer()
print("question:", card.question().rsplit(">", 1)[-1])
col.sched.answerCard(card, 3)
print("after Good:", col.sched.counts())
# Anki runs collection ops on worker threads (taskman): do one from a thread
out = {}
th = threading.Thread(target=lambda: out.update(n=len(col.find_cards("Q1*"))))
th.start(); th.join()
print("search from worker thread:", out)
print("stats html bytes:", len(col.stats().report()) if hasattr(col.stats(), "report") else "n/a")
col.close()
print(f"CORE PROBE OK in {time.time()-t:.2f}s")
