// _kioku_android: the bridge between Kioku's Python code and its Java side
// (io.ankidesk.kioku.KiokuBridge).
//
//   call(method: str, args_json: str) -> str   KiokuBridge.call(), any thread
//   view_handle(id: int) -> int                a global ref to the web view's
//                                              View, for QWindow.fromWinId()
//   set_handler(callable)                      receives KiokuBridge events (a
//                                              JSON string) on Qt's main thread
//   set_request_handler(callable)              answers KiokuBridge requests (a
//                                              JSON string in, a string out) on
//                                              Qt's main thread while the Java
//                                              side waits

#include <Python.h>

#include <QCoreApplication>
#include <QJniEnvironment>
#include <QJniObject>
#include <QMetaObject>
#include <QSemaphore>
#include <QString>

#include <memory>

#include <android/log.h>

static const char *BRIDGE = "io/ankidesk/kioku/KiokuBridge";
static PyObject *event_handler = nullptr;
static PyObject *request_handler = nullptr;

static void native_event(JNIEnv *env, jclass, jstring json) {
    const char *utf8 = env->GetStringUTFChars(json, nullptr);
    QByteArray copy(utf8);
    env->ReleaseStringUTFChars(json, utf8);
    QCoreApplication *app = QCoreApplication::instance();
    if (!app) {
        __android_log_print(ANDROID_LOG_WARN, "Kioku", "event before the app exists");
        return;
    }
    QMetaObject::invokeMethod(app, [copy]() {
        PyGILState_STATE gil = PyGILState_Ensure();
        if (event_handler) {
            PyObject *result = PyObject_CallFunction(event_handler, "s", copy.constData());
            if (!result) {
                PyErr_Print();
            }
            Py_XDECREF(result);
        }
        PyGILState_Release(gil);
    }, Qt::QueuedConnection);
}

struct Request {
    QSemaphore done;
    QByteArray reply;
};

// Queued behind the events posted before it, so it sees them handled first.
// On a timeout the Java side gets null, and the request still runs later.
static jstring native_request(JNIEnv *env, jclass, jstring json, jint timeout_ms) {
    const char *utf8 = env->GetStringUTFChars(json, nullptr);
    QByteArray copy(utf8);
    env->ReleaseStringUTFChars(json, utf8);
    QCoreApplication *app = QCoreApplication::instance();
    if (!app) {
        return nullptr;
    }
    auto request = std::make_shared<Request>();
    QMetaObject::invokeMethod(app, [copy, request]() {
        PyGILState_STATE gil = PyGILState_Ensure();
        if (request_handler) {
            PyObject *result = PyObject_CallFunction(request_handler, "s", copy.constData());
            if (result && PyUnicode_Check(result)) {
                Py_ssize_t size;
                const char *text = PyUnicode_AsUTF8AndSize(result, &size);
                if (text) {
                    request->reply = QByteArray(text, size);
                }
            }
            if (PyErr_Occurred()) {
                PyErr_Print();
            }
            Py_XDECREF(result);
        }
        PyGILState_Release(gil);
        request->done.release();
    }, Qt::QueuedConnection);
    if (!request->done.tryAcquire(1, timeout_ms)) {
        return nullptr;
    }
    return env->NewStringUTF(request->reply.constData());
}

static PyObject *py_call(PyObject *, PyObject *args) {
    const char *method;
    const char *json;
    if (!PyArg_ParseTuple(args, "ss", &method, &json)) {
        return nullptr;
    }
    QString result;
    // the Java side may wait for Android's UI thread
    Py_BEGIN_ALLOW_THREADS
    QJniObject r = QJniObject::callStaticMethod<jstring>(
        BRIDGE, "call", "(Ljava/lang/String;Ljava/lang/String;)Ljava/lang/String;",
        QJniObject::fromString(QString::fromUtf8(method)).object<jstring>(),
        QJniObject::fromString(QString::fromUtf8(json)).object<jstring>());
    result = r.toString();
    Py_END_ALLOW_THREADS
    QByteArray utf8 = result.toUtf8();
    return PyUnicode_FromStringAndSize(utf8.constData(), utf8.size());
}

static PyObject *py_view_handle(PyObject *, PyObject *args) {
    int id;
    if (!PyArg_ParseTuple(args, "i", &id)) {
        return nullptr;
    }
    QJniObject view = QJniObject::callStaticObjectMethod(
        BRIDGE, "getView", "(I)Landroid/view/View;", jint(id));
    if (!view.isValid()) {
        Py_RETURN_NONE;
    }
    QJniEnvironment env;
    jobject global = env->NewGlobalRef(view.object());
    return PyLong_FromVoidPtr(global);
}

static PyObject *py_set_handler(PyObject *, PyObject *args) {
    PyObject *handler;
    if (!PyArg_ParseTuple(args, "O", &handler)) {
        return nullptr;
    }
    Py_XINCREF(handler);
    Py_XSETREF(event_handler, handler);
    Py_RETURN_NONE;
}

static PyObject *py_set_request_handler(PyObject *, PyObject *args) {
    PyObject *handler;
    if (!PyArg_ParseTuple(args, "O", &handler)) {
        return nullptr;
    }
    Py_XINCREF(handler);
    Py_XSETREF(request_handler, handler);
    Py_RETURN_NONE;
}

static PyMethodDef methods[] = {
    {"call", py_call, METH_VARARGS, "Call KiokuBridge.call(method, args_json)."},
    {"view_handle", py_view_handle, METH_VARARGS, "Global ref to a web view's View."},
    {"set_handler", py_set_handler, METH_VARARGS, "Set the event callback."},
    {"set_request_handler", py_set_request_handler, METH_VARARGS, "Set the request callback."},
    {nullptr, nullptr, 0, nullptr},
};

static PyModuleDef module = {
    PyModuleDef_HEAD_INIT, "_kioku_android", nullptr, -1, methods,
};

extern "C" PyObject *PyInit__kioku_android(void) {
    QJniEnvironment env;
    const JNINativeMethod natives[] = {
        {"nativeEvent", "(Ljava/lang/String;)V", reinterpret_cast<void *>(native_event)},
        {"nativeRequest", "(Ljava/lang/String;I)Ljava/lang/String;",
         reinterpret_cast<void *>(native_request)},
    };
    if (!env.registerNativeMethods(BRIDGE, natives, 2)) {
        PyErr_SetString(PyExc_ImportError, "cannot register KiokuBridge's native methods");
        return nullptr;
    }
    return PyModule_Create(&module);
}
