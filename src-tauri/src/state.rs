use tokio::process::ChildStdin;
use tokio::sync::Mutex;

pub struct WorkerHandle {
    pub run_id: String,
    pub stdin: Mutex<ChildStdin>,
}

#[derive(Default)]
pub struct AppState {
    pub worker: Mutex<Option<WorkerHandle>>,
}
