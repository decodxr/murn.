use std::{
    env,
    fs,
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process::Command,
    thread,
    time::{Duration, SystemTime, UNIX_EPOCH},
};

use tauri::{WebviewUrl, WebviewWindowBuilder};

const DESKTOP_BACKEND_PORT: u16 = 7332;

fn configured_url() -> String {
    if let Ok(value) = env::var("MURN_DESKTOP_URL") {
        let trimmed = value.trim();
        if !trimmed.is_empty() {
            return trimmed.to_string();
        }
    }

    if let Ok(home) = env::var("HOME") {
        let path = PathBuf::from(home).join(".config/murn/desktop-url");
        if let Ok(value) = fs::read_to_string(path) {
            let trimmed = value.trim();
            if !trimmed.is_empty() {
                return trimmed.to_string();
            }
        }
    }

    format!("http://127.0.0.1:{DESKTOP_BACKEND_PORT}")
}

fn cache_busted_url() -> String {
    let base = configured_url();
    let separator = if base.contains('?') { '&' } else { '?' };
    let stamp = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_millis())
        .unwrap_or(0);
    format!("{base}{separator}murn_launch={stamp}")
}

fn apply_linux_webkit_workarounds() {
    #[cfg(target_os = "linux")]
    {
        // WebKitGTK can crash immediately on Wayland + NVIDIA when its DMABUF
        // renderer negotiates an unsupported buffer format. These are the
        // upstream Tauri-recommended workarounds for that exact Linux case.
        if env::var_os("__NV_DISABLE_EXPLICIT_SYNC").is_none() {
            env::set_var("__NV_DISABLE_EXPLICIT_SYNC", "1");
        }
        if env::var_os("WEBKIT_DISABLE_DMABUF_RENDERER").is_none() {
            env::set_var("WEBKIT_DISABLE_DMABUF_RENDERER", "1");
        }

        // Optional emergency fallback. The normal launcher does not enable it
        // because it disables accelerated compositing. Run with
        // MURN_WEBKIT_SAFE_MODE=1 only if the normal NVIDIA workaround still
        // crashes on a specific WebKit/driver combination.
        if env::var("MURN_WEBKIT_SAFE_MODE").ok().as_deref() == Some("1") {
            env::set_var("WEBKIT_DISABLE_COMPOSITING_MODE", "1");
        }
    }
}

fn start_backend_services() {
    let _ = Command::new("systemctl")
        .args(["--user", "start", "murn.service"])
        .status();

    let _ = Command::new("systemctl")
        .args(["--user", "start", "murn-desktop-backend.service"])
        .status();
}

fn desktop_backend_ready() -> bool {
    let address: SocketAddr = format!("127.0.0.1:{DESKTOP_BACKEND_PORT}")
        .parse()
        .expect("valid murn desktop address");

    for _ in 0..50 {
        if TcpStream::connect_timeout(&address, Duration::from_millis(180)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(180));
    }
    false
}

fn main() {
    // This must happen before GTK/WebKit is initialized.
    apply_linux_webkit_workarounds();

    tauri::Builder::default()
        .setup(|app| {
            start_backend_services();

            let url = if desktop_backend_ready() {
                WebviewUrl::External(cache_busted_url().parse()?)
            } else {
                WebviewUrl::App("offline.html".into())
            };

            WebviewWindowBuilder::new(app, "main", url)
                .title("murn.")
                .inner_size(1440.0, 900.0)
                .min_inner_size(960.0, 620.0)
                .resizable(true)
                .center()
                .build()?;

            Ok(())
        })
        .run(tauri::generate_context!())
        .expect("error while running murn. desktop");
}
