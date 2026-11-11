# Native bridge review

The desktop package pins pywebview 6.2.1. Its published wheel
`pywebview-6.2.1-py3-none-any.whl` was inspected during implementation.

In that version, `webview/platforms/edgechromium.py` calls `inject_pywebview`
after `NavigationCompleted`; injection uses `ExecuteScriptAsync`. It does not
use `AddScriptToExecuteOnDocumentCreatedAsync` in the inspected Edge backend.
The backend attaches `WebMessageReceived` on its WebView2 control, with no frame
event handlers. However, `on_script_notify` does not check the message's Source
before dispatch, and `webview/util.py` resolves nested Python attributes without
an explicit function-name allowlist. Its API discovery also recursively visits
public object attributes. Therefore this app does not rely on iframe sandboxing
or script-injection behavior to restrict a custom Python bridge.

`desktop.py` passes **no `js_api` object** to `create_window` and never calls
`window.expose`. No app Python methods, window references, file-picker functions,
or settings functions are exposed to page JavaScript. pywebview's own internal
renderer machinery is still part of the third-party runtime; this statement
does not claim that WebView2 has no internal messaging channel.

Model pickers use native `webview.menu.Menu` / `MenuAction` callbacks. Those
callbacks call native file dialogs and POST an allowlisted setting to the
already-bound `127.0.0.1` port with environment proxies and HTTP redirects
disabled. Model paths never become JavaScript; a fixed main-document event only
refreshes displayed settings. Generated games remain in their separate sandboxed
iframe and receive no application-native API.

These are source-level findings and design constraints. A Windows build,
WebView2 frame behavior, dialogs, menus and renderer isolation still require
Windows validation. Linux source tests do not establish those runtime facts.
