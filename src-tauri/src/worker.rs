use std::path::{Path, PathBuf};
use std::process::Stdio;

use anyhow::{anyhow, Context, Result};
use serde_json::{json, Value};
use tauri::{AppHandle, Emitter, Manager};
use tokio::io::{AsyncBufReadExt, AsyncWriteExt, BufReader};
use tokio::process::{ChildStderr, ChildStdout, Command};

use crate::state::{AppState, WorkerHandle};

pub const EVENT_CHANNEL: &str = "sync-event";
pub const EXIT_CHANNEL: &str = "worker-exit";

#[cfg(windows)]
const CREATE_NO_WINDOW: u32 = 0x0800_0000;

pub async fn spawn_subcommand(
    app: AppHandle,
    subcmd: &str,
    extra_args: &[&str],
) -> Result<String> {
    let (python, backend_dir) = resolve_python_command()?;
    let run_id = uuid::Uuid::new_v4().to_string();

    tracing::info!(
        target: "myrumae::worker",
        python = %python.display(),
        cwd = %backend_dir.display(),
        subcmd,
        extra = ?extra_args,
        run_id = %run_id,
        "spawning python worker"
    );

    let mut cmd = Command::new(&python);
    cmd.arg("-m").arg("app.cli").arg(subcmd);
    for a in extra_args {
        cmd.arg(a);
    }
    cmd.current_dir(&backend_dir)
        .env("PYTHONUNBUFFERED", "1")
        .env("PYTHONIOENCODING", "utf-8")
        .env("MYRUMAE_RUN_ID", &run_id)
        .stdin(Stdio::piped())
        .stdout(Stdio::piped())
        .stderr(Stdio::piped())
        .kill_on_drop(true);

    if std::env::var("LOG_LEVEL").is_err() {
        cmd.env("LOG_LEVEL", "INFO");
    }

    #[cfg(windows)]
    cmd.creation_flags(CREATE_NO_WINDOW);

    let mut child = cmd
        .spawn()
        .with_context(|| format!("failed to spawn `{} -m app.cli {}`", python.display(), subcmd))?;

    let stdin = child.stdin.take().ok_or_else(|| anyhow!("missing child stdin"))?;
    let stdout = child.stdout.take().ok_or_else(|| anyhow!("missing child stdout"))?;
    let stderr = child.stderr.take().ok_or_else(|| anyhow!("missing child stderr"))?;

    {
        let state = app.state::<AppState>();
        let mut guard = state.worker.lock().await;
        *guard = Some(WorkerHandle {
            run_id: run_id.clone(),
            stdin: tokio::sync::Mutex::new(stdin),
        });
    }

    let app_for_out = app.clone();
    let run_id_out = run_id.clone();
    tokio::spawn(async move {
        forward_stdout(app_for_out, stdout, run_id_out).await;
    });

    tokio::spawn(async move {
        forward_stderr(stderr).await;
    });

    let app_for_wait = app.clone();
    let run_id_wait = run_id.clone();
    tokio::spawn(async move {
        let code = match child.wait().await {
            Ok(status) => status.code().unwrap_or(-1),
            Err(e) => {
                tracing::error!(error = %e, "child wait failed");
                -1
            }
        };
        let _ = app_for_wait.emit(
            EXIT_CHANNEL,
            json!({ "run_id": run_id_wait, "code": code }),
        );
        let state = app_for_wait.state::<AppState>();
        let mut guard = state.worker.lock().await;
        if guard.as_ref().map(|h| h.run_id == run_id_wait).unwrap_or(false) {
            *guard = None;
        }
    });

    Ok(run_id)
}

pub async fn write_cancel(app: &AppHandle) -> Result<()> {
    let state = app.state::<AppState>();
    let guard = state.worker.lock().await;
    let Some(handle) = guard.as_ref() else {
        return Err(anyhow!("no worker running"));
    };
    let mut stdin = handle.stdin.lock().await;
    stdin.write_all(b"cancel\n").await?;
    stdin.flush().await?;
    Ok(())
}

async fn forward_stdout(app: AppHandle, stdout: ChildStdout, run_id: String) {
    let mut lines = BufReader::new(stdout).lines();
    loop {
        match lines.next_line().await {
            Ok(Some(line)) => {
                let trimmed = line.trim();
                if trimmed.is_empty() {
                    continue;
                }
                match serde_json::from_str::<Value>(trimmed) {
                    Ok(v) => {
                        if let Err(e) = app.emit(EVENT_CHANNEL, &v) {
                            tracing::error!(error = %e, "emit sync-event failed");
                        }
                    }
                    Err(_) => {
                        tracing::warn!(line = %trimmed, "non-json stdout line");
                        let wrapped = json!({
                            "type": "raw-line",
                            "ts": chrono_now_iso(),
                            "level": "warn",
                            "payload": { "line": trimmed, "run_id": run_id }
                        });
                        let _ = app.emit(EVENT_CHANNEL, &wrapped);
                    }
                }
            }
            Ok(None) => break,
            Err(e) => {
                tracing::error!(error = %e, "stdout read error");
                break;
            }
        }
    }
}

async fn forward_stderr(stderr: ChildStderr) {
    let mut lines = BufReader::new(stderr).lines();
    while let Ok(Some(line)) = lines.next_line().await {
        tracing::debug!(target: "myrumae::worker::stderr", "{line}");
    }
}

fn resolve_python_command() -> Result<(PathBuf, PathBuf)> {
    let backend_dir = match std::env::var_os("MYRUMAE_BACKEND_DIR") {
        Some(v) => PathBuf::from(v),
        None => default_backend_dir(),
    };
    if !backend_dir.exists() {
        return Err(anyhow!(
            "backend dir not found: {}",
            backend_dir.display()
        ));
    }

    let python = resolve_python_exe(&backend_dir)?;
    Ok((python, backend_dir))
}

fn default_backend_dir() -> PathBuf {
    PathBuf::from(env!("CARGO_MANIFEST_DIR"))
        .parent()
        .map(|p| p.join("backend"))
        .unwrap_or_else(|| PathBuf::from("backend"))
}

fn resolve_python_exe(backend_dir: &Path) -> Result<PathBuf> {
    if let Some(v) = std::env::var_os("MYRUMAE_PYTHON") {
        return Ok(PathBuf::from(v));
    }
    let candidates = [
        backend_dir.join(".venv").join("Scripts").join("python.exe"),
        backend_dir
            .parent()
            .map(|p| p.join(".venv").join("Scripts").join("python.exe"))
            .unwrap_or_default(),
    ];
    for c in candidates.iter() {
        if c.exists() {
            return Ok(c.clone());
        }
    }
    Ok(PathBuf::from("python"))
}

fn chrono_now_iso() -> String {
    use std::time::{SystemTime, UNIX_EPOCH};
    let secs = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.as_secs_f64())
        .unwrap_or(0.0);
    format!("epoch:{:.3}", secs)
}
