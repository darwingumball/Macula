use anyhow::{anyhow, Context, Result};
use serde::{Deserialize, Serialize};
use ssh2::Session;
use std::io::{Read, Write};
use std::net::TcpStream;
use std::path::Path;
use tauri::{AppHandle, Emitter};

#[derive(Serialize)]
pub struct CommandResult {
    pub exit_code: i32,
    pub stdout: String,
    pub stderr: String,
}

#[derive(Deserialize, Clone)]
#[serde(tag = "type")]
pub enum SshAuth {
    Password { password: String },
    Key {
        key_path: String,
        #[serde(default)]
        passphrase: Option<String>,
    },
}

#[derive(Serialize, Clone)]
pub struct UploadProgress {
    pub file: String,
    pub bytes_sent: u64,
    pub total_bytes: u64,
    pub percent: f32,
}

#[derive(Serialize)]
pub struct TestConnectionResult {
    pub ok: bool,
    pub message: String,
    pub server_banner: Option<String>,
    pub fingerprint: Option<String>,
}

fn connect_session(host: &str, port: u16, username: &str, auth: &SshAuth) -> Result<Session> {
    let addr = format!("{host}:{port}");
    let tcp = TcpStream::connect(&addr)
        .with_context(|| format!("Cannot reach {addr}"))?;
    tcp.set_read_timeout(Some(std::time::Duration::from_secs(30)))?;

    let mut sess = Session::new()?;
    sess.set_tcp_stream(tcp);
    sess.handshake().context("SSH handshake failed")?;

    match auth {
        SshAuth::Password { password } => {
            sess.userauth_password(username, password)
                .context("Password authentication failed")?;
        }
        SshAuth::Key { key_path, passphrase } => {
            let key = Path::new(key_path);
            sess.userauth_pubkey_file(
                username,
                None,
                key,
                passphrase.as_deref(),
            )
            .context("Key authentication failed")?;
        }
    }

    if !sess.authenticated() {
        return Err(anyhow!("Authentication failed"));
    }
    Ok(sess)
}

#[tauri::command]
pub async fn test_ssh_connection(
    host: String,
    port: u16,
    username: String,
    auth: SshAuth,
) -> Result<TestConnectionResult, String> {
    tokio::task::spawn_blocking(move || {
        match connect_session(&host, port, &username, &auth) {
            Ok(sess) => {
                let banner = sess.banner().map(|s| s.to_string());
                let fingerprint = sess
                    .host_key_hash(ssh2::HashType::Sha256)
                    .map(|bytes| {
                        use base64::Engine;
                        format!(
                            "SHA256:{}",
                            base64::engine::general_purpose::STANDARD_NO_PAD.encode(bytes)
                        )
                    });
                Ok(TestConnectionResult {
                    ok: true,
                    message: format!("Connected to {host}:{port} as {username}"),
                    server_banner: banner,
                    fingerprint,
                })
            }
            Err(e) => Ok(TestConnectionResult {
                ok: false,
                message: e.to_string(),
                server_banner: None,
                fingerprint: None,
            }),
        }
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e: anyhow::Error| e.to_string())
}

#[tauri::command]
pub async fn ssh_run_command(
    host: String,
    port: u16,
    username: String,
    auth: SshAuth,
    command: String,
) -> Result<CommandResult, String> {
    tokio::task::spawn_blocking(move || {
        let sess = connect_session(&host, port, &username, &auth)
            .map_err(|e| e.to_string())?;
        let mut channel = sess.channel_session().map_err(|e| e.to_string())?;
        channel.exec(&command).map_err(|e| e.to_string())?;

        let mut stdout = String::new();
        let mut stderr = String::new();
        channel.read_to_string(&mut stdout).ok();
        channel.stderr().read_to_string(&mut stderr).ok();
        channel.wait_close().ok();
        let exit_code = channel.exit_status().unwrap_or(-1);

        Ok(CommandResult { exit_code, stdout, stderr })
    })
    .await
    .map_err(|e| e.to_string())?
}

fn scp_send_file(sess: &Session, local: &Path, remote: &str) -> Result<u64> {
    let metadata = std::fs::metadata(local)?;
    let size = metadata.len();
    let mut local_file = std::fs::File::open(local)?;
    let mut channel = sess.scp_send(Path::new(remote), 0o644, size, None)?;

    let mut buf = [0u8; 65536];
    let mut sent = 0u64;
    loop {
        let n = local_file.read(&mut buf)?;
        if n == 0 {
            break;
        }
        channel.write_all(&buf[..n])?;
        sent += n as u64;
    }
    channel.send_eof()?;
    channel.wait_eof()?;
    channel.close()?;
    channel.wait_close()?;
    Ok(sent)
}

fn ensure_remote_dir(sess: &Session, remote_dir: &str) -> Result<()> {
    let mut channel = sess.channel_session()?;
    let cmd = format!("mkdir -p {remote_dir}");
    channel.exec(&cmd)?;
    channel.wait_close()?;
    Ok(())
}

#[tauri::command]
pub async fn ssh_upload_files(
    app: AppHandle,
    host: String,
    port: u16,
    username: String,
    auth: SshAuth,
    local_paths: Vec<String>,
    remote_dir: String,
) -> Result<(), String> {
    tokio::task::spawn_blocking(move || {
        inner_upload(&app, &host, port, &username, &auth, &local_paths, &remote_dir)
    })
    .await
    .map_err(|e| e.to_string())?
    .map_err(|e: anyhow::Error| e.to_string())
}

fn inner_upload(
    app: &AppHandle,
    host: &str,
    port: u16,
    username: &str,
    auth: &SshAuth,
    local_paths: &[String],
    remote_dir: &str,
) -> Result<()> {
    let sess = connect_session(host, port, username, auth)?;
    ensure_remote_dir(&sess, remote_dir)?;

    for local_str in local_paths {
        let local = Path::new(local_str);
        let filename = local
            .file_name()
            .and_then(|n| n.to_str())
            .unwrap_or("file");
        let remote_path = format!("{remote_dir}/{filename}");
        let total = std::fs::metadata(local)?.len();

        let _ = app.emit(
            "upload-progress",
            UploadProgress {
                file: filename.to_string(),
                bytes_sent: 0,
                total_bytes: total,
                percent: 0.0,
            },
        );

        let sent = scp_send_file(&sess, local, &remote_path)?;

        let _ = app.emit(
            "upload-progress",
            UploadProgress {
                file: filename.to_string(),
                bytes_sent: sent,
                total_bytes: total,
                percent: 100.0,
            },
        );
    }
    Ok(())
}
