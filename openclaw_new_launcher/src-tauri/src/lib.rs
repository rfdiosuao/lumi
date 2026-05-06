use std::io::BufRead;
use std::io::Write;
use std::sync::atomic::{AtomicU16, Ordering};
use std::process::Command;
#[cfg(windows)]
use std::os::windows::process::CommandExt;
use tauri::Manager;
use tauri::path::BaseDirectory;

static BRIDGE_PORT: AtomicU16 = AtomicU16::new(0);
static BRIDGE_TOKEN: std::sync::Mutex<Option<String>> = std::sync::Mutex::new(None);
static BRIDGE_START_LOCK: std::sync::Mutex<()> = std::sync::Mutex::new(());

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x08000000;

fn bridge_python_exe(py_path: &std::path::Path) -> std::path::PathBuf {
    if let Some(bridge_dir) = py_path.parent() {
        let local_python = bridge_dir.join("python.exe");
        if local_python.exists() {
            return local_python;
        }

        if let Some(resource_dir) = bridge_dir.parent() {
            let runtime_python = resource_dir.join("python-runtime").join("python.exe");
            if runtime_python.exists() {
                return runtime_python;
            }
        }
    }

    std::path::PathBuf::from("python")
}

fn spawn_bridge(py_path: &std::path::Path) -> Result<String, String> {
    if !py_path.exists() {
        return Err(format!("bridge.py 未找到: {}", py_path.display()));
    }

    let mut child_cmd = Command::new(bridge_python_exe(py_path));
    child_cmd.arg(py_path);
    child_cmd.env("PYTHONUTF8", "1");
    child_cmd.env("PYTHONIOENCODING", "utf-8");
    child_cmd.env("PYTHONDONTWRITEBYTECODE", "1");
    child_cmd.stdout(std::process::Stdio::piped());
    child_cmd.stderr(std::process::Stdio::piped());
    #[cfg(windows)]
    child_cmd.creation_flags(CREATE_NO_WINDOW);
    let mut child = child_cmd
        .spawn()
        .map_err(|e| format!("启动 Python bridge 失败: {}", e))?;

    let stdout = child.stdout.take().ok_or("无法获取 bridge 输出")?;
    let mut reader = std::io::BufReader::new(stdout);
    let mut line = String::new();

    loop {
        reader.read_line(&mut line).map_err(|e| e.to_string())?;
        if let Some(port_str) = line.trim().strip_prefix("BRIDGE_PORT=") {
            if let Ok(port) = port_str.parse::<u16>() {
                BRIDGE_PORT.store(port, Ordering::Relaxed);
                break;
            }
        }
        if line.is_empty() {
            return Err("无法获取 bridge 端口".to_string());
        }
        line.clear();
    }

    line.clear();
    loop {
        reader.read_line(&mut line).map_err(|e| e.to_string())?;
        if let Some(token) = line.trim().strip_prefix("BRIDGE_TOKEN=") {
            if let Ok(mut guard) = BRIDGE_TOKEN.lock() {
                *guard = Some(token.to_string());
            }
            break;
        }
        if line.is_empty() {
            break;
        }
        line.clear();
    }

    std::thread::spawn(move || {
        let stderr = child.stderr.take();
        if let Some(stderr) = stderr {
            let mut reader = std::io::BufReader::new(stderr);
            let mut err_line = String::new();
            while reader.read_line(&mut err_line).ok() > Some(0) {
                eprintln!("[bridge stderr] {}", err_line.trim());
                err_line.clear();
            }
        }
        let _ = child.wait();
    });

    Ok(format!("Bridge started on port {}", BRIDGE_PORT.load(Ordering::Relaxed)))
}

#[tauri::command]
fn get_bridge_port() -> u16 {
    BRIDGE_PORT.load(Ordering::Relaxed)
}

#[tauri::command]
fn get_portable_base_path() -> Result<String, String> {
    if cfg!(debug_assertions) {
        return std::env::current_dir()
            .map(|path| path.to_string_lossy().to_string())
            .map_err(|e| format!("get current directory failed: {}", e));
    }

    let exe_path = std::env::current_exe()
        .map_err(|e| format!("get executable path failed: {}", e))?;
    let exe_dir = exe_path
        .parent()
        .ok_or_else(|| "executable directory not found".to_string())?;
    Ok(exe_dir.to_string_lossy().to_string())
}

#[tauri::command]
async fn start_bridge(app: tauri::AppHandle) -> Result<String, String> {
    let existing_port = BRIDGE_PORT.load(Ordering::Relaxed);
    if existing_port > 0 {
        return Ok(format!("Bridge already started on port {}", existing_port));
    }

    let _guard = BRIDGE_START_LOCK
        .lock()
        .map_err(|_| "Bridge 启动锁已损坏".to_string())?;
    let existing_port = BRIDGE_PORT.load(Ordering::Relaxed);
    if existing_port > 0 {
        return Ok(format!("Bridge already started on port {}", existing_port));
    }

    // Production bundles may place resources under either `python/` or `_up_/python/`
    // depending on how paths outside src-tauri are mapped by the bundler.
    for rel_path in ["python/bridge.py", "_up_/python/bridge.py"] {
        if let Ok(resource_py_path) = app.path().resolve(rel_path, BaseDirectory::Resource) {
            if resource_py_path.exists() {
                return spawn_bridge(&resource_py_path);
            }
        }
    }

    // Release binaries run next to the bundled `_up_` directory before installation.
    if let Ok(exe_path) = std::env::current_exe() {
        if let Some(exe_dir) = exe_path.parent() {
            for rel_path in ["python/bridge.py", "_up_/python/bridge.py"] {
                let py_path = exe_dir.join(rel_path);
                if py_path.exists() {
                    return spawn_bridge(&py_path);
                }
            }
        }
    }

    // Fall back to project-relative path (dev mode)
    let py_path = std::env::current_dir()
        .map_err(|e| format!("获取当前目录失败: {}", e))?
        .join("python")
        .join("bridge.py");

    spawn_bridge(&py_path)
}

#[tauri::command]
async fn proxy_request(app: tauri::AppHandle, path: String, method: String, body: Option<String>) -> Result<String, String> {
    let mut port = BRIDGE_PORT.load(Ordering::Relaxed);
    if port == 0 {
        start_bridge(app).await?;
        port = BRIDGE_PORT.load(Ordering::Relaxed);
        if port == 0 {
            return Err("Bridge 未启动".to_string());
        }
    }

    let url = format!("http://127.0.0.1:{}/{}", port, path.trim_start_matches('/'));
    let client = reqwest::Client::new();

    let mut req = client.request(
        match method.as_str() {
            "GET" => reqwest::Method::GET,
            "POST" => reqwest::Method::POST,
            "PUT" => reqwest::Method::PUT,
            _ => return Err(format!("不支持的方法: {}", method)),
        },
        &url,
    );

    if let Some(b) = body {
        req = req.body(b).header("Content-Type", "application/json");
    }

    if let Ok(guard) = BRIDGE_TOKEN.lock() {
        if let Some(ref token) = *guard {
            req = req.header("X-Bridge-Token", token.as_str());
        }
    }

    let resp = req.send().await.map_err(|e| format!("请求失败: {}", e))?;
    let status = resp.status();
    let text = resp.text().await.map_err(|e| format!("读取响应失败: {}", e))?;
    if !status.is_success() {
        return Err(format!("[{}] {}", status.as_u16(), text));
    }
    Ok(text)
}

#[tauri::command]
async fn export_log(app: tauri::AppHandle, content: String) -> Result<String, String> {
    let mut base_dir = if let Ok(exe_path) = std::env::current_exe() {
        exe_path
            .parent()
            .map(|path| path.to_path_buf())
            .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from(".")))
    } else {
        std::env::current_dir().unwrap_or_else(|_| std::path::PathBuf::from("."))
    };

    if cfg!(debug_assertions) {
        if let Ok(app_data) = app.path().app_data_dir() {
            base_dir = app_data;
        }
    }

    let log_dir = base_dir.join("data").join("logs");
    std::fs::create_dir_all(&log_dir).map_err(|e| format!("创建日志目录失败: {}", e))?;

    let timestamp = chrono_like_timestamp();
    let path = log_dir.join(format!("openclaw-log-{}.txt", timestamp));
    let mut file = std::fs::File::create(&path).map_err(|e| format!("创建日志文件失败: {}", e))?;
    file.write_all(content.as_bytes())
        .map_err(|e| format!("写入日志失败: {}", e))?;
    Ok(path.to_string_lossy().to_string())
}

#[tauri::command]
async fn open_path(path: String) -> Result<(), String> {
    let trimmed = path.trim();
    if trimmed.is_empty() {
        return Err("路径为空".to_string());
    }

    let target = std::path::PathBuf::from(trimmed);
    if !target.exists() {
        return Err(format!("路径不存在: {}", target.display()));
    }

    #[cfg(windows)]
    {
        let mut command = Command::new("explorer.exe");
        command.arg(&target);
        command.creation_flags(CREATE_NO_WINDOW);
        command
            .spawn()
            .map_err(|e| format!("打开目录失败: {}", e))?;
        return Ok(());
    }

    #[cfg(target_os = "macos")]
    {
        Command::new("open")
            .arg(&target)
            .spawn()
            .map_err(|e| format!("打开目录失败: {}", e))?;
        return Ok(());
    }

    #[cfg(all(unix, not(target_os = "macos")))]
    {
        Command::new("xdg-open")
            .arg(&target)
            .spawn()
            .map_err(|e| format!("打开目录失败: {}", e))?;
        return Ok(());
    }
}

fn chrono_like_timestamp() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let seconds = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|duration| duration.as_secs())
        .unwrap_or(0);
    format!("{}", seconds)
}

#[cfg_attr(mobile, tauri::mobile_entry_point)]
pub fn run() {
    tauri::Builder::default()
        .setup(|app| {
            if cfg!(debug_assertions) {
                app.handle().plugin(
                    tauri_plugin_log::Builder::default()
                        .level(log::LevelFilter::Info)
                        .build(),
                )?;
            }
            app.handle().plugin(tauri_plugin_shell::init())?;
            // Start bridge on app launch
            let app_handle = app.handle().clone();
            tauri::async_runtime::spawn(async move {
                if let Err(e) = start_bridge(app_handle).await {
                    eprintln!("[Bridge startup error] {}", e);
                }
            });
            Ok(())
        })
        .invoke_handler(tauri::generate_handler![
            get_bridge_port,
            get_portable_base_path,
            start_bridge,
            proxy_request,
            export_log,
            open_path,
        ])
        .run(tauri::generate_context!())
        .expect("error while running tauri");
}
