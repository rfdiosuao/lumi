// First-run layer bootstrap for the <100MB online installer.
//
// Mirrors scripts/dist/dist-lib.mjs: download (mirror fallthrough) -> sha256
// verify -> extract -> atomic swap -> marker. Runs in the Rust shell because
// `node` itself is a downloaded layer (can't use Node to fetch Node).
//
// SAFE BY DESIGN: does nothing unless OPENCLAW_DIST_MANIFEST_URL is set AND a
// required layer is actually missing. A full/offline package (all layers
// preinstalled) is detected as present and skipped, so this is inert for the
// current portable build.

use serde::Deserialize;
use sha2::{Digest, Sha256};
use std::io::Write;
use std::path::{Path, PathBuf};

#[derive(Deserialize)]
struct Manifest {
    mirrors: Vec<String>,
    layers: Vec<Layer>,
}

#[derive(Deserialize)]
struct Layer {
    id: String,
    file: String,
    sha256: String,
    #[serde(rename = "installPath")]
    install_path: String,
    #[serde(default)]
    version: Option<String>,
    #[serde(default)]
    required: bool,
}

/// Resolve the install root (the directory that contains `OpenClawFiles/`).
pub fn install_root() -> Result<PathBuf, String> {
    if cfg!(debug_assertions) {
        return std::env::current_dir().map_err(|e| format!("cwd failed: {e}"));
    }
    let exe = std::env::current_exe().map_err(|e| format!("current_exe failed: {e}"))?;
    exe.parent()
        .map(|p| p.to_path_buf())
        .ok_or_else(|| "exe parent not found".to_string())
}

fn marker_path(install_root: &Path, layer: &Layer) -> PathBuf {
    install_root.join(&layer.install_path).join(".layer.json")
}

/// Present = marker sha matches, OR the target dir already exists with content
/// (a preinstalled / offline-delivered layer — never clobber it).
fn is_present(install_root: &Path, layer: &Layer) -> bool {
    if let Ok(raw) = std::fs::read_to_string(marker_path(install_root, layer)) {
        if let Ok(v) = serde_json::from_str::<serde_json::Value>(&raw) {
            if v.get("sha256").and_then(|s| s.as_str()) == Some(layer.sha256.as_str()) {
                return true;
            }
        }
    }
    let target = install_root.join(&layer.install_path);
    target.is_dir() && std::fs::read_dir(&target).map(|mut d| d.next().is_some()).unwrap_or(false)
}

fn client() -> Result<reqwest::Client, String> {
    reqwest::Client::builder()
        .no_proxy()
        .build()
        .map_err(|e| format!("http client: {e}"))
}

async fn fetch_manifest(url: &str) -> Result<Manifest, String> {
    let text = client()?
        .get(url)
        .send()
        .await
        .map_err(|e| format!("manifest fetch: {e}"))?
        .error_for_status()
        .map_err(|e| format!("manifest status: {e}"))?
        .text()
        .await
        .map_err(|e| format!("manifest body: {e}"))?;
    serde_json::from_str(&text).map_err(|e| format!("manifest parse: {e}"))
}

/// Stream `url` to `dest`, returning the lowercase hex sha256 of the bytes.
async fn download_verify(url: &str, dest: &Path) -> Result<String, String> {
    let mut resp = client()?
        .get(url)
        .send()
        .await
        .map_err(|e| format!("get {url}: {e}"))?
        .error_for_status()
        .map_err(|e| format!("status {url}: {e}"))?;
    let mut file = std::fs::File::create(dest).map_err(|e| format!("create {}: {e}", dest.display()))?;
    let mut hasher = Sha256::new();
    while let Some(chunk) = resp.chunk().await.map_err(|e| format!("chunk {url}: {e}"))? {
        hasher.update(&chunk);
        file.write_all(&chunk).map_err(|e| format!("write {}: {e}", dest.display()))?;
    }
    file.flush().ok();
    Ok(hex(&hasher.finalize()))
}

fn hex(bytes: &[u8]) -> String {
    let mut s = String::with_capacity(bytes.len() * 2);
    for b in bytes {
        s.push_str(&format!("{b:02x}"));
    }
    s
}

fn extract_targz(archive: &Path, dest_parent: &Path) -> Result<(), String> {
    let f = std::fs::File::open(archive).map_err(|e| format!("open {}: {e}", archive.display()))?;
    let dec = flate2::read::GzDecoder::new(f);
    let mut ar = tar::Archive::new(dec);
    ar.unpack(dest_parent).map_err(|e| format!("unpack {}: {e}", archive.display()))
}

async fn install_layer(install_root: &Path, mirrors: &[String], layer: &Layer, cache: &Path) -> Result<(), String> {
    std::fs::create_dir_all(cache).map_err(|e| format!("cache dir: {e}"))?;
    let archive = cache.join(&layer.file);

    let mut verified = false;
    let mut last_err = String::new();
    for base in mirrors {
        let url = format!("{}{}", base.trim_end_matches('/'), format!("/{}", layer.file));
        match download_verify(&url, &archive).await {
            Ok(sha) if sha == layer.sha256 => {
                verified = true;
                break;
            }
            Ok(sha) => last_err = format!("sha mismatch from {url}: got {}…", &sha[..12.min(sha.len())]),
            Err(e) => last_err = e,
        }
    }
    if !verified {
        let _ = std::fs::remove_file(&archive);
        return Err(format!("layer {}: no trusted source. {last_err}", layer.id));
    }

    let target = install_root.join(&layer.install_path);
    let stage = cache.join(format!("stage-{}-{}", layer.id, std::process::id()));
    let _ = std::fs::remove_dir_all(&stage);
    let result = (|| {
        extract_targz(&archive, &stage)?;
        // build-layers tars `-C parent <basename>`, so content is at stage/<basename>.
        let base = Path::new(&layer.install_path)
            .file_name()
            .map(|n| stage.join(n))
            .filter(|p| p.exists())
            .unwrap_or_else(|| stage.clone());
        if let Some(parent) = target.parent() {
            std::fs::create_dir_all(parent).map_err(|e| format!("mkdir {}: {e}", parent.display()))?;
        }
        let backup = target.with_extension(format!("old-{}", std::process::id()));
        if target.exists() {
            std::fs::rename(&target, &backup).map_err(|e| format!("backup {}: {e}", target.display()))?;
        }
        std::fs::rename(&base, &target).map_err(|e| format!("swap into {}: {e}", target.display()))?;
        let marker = serde_json::json!({
            "id": layer.id, "version": layer.version, "sha256": layer.sha256,
            "installedAt": chrono::Utc::now().to_rfc3339(),
        });
        std::fs::write(marker_path(install_root, layer), serde_json::to_vec_pretty(&marker).unwrap_or_default())
            .map_err(|e| format!("marker: {e}"))?;
        if backup.exists() {
            let _ = std::fs::remove_dir_all(&backup);
        }
        Ok::<(), String>(())
    })();
    let _ = std::fs::remove_dir_all(&stage);
    let _ = std::fs::remove_file(&archive);
    result
}

/// Ensure all required layers are present. No-op unless a manifest URL is
/// configured and something is actually missing.
pub async fn ensure_layers(install_root: PathBuf) -> Result<(), String> {
    let url = match std::env::var("OPENCLAW_DIST_MANIFEST_URL") {
        Ok(u) if !u.trim().is_empty() => u,
        _ => return Ok(()),
    };
    // If everything is already present we don't even need the manifest, but we
    // can't know the layer set without it; fetching is cheap.
    let manifest = match fetch_manifest(&url).await {
        Ok(m) => m,
        // Offline with preinstalled layers: don't block startup.
        Err(e) => {
            eprintln!("[bootstrap] manifest unavailable ({e}); continuing with local layers");
            return Ok(());
        }
    };
    let cache = std::env::temp_dir().join("openclaw-dist-cache");
    for layer in manifest.layers.iter().filter(|l| l.required) {
        if is_present(&install_root, layer) {
            continue;
        }
        eprintln!("[bootstrap] installing layer {}…", layer.id);
        install_layer(&install_root, &manifest.mirrors, layer, &cache).await?;
        eprintln!("[bootstrap] layer {} installed", layer.id);
    }
    Ok(())
}
