// Linked in with --pre-js: keep /home/web_user (Anki's profiles,
// collections and media, see kioku_platform.documents_dir()) in IndexedDB.
// It is loaded before main() runs and saved whenever the page calls
// __kiokuPersist() (kioku-web.js: on a timer, when the page is hidden and
// after collection operations). The folder is a MEMFS mount synced with
// IDBFS's functions: mounted as IDBFS (even without autoPersist) the app
// trapped (`unreachable` in emscripten_futex_wait) once the profile opened;
// loading from main() through Asyncify broke Qt's event loop.
//
// Memory: an iPhone ends a tab that goes over its limit, and IDBFS's own
// sync handles every changed file at once (all of them structured-cloned
// into one transaction, or all read back together), on top of the garbage
// MEMFS leaves when a file grows. So files are synced a batch at a time,
// each transaction finished before the next, saved as exact-size copies,
// and MEMFS grows files 2x (a 30 MB file was copied ~30 times at 1.125x).
if (typeof ENVIRONMENT_IS_PTHREAD === "undefined" || !ENVIRONMENT_IS_PTHREAD) {
  Module.preRun = [].concat(Module.preRun || [], () => {
    addRunDependency("kioku-storage");
    MEMFS.expandFileStorage = (node, newCapacity) => {
      const prev = node.contents ? node.contents.length : 0;
      if (prev >= newCapacity) return;
      newCapacity = Math.max(newCapacity, prev * 2, 256);
      const old = node.contents;
      node.contents = new Uint8Array(newCapacity);
      if (node.usedBytes > 0) node.contents.set(old.subarray(0, node.usedBytes), 0);
    };
    const root = FS.mount(MEMFS, {}, "/home/web_user");
    const mount = root.mount;
    let state = "idle";
    globalThis.__kiokuPersist = () => {
      if (state !== "idle") {
        state = "again";
        return;
      }
      state = "saving";
      const run = () =>
        kiokuStore(mount, false).then(
          () => (state === "again" ? ((state = "saving"), run()) : (state = "idle")),
          (err) => {
            console.error("Kioku: saving files failed", err);
            state = "idle";
          },
        );
      run();
    };
    kiokuStore(mount, true).then(
      () => removeRunDependency("kioku-storage"),
      (err) => {
        console.error("Kioku: loading saved files failed", err);
        removeRunDependency("kioku-storage");
      },
    );
  });
}

// Served by a Kioku server (shell/server.js): its files instead of
// IndexedDB, and Python is told (kioku_platform/remote.py)
function kiokuStore(mount, populate) {
  const server = globalThis.__kiokuServer;
  return (server ? server.config : Promise.resolve(null)).then((config) => {
    if (!config) return kiokuSync(mount, populate);
    if (populate) {
      ENV.KIOKU_SERVER_HOME = config.home;
      ENV.KIOKU_CLIENT = config.client;
    }
    return server.sync(mount, populate, { FS, IDBFS });
  });
}

// bytes per IndexedDB transaction when saving; files per one when loading
var KIOKU_SAVE_BATCH = 8 * 1024 * 1024;
var KIOKU_LOAD_BATCH = 8;

function kiokuSync(mount, populate) {
  const call = (fn, ...args) => new Promise((ok, fail) => fn(...args, (err, value) => (err ? fail(err) : ok(value))));
  return Promise.all([call(IDBFS.getLocalSet, mount), call(IDBFS.getRemoteSet, mount)]).then(([local, remote]) => {
    const [src, dst] = populate ? [remote, local] : [local, remote];
    const changed = Object.keys(src.entries)
      .filter((key) => {
        const theirs = dst.entries[key];
        return !theirs || src.entries[key]["timestamp"].getTime() != theirs["timestamp"].getTime();
      })
      // directories before the files in them
      .sort();
    const removed = Object.keys(dst.entries)
      .filter((key) => !src.entries[key])
      // files before their directories
      .sort()
      .reverse();
    return (populate ? kiokuLoad(remote.db, changed) : kiokuSave(remote.db, changed)).then(() =>
      removed.length ? kiokuRemove(remote.db, removed, populate) : undefined,
    );
  });
}

function kiokuTransaction(db, mode, fill) {
  return new Promise((ok, fail) => {
    const tx = db.transaction([IDBFS.DB_STORE_NAME], mode);
    tx.oncomplete = () => ok();
    tx.onerror = tx.onabort = (e) => {
      e.preventDefault();
      fail(tx.error || e.target.error);
    };
    fill(tx.objectStore(IDBFS.DB_STORE_NAME));
  });
}

async function kiokuSave(db, paths) {
  let batch = [];
  let bytes = 0;
  const flush = async () => {
    const entries = batch;
    batch = [];
    bytes = 0;
    if (entries.length) await kiokuTransaction(db, "readwrite", (store) => entries.forEach(([path, entry]) => store.put(entry, path)));
  };
  for (const path of paths) {
    let stat;
    try {
      stat = FS.stat(path);
    } catch (e) {
      continue; // removed meanwhile; the next sync drops it
    }
    if (FS.isDir(stat.mode)) {
      batch.push([path, { "timestamp": stat.mtime, "mode": stat.mode }]);
    } else if (FS.isFile(stat.mode)) {
      const node = FS.lookupPath(path).node;
      // a structured clone copies the view's whole buffer, spare capacity
      // included: keep (and save) an exact-size copy instead
      let contents = MEMFS.getFileDataAsTypedArray(node);
      if (contents.byteLength !== contents.buffer.byteLength) contents = contents.slice();
      node.contents = contents;
      batch.push([path, { "timestamp": stat.mtime, "mode": stat.mode, "contents": contents }]);
      bytes += contents.byteLength;
    }
    if (bytes >= KIOKU_SAVE_BATCH) await flush();
  }
  await flush();
}

async function kiokuLoad(db, paths) {
  for (let i = 0; i < paths.length; i += KIOKU_LOAD_BATCH) {
    const entries = [];
    await kiokuTransaction(db, "readonly", (store) =>
      paths.slice(i, i + KIOKU_LOAD_BATCH).forEach((path) => {
        store.get(path).onsuccess = (e) => entries.push([path, e.target.result]);
      }),
    );
    for (const [path, entry] of entries) {
      if (entry) await new Promise((ok, fail) => IDBFS.storeLocalEntry(path, entry, (err) => (err ? fail(err) : ok())));
    }
  }
}

function kiokuRemove(db, paths, local) {
  if (local) {
    for (const path of paths) {
      IDBFS.removeLocalEntry(path, () => {});
    }
    return Promise.resolve();
  }
  return kiokuTransaction(db, "readwrite", (store) => paths.forEach((path) => store.delete(path)));
}
