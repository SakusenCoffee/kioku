package io.ankidesk;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.app.PendingIntent;
import android.app.Service;
import android.content.Intent;
import android.content.pm.ServiceInfo;
import android.net.Uri;
import android.os.Build;
import android.os.FileObserver;
import android.os.IBinder;
import android.net.wifi.WifiManager;
import android.os.PowerManager;
import android.os.SystemClock;
import android.system.Os;
import android.system.OsConstants;
import android.util.Log;

import com.termux.x11.MainActivity;

import java.io.File;
import java.io.IOException;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

/**
 * Session supervisor, the equivalent of init + display manager + a systemd
 * unit with Restart=on-failure on a Linux kiosk:
 *
 * <ol>
 * <li>unpack the runtime if it is missing or damaged,</li>
 * <li>start the X server (Termux:X11 through app_process),</li>
 * <li>start the session (window manager, desktop shell, Anki) and wait for it to be up,</li>
 * <li>restart after a crash, give up with a readable error after repeated ones,</li>
 * <li>tear everything down when the user powers off the desktop.</li>
 * </ol>
 */
public class AnkiService extends Service {
    static final String ACTION_START = "io.ankidesk.START";
    static final String ACTION_STOP = "io.ankidesk.STOP";
    static final String EXTRA_SAFE_MODE = "safe_mode";
    static final String EXTRA_RESET = "reset_runtime";

    private static final String TAG = "AnkiService";
    private static final String CHANNEL = "anki";
    private static final int NOTIFICATION_ID = 1;
    /** Anki's main window normally appears well within this on a mid-range phone. */
    private static final long READY_TIMEOUT_MS = 180_000;
    /** Show the display anyway after this, so a start-up dialog from Anki is not hidden behind the splash. */
    private static final long SHOW_DISPLAY_AFTER_MS = 45_000;
    private static final int MAX_RESTARTS = 2;
    private static final int MIN_LOGICAL_WIDTH = 480;
    private static final long RESTART_WINDOW_MS = 3 * 60_000;

    // the remote desktop (ankidesk_remote.py): the CPU and Wi-Fi stay awake
    // with the screen off until it is turned off
    private static volatile boolean remote;
    private static PowerManager.WakeLock remoteWakeLock;
    private static WifiManager.WifiLock remoteWifiLock;
    private static AnkiService instance;

    private Prefix prefix;
    private Process xserver;
    private Process session;
    private Thread runner;
    private FileObserver openRequests;
    private PowerManager.WakeLock wakeLock;
    private volatile boolean stopRequested;
    private final List<Long> crashTimes = new ArrayList<>();

    @Override
    public IBinder onBind(Intent intent) {
        return null;
    }

    @Override
    public int onStartCommand(Intent intent, int flags, int startId) {
        instance = this;
        updateNotification();
        if (intent != null && ACTION_STOP.equals(intent.getAction())) {
            stopRequested = true;
            new Thread(this::shutdown, "anki-stop").start();
            return START_NOT_STICKY;
        }
        if (runner == null || !runner.isAlive()) {
            boolean safe = intent != null && intent.getBooleanExtra(EXTRA_SAFE_MODE, false);
            boolean reset = intent != null && intent.getBooleanExtra(EXTRA_RESET, false);
            stopRequested = false;
            crashTimes.clear();
            runner = new Thread(() -> supervise(safe, reset), "anki-supervisor");
            runner.start();
        }
        return START_NOT_STICKY;
    }

    private void supervise(boolean safeMode, boolean reset) {
        prefix = new Prefix(this);
        try {
            if (reset)
                prefix.reset();
            if (!prefix.isInstalled(this)) {
                Session.installing(new Prefix.Progress());
                prefix.install(this, Session::installing);
            }
        } catch (Exception e) {
            Log.e(TAG, "Runtime installation failed", e);
            Session.fail("Could not unpack the runtime: " + e.getMessage(), "");
            stopSelfQuietly();
            return;
        }

        acquireWakeLock();
        watchOpenRequests();
        while (!stopRequested) {
            Outcome outcome = runOnce(safeMode);
            if (stopRequested || outcome == Outcome.USER_QUIT)
                break;
            if (outcome == Outcome.FAILED_TO_START) {
                Session.fail("The desktop did not start.", logs());
                break;
            }
            // Crashed after it was up: restart, unless it keeps happening.
            long now = SystemClock.elapsedRealtime();
            crashTimes.removeIf(t -> now - t > RESTART_WINDOW_MS);
            crashTimes.add(now);
            if (crashTimes.size() > MAX_RESTARTS) {
                Session.fail("The desktop stopped unexpectedly several times.", logs());
                break;
            }
            Session.set(Session.State.STARTING, "The desktop stopped unexpectedly, restarting…");
        }

        boolean failed = Session.state == Session.State.FAILED;
        killEverything();
        if (failed) {
            // Bring the splash back so the user sees what went wrong.
            startActivity(new Intent(this, LauncherActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } else {
            Session.set(Session.State.IDLE, "");
        }
        closeDisplay();
        stopSelfQuietly();
    }

    private enum Outcome { USER_QUIT, CRASHED, FAILED_TO_START }

    private Outcome runOnce(boolean safeMode) {
        Map<String, String> env = prefix.environment();
        File ready = new File(prefix.tmp, "ankidesk-ready");
        try {
            prefix.tmp.mkdirs();
            prefix.home.mkdirs();
            AndroidBridge.writeTouchMode(this, null);
            AndroidBridge.writeBatteryState(this);
            killEverything();
            // a remote session doesn't survive a restart (ankidesk_remote.reset_stale)
            setRemote(this, false);
            ready.delete();

            Session.set(Session.State.STARTING, "Starting display…");
            if (!startXServer(env) && !startXServer(env))
                return Outcome.FAILED_TO_START;

            Session.set(Session.State.STARTING, safeMode ? "Starting desktop (Anki in safe mode)…" : "Starting desktop…");
            // Android blocks execve() on files in app data for targetSdk >= 29, so
            // the first process goes through the system linker; libtermux-exec
            // then does the same for everything it starts.
            String sh = prefix.prefix + "/bin/dash";
            List<String> cmd = new ArrayList<>(List.of("/system/bin/linker64", sh, prefix.prefix + "/libexec/ankidx/session.sh"));
            if (safeMode)
                cmd.add("--safemode");
            ProcessBuilder s = new ProcessBuilder(cmd);
            s.environment().putAll(env);
            s.environment().put("LD_PRELOAD", prefix.prefix + "/lib/libtermux-exec.so");
            s.environment().put("TERMUX_EXEC__PROC_SELF_EXE", sh);
            s.environment().put("ANKIDX_SCALE", String.valueOf(uiScale()));
            s.environment().put("ANKIDX_READY_FILE", ready.getPath());
            s.directory(prefix.home);
            s.redirectErrorStream(true).redirectOutput(new File(prefix.tmp, "session.log"));
            session = s.start();

            long started = SystemClock.elapsedRealtime();
            boolean shown = false;
            while (!stopRequested) {
                boolean sessionAlive = session.isAlive();
                boolean xAlive = xserver.isAlive();
                long elapsed = SystemClock.elapsedRealtime() - started;

                if (!shown && (ready.exists() || (sessionAlive && elapsed > SHOW_DISPLAY_AFTER_MS))) {
                    shown = true;
                    Session.set(Session.State.READY, "");
                }
                if (!sessionAlive) {
                    int code = session.exitValue();
                    Log.i(TAG, "Session exited with " + code);
                    if (!shown)
                        return Outcome.FAILED_TO_START;
                    return code == 0 && xAlive ? Outcome.USER_QUIT : Outcome.CRASHED;
                }
                if (!xAlive) {
                    Log.w(TAG, "X server died");
                    return shown ? Outcome.CRASHED : Outcome.FAILED_TO_START;
                }
                if (!shown && elapsed > READY_TIMEOUT_MS)
                    return Outcome.FAILED_TO_START;
                Thread.sleep(250);
            }
            return Outcome.USER_QUIT;
        } catch (Exception e) {
            Log.e(TAG, "Failed to start Anki", e);
            return Outcome.FAILED_TO_START;
        }
    }

    private boolean startXServer(Map<String, String> env) throws IOException, InterruptedException {
        if (xserver != null)
            xserver.destroy();
        // A crashed server leaves its socket and lock behind, which would make
        // the next server refuse to start on :0.
        File socket = new File(prefix.tmp, ".X11-unix/X0");
        socket.delete();
        new File(prefix.tmp, ".X0-lock").delete();

        ProcessBuilder x = new ProcessBuilder(List.of(
                "/system/bin/app_process", "-Xnoimage-dex2oat", "/",
                "--nice-name=" + getPackageName() + ":x11",
                "com.termux.x11.CmdEntryPoint", ":0"));
        x.environment().putAll(env);
        x.environment().put("CLASSPATH", getApplicationInfo().sourceDir);
        x.environment().remove("LD_PRELOAD");
        x.directory(prefix.tmp);
        x.redirectErrorStream(true).redirectOutput(new File(prefix.tmp, "x11.log"));
        xserver = x.start();

        for (int i = 0; i < 100 && !socket.exists() && xserver.isAlive(); i++)
            Thread.sleep(100);
        if (socket.exists())
            return true;
        Log.w(TAG, "X server did not come up");
        return false;
    }

    private String logs() {
        return "== session.log ==\n" + Prefix.tail(new File(prefix.tmp, "session.log"), 30)
                + "\n== anki.log ==\n" + Prefix.tail(new File(prefix.tmp, "anki.log"), 30)
                + "\n== x11.log ==\n" + Prefix.tail(new File(prefix.tmp, "x11.log"), 15);
    }

    /**
     * Qt scale factor, in quarter steps: close to Android's own density so text
     * reads like a phone app, but small enough that the short side of the
     * screen is at least {@link #MIN_LOGICAL_WIDTH} logical pixels, which
     * Anki's windows need. Users can override it in Anki's Preferences
     * (User interface size).
     */
    private float uiScale() {
        android.util.DisplayMetrics dm = getResources().getDisplayMetrics();
        float byDensity = Math.round(dm.density * 0.85f * 4) / 4f;
        float byWidth = (float) Math.floor(Math.min(dm.widthPixels, dm.heightPixels) * 4f / MIN_LOGICAL_WIDTH) / 4f;
        return Math.max(1f, Math.min(byDensity, byWidth));
    }

    /**
     * Requests from inside the prefix: URLs passed to xdg-open (links in cards,
     * AnkiWeb, help) and ankidesk: commands (see {@link AndroidBridge}).
     */
    private void watchOpenRequests() {
        File dir = new File(prefix.tmp, "ankidx-open");
        dir.mkdirs();
        openRequests = new FileObserver(dir.getPath(), FileObserver.MOVED_TO) {
            @Override
            public void onEvent(int event, String path) {
                if (path == null || !path.startsWith("req."))
                    return;
                File f = new File(dir, path);
                try {
                    String target = Prefix.readFile(f).trim();
                    if (target.startsWith("ankidesk:")) {
                        AndroidBridge.handle(AnkiService.this, target);
                        return;
                    }
                    Uri uri = target.startsWith("/") ? null : Uri.parse(target);
                    if (uri != null && uri.getScheme() != null)
                        startActivity(new Intent(Intent.ACTION_VIEW, uri).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
                    else
                        Log.w(TAG, "Not opening " + target);
                } catch (Exception e) {
                    Log.w(TAG, "Cannot handle open request", e);
                } finally {
                    f.delete();
                }
            }
        };
        openRequests.startWatching();
    }

    private void acquireWakeLock() {
        PowerManager pm = getSystemService(PowerManager.class);
        wakeLock = pm.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ankidesk:session");
        // Long enough for a sync or a big import after the screen turns off.
        wakeLock.acquire(10 * 60 * 1000L);
    }

    static synchronized void setRemote(android.content.Context ctx, boolean on) {
        remote = on;
        android.content.Context app = ctx.getApplicationContext();
        if (on) {
            if (remoteWakeLock == null) {
                remoteWakeLock = app.getSystemService(PowerManager.class)
                        .newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "ankidesk:remote");
                remoteWakeLock.setReferenceCounted(false);
                WifiManager wifi = app.getSystemService(WifiManager.class);
                if (wifi != null) {
                    remoteWifiLock = wifi.createWifiLock(WifiManager.WIFI_MODE_FULL_HIGH_PERF, "ankidesk:remote");
                    remoteWifiLock.setReferenceCounted(false);
                }
            }
            remoteWakeLock.acquire();
            if (remoteWifiLock != null)
                remoteWifiLock.acquire();
        } else {
            if (remoteWakeLock != null && remoteWakeLock.isHeld())
                remoteWakeLock.release();
            if (remoteWifiLock != null && remoteWifiLock.isHeld())
                remoteWifiLock.release();
        }
        AnkiService s = instance;
        if (s != null)
            s.updateNotification();
    }

    private void updateNotification() {
        NotificationManager nm = getSystemService(NotificationManager.class);
        if (Build.VERSION.SDK_INT >= 26)
            nm.createNotificationChannel(new NotificationChannel(CHANNEL, getString(R.string.app_name), NotificationManager.IMPORTANCE_LOW));
        int piFlags = PendingIntent.FLAG_IMMUTABLE;
        PendingIntent open = PendingIntent.getActivity(this, 0,
                new Intent(this, LauncherActivity.class).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK), piFlags);
        PendingIntent stop = PendingIntent.getService(this, 1,
                new Intent(this, AnkiService.class).setAction(ACTION_STOP), piFlags);
        Notification.Builder b = Build.VERSION.SDK_INT >= 26 ? new Notification.Builder(this, CHANNEL) : new Notification.Builder(this);
        if (remote)
            b.setContentText(getString(R.string.notification_remote));
        Notification n = b.setContentTitle(getString(R.string.notification_running))
                .setSmallIcon(android.R.drawable.ic_menu_agenda)
                .setContentIntent(open)
                .setOngoing(true)
                .addAction(new Notification.Action.Builder(null, getString(R.string.notification_stop), stop).build())
                .build();
        if (Build.VERSION.SDK_INT >= 34)
            startForeground(NOTIFICATION_ID, n, ServiceInfo.FOREGROUND_SERVICE_TYPE_SPECIAL_USE);
        else
            startForeground(NOTIFICATION_ID, n);
    }

    private void shutdown() {
        // Give Anki a chance to save before the hard kill.
        signalAll(OsConstants.SIGTERM);
        for (int i = 0; i < 30 && session != null && session.isAlive(); i++)
            SystemClock.sleep(100);
        killEverything();
        Session.set(Session.State.IDLE, "");
        closeDisplay();
        stopSelfQuietly();
    }

    private void closeDisplay() {
        sendBroadcast(new Intent(MainActivity.ACTION_STOP).setPackage(getPackageName()));
    }

    private void stopSelfQuietly() {
        if (openRequests != null)
            openRequests.stopWatching();
        if (wakeLock != null && wakeLock.isHeld())
            wakeLock.release();
        setRemote(this, false);
        stopForeground(STOP_FOREGROUND_REMOVE);
        stopSelf();
    }

    /** Kill everything else running under this app's uid: X server, Anki, Qt WebEngine helpers, mpv, jwm. */
    private void killEverything() {
        signalAll(OsConstants.SIGKILL);
    }

    private static void signalAll(int signal) {
        int self = android.os.Process.myPid();
        int uid = android.os.Process.myUid();
        File[] procs = new File("/proc").listFiles();
        if (procs == null)
            return;
        for (File p : procs) {
            int pid;
            try {
                pid = Integer.parseInt(p.getName());
            } catch (NumberFormatException e) {
                continue;
            }
            if (pid == self)
                continue;
            try {
                if (Os.stat(p.getPath()).st_uid == uid)
                    Os.kill(pid, signal);
            } catch (Exception ignored) {
            }
        }
    }

    @Override
    public void onDestroy() {
        stopRequested = true;
        super.onDestroy();
    }
}
