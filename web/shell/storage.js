// Linked in with --pre-js: keep /home/web_user (Anki's profiles,
// collections and media, see kioku_platform.documents_dir()) in IndexedDB.
// It is loaded before main() runs and saved whenever the page calls
// __kiokuPersist() (kioku-web.js: on a timer, when the page is hidden and
// after collection operations). The folder is a MEMFS mount synced with
// IDBFS's functions: mounted as IDBFS (even without autoPersist) the app
// trapped (`unreachable` in emscripten_futex_wait) once the profile opened;
// loading from main() through Asyncify broke Qt's event loop.
if (typeof ENVIRONMENT_IS_PTHREAD === "undefined" || !ENVIRONMENT_IS_PTHREAD) {
  Module.preRun = [].concat(Module.preRun || [], () => {
    addRunDependency("kioku-storage");
    const root = FS.mount(MEMFS, {}, "/home/web_user");
    globalThis.__kiokuPersist = () => IDBFS.queuePersist(root.mount);
    IDBFS.syncfs(root.mount, true, (err) => {
      if (err) console.error("Kioku: loading saved files failed", err);
      removeRunDependency("kioku-storage");
    });
  });
}
