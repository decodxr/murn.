use std::{
    env,
    fs,
    net::{SocketAddr, TcpStream},
    path::PathBuf,
    process::Command,
    thread,
    time::Duration,
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

fn start_backend_services() {
    // murn.service keeps the LAN/mobile endpoint alive (HTTPS when configured).
    let _ = Command::new("systemctl")
        .args(["--user", "start", "murn.service"])
        .status();

    // The desktop webview deliberately uses a loopback-only HTTP endpoint.
    // WebKit can reject a locally generated TLS certificate even when the
    // browser/phone trusts the same CA, which results in a blank native window.
    let _ = Command::new("systemctl")
        .args(["--user", "start", "murn-desktop-backend.service"])
        .status();
}

fn desktop_backend_ready() -> bool {
    let address: SocketAddr = format!("127.0.0.1:{DESKTOP_BACKEND_PORT}")
        .parse()
        .expect("valid murn desktop address");

    for _ in 0..40 {
        if TcpStream::connect_timeout(&address, Duration::from_millis(180)).is_ok() {
            return true;
        }
        thread::sleep(Duration::from_millis(180));
    }
    false
}

fn main() {
    tauri::Builder::default()
        .setup(|app| {
            start_backend_services();

            let url = if desktop_backend_ready() {
                WebviewUrl::External(configured_url().parse()?)
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
