# Patches to Anki's source

`shared/tools/anki_source.sh` checks out Anki at `ANKI_TAG`
(`shared/versions.env`) and applies every `anki-*.patch` here; both
`fetch_deps.sh` and `shared/tests/run.sh` call it. Changing `ANKI_TAG` is
enough to move to another release: the next build replaces the checkout and
applies the patches again.

## Keeping patches easy to carry to the next release

A patch conflicts only where it changes lines that Anki changes too, so:

- Put Kioku's code in **new files** (`kioku.rs` next to the file that needs
  it). New files never conflict.
- Change upstream files only by **anchor lines**: a `mod kioku;`, one call
  into Kioku's code, one replaced expression. `anki-syncserver.patch`
  changes four lines of Anki's own files; the rest is new files.
- Prefer Python over patches. Kioku changes Anki's Python code at runtime
  (`shared/python/kioku/patches.py` and friends), which never conflicts.
  Replacement functions should take `*args, **kwargs` when they only wrap
  the original, so that new parameters pass through.

## When a new release arrives

The daily `Anki update` workflow opens a pull request whose description has
the report of `shared/tools/anki_drift.py`: whether the patches apply, and
each Anki function Kioku replaces that changed (with the diff). To run it by
hand:

```sh
git clone --filter=blob:none --no-checkout https://github.com/ankitects/anki /tmp/anki
git -C /tmp/anki fetch origin tag 26.08.1 tag 26.09.3
python3 -I shared/tools/anki_drift.py /tmp/anki 26.08.1 26.09.3
```

If a patch no longer applies, check out the new tag, apply the patch with
`git apply --3way` or by hand, and regenerate it with
`git add -N . && git diff > shared/patches/<name>.patch`.
