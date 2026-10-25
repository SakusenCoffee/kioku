package io.ankidesk;

import android.annotation.SuppressLint;
import android.content.ActivityNotFoundException;
import android.content.Context;
import android.content.Intent;
import android.content.pm.PackageInfo;
import android.content.pm.PackageManager;
import android.net.Uri;
import android.os.Build;
import android.os.Environment;
import android.os.Handler;
import android.os.Looper;
import android.os.PowerManager;
import android.provider.DocumentsContract;
import android.provider.Settings;
import android.util.Log;
import android.view.View;
import android.view.WindowInsets;
import android.view.WindowInsetsController;
import android.view.inputmethod.InputMethodManager;

import org.json.JSONException;
import org.json.JSONObject;

import com.termux.x11.LoriePreferences;
import com.termux.x11.MainActivity;

import java.io.File;
import java.io.IOException;

/**
 * Commands sent from inside the prefix as {@code ankidesk:<command>} (through
 * xdg-open's request directory). They let the desktop use Android for things
 * that would otherwise need bundled apps: files, browser, settings, keyboard.
 */
final class AndroidBridge {
    private static final String TAG = "AndroidBridge";
    private static final Handler main = new Handler(Looper.getMainLooper());

    private AndroidBridge() {
    }

    static void handle(Context ctx, String request) {
        String cmd = request.substring("ankidesk:".length());
        Log.i(TAG, cmd);
        main.post(() -> {
            try {
                switch (cmd) {
                    case "keyboard/show":
                        setKeyboardVisible(true);
                        break;
                    case "keyboard/hide":
                        setKeyboardVisible(false);
                        break;
                    case "keyboard/toggle": {
                        MainActivity a = MainActivity.getFocusedOrAnyInstance();
                        if (a != null)
                            a.toggleKeyboardVisibility();
                        break;
                    }
                    case "input/touch":
                        // A tap clicks where the finger is.
                        setTouchMode(ctx, "2");
                        break;
                    case "input/direct":
                        // Touch mode while another app than Anki or the desktop is
                        // active: real touch events, so a drag scrolls a web page
                        // instead of selecting its text. Not shown as a setting.
                        ctx.sendBroadcast(new Intent("com.termux.x11.CHANGE_PREFERENCE")
                                .setPackage(ctx.getPackageName())
                                .putExtra("touchMode", "3"));
                        break;
                    case "input/trackpad":
                        // The screen acts as a laptop touchpad moving a cursor.
                        setTouchMode(ctx, "1");
                        break;
                    case "files":
                        openFiles(ctx);
                        break;
                    case "browser":
                        start(ctx, Intent.makeMainSelectorActivity(Intent.ACTION_MAIN, Intent.CATEGORY_APP_BROWSER));
                        break;
                    case "display-settings":
                        start(ctx, new Intent(ctx, LoriePreferences.class).setAction(Intent.ACTION_MAIN));
                        break;
                    case "app-settings":
                        start(ctx, new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                Uri.fromParts("package", ctx.getPackageName(), null)));
                        break;
                    case "pick-wallpaper":
                        start(ctx, new Intent(ctx, PickFileActivity.class)
                                .putExtra(PickFileActivity.EXTRA_KIND, PickFileActivity.KIND_WALLPAPER));
                        break;
                    case "pick-deck":
                        start(ctx, new Intent(ctx, PickFileActivity.class)
                                .putExtra(PickFileActivity.EXTRA_KIND, PickFileActivity.KIND_DECK));
                        break;
                    case "storage":
                        start(ctx, new Intent(ctx, StorageActivity.class));
                        break;
                    case "phone-apps":
                        start(ctx, new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME));
                        break;
                    case "remote/on":
                        AnkiService.setRemote(ctx, true);
                        writeBatteryState(ctx);
                        break;
                    case "remote/off":
                        AnkiService.setRemote(ctx, false);
                        break;
                    case "battery":
                        openBatterySettings(ctx);
                        break;
                    case "battery/state":
                        writeBatteryState(ctx);
                        break;
                    default:
                        if (cmd.equals("all-files/state")) {
                            writeAllFilesAccess(ctx);
                        } else if (cmd.startsWith("apps/")) {
                            writeAppVersions(ctx, cmd.substring("apps/".length()).split(","));
                        } else if (cmd.startsWith("app-details/")) {
                            start(ctx, new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,
                                    Uri.fromParts("package", cmd.substring("app-details/".length()), null)));
                        } else if (cmd.startsWith("launch/")) {
                            Intent launch = ctx.getPackageManager()
                                    .getLaunchIntentForPackage(cmd.substring("launch/".length()));
                            if (launch != null)
                                start(ctx, launch);
                        } else {
                            Log.w(TAG, "Unknown request " + request);
                        }
                }
            } catch (Exception e) {
                Log.w(TAG, "Failed to handle " + request, e);
            }
        });
    }

    private static void setKeyboardVisible(boolean show) {
        MainActivity a = MainActivity.getFocusedOrAnyInstance();
        if (a == null)
            return;
        View v = a.getLorieView();
        if (show)
            v.requestFocus();
        if (Build.VERSION.SDK_INT >= 30) {
            // Unlike InputMethodManager, this also hides a keyboard that was
            // shown with SHOW_FORCED (Termux:X11's own keyboard toggle).
            WindowInsetsController c = a.getWindow().getInsetsController();
            if (c != null) {
                if (show)
                    c.show(WindowInsets.Type.ime());
                else
                    c.hide(WindowInsets.Type.ime());
                return;
            }
        }
        InputMethodManager imm = (InputMethodManager) a.getSystemService(Context.INPUT_METHOD_SERVICE);
        if (show)
            imm.showSoftInput(v, InputMethodManager.SHOW_IMPLICIT);
        else
            imm.hideSoftInputFromWindow(v.getWindowToken(), 0);
    }

    /** Same values as Termux:X11's "Touchscreen input mode" setting. */
    static void setTouchMode(Context ctx, String mode) {
        ctx.sendBroadcast(new Intent("com.termux.x11.CHANGE_PREFERENCE")
                .setPackage(ctx.getPackageName())
                .putExtra("touchMode", mode));
        writeTouchMode(ctx, mode);
    }

    /**
     * Tells the desktop which touch mode is active (~/.config/kioku/touch-mode:
     * "touch" or "trackpad"), so Settings can show it.
     */
    static void writeTouchMode(Context ctx, String mode) {
        if (mode == null)
            mode = ctx.getSharedPreferences(ctx.getPackageName() + "_preferences", Context.MODE_PRIVATE)
                    .getString("touchMode", "2");
        try {
            PickFileActivity.writeAtomically(new File(new Prefix(ctx).home, ".config/kioku"), "touch-mode",
                    "1".equals(mode) ? "trackpad" : "touch");
        } catch (IOException e) {
            Log.w(TAG, "Cannot save touch mode", e);
        }
    }

    /**
     * Lets Kioku run without Android's battery limits (Doze cuts the network
     * of a battery-optimised app with the screen off, which ends a remote
     * session). Asks directly; if already allowed, opens the list to undo it.
     */
    @SuppressLint("BatteryLife")
    private static void openBatterySettings(Context ctx) {
        PowerManager pm = ctx.getSystemService(PowerManager.class);
        // the answer comes from Android's dialog or settings: look for it
        // for a minute, so the Remote page shows it
        boolean before = pm.isIgnoringBatteryOptimizations(ctx.getPackageName());
        boolean[] written = {false};
        for (int i = 1; i <= 30; i++) {
            main.postDelayed(() -> {
                if (!written[0] && pm.isIgnoringBatteryOptimizations(ctx.getPackageName()) != before) {
                    written[0] = true;
                    writeBatteryState(ctx);
                }
            }, i * 2000L);
        }
        if (before) {
            start(ctx, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
            return;
        }
        try {
            start(ctx, new Intent(Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.fromParts("package", ctx.getPackageName(), null)));
        } catch (ActivityNotFoundException e) {
            start(ctx, new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS));
        }
    }

    /** ~/.config/kioku/battery-unrestricted: "yes" or "no", for the Remote page. */
    static void writeBatteryState(Context ctx) {
        PowerManager pm = ctx.getSystemService(PowerManager.class);
        boolean free = pm.isIgnoringBatteryOptimizations(ctx.getPackageName());
        try {
            PickFileActivity.writeAtomically(new File(new Prefix(ctx).home, ".config/kioku"),
                    "battery-unrestricted", free ? "yes" : "no");
        } catch (IOException e) {
            Log.w(TAG, "Cannot save the battery state", e);
        }
    }

    /**
     * ~/.config/kioku/apps.json: {package: versionName} of those installed
     * (Preferences > Advanced > AnkiDroid's folder, kioku_platform.py). Only
     * packages listed in the manifest's queries are visible.
     */
    private static void writeAppVersions(Context ctx, String[] packages) {
        JSONObject found = new JSONObject();
        for (String p : packages) {
            try {
                PackageInfo info = ctx.getPackageManager().getPackageInfo(p, 0);
                found.put(p, info.versionName != null ? info.versionName : "");
            } catch (PackageManager.NameNotFoundException | JSONException e) {
                // not installed
            }
        }
        try {
            PickFileActivity.writeAtomically(new File(new Prefix(ctx).home, ".config/kioku"),
                    "apps.json", found.toString());
        } catch (IOException e) {
            Log.w(TAG, "Cannot save the app versions", e);
        }
    }

    /** ~/.config/kioku/all-files: "yes" or "no", whether All files access is allowed. */
    private static void writeAllFilesAccess(Context ctx) {
        boolean allowed = Build.VERSION.SDK_INT >= 30 ? Environment.isExternalStorageManager()
                : ctx.checkSelfPermission(android.Manifest.permission.WRITE_EXTERNAL_STORAGE)
                        == PackageManager.PERMISSION_GRANTED;
        try {
            PickFileActivity.writeAtomically(new File(new Prefix(ctx).home, ".config/kioku"),
                    "all-files", allowed ? "yes" : "no");
        } catch (IOException e) {
            Log.w(TAG, "Cannot save the All files access state", e);
        }
    }

    /** Android's Files app, opened at this app's home directory (HomeDocumentsProvider). */
    private static void openFiles(Context ctx) {
        String authority = ctx.getPackageName() + ".documents";
        Uri root = DocumentsContract.buildRootUri(authority, "home");
        try {
            start(ctx, new Intent(Intent.ACTION_VIEW).setDataAndType(root, DocumentsContract.Root.MIME_TYPE_ITEM));
        } catch (ActivityNotFoundException e) {
            Uri dir = DocumentsContract.buildDocumentUri(authority, new Prefix(ctx).home.getAbsolutePath());
            start(ctx, new Intent(Intent.ACTION_VIEW).setDataAndType(dir, DocumentsContract.Document.MIME_TYPE_DIR));
        }
    }

    private static void start(Context ctx, Intent i) {
        ctx.startActivity(i.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
    }
}
