use serde_json::{json, Value};
use std::path::PathBuf;
use std::process::{Command, Stdio};
use tauri::{AppHandle, Manager};

#[tauri::command]
fn run_backend_command(app: AppHandle, command: String, payload: Value) -> Result<Value, String> {
    let runtime = match resolve_runtime_context(&app) {
        Ok(runtime) => runtime,
        Err(error) => {
            return Ok(command_failure(
                &command,
                "BACKEND_RUNTIME_UNAVAILABLE",
                error,
                json!({}),
            ))
        }
    };

    let mut process = Command::new(&runtime.python_executable);
    process
        .arg("-m")
        .arg("auto_mosaic.api.cli_main")
        .arg(&command)
        .current_dir(&runtime.backend_root)
        .env("PYTHONPATH", runtime.backend_root.join("src"))
        .env("AUTO_MOSAIC_BACKEND_ROOT", &runtime.backend_root)
        .env("AUTO_MOSAIC_DATA_DIR", &runtime.data_dir)
        .env("AUTO_MOSAIC_MODEL_DIR", &runtime.model_dir)
        .env("PYTHONUTF8", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped());

    if let Some(ffmpeg) = runtime.ffmpeg_path.as_ref() {
        process.env("AUTO_MOSAIC_FFMPEG_PATH", ffmpeg);
    }
    if let Some(ffprobe) = runtime.ffprobe_path.as_ref() {
        process.env("AUTO_MOSAIC_FFPROBE_PATH", ffprobe);
    }

    // Windows: CREATE_NO_WINDOW (0x08000000) を設定してコンソールウィンドウを出さない
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        process.creation_flags(0x08000000);
    }

    let mut child = match process.spawn() {
        Ok(child) => child,
        Err(error) => {
            return Ok(command_failure(
                &command,
                "BACKEND_SPAWN_FAILED",
                format!("Failed to spawn backend command: {error}"),
                json!({
                    "python_executable": runtime.python_executable,
                    "backend_root": runtime.backend_root,
                    "bundle_mode": runtime.bundle_mode,
                }),
            ))
        }
    };

    if let Some(mut stdin) = child.stdin.take() {
        use std::io::Write;
        if let Err(error) = stdin.write_all(payload.to_string().as_bytes()) {
            return Ok(command_failure(
                &command,
                "BACKEND_STDIN_FAILED",
                format!("Failed to write payload to backend stdin: {error}"),
                json!({}),
            ));
        }
    }

    let output = match child.wait_with_output() {
        Ok(output) => output,
        Err(error) => {
            return Ok(command_failure(
                &command,
                "BACKEND_OUTPUT_FAILED",
                format!("Failed to read backend output: {error}"),
                json!({}),
            ))
        }
    };

    if output.stdout.is_empty() {
        return Ok(command_failure(
            &command,
            "BACKEND_EMPTY_STDOUT",
            "The backend returned no JSON output.".to_string(),
            json!({
                "command": command,
                "stderr_tail": tail_utf8(&output.stderr, 400),
            }),
        ));
    }

    match serde_json::from_slice(&output.stdout) {
        Ok(value) => Ok(value),
        Err(primary_error) => {
            let lossy_stdout = String::from_utf8_lossy(&output.stdout).to_string();
            serde_json::from_str(&lossy_stdout).or_else(|fallback_error| {
                Ok(command_failure(
                    &command,
                    "BACKEND_JSON_PARSE_FAILED",
                    format!("Failed to parse backend JSON: {primary_error}; fallback: {fallback_error}"),
                    json!({
                        "command": command,
                        "exit_status": output.status.code(),
                        "stdout_preview": preview_utf8(&output.stdout, 400),
                        "stderr_tail": tail_utf8(&output.stderr, 400),
                        "stdout_len": output.stdout.len(),
                        "stderr_len": output.stderr.len(),
                    }),
                ))
            })
        }
    }
}

struct RuntimeContext {
    python_executable: String,
    backend_root: PathBuf,
    data_dir: PathBuf,
    model_dir: PathBuf,
    ffmpeg_path: Option<PathBuf>,
    ffprobe_path: Option<PathBuf>,
    bundle_mode: bool,
}

fn command_failure(command: &str, code: &str, message: String, details: Value) -> Value {
    json!({
        "ok": false,
        "command": command,
        "data": Value::Null,
        "error": {
            "code": code,
            "message": message,
            "details": details,
        },
        "warnings": [],
    })
}

fn preview_utf8(bytes: &[u8], max_chars: usize) -> String {
    let text = String::from_utf8_lossy(bytes).to_string();
    text.chars().take(max_chars).collect()
}

fn tail_utf8(bytes: &[u8], max_chars: usize) -> String {
    let text = String::from_utf8_lossy(bytes).to_string();
    let chars: Vec<char> = text.chars().collect();
    let start = chars.len().saturating_sub(max_chars);
    chars[start..].iter().collect()
}

fn resolve_runtime_context(app: &AppHandle) -> Result<RuntimeContext, String> {
    if let Ok(path) = std::env::var("AUTO_MOSAIC_BACKEND_ROOT") {
        let backend_root = PathBuf::from(path);
        let default_data_dir = app
            .path()
            .app_data_dir()
            .map(|path| path.join("runtime-data"))
            .unwrap_or_else(|_| backend_root.join("..").join("..").join("user-data"));
        return Ok(RuntimeContext {
            python_executable: resolve_python(None),
            backend_root: backend_root.clone(),
            data_dir: std::env::var("AUTO_MOSAIC_DATA_DIR")
                .map(PathBuf::from)
                .unwrap_or(default_data_dir),
            model_dir: std::env::var("AUTO_MOSAIC_MODEL_DIR")
                .map(PathBuf::from)
                .unwrap_or_else(|_| backend_root.join("..").join("..").join("models")),
            ffmpeg_path: std::env::var("AUTO_MOSAIC_FFMPEG_PATH").ok().map(PathBuf::from),
            ffprobe_path: std::env::var("AUTO_MOSAIC_FFPROBE_PATH").ok().map(PathBuf::from),
            bundle_mode: false,
        });
    }

    if let Ok(current_exe) = std::env::current_exe() {
        if let Some(exe_dir) = current_exe.parent() {
            let review_root = exe_dir.join("review-runtime");
            let backend_root = review_root.join("backend");
            if backend_root.join("src").exists() {
                let python_dir = review_root.join("python");
                let model_dir = review_root.join("models");
                let ffmpeg_dir = review_root.join("ffmpeg").join("bin");
                let data_dir = app
                    .path()
                    .app_data_dir()
                    .map_err(|error| format!("Failed to resolve app data directory: {error}"))?
                    .join("runtime-data");
                std::fs::create_dir_all(&data_dir)
                    .map_err(|error| format!("Failed to prepare app data directory: {error}"))?;

                return Ok(RuntimeContext {
                    python_executable: resolve_python(Some(&python_dir)),
                    backend_root,
                    data_dir,
                    model_dir,
                    ffmpeg_path: resolve_bundled_tool(&ffmpeg_dir, "ffmpeg"),
                    ffprobe_path: resolve_bundled_tool(&ffmpeg_dir, "ffprobe"),
                    bundle_mode: true,
                });
            }
        }
    }

    if let Ok(resource_dir) = app.path().resource_dir() {
        let review_root = resource_dir.join("review-runtime");
        let backend_root = review_root.join("backend");
        if backend_root.join("src").exists() {
            let python_dir = review_root.join("python");
            let model_dir = review_root.join("models");
            let ffmpeg_dir = review_root.join("ffmpeg").join("bin");
            let data_dir = app
                .path()
                .app_data_dir()
                .map_err(|error| format!("Failed to resolve app data directory: {error}"))?
                .join("runtime-data");
            std::fs::create_dir_all(&data_dir)
                .map_err(|error| format!("Failed to prepare app data directory: {error}"))?;

            return Ok(RuntimeContext {
                python_executable: resolve_python(Some(&python_dir)),
                backend_root,
                data_dir,
                model_dir,
                ffmpeg_path: resolve_bundled_tool(&ffmpeg_dir, "ffmpeg"),
                ffprobe_path: resolve_bundled_tool(&ffmpeg_dir, "ffprobe"),
                bundle_mode: true,
            });
        }
    }

    // Dev mode: CARGO_MANIFEST_DIR is set at compile time and always points to
    // apps/desktop/src-tauri.  From there, ../../backend resolves to apps/backend.
    let manifest_dir = PathBuf::from(env!("CARGO_MANIFEST_DIR"));
    let manifest_backend = manifest_dir.join("..").join("..").join("backend");
    if manifest_backend.join("src").exists() {
        let workspace_root = manifest_dir.join("..").join("..").join("..");
        let venv_scripts = manifest_backend.join(".venv").join(if cfg!(target_os = "windows") {
            "Scripts"
        } else {
            "bin"
        });
        let venv_python = venv_scripts.join(if cfg!(target_os = "windows") {
            "python.exe"
        } else {
            "python3"
        });
        let python_dir = if venv_python.exists() {
            Some(venv_scripts)
        } else {
            None
        };
        return Ok(RuntimeContext {
            python_executable: resolve_python(python_dir.as_ref()),
            backend_root: manifest_backend,
            data_dir: workspace_root.join("apps").join("user-data"),
            model_dir: workspace_root.join("models"),
            ffmpeg_path: None,
            ffprobe_path: None,
            bundle_mode: false,
        });
    }

    let current = std::env::current_dir().map_err(|error| error.to_string())?;
    let local = current.join("..").join("backend");
    if local.join("src").exists() {
        return Ok(RuntimeContext {
            python_executable: resolve_python(None),
            backend_root: local.clone(),
            data_dir: current.join("..").join("..").join("user-data"),
            model_dir: current.join("..").join("..").join("models"),
            ffmpeg_path: None,
            ffprobe_path: None,
            bundle_mode: false,
        });
    }

    Err(String::from(
        "Could not resolve the backend runtime. Prepare the review runtime or set AUTO_MOSAIC_BACKEND_ROOT.",
    ))
}

fn resolve_python(bundled_python_dir: Option<&PathBuf>) -> String {
    if let Ok(path) = std::env::var("AUTO_MOSAIC_PYTHON") {
        return path;
    }

    if let Some(root) = bundled_python_dir {
        let bundled = root.join(if cfg!(target_os = "windows") {
            "python.exe"
        } else {
            "python3"
        });
        if bundled.exists() {
            return bundled.to_string_lossy().to_string();
        }
    }

    String::from("python")
}

fn resolve_bundled_tool(dir: &PathBuf, tool_name: &str) -> Option<PathBuf> {
    let candidates = if cfg!(target_os = "windows") {
        vec![
            dir.join(format!("{tool_name}.exe")),
            dir.join(format!("{tool_name}.cmd")),
            dir.join(format!("{tool_name}.bat")),
        ]
    } else {
        vec![dir.join(tool_name)]
    };

    candidates.into_iter().find(|candidate| candidate.exists())
}

#[tauri::command]
fn reveal_path_in_explorer(path: String) -> Result<(), String> {
    #[cfg(target_os = "windows")]
    {
        use std::os::windows::process::CommandExt;
        std::process::Command::new("explorer.exe")
            .arg(format!("/select,{path}"))
            .creation_flags(0x08000000)
            .spawn()
            .map_err(|error| format!("Failed to open Explorer: {error}"))?;
    }
    #[cfg(target_os = "macos")]
    {
        std::process::Command::new("open")
            .args(["-R", &path])
            .spawn()
            .map_err(|error| format!("Failed to open Finder: {error}"))?;
    }
    #[cfg(not(any(target_os = "windows", target_os = "macos")))]
    {
        let parent = std::path::Path::new(&path)
            .parent()
            .map(|p| p.to_string_lossy().to_string())
            .unwrap_or_else(|| path.clone());
        std::process::Command::new("xdg-open")
            .arg(&parent)
            .spawn()
            .map_err(|error| format!("Failed to open file manager: {error}"))?;
    }
    Ok(())
}

pub fn run() {
    tauri::Builder::default()
        .plugin(tauri_plugin_dialog::init())
        .invoke_handler(tauri::generate_handler![run_backend_command, reveal_path_in_explorer])
        .run(tauri::generate_context!())
        .expect("error while running tauri application");
}

#[cfg(test)]
mod tests {
    use super::{preview_utf8, tail_utf8};

    #[test]
    fn preview_utf8_truncates_from_the_front() {
        assert_eq!(preview_utf8("abcdef".as_bytes(), 4), "abcd");
    }

    #[test]
    fn tail_utf8_truncates_from_the_back() {
        assert_eq!(tail_utf8("abcdef".as_bytes(), 4), "cdef");
    }
}
