use std::sync::Mutex;
use std::process::{Command, Stdio, Child};
use std::io::{BufReader, BufRead};
use std::time::{Duration, Instant};
use serde_json::{json, Value};
use tauri::State;

pub struct SidecarState {
    pub port: u16,
    pub running: bool,
    pub child: Option<Child>,
}

#[tauri::command]
fn bm_ping() -> &'static str {
    "pong"
}

#[tauri::command]
fn bm_get_state(key: String) -> Value {
    json!({ "key": key, "stub": true })
}

#[tauri::command]
fn bm_sidecar_start(state: State<Mutex<SidecarState>>) -> Result<u16, String> {
    let mut st = state.lock().map_err(|e| e.to_string())?;

    if st.running {
        return Ok(st.port);
    }

    let port = st.port;

    let mut child = Command::new("python")
        .args(["-m", "browsermind_core.api.sidecar", "--port", &port.to_string()])
        .stdout(Stdio::piped())
        .stderr(Stdio::null())
        .spawn()
        .map_err(|e| format!("failed to spawn sidecar: {e}"))?;

    let stdout = child.stdout.take().ok_or("no stdout on child")?;
    let reader = BufReader::new(stdout);

    let deadline = Instant::now() + Duration::from_secs(15);
    let mut ready = false;

    for line in reader.lines() {
        if Instant::now() > deadline {
            let _ = child.kill();
            return Err("sidecar startup timed out".into());
        }
        match line {
            Ok(l) if l.starts_with("READY:") => {
                ready = true;
                break;
            }
            Ok(_) => continue,
            Err(e) => {
                let _ = child.kill();
                return Err(format!("error reading sidecar stdout: {e}"));
            }
        }
    }

    if !ready {
        let _ = child.kill();
        return Err("sidecar exited without READY line".into());
    }

    st.running = true;
    st.child = Some(child);
    Ok(port)
}

#[tauri::command]
fn bm_sidecar_status(state: State<Mutex<SidecarState>>) -> Value {
    match state.lock() {
        Ok(st) => json!({ "running": st.running, "port": st.port }),
        Err(_) => json!({ "running": false, "port": 0 }),
    }
}

#[tauri::command]
fn bm_sidecar_stop(state: State<Mutex<SidecarState>>) -> Result<(), String> {
    let mut st = state.lock().map_err(|e| e.to_string())?;

    if let Some(mut child) = st.child.take() {
        let _ = child.kill();
    }
    st.running = false;
    Ok(())
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_shell::init())
        .manage(Mutex::new(SidecarState {
            port: 8766,
            running: false,
            child: None,
        }))
        .invoke_handler(tauri::generate_handler![
            bm_ping,
            bm_get_state,
            bm_sidecar_start,
            bm_sidecar_status,
            bm_sidecar_stop,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}
