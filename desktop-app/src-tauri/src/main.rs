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

    "http://127.0.0.1:7331".to_string()
}

fn start_backend_service() {
    let _ = Command::new("systemctl")
        .args(["--user", "start", "murn.service"])
        .status();
}

fn backend_ready() -> bool {
    let address: SocketAddr = "127.0.0.1:7331".parse().expect("valid murn address");
    for _ in 0..32 {
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
            start_backend_service();

            let url = if backend_ready() {
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
