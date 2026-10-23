"""JavaScript injected into every page by the web view backends.

The backends differ only in how a page talks to Python; each one installs a
small BRIDGE script first that defines window.__kiokuNative:

    __kiokuNative.send(name, text)   fire-and-forget message ("console",
                                     "selection")
    __kiokuNative.call(text)         a web channel call; returns a Promise of
                                     the JSON-encoded result
"""

# Event names used with __kiokuNative.send()
CONSOLE = "console"
SELECTION = "selection"

# Stand-in for qwebchannel.js: calls on channel.objects.<name>.<method>(...)
# go to Python. Also console capture and selection tracking.
PRELUDE = r"""
(function () {
    if (window.__kioku) return;
    window.__kioku = true;
    var native = window.__kiokuNative;
    function post(level, args) {
        try {
            var parts = Array.prototype.map.call(args, function (a) {
                if (typeof a === "string") return a;
                try { return JSON.stringify(a); } catch (e) { return String(a); }
            });
            native.send("console", JSON.stringify({
                level: level, msg: parts.join(" "), src: String(location.href)
            }));
        } catch (e) {}
    }
    ["log", "info", "warn", "error", "debug"].forEach(function (name) {
        var orig = console[name];
        console[name] = function () {
            post(name, arguments);
            if (orig) orig.apply(console, arguments);
        };
    });
    window.addEventListener("error", function (e) {
        post("error", [e.message + " (" + e.filename + ":" + e.lineno + ")"]);
    });
    window.addEventListener("unhandledrejection", function (e) {
        var r = e.reason;
        post("error", ["Unhandled promise rejection: " + (r && (r.stack || r))]);
    });
    document.addEventListener("selectionchange", function () {
        try { native.send("selection", String(window.getSelection())); }
        catch (e) {}
    });

    window.qt = window.qt || {};
    window.qt.webChannelTransport = window.qt.webChannelTransport || {};
    function makeObject(objName) {
        return new Proxy({}, {
            get: function (target, method) {
                if (typeof method !== "string" || method === "then") return undefined;
                return function () {
                    var args = Array.prototype.slice.call(arguments);
                    var cb = null;
                    if (args.length && typeof args[args.length - 1] === "function") {
                        cb = args.pop();
                    }
                    native.call(JSON.stringify({
                        obj: objName, method: method, args: args
                    })).then(function (reply) {
                        if (cb) cb(JSON.parse(reply));
                    }, function (err) {
                        console.error("channel call " + objName + "." + method + " failed: " + err);
                    });
                };
            }
        });
    }
    window.QWebChannel = function (transport, initCallback) {
        var cache = {};
        this.objects = new Proxy(cache, {
            get: function (target, name) {
                if (typeof name !== "string") return undefined;
                if (!(name in target)) target[name] = makeObject(name);
                return target[name];
            }
        });
        if (initCallback) initCallback(this);
    };
})();
"""

# Desktop pages have no viewport meta; without one mobile browsers lay them
# out at 980px and shrink them. Also narrows Anki's deck list, the top bar's
# add-on buttons and add-on pop-ups on phones.
VIEWPORT = r"""
(function () {
    if (!document.querySelector("meta[name=viewport]") && document.head) {
        var m = document.createElement("meta");
        m.name = "viewport";
        m.content = "width=device-width, initial-scale=1";
        document.head.appendChild(m);
    }
    var s = document.createElement("style");
    s.textContent = "html { -webkit-text-size-adjust: 100%; }" +
        "@media (max-width: 600px) {" +
        "  table:has(.decktd) { padding: 0.5rem; max-width: 100%; }" +
        "  table:has(.decktd) .decktd { min-width: 6em; max-width: calc(100vw - 13em); }" +
        "  table:has(.decktd) .count { min-width: 2em; }" +
        "  table:has(.decktd) td, table:has(.decktd) th { padding-left: 4px !important; padding-right: 4px !important; }" +
        "  body:has(.decktd) { margin-left: 0.5em; margin-right: 0.5em; }" +
        // add-on buttons in the top bar (right-tray) covered Sync: share one
        // row with the links, or wrap to a second one
        "  .header:has(.tray-item) { display: flex; flex-wrap: wrap; justify-content: center; align-items: start; }" +
        "  .header:has(.tray-item) .hitem { padding-left: 6px; padding-right: 6px; }" +
        "  .header .tray-item { margin-left: 2px !important; margin-right: 2px !important; }" +
        // add-on pop-ups made with tippy.js (AMBOSS: 480-550px wide) ran off
        // the screen, which doesn't scroll sideways
        "  .tippy-popper { max-width: calc(100vw - 16px) !important; }" +
        "  .tippy-popper .tippy-tooltip { min-width: 0 !important; max-width: calc(100vw - 16px) !important; }" +
        "  .tippy-popper img { max-width: 100%; height: auto; }" +
        "}";
    (document.head || document.documentElement).appendChild(s);
})();
"""

# Injection times understood by every backend
AT_DOCUMENT_START = 0
AT_DOCUMENT_END = 1
